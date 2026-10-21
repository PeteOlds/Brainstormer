"""Release-related endpoints for the ideas dashboard.

Handles release CRUD, assignment, completion, notes, AI config, and
GitHub push for releases tied to parent ideas.
"""

from datetime import datetime
from flask import Blueprint, request

from app.extensions import db
from app.models import Idea, Release, ReleaseAIConfig
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
    from datetime import datetime

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
    from datetime import datetime

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
    """Bulk-move release children to SHIP/DROP based on per-child readiness."""
    release = Release.query.get_or_404(release_id)
    denied = check_access(release)
    if denied is not None:
        return denied
    data = request.get_json() or {}
    target = (data.get("status") or "shipped").strip().lower()
    if target not in ("shipped", "drop"):
        return api_error(
            "status must be 'shipped' or 'drop'.", status_code=400
        )
    children = (
        Idea.query.filter_by(release_id=release.id).all()
    )
    if not children:
        return api_error("Nothing in this release yet — move ideas into it first.", status_code=400)
    from app.services.action_context import parent_context
    from app.services.secondary_actions import run_secondary_action

    moved = 0
    skipped = 0
    for child in children:
        ctx = parent_context(child)
        row = (
            SecondaryActionResult.query.filter_by(
                idea_id=child.id, action_type="BUILD_CODE"
            )
            .filter(SecondaryActionResult.target_id.isnot(None))
            .order_by(SecondaryActionResult.executed_at.desc())
            .first()
        )
        ready = (
            row is not None
            and (row.status.value if hasattr(row.status, "value") else row.status)
            == "done"
        )
        if ready:
            target_status = "SHIP" if target == "shipped" else "DROP"
            child.status = target_status
            moved += 1
        else:
            skipped += 1
    db.session.commit()
    counts = _release_counts(release.parent_idea_id)
    return api_ok(
        {
            "moved": moved,
            "skipped": skipped,
            "status": release.status.value,
            "child_count": counts.get(str(release.id), 0),
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
    return api_ok({"message": "Release notes regenerated."})


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
    from app.tasks.github_tasks import push_release_to_github

    push_release_to_github.delay(str(release.id))
    return api_ok({"message": "Push started."})


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
    if action_type not in ("PRD_DOC", "DESIGN_DOC", "BUILD_CODE"):
        return api_error("action_type must be PRD_DOC, DESIGN_DOC, or BUILD_CODE.", status_code=400)
    children = Idea.query.filter_by(release_id=release.id).all()
    if not children:
        return api_error("Nothing in this release yet — move ideas into it first.", status_code=400)
    from app.services.action_context import parent_context
    from app.services.secondary_actions import run_secondary_action

    launched = 0
    skipped = 0
    for child in children:
        ctx = parent_context(child)
        row = (
            SecondaryActionResult.query.filter_by(
                idea_id=child.id, action_type=action_type
            )
            .filter(SecondaryActionResult.target_id.isnot(None))
            .order_by(SecondaryActionResult.executed_at.desc())
            .first()
        )
        ready = (
            row is not None
            and (row.status.value if hasattr(row.status, "value") else row.status)
            == "done"
        )
        if ready:
            run_secondary_action(child, action_type, parent_context(child))
            launched += 1
        else:
            skipped += 1
    db.session.commit()
    return api_ok(
        {
            "launched": launched,
            "skipped": skipped,
            "release_id": str(release.id),
        }
    )
