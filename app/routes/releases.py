"""Release-related endpoints for the ideas dashboard.

Handles release CRUD, assignment, completion, notes, AI config, and
GitHub push for releases tied to parent ideas.
"""

from datetime import datetime, timezone
from flask import Blueprint, request
import uuid

from app.extensions import db
from app.models import (
    Idea,
    InstanceBuildTarget,
    PromptRun,
    PromptRunStatus,
    Release,
    ReleaseAIConfig,
    SecondaryActionResult,
)
from app.utils.decorators import require_permission, token_required
from app.utils.responses import api_created, api_error, api_ok
from app.utils.tenancy import check_access, stamp
from app.services.release_notes import write_release_notes_file

bp = Blueprint("releases", __name__)


@bp.route("/ideas/<uuid:parent_id>/releases", methods=["GET"])
@token_required
def list_releases(user, parent_id):
    """Releases for one SCALE parent, each with its child count."""
    parent = Idea.query.get_or_404(parent_id)
    denied = check_access(parent)
    if denied is not None:
        return denied
    releases = (
        Release.query.filter_by(parent_idea_id=parent.id)
        .order_by(Release.created_at.desc())
        .all()
    )
    counts = _release_counts(parent.id)
    ai_rows = {
        str(r.release_id): r
        for r in ReleaseAIConfig.query.filter(
            ReleaseAIConfig.release_id.in_([r.id for r in releases])
        ).all()
    }
    data = [r.to_dict(child_count=counts.get(str(r.id), 0)) for r in releases]
    for row in data:
        ai = ai_rows.get(row["id"])
        row["ai_config"] = ai.to_dict() if ai else None
    data.append(
        {
            "id": None,
            "parent_idea_id": str(parent.id),
            "name": "No release yet",
            "status": "planned",
            "target_date": None,
            "child_count": counts.get(None, 0),
            "notes": None,
            "created_at": None,
        }
    )
    return api_ok({"releases": data})


def _release_counts(parent_id):
    """Count children per release (including 'no release' bucket)."""
    from app.models import Idea

    counts = {}
    for r in (
        Idea.query.with_entities(Idea.release_id, db.func.count(Idea.id))
        .filter_by(parent_id=parent_id)
        .group_by(Idea.release_id)
        .all()
    ):
        key = str(r[0]) if r[0] is not None else None
        counts[key] = r[1]
    return counts


@bp.route("/ideas/<uuid:parent_id>/releases", methods=["POST"])
@require_permission("change_status")
def create_release(user, parent_id):
    """New release batch for one parent (admin: same people who move status)."""
    from datetime import datetime, timezone

    from app.models.release import RELEASE_STATUSES

    parent = Idea.query.get_or_404(parent_id)
    denied = check_access(parent)
    if denied is not None:
        return denied
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return api_error("Release name is required.", status_code=400)
    if len(name) > 120:
        return api_error(
            "Release name must be 120 characters or fewer.", status_code=400
        )
    status = (data.get("status") or "planned").strip().lower()
    if status not in RELEASE_STATUSES:
        return api_error(
            "status must be one of: planned, in_progress, done.", status_code=400
        )
    target_date = None
    if data.get("target_date"):
        try:
            target_date = datetime.fromisoformat(str(data["target_date"]))
        except ValueError:
            return api_error("target_date must be ISO format.", status_code=400)
    release = Release(
        parent_idea_id=parent.id,
        name=name,
        status=status,
        target_date=target_date,
        created_by_id=user.id,
    )
    stamp(release)
    # Children inherit the parent's instance when linked at creation, but a
    # parent made before tenancy may carry NULL — fall back to the request.
    if release.instance_id is None:
        release.instance_id = parent.instance_id
    db.session.add(release)
    db.session.commit()
    return api_created({"release": release.to_dict()})


