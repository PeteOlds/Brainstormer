from flask import Blueprint, render_template, request, jsonify, current_app

from app.utils.decorators import admin_required
from app.utils.responses import api_ok, api_error, api_created
from sqlalchemy import func, or_
from app.extensions import db
from app.models import User, UserRole, Idea, PromptConfig


def _queue_depths():
    """Redis list lengths for the celery queues (instant, no worker needed)."""
    depths = {"ollama": None, "default": None}
    try:
        redis_client = current_app.extensions.get("redis_client")
        if redis_client is not None:
            for queue in depths:
                try:
                    depths[queue] = redis_client.llen(queue)
                except Exception:
                    pass
    except Exception:
        pass
    return depths


def _workers_alive():
    """Best-effort worker liveness via celery inspect (short timeout).

    Returns None when unreachable so the UI can show 'unknown' instead of
    hanging the page on a dead broker.
    """
    try:
        from app.tasks import celery
        inspect = celery.control.inspect(timeout=2)
        ping = inspect.ping() or {}
        return len(ping)
    except Exception:
        return None

bp = Blueprint("admin", __name__)




@bp.route("/admin", methods=["GET"])
@admin_required
def admin_dashboard(user):
    """Admin dashboard page."""
    return render_template("admin/dashboard.html", user=user, current_user=user)


@bp.route("/admin/users", methods=["GET"])
@admin_required
def admin_users(user):
    """User management page."""
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 20, type=int)
    search = request.args.get("search", "", type=str)
    
    query = User.query

    if search:
        conditions = [
            User.email.ilike(f"%{search}%"),
            User.name.ilike(f"%{search}%"),
        ]
        try:
            conditions.append(User.role == UserRole[search.upper()])
        except KeyError:
            pass
        query = query.filter(or_(*conditions))
    
    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=limit, error_out=False)
    
    return render_template("admin/users.html", user=user, current_user=user, pagination=pagination, search=search)


@bp.route("/admin/users/<uuid:user_id>", methods=["PATCH"])
@admin_required
def admin_update_user(user, user_id):
    """Update user (promote/demote, activate/deactivate)."""
    target_user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    
    if "role" in data:
        target_user.role = UserRole[data["role"].upper()]
    if "is_active" in data:
        target_user.is_active = data["is_active"]
    if "name" in data:
        target_user.name = data["name"]
    
    db.session.commit()
    return api_ok(target_user.to_dict())


@bp.route("/admin/users/<uuid:user_id>", methods=["DELETE"])
@admin_required
def admin_delete_user(user, user_id):
    """Delete a user (soft delete - deactivate)."""
    target_user = User.query.get_or_404(user_id)
    if target_user.id == user.id:
        return api_error("Cannot delete yourself", status_code=400)
    target_user.is_active = False
    db.session.commit()
    return api_ok({"message": "User deactivated successfully"})


@bp.route("/admin/users/create", methods=["POST"])
@admin_required
def admin_create_user(user):
    """Create a new user."""
    data = request.get_json() or {}
    
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")
    role = data.get("role", "USER")
    
    if not email or not password:
        return api_error("Email and password are required", status_code=400)
    
    if User.query.filter_by(email=email).first():
        return api_error("Email already exists", status_code=409)
    
    new_user = User(email=email, name=name, role=UserRole[role.upper()])
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    
    return api_created(new_user.to_dict())


@bp.route("/admin/prompts", methods=["GET"])
@admin_required
def admin_prompts(user):
    """Prompt management page.

    Reuses the main prompts list component (single source of truth)
    instead of the old static stub, which always rendered empty.
    """
    return render_template("prompts/list.html", user=user, current_user=user)

@bp.route("/admin/activity", methods=["GET"])
@admin_required
def activity_page(user):
    """Activity & performance dashboard page (Admin only)."""
    return render_template("admin/activity.html", user=user, current_user=user)


