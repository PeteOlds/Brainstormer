"""Compatibility layer over flask-appkit auth with refresh token rotation."""

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from flask import current_app
from flask_appkit.auth import hash_password, verify_password


# Import the RefreshToken model lazily to avoid circular imports
def get_refresh_token_model():
    from app.models import RefreshToken

    return RefreshToken


def _access_payload(user_id, role, email, instance_id) -> tuple[dict, str]:
    """Access-token claims plus the CSRF value the cookie client must echo.

    flask_jwt_extended's cookie mode refuses state-changing requests unless
    the `csrf` claim matches the X-CSRF-TOKEN header. Tokens are minted with
    PyJWT here, so the claim has to be added by hand — without it every
    cookie-authenticated write was rejected.
    """
    access_expires = current_app.config.get(
        "JWT_ACCESS_TOKEN_EXPIRES", timedelta(minutes=15)
    )
    csrf = secrets.token_urlsafe(32)
    payload = {
        "sub": str(user_id),
        "role": role,
        "csrf": csrf,
        "exp": datetime.now(timezone.utc) + access_expires,
        "iat": datetime.now(timezone.utc),
    }
    if email:
        payload["email"] = email
    if instance_id:
        payload["instance_id"] = str(instance_id)
    return payload, csrf


def create_tokens(
    user_id: str,
    role: str = "USER",
    email: str = None,
    remember: bool = False,
    instance_id: str | None = None,
) -> dict:
    """Create access and refresh tokens for a user with refresh token rotation."""
    # Create access token with role claim using PyJWT directly
    access_payload, csrf_token = _access_payload(
        user_id, role, email, instance_id
    )
    access_token = jwt.encode(
        access_payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )

    # Create refresh token and store in database
    # Use longer expiry if remember_me is checked
    refresh_days = 30 if remember else 7
    RefreshToken = get_refresh_token_model()
    raw_refresh_token, refresh_token_obj = RefreshToken.create_token(
        user_id, expires_in_days=refresh_days
    )

    # Store in database
    from app.extensions import db

    db.session.add(refresh_token_obj)
    db.session.commit()

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh_token,
        "csrf_token": csrf_token,
    }


def decode_token(token: str) -> dict:
    """Decode a JWT token."""
    return jwt.decode(
        token,
        current_app.config["JWT_SECRET_KEY"],
        algorithms=["HS256"],
    )


def rotate_refresh_token(
    raw_refresh_token: str, instance_id: str | None = None
) -> dict | None:
    """Rotate a refresh token - revoke old and create new."""
    RefreshToken = get_refresh_token_model()
    from app.extensions import db

    # Verify the old token
    old_token = RefreshToken.verify_token(raw_refresh_token)
    if not old_token or not old_token.is_valid():
        return None

    # Revoke old token
    # Create new token
    raw_refresh_token_new, new_token_obj = RefreshToken.create_token(old_token.user_id)

    # Revoke old token, link to new
    old_token.revoke(replaced_by=new_token_obj)

    # Save new token
    from app.extensions import db

    db.session.add(new_token_obj)
    db.session.commit()

    # Create new access token
    user_id = old_token.user_id
    from app.models import User

    user = User.query.get(old_token.user_id)
    if not user:
        return None

    access_payload, csrf_token = _access_payload(
        user_id, user.role.value, user.email, instance_id
    )
    access_token = jwt.encode(
        access_payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )

    db.session.add(new_token_obj)
    db.session.commit()

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh_token_new,
        "csrf_token": csrf_token,
    }


def revoke_refresh_token(raw_refresh_token: str) -> bool:
    """Revoke one refresh token by its raw value. Returns True if revoked.

    Unknown or already-revoked tokens return False rather than raising:
    logout must stay idempotent and must not leak whether a token existed.
    """
    if not raw_refresh_token:
        return False
    RefreshToken = get_refresh_token_model()
    token_obj = RefreshToken.verify_token(raw_refresh_token)
    if token_obj is None:
        return False
    if not token_obj.is_revoked:
        token_obj.revoke()
        from app.extensions import db

        db.session.commit()
    return True


def refresh_access_token(
    raw_refresh_token: str, instance_id: str | None = None
) -> dict | None:
    """Refresh access token using refresh token with rotation."""
    RefreshToken = get_refresh_token_model()

    # Verify the refresh token
    token_obj = RefreshToken.verify_token(raw_refresh_token)
    if not token_obj or not token_obj.is_valid():
        return None

    # Rotate the refresh token
    return rotate_refresh_token(raw_refresh_token, instance_id)


def decode_token(token: str) -> dict:
    """Decode a JWT token."""
    return jwt.decode(
        token,
        current_app.config["JWT_SECRET_KEY"],
        algorithms=["HS256"],
    )


# Legacy alias
generate_access_token = create_tokens

__all__ = [
    "hash_password",
    "verify_password",
    "create_tokens",
    "decode_token",
    "rotate_refresh_token",
    "revoke_refresh_token",
    "refresh_access_token",
    "generate_access_token",
]
