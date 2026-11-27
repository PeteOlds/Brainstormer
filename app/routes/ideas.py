import json
import os
import random
import string
import uuid
from datetime import datetime, timezone

from flask import Blueprint, g, request
from flask_jwt_extended import get_jwt_identity
from flask_limiter.util import get_remote_address
from sqlalchemy import asc, desc, func, or_

from app.extensions import db, limiter
from app.models import (
    Comment,
    Idea,
    IdeaEdit,
    IdeaStatusHistory,
    PromptRun,
    PromptRunStatus,
    SecondaryActionResult,
    User,
    Vote,
)
from app.models.enums import IdeaStatus
from app.utils.decorators import (
    _membership_allows_admin,
    admin_required,
    require_permission,
    token_required,
)
from app.utils.responses import api_accepted, api_created, api_error, api_ok
from app.utils.tenancy import apply_scope, check_access, current_instance_role, stamp

bp = Blueprint("ideas", __name__)
from app.services.idea_helpers import (  # noqa: F401
    _chat_enabled_for,
    _chat_gate,
    _chat_provider_error,
    _chat_rate_key,
    _check_action_allowed,
    _enqueue_action,
    _get_user_vote,
    _maybe_push_on_scale,
    _resolve_build_target,
)


@bp.route("/ideas", methods=["GET"])
@token_required
def list_ideas(user):
    """List ideas with pagination, filtering, and sorting."""
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 20, type=int)
    status = request.args.get("status")
    sort_by = request.args.get("sort_by", "created_at")
    search = request.args.get("search")
    prompt_config_id = request.args.get(
        "prompt_config_id", type=lambda x: uuid.UUID(x) if x else None
    )
    model = request.args.get("model")

    query = apply_scope(Idea.query, Idea)

    if status and status.upper() in ("ACTIVE", "ACTIVE_ONLY"):
        # ACTIVE_ONLY is a frontend-only filter - exclude dropped/archived ideas
        query = query.filter(Idea.status.notin_(["DROP", "ARCHIVE"]))
    elif status and status.upper() != "ALL":
        query = query.filter(Idea.status == status.upper())
    # 'ALL' (or absent) means no status filter.
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Idea.reference_code.ilike(like),
                Idea.prompt_title.ilike(like),
                Idea.raw_content.ilike(like),
            )
        )
    if prompt_config_id:
        query = query.filter(Idea.prompt_config_id == prompt_config_id)
    if model:
        from app.models import PromptConfig

        query = query.join(
            PromptConfig, Idea.prompt_config_id == PromptConfig.id
        ).filter(PromptConfig.model_name == model)

    # Sorting (matches the dashboard sort dropdown values)
    if sort_by == "votes":
        query = query.order_by(desc(Idea.net_score), desc(Idea.created_at))
    elif sort_by == "-votes":
        query = query.order_by(asc(Idea.net_score), desc(Idea.created_at))
    elif sort_by == "comments":
        query = query.order_by(desc(Idea.comments_count), desc(Idea.created_at))
    elif sort_by == "-created_at":
        query = query.order_by(asc(Idea.created_at))
    else:
        query = query.order_by(desc(Idea.created_at))

    if (request.args.get("mine") or "").strip().lower() in ("1", "true", "yes"):
        # My ideas: created, voted, or commented by me.
        from app.models import Comment as _Comment
        from app.models import Vote as _Vote

        query = query.filter(
            or_(
                Idea.created_by_id == user.id,
                Idea.id.in_(
                    db.session.query(_Vote.idea_id).filter(_Vote.user_id == user.id)
                ),
                Idea.id.in_(
                    db.session.query(_Comment.idea_id).filter(
                        _Comment.user_id == user.id
                    )
                ),
            )
        )

    pagination = query.paginate(page=page, per_page=limit, error_out=False)

    ideas_data = []
    from app.models import PromptRun, PromptRunStatus

    for idea in pagination.items:
        user_vote = _get_user_vote(user.id, idea.id)
        d = idea.to_dict(user_vote=user_vote)
        pending = PromptRun.query.filter(
            PromptRun.idea_id == idea.id,
            PromptRun.status.in_([PromptRunStatus.PENDING, PromptRunStatus.RUNNING]),
        ).count()
        d["pending_runs"] = pending
        ideas_data.append(d)

    return api_ok(
        {
            "ideas": ideas_data,
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
        }
    )


@bp.route("/dashboard", methods=["GET"])
@token_required
def dashboard(user):
    """Summary data for the role-based dashboard."""
    from sqlalchemy import func

    from app.models import Idea, PromptRun

    iid_scope = None
    from app.utils.tenancy import current_instance_id

    iid = current_instance_id()
    idea_q = Idea.query
    if iid is not None:
        idea_q = idea_q.filter(Idea.instance_id == iid)

    # Ideas by status
    by_status = {}
    q = db.session.query(Idea.status, func.count(Idea.id))
    if iid is not None:
        q = q.filter(Idea.instance_id == iid)
    for status, count in q.group_by(Idea.status).all():
        key = status.value if hasattr(status, "value") else str(status)
        by_status[key] = count

    # Most voted (top 5)
    most_voted = (
        idea_q.order_by(Idea.net_score.desc(), Idea.created_at.desc()).limit(5).all()
    )
    most_voted_data = [
        {
            "id": str(i.id),
            "reference_code": i.reference_code,
            "prompt_title": i.prompt_title,
            "net_score": i.net_score,
            "upvotes_count": i.upvotes_count,
            "downvotes_count": i.downvotes_count,
            "status": i.status.value if hasattr(i.status, "value") else str(i.status),
        }
        for i in most_voted
    ]

    most_commented = (
        idea_q.order_by(Idea.comments_count.desc(), Idea.created_at.desc())
        .limit(5)
        .all()
    )
    from app.models import Comment as _Comment

    most_commented_data = []
    for i in most_commented:
        latest = (
            _Comment.query.filter_by(idea_id=i.id)
            .order_by(_Comment.created_at.desc())
            .first()
        )
        most_commented_data.append(
            {
                "id": str(i.id),
                "reference_code": i.reference_code,
                "prompt_title": i.prompt_title,
                "comment_count": i.comments_count,
                "latest_comment": (
                    {
                        "body": latest.body,
                        "created_at": (
                            latest.created_at.isoformat() if latest.created_at else None
                        ),
                        "author": (
                            latest.user.name or latest.user.email
                            if latest.user
                            else None
                        ),
                    }
                    if latest
                    else None
                ),
                "status": (
                    i.status.value if hasattr(i.status, "value") else str(i.status)
                ),
            }
        )

    # Recent runs (last 10)
    run_q = PromptRun.query
    if iid is not None:
        run_q = run_q.filter(PromptRun.instance_id == iid)
    recent_runs = run_q.order_by(PromptRun.created_at.desc()).limit(10).all()
    recent_runs_data = []
    for r in recent_runs:
        idea = r.idea
        prompt = r.prompt_config
        recent_runs_data.append(
            {
                "id": str(r.id),
                "status": (
                    r.status.value if hasattr(r.status, "value") else str(r.status)
                ),
                "action_type": r.action_type,
                "provider": r.provider,
                "model": r.model,
                "duration_seconds": r.duration_seconds,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "idea_id": str(r.idea_id) if r.idea_id else None,
                "idea_reference": idea.reference_code if idea else None,
                "idea_title": idea.prompt_title if idea else None,
                "prompt_title": prompt.title if prompt else None,
            }
        )

    return api_ok(
        {
            "by_status": by_status,
            "most_voted": most_voted_data,
            "most_commented": most_commented_data,
            "recent_runs": recent_runs_data,
            "total_ideas": idea_q.count(),
        }
    )