@bp.route("/admin/activity/stats", methods=["GET"])
@admin_required
def activity_stats(user):
    """Activity, performance and popularity stats for the admin dashboard."""
    from app.models import PromptRun, PromptRunStatus

    # Optional server-side run filters (?run_status=, ?model=). The stream
    # defaults to the 20 most recent runs; a filter widens the window so
    # older matching runs aren't cut off by pagination.
    status_filter = (request.args.get("run_status") or "").upper() or None
    if status_filter and status_filter not in ("PENDING", "RUNNING", "SUCCESS", "FAILED"):
        return api_error("Invalid run_status filter", status_code=400)
    model_filter = request.args.get("model") or None
    run_limit = 50 if (status_filter or model_filter) else 20

    # --- Recent runs (activity stream, generations + follow-up actions) ---
    live_statuses = [PromptRunStatus.PENDING, PromptRunStatus.RUNNING]
    recent_runs = []
    idea_ids = set()
    prompt_ids = set()
    run_query = PromptRun.query.order_by(PromptRun.created_at.desc())
    if status_filter:
        run_query = run_query.filter(PromptRun.status == status_filter)
    for run in run_query.limit(200).all():
        item = run.to_dict()
        item["prompt_title"] = run.display_title
        recent_runs.append(item)
        if run.idea_id:
            idea_ids.add(run.idea_id)
        if run.prompt_config_id:
            prompt_ids.add(run.prompt_config_id)
    idea_refs = {}
    ideas_by_id = {}
    if idea_ids:
        for idea in Idea.query.filter(Idea.id.in_(list(idea_ids))).all():
            idea_refs[str(idea.id)] = idea.reference_code
            ideas_by_id[str(idea.id)] = idea
    # Model per run (for ?model= filtering): via the run's own prompt, else
    # via the linked idea's prompt (follow-up actions).
    prompt_ids.update(
        str(i.prompt_config_id) for i in ideas_by_id.values()
        if i.prompt_config_id)
    model_by_prompt = {}
    if prompt_ids:
        for pc in PromptConfig.query.filter(
                PromptConfig.id.in_(list(prompt_ids))).all():
            model_by_prompt[str(pc.id)] = pc.model_name
    for item in recent_runs:
        model = None
        if item["prompt_config_id"] and str(item["prompt_config_id"]) in model_by_prompt:
            model = model_by_prompt[str(item["prompt_config_id"])]
        elif item["idea_id"] and str(item["idea_id"]) in ideas_by_id:
            idea = ideas_by_id[str(item["idea_id"])]
            if idea.prompt_config_id and str(idea.prompt_config_id) in model_by_prompt:
                model = model_by_prompt[str(idea.prompt_config_id)]
        item["model"] = model
    if model_filter:
        recent_runs = [r for r in recent_runs if r["model"] == model_filter]
    recent_runs = recent_runs[:run_limit]

    # Per-run timings for the model timing graph (?model= only): successful
    # runs with a measured duration, newest first.
    model_timings = []
    if model_filter:
        timing_rows = (
            db.session.query(PromptConfig.title, PromptRun.duration_seconds,
                             PromptRun.created_at)
            .join(PromptRun, PromptRun.prompt_config_id == PromptConfig.id)
            .filter(PromptConfig.model_name == model_filter,
                    PromptRun.status == "SUCCESS",
                    PromptRun.duration_seconds.isnot(None))
            .order_by(PromptRun.created_at.desc())
            .limit(20)
            .all()
        )
        model_timings = [{
            "prompt_title": title,
            "duration_seconds": round(float(dur), 1),
            "created_at": created.isoformat() if created else None,
        } for title, dur, created in timing_rows]
    for item in recent_runs:
        if item["idea_id"] and item["idea_id"] in idea_refs:
            item["idea_reference"] = idea_refs[item["idea_id"]]
            if item["action_type"]:
                item["prompt_title"] = (
                    f"{item['action_type'].title().replace('_', ' ')}"
                    f" on {idea_refs[item['idea_id']]}")

    pending_runs = []
    for run in (PromptRun.query.filter(PromptRun.status.in_(live_statuses))
                .order_by(PromptRun.created_at.desc()).limit(10).all()):
        item = run.to_dict()
        item["prompt_title"] = run.display_title
        if run.idea_id and str(run.idea_id) in idea_refs:
            item["idea_reference"] = idea_refs[str(run.idea_id)]
        pending_runs.append(item)

    # --- Performance ---
    total_runs = PromptRun.query.count()
    status_rows = (db.session.query(PromptRun.status, func.count(PromptRun.id))
                   .group_by(PromptRun.status).all())
    by_status = {"PENDING": 0, "RUNNING": 0, "SUCCESS": 0, "FAILED": 0}
    for status, count in status_rows:
        by_status[status.value] = count
    successful = by_status.get("SUCCESS", 0)
    avg_duration = db.session.query(func.avg(PromptRun.duration_seconds)).filter(
        PromptRun.duration_seconds.isnot(None)).scalar()
    per_model_rows = (
        db.session.query(PromptConfig.model_name,
                         func.count(PromptRun.id),
                         func.avg(PromptRun.duration_seconds))
        .join(PromptRun, PromptRun.prompt_config_id == PromptConfig.id)
        .group_by(PromptConfig.model_name).all()
    )
    per_model = [{"model": name or "—", "runs": count,
                  "avg_seconds": round(avg, 1) if avg is not None else None}
                 for name, count, avg in per_model_rows]
    last_failure = (PromptRun.query.filter_by(status=PromptRunStatus.FAILED)
                    .order_by(PromptRun.finished_at.desc()).first())

    # --- Popularity: ideas + votes per prompt ---
    popular_rows = (
        db.session.query(PromptConfig.id, PromptConfig.title,
                         func.count(Idea.id),
                         func.coalesce(func.sum(Idea.net_score), 0))
        .outerjoin(Idea, Idea.prompt_config_id == PromptConfig.id)
        .group_by(PromptConfig.id, PromptConfig.title)
        .order_by(func.count(Idea.id).desc()).limit(8).all()
    )
    popular_prompts = [{"id": str(pid), "title": title, "ideas": ideas, "net_votes": int(votes or 0)}
                       for pid, title, ideas, votes in popular_rows]

    # Ideas by Model (count DISTINCT ideas: the join to runs fans out
    # one row per idea x successful run, which inflated the counts).
    model_rows = (
        db.session.query(PromptConfig.model_name,
                         func.count(func.distinct(Idea.id)),
                         func.avg(PromptRun.duration_seconds))
        .outerjoin(Idea, Idea.prompt_config_id == PromptConfig.id)
        .outerjoin(PromptRun, PromptRun.prompt_config_id == PromptConfig.id)
        .filter(PromptRun.status == 'SUCCESS')
        .group_by(PromptConfig.model_name)
        .all()
    )
    ideas_by_model = [{"model": name or "—", "count": count,
                       "avg_seconds": round(float(avg), 1) if avg is not None else None}
                      for name, count, avg in model_rows]

    # Ideas by Prompt
    prompt_rows = (
        db.session.query(PromptConfig.id, PromptConfig.title,
                         func.count(Idea.id),
                         func.coalesce(func.sum(Idea.net_score), 0))
        .outerjoin(Idea, Idea.prompt_config_id == PromptConfig.id)
        .group_by(PromptConfig.id, PromptConfig.title)
        .order_by(func.count(Idea.id).desc()).limit(8).all()
    )
    ideas_by_prompt = [{"id": str(pid), "title": title, "count": count, "net_votes": int(votes or 0)}
                       for pid, title, count, votes in prompt_rows]

    # Ideas by Status (idea lifecycle states — not run outcomes).
    idea_status_rows = (db.session.query(Idea.status, func.count(Idea.id))
                        .group_by(Idea.status).all())
    ideas_by_status = {"NEW": 0, "CONSIDERATION": 0, "DISCARDED": 0}
    for status, count in idea_status_rows:
        ideas_by_status[status.value] = count

    pending_count = (PromptRun.query.filter(
        PromptRun.status.in_(live_statuses)).count())

    return api_ok({
        "recent_runs": recent_runs,
        "pending_runs": pending_runs,
        "queues": _queue_depths(),
        "workers_alive": _workers_alive(),
        "performance": {
            "total_runs": total_runs,
            "pending_count": pending_count,
            "by_status": by_status,
            "success_rate": round(successful / total_runs, 3) if total_runs else None,
            "avg_seconds": round(float(avg_duration), 1) if avg_duration is not None else None,
            "per_model": per_model,
            "last_error": last_failure.error if last_failure else None,
        },
        "popularity": {
            "prompts": popular_prompts,
        },
        "ideas_by_model": ideas_by_model,
        "ideas_by_prompt": ideas_by_prompt,
        "ideas_by_status": ideas_by_status,
        "model_timings": model_timings,
    })


@bp.route("/admin/stats", methods=["GET"])
@admin_required
def get_stats(user):
    """Get system statistics (Admin only)."""
    total_users = User.query.count()
    total_ideas = Idea.query.count()
    total_prompts = PromptConfig.query.count()
    active_prompts = PromptConfig.query.filter(PromptConfig.is_active == True).count()

    status_counts = db.session.query(
        Idea.status,
        func.count(Idea.id)
    ).group_by(Idea.status).all()

    return api_ok({
        "users": {"total": total_users},
        "ideas": {
            "total": total_ideas,
            "by_status": {status.value: count for status, count in status_counts},
        },
        "prompts": {"total": total_prompts, "active": active_prompts},
    })