@bp.route("/releases/<uuid:release_id>", methods=["PATCH"])
@require_permission("change_status")
def update_release(user, release_id):
    """Rename / retarget / move a release through planned → in_progress → done."""
    from datetime import datetime, timezone

    from app.models.release import RELEASE_STATUSES

    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    data = request.get_json() or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return api_error("Release name cannot be empty.", status_code=400)
        if len(name) > 120:
            return api_error(
                "Release name must be 120 characters or fewer.", status_code=400
            )
        release.name = name
    if "status" in data:
        status = (data.get("status") or "").strip().lower()
        if status not in RELEASE_STATUSES:
            return api_error(
                "status must be one of: planned, in_progress, done.", status_code=400
            )
        release.status = status
    if "target_date" in data:
        if data["target_date"] is None:
            release.target_date = None
        else:
            try:
                release.target_date = datetime.fromisoformat(str(data["target_date"]))
            except ValueError:
                return api_error("target_date must be ISO format.", status_code=400)
    if "notes" in data:
        notes = data["notes"]
        if notes is not None and not isinstance(notes, str):
            return api_error("notes must be text.", status_code=400)
        release.notes = (notes or "").strip() or None
    db.session.commit()
    if "notes" in data:
        from app.models import Idea

        parent = Idea.query.get(release.parent_idea_id)
        write_release_notes_file(release, parent)
    counts = _release_counts(release.parent_idea_id)
    return api_ok(
        {"release": release.to_dict(child_count=counts.get(str(release.id), 0))}
    )


