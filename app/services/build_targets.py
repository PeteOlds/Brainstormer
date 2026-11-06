"""One rule for the repo a build writes into.

A release belongs to a SCALE parent, and its children are fixes and
improvements to that parent's app: the release writes into the parent's
repo, shared by every release under it. An idea with no parent is its own
project and gets a repo named after its reference code.

Every entry point (the release pipeline, the Build tab, bulk build
actions) goes through :func:`resolve_build_target`, so they cannot drift
apart again. Resolution never guesses between several unrelated repos;
when the caller allows it, a missing repo is created lazily under the
first configured build root.
"""

from __future__ import annotations

import os
import re
import uuid

import structlog

from app.extensions import db

logger = structlog.get_logger()

# Idea -> parent -> (never in practice) grandparent. Bounded so a bad
# cycle cannot hang a worker.
MAX_PARENT_DEPTH = 8


def root_idea(idea):
    """The SCALE parent of a child, or the idea itself when standalone."""
    from app.models import Idea

    current = idea
    seen = set()
    for _ in range(MAX_PARENT_DEPTH):
        if current is None or not getattr(current, "parent_id", None):
            break
        if current.id in seen:
            break
        seen.add(current.id)
        parent = db.session.get(Idea, current.parent_id)
        if parent is None:
            break
        current = parent
    return current or idea


def _target_by_id(instance_id, raw):
    from app.models import InstanceBuildTarget

    try:
        key = uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        return None
    return InstanceBuildTarget.query.filter_by(
        id=key, instance_id=instance_id
    ).first()


def _target_by_name(instance_id, name):
    from app.models import InstanceBuildTarget

    clean = (name or "").strip()
    if not clean or instance_id is None:
        return None
    return (
        InstanceBuildTarget.query.filter(
            InstanceBuildTarget.instance_id == instance_id,
            db.func.lower(InstanceBuildTarget.name) == clean.lower(),
        )
        .first()
    )


def _last_build_target(idea_id, instance_id):
    from app.models import SecondaryActionResult

    if idea_id is None:
        return None
    row = (
        SecondaryActionResult.query.filter_by(
            idea_id=idea_id, action_type="BUILD_CODE"
        )
        .filter(SecondaryActionResult.target_id.isnot(None))
        .order_by(SecondaryActionResult.executed_at.desc())
        .first()
    )
    if row is None:
        return None
    return _target_by_id(instance_id, row.target_id)


def _safe_folder(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "").strip())
    return clean.strip("-._")[:80]


def ensure_target_for_idea(idea, created_by_id=None):
    """Register the idea/root repo under the first build root.

    Returns ``(target, reason)``. No roots configured means no creation:
    the caller must not invent a path outside the allowed directories.
    """
    from app.models import InstanceBuildTarget
    from app.services.build_service import (
        BuildError,
        build_roots,
        ensure_target_path,
    )

    root = root_idea(idea)
    name = (getattr(root, "reference_code", "") or "").strip()
    instance_id = getattr(idea, "instance_id", None) or getattr(
        root, "instance_id", None
    )
    if not name or instance_id is None:
        return None, "This idea has no reference code or instance to name a repo after."

    existing = _target_by_name(instance_id, name)
    if existing is not None:
        return existing, None

    roots = build_roots()
    if not roots:
        return None, (
            "No build roots are configured. Add one in Admin → AI Settings "
            "before running a build."
        )
    folder = _safe_folder(name)
    if not folder:
        return None, "This idea's reference code cannot be used as a folder name."

    path = os.path.join(roots[0], folder)
    try:
        path = ensure_target_path(path)
    except BuildError as exc:
        return None, str(exc)

    target = InstanceBuildTarget(
        instance_id=instance_id,
        name=name,
        path=path,
        created_by_id=created_by_id,
    )
    try:
        with db.session.begin_nested():
            db.session.add(target)
            db.session.flush()
    except Exception:
        # Two runs can race to create the same repo. The folder is shared
        # and idempotent; reuse whichever target row won.
        existing = _target_by_name(instance_id, name)
        if existing is not None:
            return existing, None
        logger.exception(
            "build_target_auto_create_failed",
            instance_id=str(instance_id),
            name=name,
        )
        return None, (
            "The repo folder was created but could not be registered. "
            "Add it in Admin → AI Settings."
        )

    logger.info(
        "build_target_auto_created",
        instance_id=str(instance_id),
        name=name,
        path=path,
    )
    return target, None


def _no_target_reason(idea, root, release, targets) -> str:
    wanted = (getattr(root or idea, "reference_code", "") or "this idea").strip()
    names = ", ".join(sorted(t.name for t in targets)) or "none"
    if len(targets) > 1:
        return (
            f"No build repo matched {wanted} (registered: {names}). "
            "Pick one on the Build tab or add one in Admin → AI Settings."
        )
    return (
        f"No build repo is registered for {wanted}. "
        "Add one in Admin → AI Settings or pick one on the Build tab."
    )


def resolve_build_target(
    idea,
    release=None,
    explicit_id=None,
    *,
    allow_create: bool = False,
    created_by_id=None,
):
    """Return ``(target, reason)`` for a build of ``idea``.

    Order, most specific first:

    1. an explicit choice from the caller;
    2. the release's stored target (``Release.build_target_id``);
    3. a repo named after the release (the old convention);
    4. a repo named after the idea's own reference code (deliberate
       per-child repos);
    5. a repo named after the root parent's reference code (the app repo
       a release normally shares);
    6. the idea's last build repo, then the root's;
    7. the instance's only registered repo (legacy, unambiguous);
    8. when ``allow_create`` is true, a new repo named after the root
       idea's reference code, created under the first build root.

    ``reason`` is None on success and a user-safe sentence otherwise.
    """
    from app.models import InstanceBuildTarget

    if release is None and getattr(idea, "release_id", None):
        from app.models import Release

        release = db.session.get(Release, idea.release_id)

    instance_id = getattr(idea, "instance_id", None)
    root = root_idea(idea)

    if explicit_id not in (None, ""):
        target = _target_by_id(instance_id, explicit_id)
        if target is not None:
            return target, None
        # A caller that asked for a specific repo must never be silently
        # redirected into another one.
        return None, "The selected build repo no longer exists."

    if release is not None and getattr(release, "build_target_id", None):
        target = _target_by_id(instance_id, release.build_target_id)
        if target is not None:
            return target, None

    if release is not None:
        target = _target_by_name(instance_id, release.name)
        if target is not None:
            return target, None

    target = _target_by_name(instance_id, getattr(idea, "reference_code", None))
    if target is not None:
        return target, None

    if root is not None and root.id != idea.id:
        target = _target_by_name(instance_id, getattr(root, "reference_code", None))
        if target is not None:
            return target, None

    for candidate in (idea, root):
        target = _last_build_target(
            getattr(candidate, "id", None), instance_id
        )
        if target is not None:
            return target, None

    targets = (
        InstanceBuildTarget.query.filter_by(instance_id=instance_id).all()
        if instance_id is not None
        else []
    )
    if len(targets) == 1:
        return targets[0], None

    if allow_create:
        target, reason = ensure_target_for_idea(idea, created_by_id=created_by_id)
        if target is not None:
            return target, None
        return None, reason

    return None, _no_target_reason(idea, root, release, targets)
