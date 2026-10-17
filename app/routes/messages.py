"""In-app messages API (Phase 4: Talk).

Users message instance admins (feedback); admins message members or
forward to the site admin. Read timestamps drive the unread badge.
"""

import uuid
from datetime import datetime, timezone

from flask import Blueprint, request

from app.extensions import db, limiter
from app.models import Comment, Idea, Membership, Message, User
from app.utils.decorators import token_required
from app.utils.responses import api_created, api_error, api_ok
from app.utils.tenancy import (
    apply_scope,
    check_access,
    current_instance_id,
    current_instance_role,
    stamp,
)

bp = Blueprint("messages", __name__)


def _base_url():
    from flask import current_app

    return current_app.config.get("APP_BASE_URL", "") or request.host_url.rstrip("/")


def _can_message(sender, recipient_id) -> str | None:
    """None when allowed, else a plain-language reason."""
    from app.models import has_permission

    instance_id = current_instance_id()
    # Admins (legacy, site, instance) may message any member.
    if sender.role.value == "ADMIN":
        return None
    if Membership.is_site_admin(sender.id):
        return None
    if current_instance_role() in ("INSTANCE_ADMIN", "SITE_ADMIN"):
        return None
    if has_permission(sender, "manage_members", instance_id):
        return None
    # Normal users may only message instance admins.
    if instance_id is None:
        return "You can message an admin once you join an instance."
    role = Membership.get_role(recipient_id, instance_id)
    if role in ("INSTANCE_ADMIN", "SITE_ADMIN"):
        return None
    return "You can only message an admin of this instance."


@bp.route("/messages/admins", methods=["GET"])
@token_required
def list_admins(user):
    """Recipients the caller may message: admins for everyone, all members for admins."""
    from app.models import Membership

    instance_id = current_instance_id()
    admins = []
    seen = set()
    # Is the caller an admin (site, instance, legacy, or manage_members)?
    caller_is_admin = (
        user.role.value == "ADMIN"
        or Membership.is_site_admin(user.id)
        or current_instance_role() in ("INSTANCE_ADMIN", "SITE_ADMIN")
    )
    if caller_is_admin:
        # Admins may message any active member (and site admins).
        if instance_id is not None:
            for m in Membership.query.filter_by(instance_id=instance_id).all():
                if m.user_id not in seen:
                    u = User.query.get(m.user_id)
                    if u is not None and u.is_active and u.id != user.id:
                        seen.add(u.id)
                        admins.append(
                            {
                                "id": str(u.id),
                                "name": u.name,
                                "email": u.email,
                                "role": m.role,
                                "is_admin": m.role in ("INSTANCE_ADMIN", "SITE_ADMIN"),
                            }
                        )
        for u in User.query.filter_by(role="ADMIN", is_active=True).all():
            if u.id != user.id and u.id not in seen:
                seen.add(u.id)
                admins.append(
                    {
                        "id": str(u.id),
                        "name": u.name,
                        "email": u.email,
                        "role": "ADMIN",
                        "is_admin": True,
                    }
                )
    else:
        # Normal users may only message instance admins.
        if instance_id is not None:
            for m in Membership.query.filter_by(instance_id=instance_id).all():
                if m.role in ("INSTANCE_ADMIN", "SITE_ADMIN") and m.user_id not in seen:
                    u = User.query.get(m.user_id)
                    if u is not None and u.is_active and u.id != user.id:
                        seen.add(u.id)
                        admins.append(
                            {
                                "id": str(u.id),
                                "name": u.name,
                                "email": u.email,
                                "role": m.role,
                                "is_admin": True,
                            }
                        )
        for u in User.query.filter_by(role="ADMIN", is_active=True).all():
            if u.id != user.id and u.id not in seen:
                seen.add(u.id)
                admins.append(
                    {
                        "id": str(u.id),
                        "name": u.name,
                        "email": u.email,
                        "role": "ADMIN",
                        "is_admin": True,
                    }
                )
    return api_ok({"admins": admins})