@bp.route("/ideas", methods=["POST"])
@token_required
def create_idea(user):
    """Create a new idea manually.

    Available to all users with can_create_ideas=True (default).
    Format matches generated ideas: prompt_title, raw_content, structured_content (optional).
    """
    if not user.can_create_ideas:
        return api_error(
            "Manual idea creation is disabled for your account.", status_code=403
        )

    data = request.get_json() or {}

    from pydantic import ValidationError

    from app.schemas.api_schemas import IdeaCreateRequest

    try:
        IdeaCreateRequest.model_validate(data)
    except ValidationError as exc:
        return api_error("Invalid idea payload.", status_code=400, errors=exc.errors())

    prompt_title = (data.get("prompt_title") or "").strip()
    raw_content = (data.get("raw_content") or "").strip()
    structured_content = data.get("structured_content")

    # Child-idea fields (Scale-phase: Report a problem / Suggest an improvement)
    parent_id = data.get("parent_id")
    child_kind = (data.get("child_kind") or "").strip().lower() or None
    parent_idea = None
    if parent_id:
        try:
            parent_idea = Idea.query.get(uuid.UUID(str(parent_id)))
        except (ValueError, TypeError):
            parent_idea = None
        if parent_idea is None:
            return api_error("Parent idea not found.", status_code=404)
    if parent_idea is not None:
        denied = check_access(parent_idea)
        if denied is not None:
            return denied
        parent_status = (
            parent_idea.status.value
            if hasattr(parent_idea.status, "value")
            else str(parent_idea.status)
        )
        if parent_idea.child_kind:
            return api_error("Child ideas cannot have children.", status_code=400)
        if parent_status != "SCALE":
            return api_error(
                "Children can only be added to Scale-phase ideas.", status_code=400
            )
    if parent_idea is not None and not child_kind:
        return api_error("child_kind is required for child ideas.", status_code=400)
    if child_kind and child_kind not in ("enhancement", "bugfix"):
        return api_error(
            "child_kind must be 'enhancement' or 'bugfix'.", status_code=400
        )
    if child_kind and not parent_idea:
        return api_error("child_kind requires a parent_id.", status_code=400)

    if not prompt_title:
        return api_error("prompt_title is required.", status_code=400)
    if len(prompt_title) > 200:
        return api_error(
            "prompt_title must be 200 characters or fewer.", status_code=400
        )
    if not raw_content:
        return api_error("raw_content is required.", status_code=400)

    # Validate structured_content if provided
    if structured_content is not None:
        if not isinstance(structured_content, dict):
            return api_error("structured_content must be an object.", status_code=400)
        allowed = {
            "elevator_pitch": 500,
            "target_audience": 300,
            "core_value_proposition": 500,
            "monetization_strategy": 300,
        }
        unknown = [k for k in structured_content if k not in allowed]
        if unknown:
            return api_error(
                f"Unknown structured fields: {', '.join(unknown)}.", status_code=400
            )
        cleaned = {}
        for key, cap in allowed.items():
            if key not in structured_content:
                continue
            val = structured_content[key]
            if not isinstance(val, str) or not val.strip():
                return api_error(f"{key} must be a non-empty string.", status_code=400)
            if len(val.strip()) > cap:
                return api_error(
                    f"{key} must be {cap} characters or fewer.", status_code=400
                )
            cleaned[key] = val.strip()
        if not cleaned:
            return api_error(
                "structured_content must include at least one known field.",
                status_code=400,
            )
        structured_content = cleaned

    # Generate reference code (IDEA-XXXX format)
    import random
    import string

    while True:
        ref_code = f"IDEA-{''.join(random.choices(string.digits, k=4))}"
        if not Idea.query.filter_by(reference_code=ref_code).first():
            break

    idea = Idea(
        reference_code=ref_code,
        prompt_title=prompt_title,
        raw_content=raw_content,
        structured_content=structured_content,
        status="SPARK",
        prompt_config_id=None,  # Manual ideas have no associated prompt config
        created_by_id=user.id,  # Authorship drives edit-own permissions.
        parent_id=parent_idea.id if parent_idea else None,
        child_kind=child_kind if parent_idea else None,
    )
    # A child stays in its parent's instance so scoping keeps them together.
    if parent_idea and parent_idea.instance_id:
        idea.instance_id = parent_idea.instance_id
    else:
        stamp(idea)

    db.session.add(idea)
    db.session.commit()

    return api_created(idea.to_dict(include_content=True, user_vote=None))


@bp.route("/ideas/upload", methods=["POST"])
@token_required
def upload_idea_file(user):
    """Create a new idea from an uploaded markdown or text file.

    The filename (without extension) becomes the title; the file body
    becomes the idea content. Only .md/.txt text files up to 10 MB are accepted.
    """
    if not user.can_create_ideas:
        return api_error(
            "Manual idea creation is disabled for your account.", status_code=403
        )

    if "file" not in request.files:
        return api_error("No file uploaded.", status_code=400)
    file = request.files["file"]
    if not file or not file.filename:
        return api_error("No file selected.", status_code=400)

    filename = file.filename
    if not (filename.lower().endswith(".md") or filename.lower().endswith(".txt")):
        return api_error(
            "Only .md (Markdown) or .txt (text) files are accepted.", status_code=400
        )

    # Size check (10 MB).
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 10 * 1024 * 1024:
        return api_error("File must be under 10 MB.", status_code=413)
    if size == 0:
        return api_error("File is empty.", status_code=400)

    raw = file.read()
    if b"\x00" in raw:
        return api_error("File must be text, not binary.", status_code=400)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return api_error("File must be UTF-8 text.", status_code=400)

    title = os.path.splitext(filename)[0].strip() or filename
    if len(title) > 200:
        title = title[:200]
    content = text.strip()
    if not content:
        return api_error("File content is empty.", status_code=400)

    # Generate reference code
    import random
    import string

    while True:
        ref_code = f"IDEA-{''.join(random.choices(string.digits, k=4))}"
        if not Idea.query.filter_by(reference_code=ref_code).first():
            break

    idea = Idea(
        reference_code=ref_code,
        prompt_title=title,
        raw_content=content,
        status="SPARK",
        prompt_config_id=None,
        created_by_id=user.id,
    )
    stamp(idea)
    db.session.add(idea)
    db.session.commit()

    return api_created(idea.to_dict(include_content=True, user_vote=None))


@bp.route("/ideas/<uuid:idea_id>/build/check-overwrite", methods=["POST"])
@token_required
def check_build_overwrite(user, idea_id):
    """Report which preview files already exist in the target repo."""
    import uuid as _uuid

    from app.models import Idea, InstanceBuildTarget

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    data = request.get_json() or {}
    target_id = data.get("target_id")
    bt = None
    if target_id:
        try:
            bt = InstanceBuildTarget.query.filter_by(
                id=_uuid.UUID(str(target_id)), instance_id=idea.instance_id
            ).first()
        except (ValueError, TypeError):
            bt = None
    if bt is None:
        candidates = InstanceBuildTarget.query.filter_by(
            instance_id=idea.instance_id
        ).all()
        if len(candidates) == 1:
            bt = candidates[0]
    if bt is None:
        return api_error("No build target.", status_code=400)

    from app.services.build_service import join_target_path, resolve_target

    try:
        root = resolve_target(bt)
    except Exception as exc:
        return api_error(str(exc), status_code=400)

    from app.models import ActionType, SecondaryActionResult

    preview = SecondaryActionResult.query.filter_by(
        idea_id=idea.id, action_type=ActionType.BUILD_CODE, is_current=True
    ).first()
    if not preview or preview.result_data.get("written"):
        return api_ok({"existing": []})

    files = preview.result_data.get("files") or []
    existing = []
    for f in files:
        rel = f.get("path") if isinstance(f, dict) else None
        if not rel:
            continue
        try:
            full = join_target_path(root, rel)
            if os.path.exists(full):
                existing.append(rel)
        except Exception:
            pass
    return api_ok({"existing": existing})


@token_required
def find_similar_ideas(user, idea_id):
    """Find ideas similar to the given idea using embedding similarity."""
    from app.services.embedding_service import get_embedding_service

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied
    if not idea.embedding:
        return api_error(
            "This idea has no embedding yet. Try again later.", status_code=404
        )

    threshold = request.args.get("threshold", 0.85, type=float)
    limit = request.args.get("limit", 10, type=int)

    from app.utils.tenancy import current_instance_id

    svc = get_embedding_service()
    similar = svc.find_similar_ideas(
        idea.id, threshold=threshold, limit=limit, instance_id=current_instance_id()
    )

    similar_data = []
    for similar_idea, score in similar:
        data = similar_idea.to_dict()
        data["similarity_score"] = round(score, 3)
        similar_data.append(data)

    return api_ok({"ideas": similar_data})


