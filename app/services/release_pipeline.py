"""One-action release run: PRD → Design → Build → Test.

The Scale tab can start a whole release instead of clicking each phase.
A short Celery tick advances a persisted state machine:

- children are moved up the lifecycle as each phase needs it
  (SPARK → SCOPE for a PRD, SCOPE → MAP for a design, → SHIP for a build),
  with normal ``IdeaStatusHistory`` entries;
- PRDs and designs are only generated when the child has no current one;
- builds run one preview each, then **one write at a time** into the
  release repo (two manifests writing the same file concurrently would
  interleave), and a child that already has a current written build is
  left alone;
- the test phase only has to confirm the build seeded its checklist —
  running the checks stays a human decision;
- at the end the release is marked done and its children stay at SHIP.

Failures never stop the release: the child is marked failed with the
worker's reason, later phases for it are skipped, and the rest carry on.
If anything failed the release stays ``in_progress`` with the reasons on
screen, which is safer than declaring a broken release shipped.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

import structlog

from app.extensions import db

logger = structlog.get_logger()

PHASES = ("prd", "design", "build", "test")
PHASE_ACTION = {"prd": "PRD_DOC", "design": "DESIGN_DOC", "build": "BUILD_CODE"}
PHASE_STAGE = {"prd": "SCOPE", "design": "MAP", "build": "SHIP"}
PHASE_LABEL = {
    "prd": "PRD",
    "design": "Design",
    "build": "Build",
    "test": "Test",
}
TERMINAL = frozenset({"done", "skipped", "failed"})
STAGE_RANK = {"SPARK": 0, "SCOPE": 1, "MAP": 2, "SHIP": 3, "SCALE": 4}
STAGE_BY_RANK = ("SPARK", "SCOPE", "MAP", "SHIP")
TICK_SECONDS = 20
MAX_REPORT = 60


def _now():
    return datetime.now(timezone.utc)


def _status_value(idea) -> str:
    status = idea.status
    return status.value if hasattr(status, "value") else str(status)


def _blank_child(idea) -> dict:
    return {
        "reference_code": idea.reference_code,
        "title": idea.prompt_title,
        "prd": "pending",
        "design": "pending",
        "build": "pending",
        "test": "pending",
        "run_ids": {},
        "reason": None,
    }


def _load_state(release, children) -> dict:
    state = copy.deepcopy(release.pipeline_state or {})
    entries = state.get("children") or {}
    for child in children:
        entries.setdefault(str(child.id), _blank_child(child))
    state["children"] = entries
    state.setdefault("report", [])
    return state


def _report(state, line: str) -> None:
    report = state.setdefault("report", [])
    report.append(line)
    if len(report) > MAX_REPORT:
        del report[: len(report) - MAX_REPORT]


def _save(release, state: dict) -> None:
    # JSON columns must be reassigned, never mutated in place.
    release.pipeline_state = state


def _existing_current(idea_id, action_type):
    from app.models import SecondaryActionResult

    return (
        SecondaryActionResult.query.filter_by(
            idea_id=idea_id, action_type=action_type, is_current=True
        )
        .order_by(SecondaryActionResult.executed_at.desc())
        .first()
    )


def _advance_status(idea, target: str, actor_id):
    """Walk an idea up to ``target`` one legal step at a time.

    Returns ``(ok, reason)``. Archive/Drop children are left alone: a
    release cannot resurrect a rejected idea.
    """
    from app.models import IdeaStatus, IdeaStatusHistory

    current = _status_value(idea)
    if current in ("DROP", "ARCHIVE"):
        return False, f"{idea.reference_code} is {current} and was skipped."
    rank = STAGE_RANK.get(current)
    target_rank = STAGE_RANK.get(target)
    if rank is None or target_rank is None:
        return False, f"{idea.reference_code} cannot move from {current}."
    if rank >= target_rank:
        return True, None
    for next_rank in range(rank + 1, target_rank + 1):
        old = IdeaStatus[STAGE_BY_RANK[next_rank - 1]]
        new = IdeaStatus[STAGE_BY_RANK[next_rank]]
        idea.status = new
        # The column is NOT NULL; a release started by a user always has
        # one. Scripts without an actor still move the status, they just
        # cannot attribute it.
        if actor_id is not None:
            db.session.add(
                IdeaStatusHistory(
                    idea_id=idea.id,
                    old_status=old,
                    new_status=new,
                    changed_by_id=actor_id,
                )
            )
    db.session.flush()
    return True, None


def _actor_id(release, state):
    raw = (state or {}).get("actor_id") or release.created_by_id
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None


def _merged_config(child, status_value: str) -> dict:
    from app.models import resolve_release, resolve_stage

    stage_cfg = resolve_stage(child.instance_id, status_value)
    release_cfg = resolve_release(child)
    return {**stage_cfg, **{k: v for k, v in release_cfg.items() if v is not None}}


def _prepare_launch(child, action_type: str, extra: dict | None = None) -> dict:
    """Create the run row; the caller enqueues it after committing.

    A worker can pick a task up within milliseconds. Enqueueing before the
    PromptRun row commits meant the worker loaded a row that did not exist
    yet, ran anyway, and never updated the run (seen live: the design step
    stayed PENDING while its document was already saved).
    """
    from app.models import PromptRun, PromptRunStatus
    from app.tasks.ollama_tasks import run_secondary_action

    config = _merged_config(child, _status_value(child))
    provider = (config.get("provider") or "ollama").lower()
    model = config.get("model_name")
    run = PromptRun(
        instance_id=child.instance_id,
        action_type=action_type,
        triggered_by="manual",
        idea_id=child.id,
        status=PromptRunStatus.PENDING,
        job_type="ai",
        provider=provider,
        model=model,
        queue="opencode" if provider == "opencode" else "ollama",
    )
    db.session.add(run)
    db.session.flush()
    return {
        "run_id": str(run.id),
        "provider": provider,
        "task": run_secondary_action,
        "args": [str(child.id), action_type],
        "kwargs": {
            "model_override": model,
            "extra_context": dict(extra or {}),
            "run_id": str(run.id),
            "provider_override": provider,
        },
    }


def _enqueue_launch(launch: dict) -> None:
    from app.tasks import enqueue_generation

    enqueue_generation(
        launch["task"],
        launch["args"],
        launch["kwargs"],
        launch["provider"],
    )


def _poll(run_id):
    from app.models import PromptRun

    if not run_id:
        return None
    try:
        return db.session.get(PromptRun, uuid.UUID(str(run_id)))
    except (ValueError, TypeError):
        return None


def _mark_failed(entry, run, phase: str) -> None:
    entry[phase] = "failed"
    error = getattr(run, "error", None) or "the run failed"
    entry["reason"] = str(error)[:500]
    entry["run_ids"].pop(phase, None)


def _skip_child(entry, reason: str) -> None:
    entry["reason"] = reason[:500]
    for phase in PHASES:
        if entry[phase] not in TERMINAL:
            entry[phase] = "skipped"


def _skip_later(entry, after_phase: str) -> None:
    start = PHASES.index(after_phase) + 1
    for phase in PHASES[start:]:
        if entry[phase] not in ("done", "failed"):
            entry[phase] = "skipped"


def _resolve_target(release, child):
    """The repo a release build writes into.

    Order: the repo named after the release (the convention the release
    UI already documents), the repo the child last built into, then the
    instance's only registered repo. Ambiguous means fail with a reason,
    never guess.
    """
    from app.models import InstanceBuildTarget, SecondaryActionResult

    target = InstanceBuildTarget.query.filter_by(
        instance_id=child.instance_id, name=release.name
    ).first()
    if target is not None:
        return target
    last = (
        db.session.query(InstanceBuildTarget)
        .join(
            SecondaryActionResult,
            SecondaryActionResult.target_id == InstanceBuildTarget.id,
        )
        .filter(
            SecondaryActionResult.idea_id == child.id,
            SecondaryActionResult.action_type == "BUILD_CODE",
        )
        .order_by(SecondaryActionResult.executed_at.desc())
        .first()
    )
    if last is not None:
        return last
    targets = InstanceBuildTarget.query.filter_by(
        instance_id=child.instance_id
    ).all()
    return targets[0] if len(targets) == 1 else None


def _phase_settled(state, phase: str, child_ids) -> bool:
    for idea_id in child_ids:
        if state["children"][idea_id][phase] not in TERMINAL:
            return False
    return True


def _phase_failed(state, phase: str, child_ids) -> bool:
    return any(
        state["children"][idea_id][phase] == "failed" for idea_id in child_ids
    )


def _process_docs(release, children, phase: str, state, pending: list):
    """Advance PRD or Design: skip existing docs, queue missing ones."""
    action = PHASE_ACTION[phase]
    stage = PHASE_STAGE[phase]
    actor = _actor_id(release, state)
    launched = False
    for child in children:
        entry = state["children"][str(child.id)]
        if entry[phase] in TERMINAL:
            continue

        if entry[phase] == "running":
            run = _poll(entry["run_ids"].get(phase))
            if run is None:
                entry[phase] = "failed"
                entry["reason"] = "The run disappeared; start the release again."
                entry["run_ids"].pop(phase, None)
            elif run.status.value == "SUCCESS":
                entry[phase] = "done"
                entry["run_ids"].pop(phase, None)
            elif run.status.value == "FAILED":
                _mark_failed(entry, run, phase)
            continue

        # Existing current document: no need to spend a model call.
        if _existing_current(child.id, action) is not None:
            entry[phase] = "done"
            continue

        ok, reason = _advance_status(child, stage, actor)
        if not ok:
            _skip_child(entry, reason)
            continue

        launch = _prepare_launch(child, action)
        entry[phase] = "running"
        entry["run_ids"][phase] = launch["run_id"]
        pending.append(launch)
        launched = True
        _report(
            state,
            f"{child.reference_code}: started {PHASE_LABEL[phase]}",
        )

    # Nothing running and still pending means the launch did not take:
    # fail those children with a plain reason instead of ticking forever.
    if not launched:
        for child in children:
            entry = state["children"][str(child.id)]
            if entry[phase] == "pending":
                entry[phase] = "failed"
                entry["reason"] = "Could not start this step."


def _process_build(release, children, state, pending: list):
    """Preview and write one child at a time, in creation order.

    Sequential on purpose: each preview reads the repo, and the next
    preview must see the previous child's written files. Two previews in
    flight would both describe the original app, and the second write
    would drop the first fix. One operation per tick keeps that honest.
    """
    actor = _actor_id(release, state)

    # 1. Poll whatever is in flight (a preview generation or a write).
    for child in children:
        entry = state["children"][str(child.id)]
        build_state = entry["build"]
        if build_state not in ("running", "writing"):
            continue
        key = "build" if build_state == "running" else "build_confirm"
        run = _poll(entry["run_ids"].get(key))
        if run is None:
            entry["build"] = "failed"
            entry["reason"] = "The build run disappeared."
            entry["run_ids"].pop(key, None)
        elif run.status.value == "SUCCESS":
            entry["build"] = "preview_ready" if build_state == "running" else "done"
            entry["run_ids"].pop(key, None)
            if build_state == "writing":
                _report(state, f"{child.reference_code}: build written")
        elif run.status.value == "FAILED":
            _mark_failed(entry, run, "build")
            entry["run_ids"].pop(key, None)

    in_flight = any(
        state["children"][str(c.id)]["build"] in ("running", "writing")
        for c in children
    )
    if in_flight:
        return

    # 2. A finished preview must be written before any new preview starts:
    # a later preview would otherwise read the repo without the earlier fix.
    for child in children:
        entry = state["children"][str(child.id)]
        if entry["build"] != "preview_ready":
            continue
        target = _resolve_target(release, child)
        if target is None:
            entry["build"] = "failed"
            entry["reason"] = (
                f"No build repo named “{release.name}” (and more than one repo "
                "is registered). Add one in Admin → AI Settings or pick a repo "
                "on the Build tab."
            )
            continue
        ok, reason = _advance_status(child, "SHIP", actor)
        if not ok:
            _skip_child(entry, reason)
            continue
        launch = _prepare_launch(
            child,
            "BUILD_CODE",
            {"confirm_build": True, "target_id": str(target.id)},
        )
        entry["run_ids"]["build_confirm"] = launch["run_id"]
        entry["build"] = "writing"
        pending.append(launch)
        return

    # 3. No write waiting: start the next preview, one per tick.
    for child in children:
        entry = state["children"][str(child.id)]
        if entry["build"] != "pending":
            continue
        target = _resolve_target(release, child)
        if target is None:
            entry["build"] = "failed"
            entry["reason"] = (
                f"No build repo named “{release.name}” (and more than one repo "
                "is registered). Add one in Admin → AI Settings or pick a repo "
                "on the Build tab."
            )
            continue
        current = _existing_current(child.id, "BUILD_CODE")
        current_written = bool(
            current
            and current.result_data.get("written")
            and str(current.target_id) == str(target.id)
        )
        if current_written:
            # A child that already has a current build is not rebuilt by a
            # release run; use Recreate on the idea when that is intended.
            entry["build"] = "done"
            entry["reason"] = "Already built in this repo — left unchanged."
            _report(state, f"{child.reference_code}: already built, left alone")
            continue

        ok, reason = _advance_status(child, "SHIP", actor)
        if not ok:
            _skip_child(entry, reason)
            continue
        if (
            current is not None
            and not current.result_data.get("written")
            and str(current.target_id) == str(target.id)
        ):
            # A preview already exists for this repo: confirm it directly.
            entry["build"] = "preview_ready"
            return
        launch = _prepare_launch(
            child,
            "BUILD_CODE",
            {"confirm_build": False, "target_id": str(target.id)},
        )
        entry["build"] = "running"
        entry["run_ids"]["build"] = launch["run_id"]
        pending.append(launch)
        _report(state, f"{child.reference_code}: build preview started")
        return

    # Nothing left to act on; the phase is settled for the build step.
    for child in children:
        entry = state["children"][str(child.id)]
        if entry["build"] in ("pending", "preview_ready"):
            entry["build"] = "failed"
            entry["reason"] = entry.get("reason") or "Could not start the build."


def _seed_build_tests(child) -> int:
    """Safety net: the write seeds checks, but older builds may not have."""
    from app.services.build_tests import derive_build_tests, seed_idea_tests

    row = _existing_current(child.id, "BUILD_CODE")
    if row is None or not row.result_data.get("written"):
        return 0
    data = row.result_data
    tests = derive_build_tests(
        data.get("files") or [],
        data,
        data.get("tests"),
        data.get("runbook"),
    )
    stats = seed_idea_tests(child, tests)
    return (
        stats["created"]
        + stats["updated"]
        + stats["removed"]
        + (0 if tests else 1)
    )


def _process_test(children, state):
    for child in children:
        entry = state["children"][str(child.id)]
        if entry["test"] in TERMINAL:
            continue
        if entry["build"] != "done":
            entry["test"] = "skipped"
            entry["reason"] = entry.get("reason") or "No build to test."
            continue
        try:
            _seed_build_tests(child)
            entry["test"] = "done"
        except Exception as exc:
            logger.exception(
                "release_test_seed_failed", idea_id=str(child.id), error=str(exc)
            )
            entry["test"] = "failed"
            entry["reason"] = "Build written but its test checklist could not be saved."
    db.session.flush()


def _finish(release, state, children):
    from app.models import Idea

    failed = [
        c for c in state["children"].values() if "failed" in {c[p] for p in PHASES}
    ]
    release.pipeline_phase = "done"
    release.pipeline_finished_at = _now()
    if failed:
        release.pipeline_status = "failed"
        release.status = "in_progress"
        release.pipeline_error = (
            f"{len(failed)} of {len(children)} idea(s) did not finish. "
            "Open the failed rows for the reason, then run the release again."
        )
        _report(state, "Release stopped with failures — review and re-run.")
    else:
        release.pipeline_status = "done"
        release.status = "done"
        release.completed_at = _now()
        release.pipeline_error = None
        shipped = [c for c in children if _status_value(c) not in ("DROP", "ARCHIVE")]
        from app.services.release_notes import build_release_notes

        release.notes = build_release_notes(
            release, children, len(shipped), len(children) - len(shipped)
        )
        _report(state, "Release finished.")
    _save(release, state)
    db.session.commit()
    if not failed:
        try:
            from app.services.release_notes import write_release_notes_file

            parent = db.session.get(Idea, release.parent_idea_id)
            write_release_notes_file(release, parent)
        except Exception:
            logger.exception(
                "release_notes_write_failed", release_id=str(release.id)
            )
    logger.info(
        "release_pipeline_finished",
        release_id=str(release.id),
        status=release.pipeline_status,
        failed=len(failed),
    )


def _schedule(release_id: str, countdown: int = TICK_SECONDS) -> None:
    from flask import current_app

    # Eager tests drive advance_release() directly; scheduling inside an
    # eager task would recurse.
    try:
        if current_app.config.get("CELERY_TASK_ALWAYS_EAGER"):
            return
    except RuntimeError:
        return
    from app.tasks.release_tasks import release_pipeline_tick

    release_pipeline_tick.apply_async(
        args=[str(release_id)], countdown=countdown, queue="default"
    )


def start_release_pipeline(release, user=None):
    """Start (or resume) the one-action run. Returns (ok, message)."""
    from app.models import Idea

    if release.pipeline_status in ("running", "stopping"):
        return False, "This release is already running."
    children = (
        Idea.query.filter_by(release_id=release.id)
        .order_by(Idea.created_at.asc())
        .all()
    )
    if not children:
        return False, "Nothing in this release yet — add ideas to it first."

    state = _load_state(release, children)
    # Re-runs keep finished work and retry the rest. Skipped steps are
    # retried too (they were skipped because an earlier step failed), but
    # rejected ideas stay untouched.
    for child in children:
        entry = state["children"][str(child.id)]
        if _status_value(child) in ("DROP", "ARCHIVE"):
            continue
        for phase in PHASES:
            if entry[phase] in ("failed", "skipped"):
                entry[phase] = "pending"
                entry["reason"] = None
                entry["run_ids"].pop(phase, None)
                entry["run_ids"].pop("build_confirm", None)
    state["report"] = []
    state["actor_id"] = (
        str(user.id)
        if user is not None
        else (str(release.created_by_id) if release.created_by_id else None)
    )
    _report(state, f"Release run started by {getattr(user, 'email', 'system')}")

    phase = "prd"
    for candidate in PHASES:
        if not _phase_settled(
            state, candidate, [str(c.id) for c in children]
        ):
            phase = candidate
            break
    else:
        # Everything already done — a re-run just refreshes the end state.
        release.pipeline_status = "running"
        release.pipeline_phase = "done"
        release.pipeline_state = state
        release.pipeline_started_at = _now()
        release.pipeline_finished_at = None
        release.pipeline_error = None
        _save(release, state)
        db.session.commit()
        _finish(release, state, children)
        return True, "Release was already complete."

    release.pipeline_status = "running"
    release.pipeline_phase = phase
    release.pipeline_started_at = _now()
    release.pipeline_finished_at = None
    release.pipeline_error = None
    release.status = "in_progress"
    _save(release, state)
    db.session.commit()
    _schedule(release.id, countdown=0)
    logger.info(
        "release_pipeline_started", release_id=str(release.id), phase=phase
    )
    return True, "Release run started."


def stop_release_pipeline(release):
    if release.pipeline_status not in ("running", "stopping"):
        return False, "This release is not running."
    release.pipeline_status = "stopping"
    db.session.commit()
    return True, "Stopping after the current step."


def advance_release(release_id) -> bool:
    """Advance one tick. Returns True when another tick is needed."""
    from app.models import Idea, Release

    try:
        key = uuid.UUID(str(release_id))
    except (ValueError, TypeError):
        return False
    release = (
        db.session.query(Release)
        .filter_by(id=key)
        .with_for_update()
        .first()
    )
    if release is None:
        return False

    if release.pipeline_status == "stopping":
        state = _load_state(
            release,
            Idea.query.filter_by(release_id=release.id).all(),
        )
        release.pipeline_status = "idle"
        release.pipeline_phase = "done"
        release.pipeline_finished_at = _now()
        _report(state, "Stopped by request.")
        _save(release, state)
        db.session.commit()
        return False
    if release.pipeline_status != "running":
        return False

    children = (
        Idea.query.filter_by(release_id=release.id)
        .order_by(Idea.created_at.asc())
        .all()
    )
    if not children:
        release.pipeline_status = "failed"
        release.pipeline_error = "Nothing in this release yet."
        release.pipeline_finished_at = _now()
        db.session.commit()
        return False

    state = _load_state(release, children)
    child_ids = [str(c.id) for c in children]

    # One phase at a time; a settled phase falls through to the next.
    start = PHASES.index(release.pipeline_phase or "prd")
    for phase in PHASES[start:]:
        release.pipeline_phase = phase
        pending = []
        if phase in ("prd", "design"):
            _process_docs(release, children, phase, state, pending)
        elif phase == "build":
            _process_build(release, children, state, pending)
        else:
            _process_test(children, state)

        _save(release, state)
        db.session.commit()

        # Only now can a worker see the PromptRun row. Enqueueing before
        # this commit let a fast worker run without a run row to update.
        for launch in pending:
            try:
                _enqueue_launch(launch)
            except Exception:
                logger.exception(
                    "release_launch_failed", run_id=launch["run_id"]
                )
                from app.models import PromptRun

                run = _poll(launch["run_id"])
                if run is not None:
                    run.mark_failed("Could not queue this step.")
                    db.session.commit()

        if not _phase_settled(state, phase, child_ids):
            _schedule(release.id)
            return True

        if phase != "test":
            for child in children:
                entry = state["children"][str(child.id)]
                if entry[phase] == "failed":
                    _skip_later(entry, phase)

    _finish(release, state, children)
    return False