@bp.route("/messages", methods=["GET"])
@token_required
def list_messages(user):
    """Inbox (received) + sent, newest first, server-side paginated."""
    page = request.args.get("page", 1, type=int)
    limit = min(request.args.get("limit", 20, type=int), 100)
    box = (request.args.get("box") or "all").strip().lower()

    query = apply_scope(Message.query, Message)
    if box == "inbox":
        query = query.filter(Message.recipient_id == user.id)
    elif box == "sent":
        query = query.filter(Message.sender_id == user.id)
    else:
        query = query.filter(
            (Message.recipient_id == user.id) | (Message.sender_id == user.id)
        )
    query = query.order_by(Message.created_at.desc())
    pagination = query.paginate(page=page, per_page=limit, error_out=False)
    base = _base_url()
    return api_ok(
        {
            "messages": [m.to_dict(base_url=base) for m in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
        }
    )


@bp.route("/messages/unread-count", methods=["GET"])
@token_required
def unread_count(user):
    """Unread inbox count for the homepage badge."""
    from app.utils.tenancy import current_instance_id

    iid = current_instance_id()
    query = apply_scope(Message.query, Message).filter(
        Message.recipient_id == user.id, Message.read_at.is_(None)
    )
    return api_ok({"unread": query.count()})


@bp.route("/messages", methods=["POST"])
@token_required
def send_message(user):
    """Send a message (users → admins; admins → any member)."""
    data = request.get_json(silent=True) or {}
    body = (data.get("body") or "").strip()
    if not body:
        return api_error("Message text is required.", status_code=400)
    if len(body) > 2000:
        return api_error("Messages must be 2000 characters or fewer.", status_code=400)
    try:
        recipient_id = uuid.UUID(str(data.get("recipient_id") or ""))
    except (ValueError, TypeError, AttributeError):
        return api_error("recipient_id is required.", status_code=400)
    recipient = User.query.get(recipient_id)
    if recipient is None or not recipient.is_active:
        return api_error("Recipient not found.", status_code=404)
    if recipient.id == user.id:
        return api_error("You cannot message yourself.", status_code=400)
    denied = _can_message(user, recipient.id)
    if denied is not None:
        return api_error(denied, status_code=403)

    idea_id = comment_id = None
    if data.get("idea_id"):
        try:
            idea_id = uuid.UUID(str(data["idea_id"]))
        except (ValueError, TypeError):
            return api_error("Invalid idea_id.", status_code=400)
        idea = Idea.query.get(idea_id)
        if idea is None:
            return api_error("Idea not found.", status_code=404)
        if check_access(idea) is not None:
            return api_error("Idea not found.", status_code=404)
    if data.get("comment_id"):
        try:
            comment_id = uuid.UUID(str(data["comment_id"]))
        except (ValueError, TypeError):
            return api_error("Invalid comment_id.", status_code=400)
        comment = Comment.query.get(comment_id)
        if comment is None:
            return api_error("Comment not found.", status_code=404)
        if check_access(comment) is not None:
            return api_error("Comment not found.", status_code=404)
        idea_id = comment.idea_id

    msg = Message(
        sender_id=user.id,
        recipient_id=recipient.id,
        body=body,
        idea_id=idea_id,
        comment_id=comment_id,
    )
    stamp(msg)
    if msg.instance_id is None and idea_id is not None:
        idea = Idea.query.get(idea_id)
        if idea is not None:
            msg.instance_id = idea.instance_id
    db.session.add(msg)
    db.session.commit()
    # Slack bridge (two-way): mirror outbound and let replies come back.
    try:
        from app.services.message_slack import mirror_message_to_slack

        mirror_message_to_slack(msg, app_base_url=_base_url())
    except Exception:
        pass  # Slack is optional; never break messaging.
    return api_created({"message": msg.to_dict(base_url=_base_url())})


@bp.route("/messages/<uuid:message_id>/read", methods=["PATCH"])
@token_required
def mark_read(user, message_id):
    """Record the read timestamp (recipient only)."""
    msg = Message.query.get_or_404(message_id)
    denied = check_access(msg)
    if denied is not None:
        return denied
    if msg.recipient_id != user.id:
        return api_error("Only the recipient can mark this read.", status_code=403)
    if msg.read_at is None:
        msg.read_at = datetime.now(timezone.utc)
        db.session.commit()
    return api_ok({"message": msg.to_dict(base_url=_base_url())})


@bp.route("/messages/<uuid:message_id>", methods=["DELETE"])
@token_required
def delete_message(user, message_id):
    """Delete own sent message, or any message as an admin."""
    from app.models import has_permission
    from flask import g

    msg = Message.query.get_or_404(message_id)
    denied = check_access(msg)
    if denied is not None:
        return denied
    if (
        msg.sender_id != user.id
        and user.role.value != "ADMIN"
        and not has_permission(user, "manage_members", getattr(g, "instance_id", None))
    ):
        return api_error("Not permitted.", status_code=403)
    db.session.delete(msg)
    db.session.commit()
    return api_ok({"deleted": str(message_id)})
