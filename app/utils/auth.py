"""Compatibility layer over flask-appkit auth with refresh token rotation."""

from datetime import timedelta, datetime, timezone
from flask import current_app
from flask_appkit.auth import hash_password, verify_password
import jwt

# Import the RefreshToken model lazily to avoid circular imports
def get_refresh_token_model():
    from app.models import RefreshToken
    return RefreshToken


def create_tokens(user_id: str, role: str = "USER", email: str = None, remember: bool = False) -> dict:
    """Create access and refresh tokens for a user with refresh token rotation."""
    access_expires = current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", timedelta(minutes=15))
    
    # Create access token with role claim using PyJWT directly
    access_payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + access_expires,
        "iat": datetime.now(timezone.utc),
    }
    if email:
        access_payload["email"] = email
    
    access_token = jwt.encode(
        access_payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )
    
    # Create refresh token and store in database
    # Use longer expiry if remember_me is checked
    refresh_days = 30 if remember else 7
    RefreshToken = get_refresh_token_model()
    raw_refresh_token, refresh_token_obj = RefreshToken.create_token(user_id, expires_in_days=refresh_days)
    
    # Store in database
    from app.extensions import db
    db.session.add(refresh_token_obj)
    db.session.commit()
    
    return {
        "access_token": access_token,
        "refresh_token": raw_refresh_token,
    }


def decode_token(token: str) -> dict:
    """Decode a JWT token."""
    return jwt.decode(
        token,
        current_app.config["JWT_SECRET_KEY"],
        algorithms=["HS256"],
    )


def rotate_refresh_token(raw_refresh_token: str) -> dict | None:
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

    access_expires = current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", timedelta(minutes=15))
    access_payload = {
        "sub": str(user_id),
        "role": user.role.value,
        "exp": datetime.now(timezone.utc) + access_expires,
        "iat": datetime.now(timezone.utc),
    }
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
    }


def refresh_access_token(raw_refresh_token: str) -> dict | None:
    """Refresh access token using refresh token with rotation."""
    RefreshToken = get_refresh_token_model()
    
    # Verify the refresh token
    token_obj = RefreshToken.verify_token(raw_refresh_token)
    if not token_obj or not token_obj.is_valid():
        return None
    
    # Rotate the refresh token
    return rotate_refresh_token(raw_refresh_token)


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
    "refresh_access_token",
    "generate_access_token",
]
