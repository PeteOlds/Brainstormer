"""Instance scoping helpers (Phase 1).

Every request resolves `(instance_id, membership_role)` from the JWT
`instance_id` claim into `flask.g`. Tokens without the claim keep the
legacy unscoped behaviour, so existing clients and tests keep working;
full enforcement (claim required) lands with the Phase 5 switcher.

Server-side scoping here is the enforcement layer. Postgres RLS policies
(see the Phase 1 migration) are a failsafe only.
"""

import uuid
from typing import Any

from flask import g

# Write paths that stay open on expired instances (auth flows, own
# settings, social login). Everything else mutating is gated.
EXPIRY_WRITE_ALLOWLIST = (
    "/api/v1/register",
    "/api/v1/login",
    "/api/v1/refresh",
    "/api/v1/logout",
    "/api/v1/me",
    "/api/v1/me/settings",
    "/api/v1/oauth/",
)


def parse_instance_claim(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def current_instance_id() -> uuid.UUID | None:
    """Instance UUID from the request context, or None when unscoped."""
    return getattr(g, "instance_id", None)


def current_instance_role() -> str | None:
    return getattr(g, "instance_role", None)


def has_instance_column(model: Any) -> bool:
    return "instance_id" in model.__table__.columns


def apply_scope(query: Any, model: Any) -> Any:
    """Filter a query to the request instance when scoped and supported."""
    instance_id = current_instance_id()
    if instance_id is not None and has_instance_column(model):
        query = query.filter(model.instance_id == instance_id)
    return query


def check_access(obj: Any) -> Any:
    """404 tuple when obj belongs to another instance; else None."""
    instance_id = current_instance_id()
    if instance_id is None or not hasattr(obj, "instance_id"):
        return None
    obj_instance = getattr(obj, "instance_id")
    if obj_instance is not None and obj_instance != instance_id:
        from flask import jsonify

        return jsonify({"success": False, "message": "Not found."}), 404
    return None


def stamp(obj: Any) -> Any:
    """Tag a new row with the request instance when scoped."""
    instance_id = current_instance_id()
    if (
        instance_id is not None
        and hasattr(obj, "instance_id")
        and getattr(obj, "instance_id") is None
    ):
        obj.instance_id = instance_id
    return obj


def is_site_admin(user: Any) -> bool:
    """Site-wide grant (NULL-instance SITE_ADMIN membership)."""
    from app.models import Membership

    return Membership.is_site_admin(user.id)


def instance_expired(instance_id: Any) -> bool:
    """True when writes must stop: suspended status or outside [start, end].

    Dates are recorded-but-unenforced everywhere except here: an
    end_date in the past (or a not-yet-started instance) blocks writes
    while reads keep working.
    """
    if instance_id is None:
        return False
    from datetime import datetime, timezone

    from app.models import Instance
    from app.models.types import ensure_aware

    instance = Instance.query.get(instance_id)
    if instance is None:
        return False
    if (instance.status or "active") != "active":
        return True
    now = datetime.now(timezone.utc)
    if instance.start_date and ensure_aware(instance.start_date) > now:
        return True
    return bool(instance.end_date and ensure_aware(instance.end_date) < now)


def expiry_gate_rejection():
    """403 when this write targets an expired instance; else None.

    Runs after JWT verification inside the auth decorators, so the claim
    is already trusted. Auth flows and own-settings stay open.
    """
    from flask import jsonify, request

    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    instance_id = getattr(g, "instance_id", None)
    if instance_id is None:
        return None
    if any(request.path.startswith(p) for p in EXPIRY_WRITE_ALLOWLIST):
        return None
    if instance_expired(instance_id):
        return (
            jsonify(
                {
                    "error": "Forbidden",
                    "message": "This instance is expired or suspended; writes are disabled.",
                    "error_code": "INSTANCE_INACTIVE",
                }
            ),
            403,
        )
    return None


def resolve_membership(user: Any) -> tuple:
    """(instance_id, role) for the request, enforcing membership.

    Returns (None, None) for legacy unscoped tokens. Raises PermissionError
    when the token names an instance the user does not belong to (unless
    site admin).
    """
    from app.models import Membership

    claims = getattr(g, "jwt_claims", {}) or {}
    instance_id = parse_instance_claim(claims.get("instance_id"))
    if instance_id is None:
        return None, None
    if Membership.is_site_admin(user.id):
        return instance_id, "SITE_ADMIN"
    role = Membership.get_role(user.id, instance_id)
    if role is None:
        raise PermissionError("No membership for this instance.")
    return instance_id, role


def set_rls_instance(instance_id: Any) -> None:
    """Best-effort Postgres RLS context for this request/transaction.

    Never breaks a request: RLS is the failsafe, server-side scoping above
    is the enforcement. CLI and worker paths without a request simply skip
    it (policies are permissive when the setting is absent).
    """
    if instance_id is None:
        return
    try:
        from sqlalchemy import text

        from app.extensions import db

        db.session.execute(
            text("SET LOCAL app.instance_id = :iid"), {"iid": str(instance_id)}
        )
    except Exception:
        pass
