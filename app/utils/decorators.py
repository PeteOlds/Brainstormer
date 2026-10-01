import uuid
from functools import wraps

from flask import g, jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from app.extensions import db


def _resolve_user(user_id):
    """Resolve user by UUID string."""
    # Lazy import to avoid circular imports
    from app.models import User

    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None
    return db.session.get(User, uid)


def _attach_instance_context(user):
    """Resolve (instance, role) from the JWT claim into flask.g.

    Legacy tokens without the claim stay unscoped. A claim naming an
    instance the user does not belong to is rejected (403) unless the
    user holds a site-wide grant.
    """
    from app.utils.tenancy import resolve_membership, set_rls_instance

    g.jwt_claims = get_jwt()
    try:
        instance_id, role = resolve_membership(user)
    except PermissionError:
        return (
            jsonify({"success": False, "message": "No membership for this instance."}),
            403,
        )
    g.instance_id = instance_id
    g.instance_role = role
    set_rls_instance(instance_id)
    return None


def _membership_allows_admin(user) -> bool:
    """Legacy ADMIN role or an admin membership in the request instance."""
    if user.role.value == "ADMIN":
        return True
    role = getattr(g, "instance_role", None)
    if role in ("INSTANCE_ADMIN", "SITE_ADMIN"):
        return True
    if role is None:
        # Unscoped legacy token: fall back to a site-wide grant.
        from app.utils.tenancy import is_site_admin

        return is_site_admin(user)
    return False


def token_required(fn):
    """Decorator to require valid JWT token."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = _resolve_user(user_id)
        if not user or not user.is_active:
            return (
                jsonify(
                    {"error": "Unauthorized", "message": "User not found or inactive."}
                ),
                401,
            )
        rejected = _attach_instance_context(user)
        if rejected is not None:
            return rejected
        from app.utils.tenancy import expiry_gate_rejection

        gated = expiry_gate_rejection()
        if gated is not None:
            return gated
        return fn(user, *args, **kwargs)

    return wrapper


def admin_required(fn):
    """Decorator to require admin role (legacy ADMIN or instance admin)."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = _resolve_user(user_id)
        if not user or not user.is_active:
            return (
                jsonify(
                    {"error": "Unauthorized", "message": "User not found or inactive."}
                ),
                401,
            )
        rejected = _attach_instance_context(user)
        if rejected is not None:
            return rejected
        from app.utils.tenancy import expiry_gate_rejection

        gated = expiry_gate_rejection()
        if gated is not None:
            return gated
        if not _membership_allows_admin(user):
            return (
                jsonify({"error": "Forbidden", "message": "Admin access required."}),
                403,
            )
        return fn(user, *args, **kwargs)

    return wrapper


def site_admin_required(fn):
    """Decorator to require a site-wide grant (NULL-instance SITE_ADMIN)."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = _resolve_user(user_id)
        if not user or not user.is_active:
            return (
                jsonify(
                    {"error": "Unauthorized", "message": "User not found or inactive."}
                ),
                401,
            )
        rejected = _attach_instance_context(user)
        if rejected is not None:
            return rejected
        from app.utils.tenancy import expiry_gate_rejection

        gated = expiry_gate_rejection()
        if gated is not None:
            return gated
        from app.utils.tenancy import is_site_admin

        if not is_site_admin(user):
            return (
                jsonify(
                    {"error": "Forbidden", "message": "Site admin access required."}
                ),
                403,
            )
        return fn(user, *args, **kwargs)

    return wrapper


def require_permission(perm):
    """Decorator requiring one matrix permission (Phase 9 roles).

    Legacy ADMIN users, site-wide grants, and INSTANCE_ADMIN pass
    everything; other roles pass per `ROLE_PERMISSIONS`.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = _resolve_user(user_id)
            if not user or not user.is_active:
                return (
                    jsonify(
                        {
                            "error": "Unauthorized",
                            "message": "User not found or inactive.",
                        }
                    ),
                    401,
                )
            rejected = _attach_instance_context(user)
            if rejected is not None:
                return rejected
            from app.models import has_permission

            if not has_permission(user, perm, getattr(g, "instance_id", None)):
                return (
                    jsonify(
                        {
                            "error": "Forbidden",
                            "message": f"This action requires the '{perm}' permission.",
                        }
                    ),
                    403,
                )
            return fn(user, *args, **kwargs)

        return wrapper

    return decorator
