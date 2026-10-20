import json
import random
import string
import uuid
from datetime import datetime, timezone

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import asc, desc, func, or_

from app.extensions import db, limiter
from app.models import (
    Comment,
    Idea,
    IdeaEdit,
    IdeaStatusHistory,
    SecondaryActionResult,
    User,
    Vote,
)
from app.models.enums import IdeaStatus
from app.utils.decorators import (
    admin_required,
    _membership_allows_admin,
    require_permission,
    token_required,
)
from app.utils.responses import api_created, api_error, api_ok
from app.utils.tenancy import apply_scope, check_access, current_instance_role, stamp
from flask_limiter.util import get_remote_address

bp = Blueprint("ideas", __name__)


def _get_user_vote(user_id: uuid.UUID, idea_id: uuid.UUID) -> int | None:
    """Get user's vote on an idea (1, -1, or None)."""
    vote = Vote.query.filter_by(user_id=user_id, idea_id=idea_id).first()
    return vote.value if vote else None


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
    for idea in pagination.items:
        user_vote = _get_user_vote(user.id, idea.id)
        ideas_data.append(idea.to_dict(user_vote=user_vote))

    return api_ok(
        {
            "ideas": ideas_data,
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
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

    prompt_title = (data.get("prompt_title") or "").strip()
    raw_content = (data.get("raw_content") or "").strip()
    structured_content = data.get("structured_content")

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
    )
    stamp(idea)

    db.session.add(idea)
    db.session.commit()

    return api_created(idea.to_dict(user_vote=None))


@bp.route("/ideas/<uuid:idea_id>/similar", methods=["GET"])
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

    return api_ok({"idea": idea.to_dict(user_vote=user.id), "parent": parent_context_data})


@bp.route("/ideas/<uuid:idea_id>/status", methods=["PATCH"])
@token_required
def update_idea_status(user, idea_id):
    """Move an idea to a new lifecycle stage (admin/member gated)."""
    from app.utils.decorators import _membership_allows_admin

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
    idea.status = IdeaStatus[new_status]

    # Record status transition
    from app.models import IdeaStatusHistory

    history = IdeaStatusHistory(
        idea_id=idea.id,
        from_status=old_status,
        to_status=idea.status,
        changed_by_id=user.id,
    )
    db.session.add(history)
    db.session.commit()

    return api_ok(
        {
            "idea": idea.to_dict(user_vote=user.id),
            "previous_status": old_status.value,
            "new_status": idea.status.value,
        }
    )


def _maybe_push_on_scale(idea):
    """Auto-push to GitHub when an idea enters Scale, if GitHub is configured."""
    from app.models import InstanceGitHubConfig

    if idea.status.value != "SCALE" or not idea.instance_id:
        return

    from app.models import InstanceGitHubConfig

    config = (
        InstanceGitHubConfig.query.filter_by(instance_id=idea.instance_id).first()
    )
    if not config or not config.pat:
        return

    from app.tasks.github_tasks import push_release_to_github

    # Enqueue as a one-off "release" for this idea
    push_release_to_github.delay(f"idea:{idea.id}")


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

    moved = 0
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
        idea.status = new_status

        # Record status transition
        from app.models import IdeaStatusHistory

        history = IdeaStatusHistory(
            idea_id=idea.id,
            from_status=old_status,
            to_status=new_status,
            changed_by_id=user.id,
        )
        db.session.add(history)
        moved += 1

    db.session.commit()
    return api_ok({"moved": moved, "status": new_status.value})


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
        return api_error("direction must be 1 (upvote) or -1 (downvote).", status_code=400)

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    existing = Vote.query.filter_by(user_id=user.id, idea_id=idea_id).first()
    if existing:
        if existing.value == direction:
            # Toggling off same direction = remove vote
            db.session.delete(existing)
            db.session.commit()
            return api_ok({"message": "Vote removed.", "user_vote": 0})
        else:
            # Switching direction
            existing.value = direction
            db.session.commit()
            return api_ok(
                {
                    "message": f"Vote changed to {'upvote' if direction == 1 else 'downvote'}.",
                    "user_vote": direction,
                    "net_votes": idea.net_score,
                    "upvotes_count": idea.upvotes_count,
                    "downvotes_count": idea.downvotes_count,
                }
            )
    else:
        vote = Vote(user_id=user.id, idea_id=idea_id, value=direction)
        db.session.add(vote)
        db.session.commit()
        return api_ok(
            {
                "message": f"Vote recorded: {'upvote' if direction == 1 else 'downvote'}.",
                "user_vote": direction,
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
@token_required
def discovery(user):
    """Discovery endpoint: skills, guidelines, and available providers."""
    from app.services.discovery import discover

    data = discover(user)
    return api_ok(data)


def _child_default_target(idea):
    """Default build target for a child idea (its parent's release target if any)."""
    if not idea.parent_id:
        return None
    parent = Idea.query.get(idea.parent_id)
    if parent and parent.release_id:
        from app.models import InstanceBuildTarget

        return InstanceBuildTarget.query.filter_by(
            instance_id=parent.instance_id,
            name=parent.release.name,
        ).first()
    return None


def _resolve_build_target(idea, target_id):
    """Resolve a build target for an idea (from release or explicit target)."""
    from app.models import InstanceBuildTarget

    if target_id:
        try:
            return InstanceBuildTarget.query.get(uuid.UUID(str(target_id)))
        except (ValueError, TypeError):
            return None
    # Fall back to the idea's release target
    if idea.release_id:
        from app.models import Release

        release = Release.query.get(idea.release_id)
        if release:
            return InstanceBuildTarget.query.filter_by(
                instance_id=release.instance_id, name=release.name
            ).first()
    return None


def _check_action_allowed(idea, action_type):
    """Check if a secondary action is allowed for this idea in its current state."""
    from app.models import IdeaStatus

    st = idea.status
    if action_type == "PRD_DOC":
        return st not in (IdeaStatus.SPARK, IdeaStatus.DROP, IdeaStatus.ARCHIVE)
    if action_type == "DESIGN_DOC":
        return st in (IdeaStatus.MAP, IdeaStatus.SHIP, IdeaStatus.SCALE, IdeaStatus.FREEZE)
    if action_type == "BUILD_CODE":
        return st in (IdeaStatus.SHIP, IdeaStatus.SCALE)
    return True


def _enqueue_action(idea, action_type, extra=None):
    """Enqueue a secondary action task."""
    from app.tasks.ollama_tasks import run_secondary_action

    from app.services.action_context import build_idea_context

    context = build_idea_context(idea)
    if action_type == "BUILD_CODE" and not extra.get("target_id"):
        target = _resolve_build_target(idea, extra.get("target_id"))
        if not target:
            return None, "No build target available for this idea."
        extra["target_id"] = str(target.id)

    return run_secondary_action.delay(
        idea_id=str(idea.id),
        action_type=action_type,
        extra=extra or {},
    )


@bp.route("/ideas/<uuid:idea_id>/actions", methods=["POST"])
@token_required
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
    if action_type not in ("PRD_DOC", "DESIGN_DOC", "BUILD_CODE"):
        return api_error(
            "action_type must be PRD_DOC, DESIGN_DOC, or BUILD_CODE.",
            status_code=400,
        )

    extra = data.get("extra", {}) or {}
    task_id, error = _enqueue_action(idea, action_type, extra)
    if error:
        return api_error(error, status_code=400)

    return api_ok({"task_id": task_id, "action_type": action_type})


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
    return api_ok({"actions": actions})


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
        Comment.query.filter_by(
            idea_id=result.idea_id, action_result_id=result.id
        )
        .filter_by(parent_id=None)
        .order_by(Comment.created_at.asc())
    )
    pagination = query.paginate(page=page, per_page=limit, error_out=False)

    comments = []
    for c in pagination.items:
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
    body = (data.get("body") or "").strip()
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
                return api_error("Parent comment not found.", status_code=404)
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
    """List comments for an idea, threaded."""
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    page = request.args.get("page", 1, type=int)
    limit = min(request.args.get("limit", 50, type=int), 100)
    phase = request.args.get("phase")

    from app.models import Comment

    query = Comment.query.filter_by(idea_id=idea_id, parent_id=None).order_by(
        Comment.created_at.asc()
    )
    if phase:
        query = query.filter_by(phase=phase)
    pagination = query.paginate(page=page, per_page=limit, error_out=False)

    comments = []
    for c in pagination.items:
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
    body = (data.get("body") or "").strip()
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
                return api_error("Parent comment not found.", status_code=404)
        except (ValueError, TypeError):
            return api_error("Invalid parent_id.", status_code=400)

    comment = Comment(
        idea_id=idea.id,
        user_id=user.id,
        body=body,
        parent_id=parent_id,
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
    body = (data.get("body") or "").strip()
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
    db.session.commit()

    return api_ok({"message": "Comment deleted."})


def _chat_rate_key():
    """Rate-limit key for chat: per user per idea."""
    return f"chat:{get_jwt_identity()}"


def _chat_gate(idea):
    """Check chat rate limits and return (allowed, error_message_or_None).

    Rate limit: 3 messages per minute per idea per user. Fails open if Redis
    is unavailable.
    """
    from app.extensions import redis_client

    key = f"chat:{get_jwt_identity()}:{idea.id}"
    try:
        current = redis_client.get(key)
    except Exception:
        # Redis unavailable: fail open
        return True, None
    if current:
        count = int(current)
        limit = 3
        if count >= limit:
            return False, "Rate limit exceeded. Please wait before sending another message."
    return True, None


def _chat_provider_error(err):
    """Format a provider error into a user-friendly message."""
    msg = str(err)
    if "timeout" in msg.lower():
        return "The AI provider took too long to respond. Please try again."
    if "rate limit" in msg.lower():
        return "The AI provider is rate-limited. Please try again shortly."
    if "connection" in msg.lower():
        return "Cannot connect to the AI provider. Please check your connection."
    return f"AI error: {msg}"


@bp.route("/ideas/<uuid:idea_id>/chat", methods=["POST"])
@token_required
def chat_with_idea(user, idea_id):
    """Send a chat message about an idea (prose turn)."""
    from app.services.ollama_client import OllamaClient
    from app.services.action_context import build_idea_context

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    allowed, err = _chat_gate(idea)
    if not allowed:
        return api_error(err, status_code=429)

    data = request.get_json() or {}
    body = (data.get("body") or "").strip()
    if not body:
        return api_error("Message body is required.", status_code=400)

    context = build_idea_context(idea)
    context["user_message"] = body

    from app.services.ollama_client import OllamaClient

    client = OllamaClient()
    try:
        result = client.generate(
            prompt=f"Context: {context['context']}\n\nUser: {body}\nAssistant:",
            model=idea.instance.ai_config.provider if idea.instance and idea.instance.ai_config else "ollama",
        )
    except Exception as e:
        return api_error(_chat_provider_error(err), status_code=500)

    comment = Comment(
        idea_id=idea.id,
        user_id=user.id,
        body=body,
    )
    db.session.add(comment)
    db.session.commit()

    ai_response = result.get("response", "").strip()
    ai_comment = Comment(
        idea_id=idea.id,
        user_id=None,  # AI-generated
        body=ai_response,
        is_ai_generated=True,
    )
    db.session.add(ai_comment)
    db.session.commit()

    return api_ok(
        {
            "user_comment": comment.to_dict(),
            "ai_response": ai_comment.to_dict(),
        }
    )


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

    return api_ok(
        {
            "sessions": [
                {
                    "id": str(s.id),
                    "idea_id": str(s.idea_id),
                    "phase": s.phase,
                    "model_used": s.model_used,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in sessions
            ]
        }
    )


@bp.route("/ideas/<uuid:idea_id>/chat/iterate", methods=["POST"])
@token_required
def chat_iterate(user, idea_id):
    """Iterate on an idea using AI chat (refine/expand)."""
    from app.services.ollama_client import OllamaClient
    from app.services.action_context import build_idea_context

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    allowed, err = _chat_gate(idea)
    if not allowed:
        return api_error(err, status_code=429)

    data = request.get_json() or {}
    body = (data.get("body") or "").strip()
    if not body:
        return api_error("Message body is required.", status_code=400)

    context = build_idea_context(idea)
    context["user_message"] = body

    client = OllamaClient()
    try:
        result = client.generate(
            prompt=f"Context: {context['context']}\n\nUser: {body}\nAssistant:",
            model=idea.instance.ai_config.provider if idea.instance and idea.instance.ai_config else "ollama",
        )
    except Exception as e:
        return api_error(_chat_provider_error(err), status_code=500)

    ai_response = result.get("response", "").strip()

    comment = Comment(
        idea_id=idea.id,
        user_id=user.id,
        body=body,
    )
    db.session.add(comment)
    db.session.commit()

    ai_comment = Comment(
        idea_id=idea.id,
        user_id=None,
        body=ai_response,
        is_ai_generated=True,
    )
    db.session.add(ai_comment)
    db.session.commit()

    return api_ok(
        {
            "user_comment": comment.to_dict(),
            "ai_response": ai_comment.to_dict(),
        }
    )


@bp.route("/ideas/<uuid:idea_id>/chat/rollback", methods=["POST"])
@token_required
def chat_rollback(user, idea_id):
    """Rollback an idea to a previous version via chat."""
    from app.services.ollama_client import OllamaClient

    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    data = request.get_json() or {}
    version = data.get("version")
    if not version:
        return api_error("Version is required.", status_code=400)

    try:
        version_num = int(version)
    except (TypeError, ValueError):
        return api_error("Version must be an integer.", status_code=400)

    from app.models import IdeaEdit

    edit = (
        IdeaEdit.query.filter_by(idea_id=idea.id, version=version_num).first()
    )
    if not edit:
        return api_error(f"Version {version} not found for this idea.", status_code=404)

    idea.raw_content = edit.content_before
    idea.structured_content = None
    idea.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return api_ok({"message": f"Rolled back to version {version}."})


@bp.route("/ideas/<uuid:idea_id>/comments/<uuid:comment_id>/flag", methods=["PATCH"])
@token_required
def flag_comment(user, comment_id):
    """Ignore/unignore a comment (admin only)."""
    from app.models import Comment

    comment = Comment.query.get_or_404(comment_id)
    if not _membership_allows_admin(user):
        return api_error("Admin access required.", status_code=403)

    comment.is_ignored = not comment.is_ignored
    db.session.commit()

    return api_ok({"comment": comment.to_dict()})


@bp.route("/ideas/<uuid:idea_id>", methods=["PATCH"])
@token_required
def update_idea_content(user, idea_id):
    """Edit an idea's title or content (owner or admin)."""
    idea = Idea.query.get_or_404(idea_id)
    denied = check_access(idea)
    if denied is not None:
        return denied

    data = request.get_json() or {}
    title = data.get("prompt_title")
    content = data.get("raw_content")

    if title is not None:
        title = title.strip()
        if not title:
            return api_error("Title cannot be empty.", status_code=400)
        if len(title) > 200:
            return api_error("Title must be 200 characters or fewer.", status_code=400)
        idea.prompt_title = title

    if content is not None:
        content = content.strip()
        if not content:
            return api_error("Content cannot be empty.", status_code=400)
        idea.raw_content = content

    idea.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return api_ok({"idea": idea.to_dict(user_vote=user.id)})


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
    if result_data is not None and not isinstance(result_data, dict):
        return api_error("result_data must be an object.", status_code=400)

    if result_data is not None:
        result.result_data = result_data
    db.session.commit()

    return api_ok({"action_result": result.to_dict()})