@bp.route("/ideas/<uuid:idea_id>", methods=["GET"])
@token_required
def get_idea(user, idea_id):
    """Get a single idea with full details."""
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    # Build parent context (parent breadcrumb)
    parent_context_data = None
    if idea.parent_id:
        parent = Idea.query.get(idea.parent_id)
        if parent:
            parent_context_data = {
                "id": str(parent.id),
                "reference_code": parent.reference_code,
                "prompt_title": parent.prompt_title,
                "status": parent.status.value,
            }

    # Full secondary action results (with output/runbook) for the detail
    # view's Build tab: the frontend expects payload.actions to render
    # "How to run" instructions, file preview, and write report.
    actions = [
        a.to_dict()
        for a in idea.actions.order_by(SecondaryActionResult.executed_at.desc()).all()
    ]

    # Running actions (PENDING/RUNNING PromptRuns) so the UI can show
    # "Running..." instead of "No results yet".
    from app.models import PromptRun, PromptRunStatus

    running = [
        r.action_type
        for r in PromptRun.query.filter(
            PromptRun.idea_id == idea.id,
            PromptRun.status.in_([PromptRunStatus.PENDING, PromptRunStatus.RUNNING]),
        ).all()
        if r.action_type
    ]

    # Child count for parent ideas (used by the detail view).
    child_count = Idea.query.filter_by(parent_id=idea.id).count()

    from app.models import IdeaEdit

    edit_history = [
        e.to_dict()
        for e in IdeaEdit.query.filter_by(idea_id=idea.id)
        .order_by(IdeaEdit.edited_at.desc())
        .all()
    ]

    payload = {
        "idea": idea.to_dict(
            user_vote=_get_user_vote(user.id, idea.id), include_content=True
        ),
        "actions": actions,
        "running_actions": running,
        "parent": parent_context_data,
        "child_count": child_count,
        "edit_history": edit_history,
    }

    # Per-idea generation time is an operational metric: admins only.
    # `duration_seconds` is recorded on the PromptRun that produced the idea.
    from app.utils.decorators import _membership_allows_admin

    if _membership_allows_admin(user):
        last_run = (
            PromptRun.query.filter_by(idea_id=idea.id)
            .order_by(PromptRun.started_at.desc())
            .first()
        )
        if last_run is not None and last_run.duration_seconds is not None:
            payload["idea"]["generation_seconds"] = last_run.duration_seconds

    return api_ok(payload)


@bp.route("/ideas/<uuid:idea_id>/status", methods=["PATCH"])
@require_permission("change_status")
def update_idea_status(user, idea_id):
    """Move an idea to a new lifecycle stage (admin/member gated)."""
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    data = request.get_json() or {}
    new_status = (data.get("status") or "").strip().upper()
    if new_status not in [s.value for s in IdeaStatus]:
        return api_error(
            f"Invalid status. Must be one of: {', '.join(s.value for s in IdeaStatus)}.",
            status_code=400,
        )

    old_status = idea.status
    from app.models.lifecycle import can_transition

    if not can_transition(old_status, IdeaStatus[new_status]):
        return api_error(
            f"Illegal transition {old_status.value} -> {new_status}.",
            status_code=400,
        )
    idea.status = IdeaStatus[new_status]

    # Record status transition
    from app.models import IdeaStatusHistory

    history = IdeaStatusHistory(
        idea_id=idea.id,
        old_status=old_status,
        new_status=idea.status,
        changed_by_id=user.id,
    )
    db.session.add(history)
    db.session.commit()

    return api_ok(
        {
            "idea": idea.to_dict(user_vote=_get_user_vote(user.id, idea.id)),
            "status": idea.status.value,
            "previous_status": old_status.value,
            "new_status": idea.status.value,
        }
    )


@bp.route("/ideas/bulk-status", methods=["PATCH"])
@require_permission("change_status")
def bulk_update_idea_status(user):
    """Bulk move multiple ideas to a new status (admin only)."""
    from app.models import IdeaStatus

    data = request.get_json() or {}
    idea_ids = data.get("idea_ids", [])
    status = data.get("status")

    if not idea_ids or not isinstance(idea_ids, list):
        return api_error("Missing required field: idea_ids.", status_code=400)
    if not status:
        return api_error("Missing required field: status.", status_code=400)

    try:
        new_status = IdeaStatus[status.upper()]
    except KeyError:
        return api_error(
            f"Invalid status: {status}. Must be one of: "
            f"{', '.join(s.value for s in IdeaStatus)}.",
            status_code=400,
        )

    from app.models.lifecycle import can_transition

    moved = 0
    skipped = []
    for raw_id in idea_ids:
        try:
            idea = Idea.query.get(uuid.UUID(str(raw_id)))
        except (ValueError, TypeError):
            continue
        if idea is None:
            continue
        denied = check_access(idea)
        if denied is not None:
            continue
        old_status = idea.status
        if not can_transition(old_status, new_status):
            skipped.append(
                {
                    "reference_code": idea.reference_code,
                    "reason": f"Illegal transition {old_status.value} -> {new_status.value}.",
                }
            )
            continue
        idea.status = new_status

        # Record status transition
        from app.models import IdeaStatusHistory

        history = IdeaStatusHistory(
            idea_id=idea.id,
            old_status=old_status,
            new_status=new_status,
            changed_by_id=user.id,
        )
        db.session.add(history)
        moved += 1

    db.session.commit()
    return api_ok(
        {
            "moved": moved,
            "updated_count": moved,
            "status": new_status.value,
            "skipped": skipped,
            "skipped_illegal": len(skipped),
        }
    )


@bp.route("/ideas/phase-counts", methods=["GET"])
@token_required
def phase_counts(user):
    """Ideas per lifecycle phase (homepage pie + admin analytics)."""
    from sqlalchemy import func

    rows = (
        apply_scope(db.session.query(Idea.status, func.count(Idea.id)), Idea)
        .group_by(Idea.status)
        .all()
    )
    counts = {(s.value if hasattr(s, "value") else s): n for s, n in rows}
    return api_ok({"counts": counts, "total": sum(counts.values())})


@bp.route("/ideas/<uuid:idea_id>/children", methods=["GET"])
@token_required
def list_children(user, idea_id):
    """Children (enhancements/bugfixes) of one idea, server-side paginated."""
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied
    page = request.args.get("page", 1, type=int)
    limit = min(request.args.get("limit", 20, type=int), 100)
    release_id = request.args.get("release_id")
    kind = (request.args.get("kind") or "").strip().lower() or None

    query = Idea.query.filter_by(parent_id=idea.id)
    if kind:
        query = query.filter_by(child_kind=kind)
    if release_id == "none":
        query = query.filter(Idea.release_id.is_(None))
    elif release_id:
        try:
            query = query.filter_by(release_id=uuid.UUID(str(release_id)))
        except (ValueError, TypeError):
            return api_error("Invalid release_id.", status_code=400)
    query = query.order_by(desc(Idea.created_at))
    pagination = query.paginate(page=page, per_page=limit, error_out=False)
    ideas_data = []
    for child in pagination.items:
        user_vote = _get_user_vote(user.id, child.id)
        ideas_data.append(child.to_dict(user_vote=user_vote))

    # Build status per child (one batched query): the latest BUILD_CODE
    # run's state, so the Scale tab can show Queued/Running/Done/Failed
    # without opening each idea.
    from app.models import PromptRun, PromptRunStatus

    child_ids = [c.id for c in pagination.items]
    run_rows = (
        PromptRun.query.filter(
            PromptRun.idea_id.in_(child_ids),
            PromptRun.action_type == "BUILD_CODE",
        )
        .order_by(PromptRun.created_at.desc())
        .all()
    )
    latest_by_idea = {}
    for r in run_rows:
        latest_by_idea.setdefault(r.idea_id, r)
    for row, child in zip(ideas_data, pagination.items):
        run = latest_by_idea.get(child.id)
        if run is None:
            row["build_status"] = None
        else:
            row["build_status"] = {
                "status": run.status.value,
                "job_id": run.job_id,
                "error": (
                    (run.error or None)
                    if run.status == PromptRunStatus.FAILED
                    else None
                ),
            }
    return api_ok(
        {
            "ideas": ideas_data,
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
        }
    )


