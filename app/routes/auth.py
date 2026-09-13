from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, unset_jwt_cookies, get_jwt_identity

from app.extensions import db
from app.models import User
from app.utils import auth
from app.utils.decorators import token_required
from app.utils.responses import api_error
from app.utils.responses import api_ok

bp = Blueprint("auth", __name__)


def _set_auth_cookies(resp, tokens, remember=False):
    """Mirror JWTs into cookies so plain browser navigation carries auth.

    Tokens are custom PyJWT (no CSRF claim), so flask_jwt_extended's
    set_access_cookies() cannot be used — set plain cookies instead.
    verify_jwt_in_request() accepts them via JWT_TOKEN_LOCATION cookies.
    JS API calls keep using the Authorization header.
    """
    access_max_age = int(current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", 900).total_seconds())
    refresh_max_age = (30 if remember else 7) * 24 * 3600
    secure = bool(current_app.config.get("JWT_COOKIE_SECURE", False))
    samesite = current_app.config.get("JWT_COOKIE_SAMESITE", "Strict")
    resp.set_cookie(
        current_app.config.get("JWT_ACCESS_COOKIE_NAME", "access_token"),
        tokens["access_token"], max_age=access_max_age,
        httponly=True, secure=secure, samesite=samesite, path="/",
    )
    resp.set_cookie(
        current_app.config.get("JWT_REFRESH_COOKIE_NAME", "refresh_token"),
        tokens["refresh_token"], max_age=refresh_max_age,
        httponly=True, secure=secure, samesite=samesite, path="/",
    )
    return resp


@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return api_error("Email and password are required.", 400)
    if len(password) < 8:
        return api_error("Password must be at least 8 characters.", 400)
    if User.query.filter_by(email=email).first():
        return api_error("Email already registered.", 409)

    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    remember = data.get("remember", False)
    tokens = auth.create_tokens(user.id, user.role.value, user.email, remember)
    resp, code = api_ok({"user": user.to_dict(), "access_token": tokens["access_token"], "refresh_token": tokens["refresh_token"]}, "User created.", 201)
    # Also set JWT cookies so plain browser navigation (admin HTML pages) carries auth.
    # JS API calls keep using the Authorization header; tests use headers-only config.
    _set_auth_cookies(resp, tokens, remember)
    return resp, code


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return api_error("Invalid credentials.", 401)
    if not user.is_active:
        return api_error("Account is disabled.", 403)

    user.record_login()
    db.session.commit()

    remember = data.get("remember", False)
    tokens = auth.create_tokens(user.id, user.role.value, user.email, remember)
    resp, code = api_ok({"user": user.to_dict(), "access_token": tokens["access_token"], "refresh_token": tokens["refresh_token"]})
    # Also set JWT cookies so plain browser navigation (admin HTML pages) carries auth.
    _set_auth_cookies(resp, tokens, remember)
    return resp, code


@bp.route("/refresh", methods=["POST"])
def refresh():
    # Get refresh token from request body
    refresh_token = request.json.get("refresh_token") if request.is_json else None
    if not refresh_token:
        return api_error("Refresh token required.", 400)
    
    tokens = auth.refresh_access_token(refresh_token)
    if not tokens:
        return api_error("Invalid or expired refresh token.", 401)
    
    return api_ok(tokens)


@bp.route("/me", methods=["GET"])
@token_required
def me(current_user):
    return api_ok({"user": current_user.to_dict()})


@bp.route("/logout", methods=["POST"])
@token_required
def logout(current_user):
    # api_ok returns a (response, status) tuple; unset cookies on the
    # Response object itself (passing the tuple 500'd every logout).
    response, code = api_ok({"message": "Logged out successfully"})
    unset_jwt_cookies(response)
    return response, code