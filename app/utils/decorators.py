import uuid
from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
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


def token_required(fn):
    """Decorator to require valid JWT token."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = _resolve_user(user_id)
        if not user or not user.is_active:
            return jsonify({"error": "Unauthorized", "message": "User not found or inactive."}), 401
        return fn(user, *args, **kwargs)
    return wrapper


def admin_required(fn):
    """Decorator to require admin role."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = _resolve_user(user_id)
        if not user or not user.is_active:
            return jsonify({"error": "Unauthorized", "message": "User not found or inactive."}), 401
        if user.role.value != "ADMIN":
            return jsonify({"error": "Forbidden", "message": "Admin access required."}), 403
        return fn(user, *args, **kwargs)
    return wrapper