@bp.route("/ideas/<uuid:parent_id>/scale-status", methods=["GET"])
@token_required
def scale_status(user, parent_id):
    """Build run states for one parent's children (Scale tab auto-refresh).

    Returns {child_id: {"status": ..., "job_id": ..., "error": ...}} so the
    tab can poll while any build is queued or running.
    """
    from app.models import PromptRun, PromptRunStatus

    parent = Idea.query.get_or_404(parent_id)
    denied = check_access(parent)
    if denied is not None:
        return denied
    child_ids = [c.id for c in Idea.query.filter_by(parent_id=parent.id).all()]
    if not child_ids:
        return api_ok({"builds": {}})
    run_rows = (
        db.session.query(
            PromptRun.idea_id,
            PromptRun.status,
            PromptRun.job_id,
            PromptRun.error,
            PromptRun.created_at,
        )
        .filter(
            PromptRun.idea_id.in_(child_ids),
            PromptRun.action_type == "BUILD_CODE",
        )
        .order_by(PromptRun.created_at.desc())
        .all()
    )
    latest_by_idea = {}
    for idea_id, status, job_id, error, _created in run_rows:
        if idea_id not in latest_by_idea:
            latest_by_idea[idea_id] = (status, job_id, error)
    builds = {}
    for cid, (status, job_id, error) in latest_by_idea.items():
        builds[str(cid)] = {
            "status": status.value,
            "job_id": job_id,
            "error": (error or None) if status == PromptRunStatus.FAILED else None,
        }
    return api_ok({"builds": builds})


@bp.route("/ideas/<uuid:idea_id>/vote", methods=["POST"])
@token_required
def vote_idea(user, idea_id):
    """Upvote or downvote an idea (toggle)."""
    from app.models import Vote

    data = request.get_json() or {}
    direction = data.get("direction")
    if direction not in (1, -1):
        return api_error(
            "direction must be 1 (upvote) or -1 (downvote).", status_code=400
        )

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    existing = Vote.query.filter_by(user_id=user.id, idea_id=idea_id).first()
    if existing:
        if existing.value == direction:
            # Toggling off same direction = remove vote
            db.session.delete(existing)
            db.session.flush()
            idea.update_vote_counts()
            db.session.commit()
            return api_ok(
                {
                    "message": "Vote removed.",
                    "user_vote": 0,
                    "current_user_vote": 0,
                    "net_votes": idea.net_score,
                    "upvotes_count": idea.upvotes_count,
                    "downvotes_count": idea.downvotes_count,
                }
            )
        else:
            # Switching direction
            existing.value = direction
            db.session.flush()
            idea.update_vote_counts()
            db.session.commit()
            return api_ok(
                {
                    "message": f"Vote changed to {'upvote' if direction == 1 else 'downvote'}.",
                    "user_vote": direction,
                    "current_user_vote": direction,
                    "net_votes": idea.net_score,
                    "upvotes_count": idea.upvotes_count,
                    "downvotes_count": idea.downvotes_count,
                }
            )
    else:
        vote = Vote(user_id=user.id, idea_id=idea_id, value=direction)
        db.session.add(vote)
        db.session.flush()
        idea.update_vote_counts()
        db.session.commit()
        return api_ok(
            {
                "message": f"Vote recorded: {'upvote' if direction == 1 else 'downvote'}.",
                "user_vote": direction,
                "current_user_vote": direction,
                "net_votes": idea.net_score,
                "upvotes_count": idea.upvotes_count,
                "downvotes_count": idea.downvotes_count,
            }
        )


@bp.route("/actions", methods=["GET"])
@token_required
def list_actions(user):
    """List available secondary actions for the current user/context."""
    from app.services.discovery import discover_actions

    actions = discover_actions(user)
    return api_ok({"actions": actions})


@bp.route("/discovery", methods=["GET"])
@require_permission("view_discovery")
def discovery(user):
    """Discovery endpoint: skills, guidelines, and available providers."""
    from app.services.discovery import discover

    data = discover(user)
    return api_ok(data)


@bp.route("/ideas/<uuid:idea_id>/run-full", methods=["POST"])
@token_required
def run_full_pipeline_endpoint(user, idea_id):
    from app.models import Idea, IdeaStatus
    from app.utils.decorators import _membership_allows_admin

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied
    if not _membership_allows_admin(user):
        return api_error("Admin access required.", status_code=403)
    from app.models import IdeaStatus as _IS

    if idea.status in (_IS.DROP, _IS.ARCHIVE, _IS.FREEZE):
        return api_error(
            "Full run is not available for dropped, archived, or frozen ideas.",
            status_code=400,
        )

    # Persist a PENDING row before enqueue so the Flutter shell can show a
    # status that survives navigation and refresh. The task moves it to
    # RUNNING/SUCCESS/FAILED; without this row a full run has no server-side
    # state until one of its child actions happens to create one.
    run = PromptRun(
        instance_id=idea.instance_id,
        action_type="FULL_PIPELINE",
        triggered_by="manual",
        idea_id=idea.id,
        status=PromptRunStatus.PENDING,
        job_type="ai",
    )
    db.session.add(run)
    db.session.commit()

    from app.tasks.ollama_tasks import run_full_pipeline

    try:
        task = run_full_pipeline.delay(str(idea.id), run_id=str(run.id))
    except Exception:
        run.mark_failed("Failed to enqueue full pipeline")
        db.session.commit()
        raise
    run.job_id = task.id
    db.session.commit()
    return api_accepted({"task_id": task.id, "run_id": str(run.id)})


