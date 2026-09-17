from flask import Blueprint, request
from sqlalchemy import func, desc, asc
import json
import uuid

from app.extensions import db
from app.models import Idea, Vote, SecondaryActionResult, IdeaStatusHistory, User, Comment, IdeaEdit
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

    if status and status.upper() not in ('ACTIVE_ONLY', 'ALL'):
        query = query.filter(Idea.status == status.upper())
    elif status and status.upper() == 'ACTIVE_ONLY':
        # ACTIVE_ONLY is a frontend-only filter - exclude DISCARDED ideas
        query = query.filter(Idea.status != 'DISCARDED')
    # 'ALL' (or absent) means no status filter.
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


@bp.route("/ideas/<uuid:idea_id>/similar", methods=["GET"])
@token_required
def find_similar_ideas(user, idea_id):
    """Find ideas similar to the given idea using embedding similarity."""
    from app.services.embedding_service import get_embedding_service

    idea = Idea.query.get_or_404(idea_id)
    if not idea.embedding:
        return api_error("This idea has no embedding yet. Try again later.", status_code=404)

    threshold = request.args.get("threshold", 0.85, type=float)
    limit = request.args.get("limit", 10, type=int)

    svc = get_embedding_service()
    similar = svc.find_similar_ideas(idea.id, threshold=threshold, limit=limit)

    similar_data = []
    for similar_idea, score in similar:
        data = similar_idea.to_dict()
        data["similarity_score"] = round(score, 3)
        similar_data.append(data)

    return api_ok({
        "idea_id": str(idea_id),
        "similar_ideas": similar_data,
        "threshold": threshold,
        "count": len(similar_data),
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
        "edit_history": _edit_history(idea_id),
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

    # Rerun answers: optional list of user answers to a previous run's open
    # questions. Only PRD_DOC consumes them; ignored for other actions.
    answers = data.get("answers") or []
    if answers and not isinstance(answers, list):
        return api_error("answers must be a list of strings", status_code=400)
    answers = [str(a) for a in answers if str(a).strip()]

    # PRD_DOC reruns replace: one current PRD per idea.
    if action_type == "PRD_DOC":
        from app.models import SecondaryActionResult
        SecondaryActionResult.query.filter_by(
            idea_id=idea.id, action_type="PRD_DOC").delete()
        db.session.commit()

    # Record the run first so it shows as pending immediately.
    from app.models import PromptRun
    run = PromptRun(prompt_config_id=None, action_type=action_type,
                    idea_id=idea.id, triggered_by="manual")
    db.session.add(run)
    db.session.commit()

    # Enqueue action task
    from app.tasks.ollama_tasks import run_secondary_action
    job = run_secondary_action.delay(str(idea_id), action_type, model_override,
                                     run_id=str(run.id),
                                     extra_context={"answers": answers} if answers else None)
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

def _edit_history(idea_id):
    """Audit trail newest-first with editor names."""
    edits = (IdeaEdit.query.filter_by(idea_id=idea_id)
             .order_by(IdeaEdit.edited_at.desc()).all())
    names = {}
    editor_ids = {e.editor_id for e in edits}
    if editor_ids:
        for u in User.query.filter(User.id.in_(list(editor_ids))).all():
            names[u.id] = u.name or u.email
    return [e.to_dict(editor_name=names.get(e.editor_id, "Unknown")) for e in edits]


def _comment_tree(idea_id):
    """Nested comment tree for an idea, oldest first, with author names."""
    comments = (Comment.query.filter_by(idea_id=idea_id)
                .order_by(Comment.created_at).all())
    authors = {}
    user_ids = {c.user_id for c in comments}
    if user_ids:
        for u in User.query.filter(User.id.in_(list(user_ids))).all():
            authors[u.id] = u.name or u.email
    by_parent = {}
    for c in comments:
        by_parent.setdefault(c.parent_id, []).append(c)

    def build(node):
        return [child.to_dict(
            author_name=authors.get(child.user_id, "Unknown"),
            children=build(child),
        ) for child in by_parent.get(node.id if node else None, [])]

    return build(None)


@bp.route("/ideas/<uuid:idea_id>/comments", methods=["GET"])
@token_required
def list_comments(user, idea_id):
    """Nested comment thread for an idea."""
    Idea.query.get_or_404(idea_id)
    return api_ok({"comments": _comment_tree(idea_id)})


@bp.route("/ideas/<uuid:idea_id>/comments", methods=["POST"])
@token_required
def create_comment(user, idea_id):
    """Post a comment or a reply (parent_id must belong to the same idea)."""
    Idea.query.get_or_404(idea_id)
    data = request.get_json() or {}
    body = (data.get("body") or "").strip()
    if not body:
        return api_error("Comment body is required.", status_code=400)
    if len(body) > 2000:
        return api_error("Comment body must be 2000 characters or fewer.", status_code=400)

    parent = None
    if data.get("parent_id"):
        try:
            parent = Comment.query.get(uuid.UUID(str(data["parent_id"])))
        except (ValueError, TypeError):
            return api_error("Invalid parent_id.", status_code=400)
        if not parent or parent.idea_id != idea_id:
            return api_error("parent_id must belong to the same idea.", status_code=400)

    comment = Comment(idea_id=idea_id, user_id=user.id,
                      parent_id=parent.id if parent else None, body=body)
    db.session.add(comment)
    db.session.commit()
    return api_created({"comment": comment.to_dict(
        author_name=user.name or user.email)})


def _comment_or_403(user, comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != user.id and user.role.value != "ADMIN":
        return None, api_error("Not permitted.", status_code=403)
    return comment, None


@bp.route("/comments/<uuid:comment_id>", methods=["PATCH"])
@token_required
def update_comment(user, comment_id):
    """Edit own comment (admins may edit any). Deleted stubs stay deleted."""
    comment, err = _comment_or_403(user, comment_id)
    if err:
        return err
    if comment.is_deleted:
        return api_error("Deleted comments cannot be edited.", status_code=400)
    data = request.get_json() or {}
    body = (data.get("body") or "").strip()
    if not body:
        return api_error("Comment body is required.", status_code=400)
    if len(body) > 2000:
        return api_error("Comment body must be 2000 characters or fewer.", status_code=400)
    comment.body = body
    db.session.commit()
    return api_ok({"comment": comment.to_dict()})


@bp.route("/comments/<uuid:comment_id>", methods=["DELETE"])
@token_required
def delete_comment(user, comment_id):
    """Soft-delete: children reparent to the deleted node's parent."""
    comment, err = _comment_or_403(user, comment_id)
    if err:
        return err
    for child in Comment.query.filter_by(parent_id=comment.id).all():
        child.parent_id = comment.parent_id
    comment.is_deleted = True
    comment.body = "[deleted]"
    db.session.commit()
    return api_ok({"deleted": str(comment.id)})


EDITABLE_FIELDS = ("prompt_title", "raw_content", "structured_content")


@bp.route("/ideas/<uuid:idea_id>", methods=["PATCH"])
@admin_required
def update_idea_content(user, idea_id):
    """Edit idea content fields (Admin only). Status keeps its own endpoint."""
    idea = Idea.query.get_or_404(idea_id)
    data = request.get_json() or {}

    updates = {f: data[f] for f in EDITABLE_FIELDS if f in data}
    if not updates:
        return api_error("Nothing to update. Editable fields: prompt_title, raw_content, structured_content.", status_code=400)

    if "prompt_title" in updates:
        title = (updates["prompt_title"] or "").strip()
        if not title:
            return api_error("prompt_title must not be empty.", status_code=400)
        if len(title) > 200:
            return api_error("prompt_title must be 200 characters or fewer.", status_code=400)
        updates["prompt_title"] = title
    if "raw_content" in updates:
        body = (updates["raw_content"] or "").strip()
        if not body:
            return api_error("raw_content must not be empty.", status_code=400)
        updates["raw_content"] = body
    if "structured_content" in updates:
        sc = updates["structured_content"]
        if not isinstance(sc, dict):
            return api_error("structured_content must be an object.", status_code=400)
        allowed = {
            "elevator_pitch": 500,
            "target_audience": 300,
            "core_value_proposition": 500,
            "monetization_strategy": 300,
        }
        unknown = [k for k in sc if k not in allowed]
        if unknown:
            return api_error(f"Unknown structured fields: {', '.join(unknown)}.", status_code=400)
        cleaned = {}
        for key, cap in allowed.items():
            if key not in sc:
                continue
            val = sc[key]
            if not isinstance(val, str) or not val.strip():
                return api_error(f"{key} must be a non-empty string.", status_code=400)
            if len(val.strip()) > cap:
                return api_error(f"{key} must be {cap} characters or fewer.", status_code=400)
            cleaned[key] = val.strip()
        if not cleaned:
            return api_error("structured_content must include at least one known field.", status_code=400)
        updates["structured_content"] = cleaned

    for field, new_value in updates.items():
        if field == "structured_content":
            current = idea.structured_content
            if isinstance(current, str):
                try:
                    current = json.loads(current)
                except (ValueError, TypeError):
                    current = {}
            if not isinstance(current, dict):
                current = {}
            # Build a FRESH dict: mutating the tracked object in place makes
            # SQLAlchemy compare new-vs-mutated (equal) and skip the UPDATE.
            updated = dict(current)
            for key, val in new_value.items():
                if updated.get(key) == val:
                    continue
                db.session.add(IdeaEdit(
                    idea_id=idea.id, editor_id=user.id,
                    field=f"structured_content.{key}",
                    old_value=updated.get(key), new_value=val))
                updated[key] = val
            idea.structured_content = updated
            # Keep the rendered display in sync with the edited fields.
            idea.raw_content = json.dumps(updated)
            continue
        old_value = getattr(idea, field)
        if old_value == new_value:
            continue
        setattr(idea, field, new_value)
        db.session.add(IdeaEdit(
            idea_id=idea.id, editor_id=user.id,
            field=field, old_value=old_value, new_value=new_value))
    db.session.commit()
    return api_ok(idea.to_dict(user_vote=_get_user_vote(user.id, idea.id)))
