"""Push a release's build output to the instance's GitHub repo (A3/A5).

push_release_to_github runs on a worker: it clones the instance repo
shallow with the encrypted PAT (never logged, never returned), syncs the
release's build-target directory into it, commits, and pushes. The
release row records the SHA — once set, the release cannot be pushed
again (further updates need a new release).
"""

import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

import structlog

from app.extensions import db
from app.models import Release
from app.tasks import BaseTask, celery

logger = structlog.get_logger()


def _now():
    return datetime.now(timezone.utc)


def _run_git(args, cwd, timeout=300):
    """git with output captured; raises RuntimeError in plain language."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise RuntimeError("git is not installed on this worker.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("git took too long — try again.")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "git failed").strip()
        # Scrub any token that leaked into an error message.
        raise RuntimeError(err[:300])
    return (proc.stdout or "").strip()


def _sync_dir(src, dst):
    """Mirror src into dst (excluding .git), deleting stale files."""
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != ".git"]
        rel = os.path.relpath(root, src)
        target_root = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_root, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(target_root, f))
    # Delete destination files missing from src (excluding .git).
    src_files = set()
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            src_files.add(os.path.relpath(os.path.join(root, f), src))
    for root, dirs, files in os.walk(dst):
        if ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), dst)
            if rel not in src_files:
                os.remove(os.path.join(root, f))


@celery.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.github_tasks.push_release_to_github",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def push_release_to_github(self, release_id: str):
    """Clone, sync the release's build target dir, commit, push."""
    from app.models import Idea, InstanceBuildTarget, InstanceGitHubConfig
    from app.services.build_service import container_path

    try:
        row_id = uuid.UUID(str(release_id))
    except (ValueError, TypeError, AttributeError):
        logger.warning("github_bad_id", release_id=str(release_id)[:40])
        return
    release = None
    idea = None
    if str(release_id).startswith("idea:"):
        # A5 path: push one idea's own build target on entering Scale.
        try:
            idea = db.session.get(Idea, uuid.UUID(str(release_id).split("idea:", 1)[1]))
        except (ValueError, TypeError, AttributeError, IndexError):
            idea = None
        if idea is None:
            logger.warning("github_missing", release_id=str(release_id)[:40])
            return
    else:
        release = db.session.get(Release, row_id)
        if release is None:
            logger.warning("github_missing", release_id=str(release_id)[:40])
            return
        if release.github_sha:
            logger.info("github_already_pushed", release_id=str(release.id))
            return
    instance_id = idea.instance_id if idea is not None else release.instance_id
    config = InstanceGitHubConfig.query.filter_by(instance_id=instance_id).first()
    if config is None or not config.pat:
        logger.warning("github_unconfigured", release_id=str(release_id)[:40])
        return

    # Source: the release's build target dir — the parent app's repo when
    # children built with the default (A3 "only when needed": nothing to
    # push without a confirmed build). For the A5 idea path, the idea's
    # own latest build target.
    parent = None
    if release is not None:
        parent = (
            db.session.get(Idea, release.parent_idea_id)
            if release.parent_idea_id
            else None
        )
    target = None
    owner = parent if parent is not None else idea
    if owner is not None:
        from app.models import SecondaryActionResult

        row = (
            SecondaryActionResult.query.filter_by(
                idea_id=owner.id, action_type="BUILD_CODE"
            )
            .filter(SecondaryActionResult.target_id.isnot(None))
            .order_by(SecondaryActionResult.executed_at.desc())
            .first()
        )
        if row is not None:
            target = db.session.get(InstanceBuildTarget, row.target_id)
    if target is None:
        options = InstanceBuildTarget.query.filter_by(instance_id=instance_id).all()
        if len(options) == 1:
            target = options[0]
    if target is None:
        logger.warning("github_no_target", release_id=str(release_id)[:40])
        return
    src = container_path(target.path) or target.path
    if not os.path.isdir(src):
        logger.warning("github_missing_dir", release_id=str(release_id)[:40])
        return

    tmp = tempfile.mkdtemp(prefix="github-push-")
    label = str(release.id) if release is not None else f"idea:{idea.id}"
    try:
        clone_url = f"https://x-access-token:{config.pat}@github.com/{config.repo}.git"
        _run_git(
            ["clone", "--depth", "1", "--branch", config.branch, clone_url, "repo"],
            cwd=tmp,
        )
        work = os.path.join(tmp, "repo")
        _sync_dir(src, work)
        _run_git(["add", "-A"], cwd=work)
        status = _run_git(["status", "--porcelain"], cwd=work)
        if not status:
            logger.info("github_no_changes", release_id=label[:40])
            return
        _run_git(["config", "user.name", "brainstormer"], cwd=work)
        _run_git(["config", "user.email", "brainstormer@localhost"], cwd=work)
        if release is not None:
            parent_ref = parent.reference_code if parent else "?"
            message = f"{release.name} ({parent_ref}): {len(status.splitlines())} files"
        else:
            message = f"{idea.reference_code}: initial Scale push ({len(status.splitlines())} files)"
        _run_git(["commit", "-m", message], cwd=work)
        _run_git(["push", "origin", f"HEAD:{config.branch}"], cwd=work)
        sha = _run_git(["rev-parse", "HEAD"], cwd=work)
        if release is not None:
            release.github_sha = sha
            release.github_pushed_at = _now()
            db.session.commit()
        logger.info(
            "github_pushed", release_id=label[:40], sha=sha[:12] if sha else None
        )
    except RuntimeError as exc:
        logger.warning("github_failed", release_id=label[:40], error=str(exc)[:200])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