@bp.route("/pipeline/status", methods=["GET"])
@token_required
def pipeline_status(user):
    """Compact status of active full-pipeline and release runs.

    Used by the Flutter shell's persistent status bar. Only PENDING/RUNNING
    idea runs and running/stopping releases are returned; historical runs are
    still available on Admin → Activity and the release card respectively.
    """
    from app.models import Release

    idea_rows = (
        apply_scope(
            db.session.query(PromptRun, Idea).filter(
                PromptRun.action_type == "FULL_PIPELINE",
                PromptRun.status.in_(
                    [PromptRunStatus.PENDING, PromptRunStatus.RUNNING]
                ),
            ),
            PromptRun,
        )
        .join(Idea, PromptRun.idea_id == Idea.id)
        .order_by(PromptRun.created_at.desc())
        .limit(50)
        .all()
    )
    idea_runs = [
        {
            "run_id": str(run.id),
            "idea_id": str(run.idea_id),
            "reference_code": idea.reference_code,
            "prompt_title": idea.prompt_title,
            "status": run.status.value,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
        for run, idea in idea_rows
    ]

    release_rows = (
        apply_scope(
            Release.query.filter(Release.pipeline_status.in_(["running", "stopping"])),
            Release,
        )
        .order_by(Release.pipeline_started_at.desc())
        .limit(50)
        .all()
    )
    release_runs = []
    for release in release_rows:
        summary = release.pipeline_summary()
        release_runs.append(
            {
                "release_id": str(release.id),
                "parent_idea_id": str(release.parent_idea_id),
                "name": release.name,
                "status": summary["status"],
                "phase": summary["phase"],
                "error": summary["error"],
                "total": summary["total"],
                "counts": summary["counts"],
            }
        )

    return api_ok({"idea_runs": idea_runs, "release_runs": release_runs})


@bp.route("/ideas/<uuid:idea_id>/actions", methods=["POST"])
@require_permission("run_actions")
def run_action(user, idea_id):
    """Start a secondary action (PRD/Design/Build) for an idea."""
    from app.models import Idea

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    data = request.get_json() or {}
    action_type = data.get("action_type")
    if not action_type:
        return api_error("action_type is required.", status_code=400)
    from app.services.secondary_actions import is_known_action

    if not is_known_action(action_type):
        return api_error(
            "Unknown action type.",
            status_code=400,
        )
    from pydantic import ValidationError

    from app.schemas.api_schemas import ActionRequest

    try:
        ActionRequest.model_validate(data)
    except ValidationError as exc:
        return api_error(
            "Invalid action payload.", status_code=400, errors=exc.errors()
        )

    if action_type == "PRD_DOC":
        from app.models import IdeaStatus

        st = idea.status.value if hasattr(idea.status, "value") else str(idea.status)
        if st not in ("SCOPE", "MAP", "SHIP", "SCALE", "FREEZE"):
            return api_error(
                f"PRD_DOC needs the idea at Scope or later (it is in {st.title()}).",
                status_code=400,
            )
    if action_type == "PRD_DOC":
        from app.models import IdeaStatus

        st = idea.status.value if hasattr(idea.status, "value") else str(idea.status)
        if st not in ("SCOPE", "MAP", "SHIP", "SCALE", "FREEZE"):
            return api_error(
                f"PRD_DOC needs the idea at Scope or later (it is in {st.title()}).",
                status_code=400,
            )
    if action_type == "DESIGN_DOC":
        from app.models import IdeaStatus

        st = idea.status.value if hasattr(idea.status, "value") else str(idea.status)
        if st not in ("MAP", "SHIP", "SCALE", "FREEZE"):
            return api_error(
                f"DESIGN_DOC needs the idea at Map or later (it is in {st.title()}).",
                status_code=400,
            )
        from app.models import ActionType, SecondaryActionResult

        has_prd = (
            SecondaryActionResult.query.filter_by(
                idea_id=idea.id, action_type=ActionType.PRD_DOC, is_current=True
            ).first()
            is not None
        )
        if not has_prd:
            return api_error(
                "A Design needs a current Brief first. Run Brief on this idea.",
                status_code=400,
            )
    if action_type == "BUILD_CODE":
        from app.models import IdeaStatus

        st = idea.status.value if hasattr(idea.status, "value") else str(idea.status)
        if st not in ("SHIP", "SCALE"):
            return api_error(
                f"BUILD_CODE needs the idea at Ship or later (it is in {st.title()}).",
                status_code=400,
            )
        from app.models import ActionType, SecondaryActionResult

        has_design = (
            SecondaryActionResult.query.filter_by(
                idea_id=idea.id, action_type=ActionType.DESIGN_DOC, is_current=True
            ).first()
            is not None
        )
        if not has_design:
            return api_error(
                "A Build needs a current Design doc first. Run Design on this idea.",
                status_code=400,
            )

    # The frontend sometimes sends action fields at the top level of the
    # request body (executeAction spreads extra) instead of nesting them
    # under "extra". Merge top-level action fields into extra so BUILD_CODE
    # target_id, model_override, etc. are seen by _enqueue_action.
    extra = data.get("extra", {}) or {}
    for key in (
        "target_id",
        "model_override",
        "provider_override",
        "skills",
        "guidelines",
        "answers",
        "confirm_build",
        "build_stage",
    ):
        if key in data and key not in extra:
            extra[key] = data[key]
    # Validate provider_override up front so a bad value (or an
    # unconfigured OpenCode instance) fails fast with a 400 instead of a
    # queued, failing run.
    from app.models.lifecycle import ACTIONS_BLOCKED_STATES

    if idea.status in ACTIONS_BLOCKED_STATES:
        return api_error(
            "Dropped and archived ideas are read-only. Restore the idea first.",
            status_code=400,
        )
    # Stage gates are enforced here, not only in the UI: the API must not
    # queue a Build on a Spark idea, or a Build without a Design doc.
    if not _check_action_allowed(idea, action_type):
        labels = {"PRD_DOC": "Scope", "DESIGN_DOC": "Map", "BUILD_CODE": "Ship"}
        status = (
            idea.status.value if hasattr(idea.status, "value") else str(idea.status)
        )
        return api_error(
            f"{action_type} needs the idea at {labels[action_type]} or later "
            f"(it is in {status.title()}).",
            status_code=400,
        )
    if action_type == "BUILD_CODE":
        from app.models import ActionType, SecondaryActionResult

        has_design = (
            SecondaryActionResult.query.filter_by(
                idea_id=idea.id, action_type=ActionType.DESIGN_DOC, is_current=True
            ).first()
            is not None
        )
        if not has_design:
            return api_error(
                "A Build needs a current Design doc first. Run Design on this idea.",
                status_code=400,
            )

    if action_type == "BUILD_CODE":
        try:
            build_stage = int(extra.get("build_stage") or 1)
        except (TypeError, ValueError):
            return api_error("build_stage must be 1, 2 or 3.", status_code=400)
        if build_stage not in (1, 2, 3):
            return api_error("build_stage must be 1, 2 or 3.", status_code=400)
        extra["build_stage"] = build_stage

    task_id, run_id, error = _enqueue_action(idea, action_type, extra)
    if error:
        return api_error(error, status_code=400)

    return api_accepted(
        {"task_id": task_id, "run_id": run_id, "action_type": action_type}
    )


@bp.route("/ideas/<uuid:idea_id>/actions", methods=["GET"])
@token_required
def get_actions(user, idea_id):
    """List available and completed secondary actions for an idea."""
    from app.services.discovery import discover_actions

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    actions = discover_actions(user, idea)
    results = [
        a.to_dict() if hasattr(a, "to_dict") else a
        for a in SecondaryActionResult.query.filter_by(idea_id=idea.id)
        .order_by(SecondaryActionResult.executed_at.desc())
        .all()
    ]
    return api_ok({"actions": actions, "results": results})


@bp.route("/ideas/<uuid:idea_id>/actions/<uuid:run_id>/status", methods=["GET"])
@token_required
def action_run_status(user, idea_id, run_id):
    """Get the status of an in-progress secondary action run."""
    from app.models import Idea, PromptRun

    run = PromptRun.query.get_or_404(run_id)
    if str(run.idea_id) != str(idea_id):
        return api_error("Run not found for this idea.", status_code=404)
    idea = Idea.query.get(run.idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied
    return api_ok(
        {
            "status": run.status.value,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error": run.error,
            "action_type": run.action_type,
        }
    )


@bp.route("/actions/<uuid:result_id>/comments", methods=["GET"])
@token_required
def list_doc_comments(user, result_id):
    """List comments on a document result."""
    result = SecondaryActionResult.query.get_or_404(result_id)
    denied = check_access(result.idea)
    if denied is not None:
        return denied

    page = request.args.get("page", 1, type=int)
    limit = min(request.args.get("limit", 50, type=int), 100)

    from app.models import Comment

    query = (
        Comment.query.filter_by(idea_id=result.idea_id, action_result_id=result.id)
        .filter_by(parent_id=None)
        .order_by(Comment.created_at.asc())
    )
    pagination = query.paginate(page=page, per_page=limit, error_out=False)

    comments = []
    for c in pagination.items:
        if c.action_result_id is not None and str(c.action_result_id) != str(result_id):
            continue
        comments.append(
            {
                "id": str(c.id),
                "body": c.body,
                "user_id": str(c.user_id),
                "user_email": c.user.email if c.user else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "phase": c.phase,
                "is_ignored": c.is_ignored,
                "is_deleted": c.is_deleted,
                "parent_id": str(c.parent_id) if c.parent_id else None,
                "depth": c.depth,
                "action_result_id": (
                    str(c.action_result_id) if c.action_result_id else None
                ),
            }
        )

    return api_ok(
        {
            "comments": comments,
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
        }
    )


@bp.route("/actions/<uuid:result_id>/comments", methods=["POST"])
@token_required
def create_doc_comment(user, result_id):
    """Add a comment to a document result."""
    global Comment
    result = SecondaryActionResult.query.get_or_404(result_id)
    denied = check_access(result.idea)
    if denied is not None:
        return denied

    data = request.get_json() or {}
    body = (data.get("body") or data.get("message") or "").strip()
    if not body:
        return api_error("Comment body is required.", status_code=400)
    if len(body) > 2000:
        return api_error(
            "Comment body must be 2000 characters or fewer.", status_code=400
        )

    parent_id = data.get("parent_id")
    parent_comment = None
    if parent_id:
        try:
            parent_comment = Comment.query.get(uuid.UUID(str(parent_id)))
            if parent_comment is None or parent_comment.idea_id != idea_id:
                return api_error(
                    "Parent comment must belong to the same idea.", status_code=400
                )
        except (ValueError, TypeError):
            return api_error("Invalid parent_id.", status_code=400)

    comment = Comment(
        idea_id=result.idea_id,
        user_id=user.id,
        body=body,
        parent_id=parent_comment.id if parent_comment else None,
        action_result_id=result.id,
    )
    db.session.add(comment)
    db.session.commit()

    return api_created({"comment": comment.to_dict()})


@bp.route("/ideas/<uuid:idea_id>/comments", methods=["GET"])
@token_required
def list_idea_comments(user, idea_id):
    """List comments for an idea, threaded."""
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    is_admin = getattr(user, "is_site_admin", False) or getattr(user, "role", None) in (
        "ADMIN",
        "admin",
    )

    from app.models import Comment, IdeaStatus

    phase = (request.args.get("phase") or "").strip().upper() or None
    if phase is not None and phase not in [st.value for st in IdeaStatus]:
        return api_error(f"Unknown phase '{phase}'.", status_code=400)

    query = Comment.query.filter_by(idea_id=idea_id, parent_id=None)
    if phase is not None:
        query = query.filter_by(phase=phase)
    query = query.order_by(Comment.created_at.asc())
    pagination = query.paginate(page=1, per_page=100, error_out=False)

    comments = []
    for c in pagination.items:
        if c.is_ignored and not is_admin:
            continue
        # Idea-level comments have no action_result_id; doc comments belong to a document.
        if c.action_result_id is not None:
            continue
        replies = []
        for r in c.replies:
            if r.is_ignored and not is_admin:
                continue
            if r.action_result_id is not None:
                continue
            replies.append(
                r.to_dict(
                    include_flag=is_admin, author_name=r.user.email if r.user else None
                )
            )
        comments.append(
            c.to_dict(
                include_flag=is_admin,
                children=replies,
                author_name=c.user.email if c.user else None,
                action_result_id=c.action_result_id,
            )
        )

    return api_ok({"comments": comments, "total": pagination.total})


@bp.route("/ideas/<uuid:idea_id>/comments", methods=["POST"])
@token_required
def create_comment(user, idea_id):
    """Create a comment on an idea."""
    from app.models import Comment

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    data = request.get_json() or {}
    body = (data.get("body") or data.get("message") or "").strip()
    if not body:
        return api_error("Comment body is required.", status_code=400)
    if len(body) > 2000:
        return api_error(
            "Comment body must be 2000 characters or fewer.", status_code=400
        )

    parent_id = data.get("parent_id")
    parent_comment = None
    if parent_id:
        try:
            parent_comment = Comment.query.get(uuid.UUID(str(parent_id)))
            if parent_comment is None or parent_comment.idea_id != idea.id:
                return api_error(
                    "Parent comment must belong to the same idea.", status_code=400
                )
        except (ValueError, TypeError):
            return api_error("Invalid parent_id.", status_code=400)

    comment = Comment(
        idea_id=idea.id,
        user_id=user.id,
        body=body,
        parent_id=parent_id,
        # Phase = the stage the idea was in when the comment was made.
        phase=idea.status.value if hasattr(idea.status, "value") else str(idea.status),
    )
    db.session.add(comment)
    db.session.commit()

    return api_created({"comment": comment.to_dict()})


@bp.route("/comments/<uuid:comment_id>", methods=["PATCH"])
@token_required
def update_comment(user, comment_id):
    """Edit a comment (owner or admin)."""
    from app.models import Comment

    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != user.id and not _membership_allows_admin(user):
        return api_error("You can only edit your own comments.", status_code=403)
    if comment.is_deleted:
        return api_error("Deleted comments cannot be edited.", status_code=400)

    data = request.get_json() or {}
    body = (data.get("body") or data.get("message") or "").strip()
    if not body:
        return api_error("Comment body is required.", status_code=400)
    if len(body) > 2000:
        return api_error(
            "Comment body must be 2000 characters or fewer.", status_code=400
        )

    comment.body = body
    comment.is_edited = True
    comment.edited_at = datetime.now(timezone.utc)
    db.session.commit()

    return api_ok({"comment": comment.to_dict()})


@bp.route("/comments/<uuid:comment_id>", methods=["DELETE"])
@token_required
def delete_comment(user, comment_id):
    """Soft-delete a comment (owner or admin)."""
    from app.models import Comment

    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != user.id and not _membership_allows_admin(user):
        return api_error("You can only delete your own comments.", status_code=403)

    comment.is_deleted = True
    comment.deleted_at = datetime.now(timezone.utc)
    for child in Comment.query.filter_by(parent_id=comment.id).all():
        child.parent_id = comment.parent_id
    db.session.commit()

    return api_ok({"message": "Comment deleted."})


@bp.route("/ideas/<uuid:idea_id>/chat", methods=["POST"])
@token_required
def chat_with_idea(user, idea_id):
    """One prose chat turn about an idea (no idea changes)."""
    from app.models import EntitlementError
    from app.services.chat import ChatError, chat_turn
    from app.services.llm_backends import BudgetExhausted

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    if idea.instance_id is not None and not _chat_enabled_for(idea.instance_id):
        return api_error(
            "Chat is turned off for this instance. An admin can enable it in AI Settings.",
            status_code=403,
            error_code="CHAT_DISABLED",
        )

    allowed, err = _chat_gate(idea)
    if not allowed:
        return api_error(err, status_code=429)

    data = request.get_json() or {}
    body = (data.get("body") or data.get("message") or "").strip()
    if not body:
        return api_error("Message body is required.", status_code=400)
    if len(body) > 4000:
        return api_error("Message is too long (max 4000 characters).", status_code=400)
    model_override = data.get("model_override")
    if model_override and not _membership_allows_admin(user):
        return api_error("Only admins can choose a chat model.", status_code=403)

    try:
        session, reply = chat_turn(idea, user, body, model_override=model_override)
    except EntitlementError as exc:
        if exc.key == "chat":
            return api_error(str(exc), status_code=403, error_code="CHAT_DISABLED")
        return api_error(str(exc), status_code=403, error_code="NOT_ENTITLED")
    except BudgetExhausted as exc:
        retry = exc.retry_after
        return api_error(
            "The AI budget for this instance is used up. Try again later.",
            status_code=429,
            errors={"retry_after_seconds": retry} if retry else None,
        )
    except ChatError as exc:
        return api_error(str(exc), status_code=400)
    except Exception as exc:
        return api_error(_chat_provider_error(exc), status_code=500)

    return api_ok({"session_id": str(session.id), "reply": reply.to_dict()})


@bp.route("/ideas/<uuid:idea_id>/chat", methods=["GET"])
@token_required
def list_chat_sessions(user, idea_id):
    """List chat sessions for an idea."""
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    from app.models import ChatSession

    sessions = (
        ChatSession.query.filter_by(idea_id=idea_id, user_id=user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )

    return api_ok({"sessions": [s.to_dict(include_turns=True) for s in sessions]})


@bp.route("/ideas/<uuid:idea_id>/chat/iterate", methods=["POST"])
@token_required
def chat_iterate(user, idea_id):
    """Apply explicit content edits as a versioned, audited iteration."""
    from app.services.chat import ChatError, iterate_idea

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    # Only the author or an instance admin may edit an idea.
    is_owner = idea.created_by_id is not None and idea.created_by_id == user.id
    if not is_owner and not _membership_allows_admin(user):
        return api_error("You can only edit your own ideas.", status_code=403)

    data = request.get_json() or {}
    content = data.get("content")
    message = (data.get("message") or data.get("body") or "").strip() or None
    if not isinstance(content, dict):
        return api_error("content must be an object.", status_code=400)
    model_override = data.get("model_override")
    if model_override and not _membership_allows_admin(user):
        return api_error("Only admins can choose a chat model.", status_code=403)
    try:
        _session, turn = iterate_idea(
            idea,
            user,
            content,
            message=message,
            model_override=model_override,
        )
    except ChatError as exc:
        return api_error(str(exc), status_code=400)

    return api_ok(
        {
            "idea": idea.to_dict(
                user_vote=_get_user_vote(user.id, idea.id), include_content=True
            ),
            "turn": turn.to_dict(),
        }
    )


@bp.route("/ideas/<uuid:idea_id>/chat/rollback", methods=["POST"])
@token_required
def chat_rollback(user, idea_id):
    """Restore the state before an iterate turn (audited, reversible)."""
    import uuid as _uuid

    from app.services.chat import ChatError, ChatNotFoundError, rollback_turn

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    is_owner = idea.created_by_id is not None and idea.created_by_id == user.id
    if not is_owner and not _membership_allows_admin(user):
        return api_error("You can only edit your own ideas.", status_code=403)

    data = request.get_json() or {}
    raw_turn = data.get("turn_id")
    if not raw_turn:
        return api_error("turn_id is required.", status_code=400)
    try:
        turn_id = _uuid.UUID(str(raw_turn))
    except (TypeError, ValueError):
        return api_error("turn_id must be a valid id.", status_code=400)

    try:
        turn = rollback_turn(idea, user, turn_id)
    except ChatNotFoundError as exc:
        return api_error(str(exc), status_code=404)
    except ChatError as exc:
        return api_error(str(exc), status_code=400)

    return api_ok(
        {
            "idea": idea.to_dict(
                user_vote=_get_user_vote(user.id, idea.id), include_content=True
            ),
            "turn": turn.to_dict(),
        }
    )


@bp.route("/comments/<uuid:comment_id>/flag", methods=["PATCH"])
@token_required
def flag_comment(user, comment_id):
    """Ignore/unignore a comment (admin only)."""
    from app.models import Comment

    comment = Comment.query.get_or_404(comment_id)
    if not _membership_allows_admin(user):
        return api_error("Admin access required.", status_code=403)

    data = request.get_json(silent=True) or {}
    if "is_ignored" in data:
        if not isinstance(data["is_ignored"], bool):
            return api_error("is_ignored must be true or false.", status_code=400)
        new_value = data["is_ignored"]
    else:
        new_value = not comment.is_ignored
    if new_value != comment.is_ignored:
        from app.models import IdeaEdit

        db.session.add(
            IdeaEdit(
                idea_id=comment.idea_id,
                editor_id=user.id,
                instance_id=comment.instance_id,
                field=f"comment:{comment.id}:is_ignored",
                old_value=str(comment.is_ignored),
                new_value=str(new_value),
            )
        )
    comment.is_ignored = new_value
    db.session.commit()

    return api_ok({"comment": comment.to_dict(include_flag=True)})


@bp.route("/ideas/<uuid:idea_id>", methods=["PATCH"])
@token_required
def update_idea_content(user, idea_id):
    """Edit an idea's title or content (owner or admin)."""
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    # Only the author or an instance admin may edit an idea's content.
    is_owner = idea.created_by_id is not None and idea.created_by_id == user.id
    if not is_owner and not _membership_allows_admin(user):
        return api_error("You can only edit your own ideas.", status_code=403)

    data = request.get_json() or {}
    title = data.get("prompt_title")
    content = data.get("raw_content")
    structured = data.get("structured_content")

    # Reject unknown/empty payloads up front.
    if not data:
        return api_error("Nothing to update.", status_code=400)
    if "status" in data:
        return api_error("Use /status to change an idea's stage.", status_code=400)

    from app.models import IdeaEdit

    edits = []
    if title is not None:
        title = title.strip()
        if not title:
            return api_error("Title cannot be empty.", status_code=400)
        if len(title) > 200:
            return api_error("Title must be 200 characters or fewer.", status_code=400)
        if title != idea.prompt_title:
            edits.append(
                IdeaEdit(
                    idea_id=idea.id,
                    editor_id=user.id,
                    instance_id=idea.instance_id,
                    field="prompt_title",
                    old_value=idea.prompt_title,
                    new_value=title,
                )
            )
            idea.prompt_title = title
    if content is not None:
        content = content.strip()
        if not content:
            return api_error("Content cannot be empty.", status_code=400)
        if content != idea.raw_content:
            edits.append(
                IdeaEdit(
                    idea_id=idea.id,
                    editor_id=user.id,
                    instance_id=idea.instance_id,
                    field="raw_content",
                    old_value=idea.raw_content,
                    new_value=content,
                )
            )
            idea.raw_content = content
    if structured is not None:
        if not isinstance(structured, dict):
            return api_error("structured_content must be an object.", status_code=400)
        if not structured:
            return api_error("structured_content cannot be empty.", status_code=400)
        old = idea.structured_content or {}
        for key, val in structured.items():
            if key not in (
                "elevator_pitch",
                "target_audience",
                "value_proposition",
                "key_features",
                "monetization",
            ):
                return api_error(f"Unknown structured field '{key}'.", status_code=400)
            if not isinstance(val, str) or not val.strip():
                return api_error(f"{key} must be a non-empty string.", status_code=400)
            if len(val.strip()) > 500:
                return api_error(
                    f"{key} must be 500 characters or fewer.", status_code=400
                )
            if old.get(key) == val:
                continue
            edits.append(
                IdeaEdit(
                    idea_id=idea.id,
                    editor_id=user.id,
                    instance_id=idea.instance_id,
                    field=f"structured_content.{key}",
                    old_value=old.get(key),
                    new_value=val,
                )
            )
        idea.structured_content = {**old, **structured}
        if "elevator_pitch" in structured:
            idea.raw_content = structured["elevator_pitch"]
    for e in edits:
        db.session.add(e)
    idea.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return api_ok(
        {
            "idea": idea.to_dict(user_vote=_get_user_vote(user.id, idea.id)),
            "edit_history": [e.to_dict() for e in edits],
        }
    )


@bp.route("/actions/<uuid:result_id>", methods=["PATCH"])
@token_required
def edit_action_result(user, result_id):
    """Edit an existing action result document."""
    result = SecondaryActionResult.query.get_or_404(result_id)
    denied = check_access(result.idea)
    if denied is not None:
        return denied

    data = request.get_json() or {}
    result_data = data.get("result_data")
    if result_data is None and "result_data" not in data:
        # Allow other edits (none currently); fall through.
        pass
    if result_data is not None and not isinstance(result_data, dict):
        return api_error("result_data must be an object.", status_code=400)
    if result_data is not None and not result_data:
        return api_error("result_data cannot be empty.", status_code=400)
    if "result_data" not in data:
        return api_error("result_data is required.", status_code=400)

    if result_data is not None:
        from pydantic import ValidationError

        from app.models import ActionType
        from app.schemas.ollama_schemas import _ACTION_SCHEMAS

        schema = _ACTION_SCHEMAS.get(
            result.action_type.value
            if hasattr(result.action_type, "value")
            else str(result.action_type)
        )
        if schema is not None:
            try:
                schema.model_validate(result_data)
            except ValidationError as exc:
                return api_error(
                    "result_data does not match the expected schema.",
                    status_code=400,
                    errors=exc.errors(),
                )

        if result.action_type in (ActionType.PRD_DOC, ActionType.DESIGN_DOC):
            # Documents are versioned, never overwritten: keep the old row
            # (so its comment threads stay pinned) and make the edit current.
            result.is_current = False
            result = SecondaryActionResult(
                idea_id=result.idea_id,
                action_type=result.action_type,
                model_used=result.model_used,
                result_data=result_data,
                target_id=result.target_id,
                version=result.version + 1,
                is_current=True,
                edited_by_id=user.id,
            )
            db.session.add(result)
        else:
            result.result_data = result_data
    db.session.commit()

    return api_ok({"action_result": result.to_dict(), "version": result.version})


@bp.route("/ideas/<uuid:idea_id>/tests", methods=["GET"])
@token_required
def list_idea_tests(user, idea_id):
    from app.models import IdeaTest, TestStatus, TestType

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    status_filter = request.args.get("status")
    type_filter = request.args.get("type")
    q = IdeaTest.query.filter_by(idea_id=idea.id)
    if status_filter:
        try:
            q = q.filter(IdeaTest.status == TestStatus(status_filter))
        except ValueError:
            return api_error("Unknown status filter.", 400)
    if type_filter:
        try:
            q = q.filter(IdeaTest.test_type == TestType(type_filter))
        except ValueError:
            return api_error("Unknown type filter.", 400)
    rows = q.order_by(IdeaTest.created_at.asc()).all()
    return api_ok({"tests": [r.to_dict() for r in rows]})


@bp.route("/ideas/<uuid:idea_id>/tests/run", methods=["POST"])
@token_required
def run_idea_tests_endpoint(user, idea_id):
    """Kick off the build's generated test suite (or selected subset) in the background."""
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied
    from app.tasks.test_tasks import run_idea_tests

    data = request.get_json(silent=True) or {}
    selected = data.get("test_ids") or []
    if not isinstance(selected, list):
        selected = []
    selected = [str(x) for x in selected]
    async_result = run_idea_tests.apply_async(
        args=[str(idea.id), selected], queue="default"
    )
    return api_ok(
        {
            "message": "Tests started; refresh to see results.",
            "run_id": async_result.id,
        },
        202,
    )


@bp.route("/ideas/<uuid:idea_id>/tests/run-status", methods=["GET"])
@token_required
def idea_tests_run_status(user, idea_id):
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied
    from app.models import TestRun

    row = (
        TestRun.query.filter_by(idea_id=idea.id)
        .order_by(TestRun.started_at.desc())
        .first()
    )
    if row is None:
        return api_ok({"run": None})
    return api_ok({"run": row.to_dict()})


@bp.route("/ideas/<uuid:idea_id>/tests", methods=["POST"])
@token_required
def create_idea_test(user, idea_id):
    from app.models import IdeaTest, TestStatus, TestType

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return api_error("name is required.", 400)
    test_type = data.get("test_type", TestType.UNIT.value)
    try:
        test_type = TestType(test_type)
    except ValueError:
        return api_error(f"Unknown test_type {test_type!r}.", 400)
    status = data.get("status", TestStatus.NOT_RUN.value)
    try:
        status = TestStatus(status)
    except ValueError:
        return api_error(f"Unknown status {status!r}.", 400)

    coverage = data.get("coverage_pct")
    if coverage is not None:
        try:
            coverage = float(coverage)
        except (TypeError, ValueError):
            return api_error("coverage_pct must be a number.", 400)
        if coverage < 0 or coverage > 100:
            return api_error("coverage_pct must be 0-100.", 400)

    row = IdeaTest(
        idea_id=idea.id,
        instance_id=getattr(g, "instance_id", None),
        name=name,
        description=data.get("description"),
        test_type=test_type,
        status=status,
        coverage_pct=coverage,
        created_by_id=user.id,
    )
    if status != TestStatus.NOT_RUN:
        row.last_run_at = datetime.now(timezone.utc)
        row.last_run_output = data.get("last_run_output")
    db.session.add(row)
    db.session.commit()
    return api_ok({"test": row.to_dict()}, "Created.", 201)


@bp.route("/ideas/<uuid:idea_id>/tests/<uuid:test_id>", methods=["PUT", "PATCH"])
@token_required
def update_idea_test(user, idea_id, test_id):
    from app.models import IdeaTest, TestStatus, TestType

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied
    row = IdeaTest.query.filter_by(id=test_id, idea_id=idea.id).first()
    if row is None:
        return api_error("Test not found.", 404)

    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return api_error("name cannot be empty.", 400)
        row.name = name
    if "description" in data:
        row.description = data.get("description")
    if "test_type" in data:
        try:
            row.test_type = TestType(data["test_type"])
        except ValueError:
            return api_error(f"Unknown test_type {data['test_type']!r}.", 400)
    if "status" in data:
        try:
            row.status = TestStatus(data["status"])
        except ValueError:
            return api_error(f"Unknown status {data['status']!r}.", 400)
        row.last_run_at = datetime.now(timezone.utc)
    if "coverage_pct" in data:
        cov = data["coverage_pct"]
        if cov is None:
            row.coverage_pct = None
        else:
            try:
                cov = float(cov)
            except (TypeError, ValueError):
                return api_error("coverage_pct must be a number.", 400)
            if cov < 0 or cov > 100:
                return api_error("coverage_pct must be 0-100.", 400)
            row.coverage_pct = cov
    if "last_run_output" in data:
        row.last_run_output = data.get("last_run_output")
    db.session.commit()
    return api_ok({"test": row.to_dict()})


@bp.route("/ideas/<uuid:idea_id>/tests/<uuid:test_id>", methods=["DELETE"])
@token_required
def delete_idea_test(user, idea_id, test_id):
    from app.models import IdeaTest

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied
    row = IdeaTest.query.filter_by(id=test_id, idea_id=idea.id).first()
    if row is None:
        return api_error("Test not found.", 404)
    db.session.delete(row)
    db.session.commit()
    return api_ok({"message": "Deleted."})


@bp.route("/ideas/<uuid:idea_id>/tests/summary", methods=["GET"])
@token_required
def idea_tests_summary(user, idea_id):
    from app.models import IdeaTest, TestStatus

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    rows = IdeaTest.query.filter_by(idea_id=idea.id).all()
    counts = {s.value: 0 for s in TestStatus}
    for r in rows:
        counts[r.status.value] += 1
    coverages = [r.coverage_pct for r in rows if r.coverage_pct is not None]
    return api_ok(
        {
            "total": len(rows),
            "counts": counts,
            "coverage_pct": (sum(coverages) / len(coverages)) if coverages else None,
            "last_run_at": (
                max(
                    (r.last_run_at for r in rows if r.last_run_at), default=None
                ).isoformat()
                if any(r.last_run_at for r in rows)
                else None
            ),
        }
    )


@bp.route("/ideas/<uuid:idea_id>/tests/diagnose", methods=["POST"])
@token_required
def diagnose_idea_tests(user, idea_id):
    """Ask the local LLM to diagnose failing tests for an idea."""
    from app.models import Idea, IdeaTest, ManagedApp, TestStatus

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    failed = (
        IdeaTest.query.filter_by(idea_id=idea.id)
        .filter(IdeaTest.status == TestStatus.FAILED)
        .all()
    )
    failed_names = [r.name for r in failed]
    log_text = ""
    ma = ManagedApp.query.filter_by(idea_id=idea.id).first()
    if ma and (ma.spec or {}).get("log_path"):
        lp = (ma.spec or {}).get("log_path")
        if os.path.exists(lp):
            try:
                with open(lp, "r", errors="replace") as fh:
                    log_text = "".join(fh.readlines()[-20:])[:500]
            except OSError:
                log_text = ""

    prompt = (
        "A generated app has failing tests. "
        f"Failed tests: {', '.join(failed_names) or 'none'}. "
        "Log tail: " + (log_text or "n/a") + ". "
        "In 3-5 sentences, explain the likely root cause and concrete fix steps for a non-technical user."
    )
    try:
        from app.services.ollama_client import OllamaClient

        client = OllamaClient(timeout=60.0)
        r = client.generate_sync(
            prompt=prompt, model="llama3:8b", format=None, options={"temperature": 0.2}
        )
        diagnosis = r.get("response", "") if isinstance(r, dict) else str(r)
        if not diagnosis or diagnosis.strip() in ("{}", "{  }"):
            diagnosis = "The AI could not produce a diagnosis. Check the app log and the failing test names above."
    except Exception as exc:
        return api_ok({"diagnosis": f"Diagnosis failed: {exc}"})
    return api_ok({"diagnosis": diagnosis})
