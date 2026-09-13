from flask import Blueprint, request
from sqlalchemy import func, desc, asc
import uuid

from app.extensions import db
from app.models import Idea, Vote, SecondaryActionResult, IdeaStatusHistory, User
from app.utils.decorators import token_required, admin_required
from app.utils.responses import api_ok, api_error, api_created

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
    prompt_config_id = request.args.get("prompt_config_id", type=lambda x: uuid.UUID(x) if x else None)
    model = request.args.get("model")

    query = Idea.query

    if status and status.upper() != 'ACTIVE_ONLY':
        query = query.filter(Idea.status == status.upper())
    elif status and status.upper() == 'ACTIVE_ONLY':
        # ACTIVE_ONLY is a frontend-only filter - exclude DISCARDED ideas
        query = query.filter(Idea.status != 'DISCARDED')
    if prompt_config_id:
        query = query.filter(Idea.prompt_config_id == prompt_config_id)
    if model:
        from app.models import PromptConfig
        query = query.join(PromptConfig, Idea.prompt_config_id == PromptConfig.id).filter(
            PromptConfig.model_name == model)

    # Sorting
    if sort_by == "votes":
        query = query.order_by(desc(Idea.net_score), desc(Idea.created_at))
    elif sort_by == "created_at":
        query = query.order_by(desc(Idea.created_at))
    else:
        query = query.order_by(desc(Idea.created_at))

    pagination = query.paginate(page=page, per_page=limit, error_out=False)

    ideas_data = []
    for idea in pagination.items:
        user_vote = _get_user_vote(user.id, idea.id)
        ideas_data.append(idea.to_dict(user_vote=user_vote))

    return api_ok({
        "ideas": ideas_data,
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    })


@bp.route("/ideas/<uuid:idea_id>", methods=["GET"])
@token_required
def get_idea(user, idea_id):
    """Get full idea details with action history."""
    idea = Idea.query.get_or_404(idea_id)
    user_vote = _get_user_vote(user.id, idea.id)

    # Get action results
    actions = SecondaryActionResult.query.filter_by(idea_id=idea_id).order_by(SecondaryActionResult.executed_at).all()

    payload = {
        "idea": idea.to_dict(include_content=True, user_vote=user_vote),
        "actions": [a.to_dict() for a in actions],
    }
    if user.role.value == "ADMIN":
        # Generation duration is admin-only: how long the linked run took.
        from app.models import PromptRun, PromptRunStatus
        run = (PromptRun.query.filter_by(idea_id=idea.id, status=PromptRunStatus.SUCCESS)
               .order_by(PromptRun.finished_at.desc()).first())
        payload["generation_seconds"] = run.duration_seconds if run else None

    return api_ok(payload)


@bp.route("/ideas/<uuid:idea_id>/status", methods=["PATCH"])
@admin_required
def update_idea_status(user, idea_id):
    """Update idea status (Admin only)."""
    idea = Idea.query.get_or_404(idea_id)
    data = request.get_json() or {}

    new_status = data.get("status")
    if not new_status:
        return api_error("Missing required field: status", status_code=400)

    if new_status.upper() == 'ACTIVE_ONLY':
        return api_error("ACTIVE_ONLY is not a valid status value", status_code=400)
    
    try:
        from app.models import IdeaStatus
        new_status_enum = IdeaStatus[new_status.upper()]
    except KeyError:
        return api_error(f"Invalid status: {new_status}", status_code=400)

    old_status = idea.status
    if old_status == new_status_enum:
        return api_ok(idea.to_dict(user_vote=_get_user_vote(user.id, idea.id)))

    # Update status
    idea.status = new_status_enum

    # Create history record
    history = IdeaStatusHistory(
        idea_id=idea.id,
        changed_by_id=user.id,
        old_status=old_status,
        new_status=new_status_enum,
    )
    db.session.add(history)
    db.session.commit()

    return api_ok(idea.to_dict(user_vote=_get_user_vote(user.id, idea.id)))


@bp.route("/ideas/<uuid:idea_id>/vote", methods=["POST"])
@token_required
def vote_idea(user, idea_id):
    """Cast or update vote on an idea."""
    idea = Idea.query.get_or_404(idea_id)
    data = request.get_json() or {}

    direction = data.get("direction")
    if direction not in (1, -1):
        return api_error("Invalid direction. Must be 1 (upvote) or -1 (downvote)", status_code=400)

    # Check existing vote
    existing_vote = Vote.query.filter_by(user_id=user.id, idea_id=idea_id).first()

    if existing_vote:
        if existing_vote.value == direction:
            # Same vote - remove it (toggle off)
            db.session.delete(existing_vote)
        else:
            # Flip vote
            existing_vote.value = direction
    else:
        # New vote
        vote = Vote(user_id=user.id, idea_id=idea_id, value=direction)
        db.session.add(vote)

    # Update cached counts
    idea.update_vote_counts()
    db.session.commit()

    user_vote = _get_user_vote(user.id, idea_id)
    return api_ok({
        "idea_id": str(idea_id),
        "net_votes": idea.net_score,
        "current_user_vote": user_vote,
    })


@bp.route("/actions", methods=["GET"])
@token_required
def list_actions(user):
    """List available follow-up AI actions (driven by the registry)."""
    from app.services.secondary_actions import list_actions as registry_actions
    return api_ok({"actions": registry_actions()})


@bp.route("/ideas/<uuid:idea_id>/actions", methods=["POST"])
@admin_required
def run_action(user, idea_id):
    """Run a secondary action on an idea (Admin only)."""
    from app.services.secondary_actions import get_action, list_actions as registry_actions

    idea = Idea.query.get_or_404(idea_id)
    data = request.get_json() or {}

    action_type = data.get("action_type")
    if not action_type:
        return api_error("Missing required field: action_type", status_code=400)
    entry = get_action(action_type)
    if entry is None:
        known = [a["key"] for a in registry_actions()]
        return api_error(f"Unknown action_type: {action_type}. Known: {', '.join(known)}", status_code=400)
    action_type = entry["key"]

    model_override = data.get("model_override")

    # Record the run first so it shows as pending immediately.
    from app.models import PromptRun
    run = PromptRun(prompt_config_id=None, action_type=action_type,
                    idea_id=idea.id, triggered_by="manual")
    db.session.add(run)
    db.session.commit()

    # Enqueue action task
    from app.tasks.ollama_tasks import run_secondary_action
    job = run_secondary_action.delay(str(idea_id), action_type, model_override,
                                     run_id=str(run.id))
    run.job_id = job.id
    db.session.commit()

    return api_ok({
        "job_id": job.id,
        "run": run.to_dict(),
        "status": "PENDING",
        "message": f"{action_type} analysis enqueued for processing.",
    }, status_code=202)


@bp.route("/ideas/<uuid:idea_id>/actions", methods=["GET"])
@token_required
def get_actions(user, idea_id):
    """Get action results for an idea."""
    idea = Idea.query.get_or_404(idea_id)
    actions = SecondaryActionResult.query.filter_by(idea_id=idea_id).order_by(SecondaryActionResult.executed_at).all()
    return api_ok({"results": [a.to_dict() for a in actions]})