@bp.route("/releases/<uuid:release_id>", methods=["DELETE"])
@require_permission("change_status")
def delete_release(user, release_id):
    """Delete an empty release. Non-empty ones must be reassigned first."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    held = Idea.query.filter_by(release_id=release.id).count()
    if held:
        return api_error(
            f"Move the {held} idea(s) out of this release first.",
            status_code=400,
        )
    db.session.delete(release)
    db.session.commit()
    return api_ok({"deleted": str(release_id)})


@bp.route("/releases/<uuid:release_id>/assign", methods=["PATCH"])
@require_permission("change_status")
def assign_release(user, release_id):
    """Move child ideas into (or out of, with release_id null) a release."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    data = request.get_json() or {}
    idea_ids = data.get("idea_ids", [])
    if not isinstance(idea_ids, list) or not idea_ids:
        return api_error("Missing required field: idea_ids.", status_code=400)
    moved = 0
    for raw in idea_ids:
        try:
            child = Idea.query.get(uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            continue
        if child is None or child.parent_id != release.parent_idea_id:
            continue  # Only this parent's children can join its releases.
        if check_access(child) is not None:
            continue
        child.release_id = release.id
        moved += 1
    db.session.commit()
    return api_ok({"moved": moved, "release_id": str(release.id)})


@bp.route("/releases/<uuid:release_id>/unassign", methods=["PATCH"])
@require_permission("change_status")
def unassign_release(user, release_id):
    """Move child ideas back to 'No release yet'."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    data = request.get_json() or {}
    idea_ids = data.get("idea_ids", [])
    if not isinstance(idea_ids, list) or not idea_ids:
        return api_error("Missing required field: idea_ids.", status_code=400)
    moved = 0
    for raw in idea_ids:
        try:
            child = Idea.query.get(uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            continue
        if child is None or child.release_id != release.id:
            continue
        child.release_id = None
        moved += 1
    db.session.commit()
    return api_ok({"moved": moved, "release_id": str(release.id)})


@bp.route("/releases/<uuid:release_id>/complete", methods=["POST"])
@require_permission("change_status")
def complete_release(user, release_id):
    """Bulk-move release children to SHIP/DROP and mark the release done."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    data = request.get_json() or {}
    target = (data.get("status") or "shipped").strip().lower()
    if target in ("ship", "shipped"):
        target = "shipped"
    elif target in ("drop", "dropped"):
        target = "drop"
    else:
        return api_error(
            "status must be 'shipped' or 'drop'.", status_code=400
        )
    children = Idea.query.filter_by(release_id=release.id).all()
    if not children:
        return api_error("Nothing in this release yet — move ideas into it first.", status_code=400)

    moved = 0
    for child in children:
        child.status = "SHIP" if target == "shipped" else "DROP"
        moved += 1
    release.status = "done"
    release.completed_at = datetime.now(timezone.utc)
    from app.services.release_notes import (
        build_release_notes,
        write_release_notes_file,
    )

    release.notes = build_release_notes(release, children, moved)
    db.session.commit()

    parent = Idea.query.get(release.parent_idea_id)
    write_release_notes_file(release, parent)
    counts = _release_counts(release.parent_idea_id)
    return api_ok(
        {
            "moved": moved,
            "skipped": 0,
            "status": "SHIP" if target == "shipped" else "DROP",  # frontend keys off uppercase
            "child_count": counts.get(str(release.id), 0),
            "total": moved,
            "updated_count": moved,
            "skipped_illegal": 0,
            "release": release.to_dict(child_count=counts.get(str(release.id), 0)),
        }
    )


@bp.route("/releases/<uuid:release_id>/notes", methods=["POST"])
@require_permission("change_status")
def regenerate_release_notes(user, release_id):
    """Rebuild deterministic release notes for one release."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    parent = Idea.query.get(release.parent_idea_id)
    write_release_notes_file(release, parent)
    return api_ok({"message": "Release notes regenerated.", "release": release.to_dict()})


@bp.route("/releases/<uuid:release_id>/ai-config", methods=["GET"])
@token_required
def get_release_ai_config(user, release_id):
    """Get per-release AI settings override."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    row = ReleaseAIConfig.query.filter_by(release_id=release.id).first()
    return api_ok({"ai_config": row.to_dict() if row else None})


@bp.route("/releases/<uuid:release_id>/ai-config", methods=["PUT"])
@require_permission("change_status")
def update_release_ai_config(user, release_id):
    """Create or update per-release AI settings (override stage defaults)."""
    from app.models import PROVIDERS, STAGES, ReleaseAIConfig

    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    data = request.get_json() or {}
    provider = data.get("provider")
    if provider is not None:
        provider = str(provider).strip().lower() or None
        if provider is not None and provider not in PROVIDERS:
            return api_error(
                f"provider must be one of: {', '.join(PROVIDERS)}.", status_code=400
            )
    model_name = data.get("model_name")
    if model_name is not None:
        model_name = str(model_name).strip() or None
        if model_name is not None and len(model_name) > 100:
            return api_error("model_name must be 100 characters or fewer.", status_code=400)
    temperature = data.get("temperature")
    if temperature is not None:
        try:
            temperature = float(temperature)
            if not 0 <= temperature <= 2:
                return api_error("temperature must be between 0 and 2.", status_code=400)
        except (TypeError, ValueError):
            return api_error("temperature must be a number.", status_code=400)
    top_p = data.get("top_p")
    if top_p is not None:
        try:
            top_p = float(top_p)
            if not 0 <= top_p <= 1:
                return api_error("top_p must be between 0 and 1.", status_code=400)
        except (TypeError, ValueError):
            return api_error("top_p must be a number.", status_code=400)
    num_predict = data.get("num_predict")
    if num_predict is not None:
        try:
            num_predict = int(num_predict)
            if not 1 <= num_predict <= 4096:
                return api_error("num_predict must be between 1 and 4096.", status_code=400)
        except (TypeError, ValueError):
            return api_error("num_predict must be an integer.", status_code=400)
    skills = data.get("skills")
    if skills is not None:
        if not isinstance(skills, list) or not all(isinstance(v, str) for v in skills):
            return api_error("skills must be a list of strings.", status_code=400)
    guidelines = data.get("guidelines")
    if guidelines is not None:
        if not isinstance(guidelines, list) or not all(isinstance(v, str) for v in guidelines):
            return api_error("guidelines must be a list of strings.", status_code=400)
    row = ReleaseAIConfig.query.filter_by(release_id=release.id).first()
    if row is None:
        row = ReleaseAIConfig(release_id=release.id)
        db.session.add(row)
    if provider is not None:
        row.provider = provider
    if model_name is not None:
        row.model_name = model_name
    if temperature is not None:
        row.temperature = temperature
    if top_p is not None:
        row.top_p = top_p
    if num_predict is not None:
        row.num_predict = num_predict
    if skills is not None:
        row.skills = skills
    if guidelines is not None:
        row.guidelines = guidelines
    db.session.commit()
    return api_ok({"ai_config": row.to_dict()})


@bp.route("/releases/<uuid:release_id>/ai-config", methods=["DELETE"])
@require_permission("change_status")
def delete_release_ai_config(user, release_id):
    """Delete per-release AI settings (falls back to stage config)."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    row = ReleaseAIConfig.query.filter_by(release_id=release.id).first()
    if row is not None:
        db.session.delete(row)
        db.session.commit()
    return api_ok({"message": "AI settings cleared."})


@bp.route("/releases/<uuid:release_id>/github-push", methods=["POST"])
@require_permission("change_status")
def push_release_to_github_route(user, release_id):
    """Trigger a GitHub push for a finished release."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    from app.models import InstanceGitHubConfig

    status_val = release.status.value if hasattr(release.status, "value") else str(release.status)
    if status_val != "done":
        return api_error("Finish the release before pushing.", status_code=400)
    gh = InstanceGitHubConfig.query.filter_by(instance_id=release.instance_id).first()
    if release.github_sha:
        return api_error("This release is already on GitHub.", status_code=400)
    if gh is None or not gh.repo:
        return api_error("GitHub is not set up for this instance.", status_code=400)
    from app.tasks import enqueue_generation
    from app.tasks.github_tasks import push_release_to_github

    result = enqueue_generation(
        push_release_to_github, [str(release.id)], {}, provider="github"
    )
    return api_ok({"message": "Push started.", "job_id": result.id}, status_code=202)


@bp.route("/releases/<uuid:release_id>/run-action", methods=["POST"])
@require_permission("change_status")
def bulk_run_action(user, release_id):
    """Start a secondary action (PRD/Design/Build) for every idea in a release."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    data = request.get_json() or {}
    action_type = data.get("action_type")
    from app.services.secondary_actions import is_known_action

    if not is_known_action(action_type):
        return api_error("Unknown action type.", status_code=400)
    confirm_build = bool(data.get("confirm_build", False))
    children = Idea.query.filter_by(release_id=release.id).all()
    if not children:
        return api_error("Nothing in this release yet — move ideas into it first.", status_code=400)
    from app.services.action_context import parent_context
    from app.tasks.ollama_tasks import run_secondary_action
    from app.tasks import enqueue_generation

    requested_target = data.get("target_id")

    def _resolve_target(child, row):
        """Repo this child's build writes into.

        Order: explicit request, the repo its previous run used, then the
        instance's only registered repo. Anything ambiguous stays None so
        the caller can skip with a reason instead of guessing.
        """
        for candidate in (requested_target, getattr(row, "target_id", None)):
            if not candidate:
                continue
            try:
                found = InstanceBuildTarget.query.filter_by(
                    id=uuid.UUID(str(candidate)), instance_id=child.instance_id
                ).first()
            except (ValueError, TypeError, AttributeError):
                found = None
            if found is not None:
                return found
        targets = InstanceBuildTarget.query.filter_by(instance_id=child.instance_id).all()
        return targets[0] if len(targets) == 1 else None

    launched = 0
    started = []
    skipped = []
    # Gate hints: the stage a child must reach before this action runs.
    _gate = {
        "PRD_DOC": "Scope",
        "DESIGN_DOC": "Map",
        "BUILD_CODE": "Ship",
    }
    from app.routes.ideas import _check_action_allowed

    for child in children:
        ctx = parent_context(child)
        rows_q = SecondaryActionResult.query.filter_by(
            idea_id=child.id, action_type=action_type
        )
        if action_type == "BUILD_CODE":
            # Only builds carry a repo; other actions must not be filtered
            # by it (that hid every PRD and broke the "already has one" skip).
            rows_q = rows_q.filter(SecondaryActionResult.target_id.isnot(None))
        row = rows_q.order_by(SecondaryActionResult.executed_at.desc()).first()

        if not _check_action_allowed(child, action_type):
            skipped.append(
                {
                    "reference_code": child.reference_code,
                    "reason": (
                        f"{child.reference_code} is in {child.status}; move it "
                        f"to {_gate.get(action_type, 'the right stage')} first."
                    ),
                }
            )
            continue

        # Bulk docs skip work that already exists; recreating one is the
        # single-idea path (Recreate), not a release-wide sweep.
        if action_type in ("PRD_DOC", "DESIGN_DOC") and row is not None and row.is_current:
            skipped.append(
                {
                    "reference_code": child.reference_code,
                    "reason": "Already has one — recreate it from the idea if you need a new version.",
                }
            )
            continue

        target = _resolve_target(child, row) if action_type == "BUILD_CODE" else None
        if action_type == "BUILD_CODE" and target is None:
            skipped.append(
                {
                    "reference_code": child.reference_code,
                    "reason": "No build repo selected — pick one on the Build tab or register one in Admin → AI Settings.",
                }
            )
            continue
        # SecondaryActionResult has no `status` column — use is_current instead.
        # Preview (confirm_build=false) always enqueues; write (confirm_build=true)
        # requires a prior completed preview for the same repo.
        if confirm_build:
            ready = (
                target is not None
                and row is not None
                and row.is_current
                and str(row.target_id) == str(target.id)
            )
        else:
            ready = True
        if ready:
            run = PromptRun(
                instance_id=child.instance_id,
                action_type=action_type,
                triggered_by="manual",
                idea_id=child.id,
                status=PromptRunStatus.PENDING,
                job_type="ai",
            )
            db.session.add(run)
            db.session.commit()

            # Pass everything the worker needs: without target_id the task
            # fails with "Unknown build target for this instance", which is
            # exactly what the release-wide build-all used to do.
            extra = {"confirm_build": confirm_build}
            if target is not None:
                extra["target_id"] = str(target.id)
                extra["target_name"] = target.name

            # Release settings win over the stage defaults for every idea
            # in it (the panel on the card promises exactly that). The
            # previous run's model is only a display detail, never an
            # override — copying it made the panel a no-op after the
            # first run.
            merged = {}
            try:
                from app.models import resolve_release, resolve_stage

                stage_cfg = resolve_stage(
                    child.instance_id,
                    getattr(child.status, "value", child.status),
                )
                release_cfg = resolve_release(child)
                merged = {
                    **stage_cfg,
                    **{k: v for k, v in release_cfg.items() if v is not None},
                }
            except Exception:
                merged = {}
            child_provider = (merged.get("provider") or "ollama").lower()

            run.job_type = "ai"
            run.provider = child_provider
            run.model = merged.get("model_name")
            run.queue = "opencode" if child_provider == "opencode" else "ollama"
            db.session.commit()

            enqueue_generation(
                run_secondary_action,
                [str(child.id), action_type],
                {
                    "model_override": merged.get("model_name"),
                    "extra_context": extra,
                    "run_id": str(run.id),
                    "provider_override": merged.get("provider"),
                },
                provider=child_provider,
            )
            launched += 1
            started.append(child.reference_code)
        else:
            skipped.append(
                {
                    "reference_code": child.reference_code,
                    "reason": "No completed build preview for this repo — run Build preview first.",
                }
            )
    db.session.commit()
    summary = (
        f"Started {launched} of {len(children)}. "
        + (f"Skipped {len(skipped)}." if skipped else "Nothing skipped.")
    )
    return api_ok(
        {
            "started": started,
            "launched": launched,
            "skipped": skipped,
            "summary": summary,
            "release_id": str(release.id),
        },
        status_code=202,
    )


# ---- One-action release run (PRD -> Design -> Build -> Test) -------------


@bp.route("/releases/<uuid:release_id>/pipeline", methods=["POST"])
@require_permission("change_status")
def start_release_pipeline_route(user, release_id):
    """Start (or resume) the whole release in one action."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    from app.services.release_pipeline import start_release_pipeline

    ok, message = start_release_pipeline(release, user)
    if not ok:
        return api_error(message, status_code=400)
    count = Idea.query.filter_by(release_id=release.id).count()
    return api_ok(
        {"message": message, "release": release.to_dict(child_count=count)},
        status_code=202,
    )


@bp.route("/releases/<uuid:release_id>/pipeline/stop", methods=["POST"])
@require_permission("change_status")
def stop_release_pipeline_route(user, release_id):
    """Stop after the current step; already-finished work is kept."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    from app.services.release_pipeline import stop_release_pipeline

    ok, message = stop_release_pipeline(release)
    if not ok:
        return api_error(message, status_code=400)
    count = Idea.query.filter_by(release_id=release.id).count()
    return api_ok({"message": message, "release": release.to_dict(child_count=count)})


@bp.route("/releases/<uuid:release_id>/pipeline", methods=["GET"])
@token_required
def get_release_pipeline(user, release_id):
    """Poll progress: compact summary plus per-child state and report."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    count = Idea.query.filter_by(release_id=release.id).count()
    return api_ok(
        {
            "pipeline": release.pipeline_summary(),
            "child_count": count,
            "state": release.pipeline_state or {},
        }
    )
