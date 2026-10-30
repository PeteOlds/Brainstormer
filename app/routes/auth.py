from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, unset_jwt_cookies

from app.extensions import db, limiter
from app.models import User
from app.utils import auth
from app.utils.decorators import token_required
from app.utils.responses import api_error, api_ok

bp = Blueprint("auth", __name__)


def _set_auth_cookies(resp, tokens, remember=False):
    """Mirror JWTs into cookies so plain browser navigation carries auth.

    Tokens are custom PyJWT (no CSRF claim), so flask_jwt_extended's
    set_access_cookies() cannot be used — set plain cookies instead.
    verify_jwt_in_request() accepts them via JWT_TOKEN_LOCATION cookies.
    JS API calls keep using the Authorization header.
    """
    access_max_age = int(
        current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", 900).total_seconds()
    )
    refresh_max_age = (30 if remember else 7) * 24 * 3600
    secure = bool(current_app.config.get("JWT_COOKIE_SECURE", False))
    samesite = current_app.config.get("JWT_COOKIE_SAMESITE", "Strict")
    resp.set_cookie(
        current_app.config.get("JWT_ACCESS_COOKIE_NAME", "access_token"),
        tokens["access_token"],
        max_age=access_max_age,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
    )
    # Readable by JS on purpose: the double-submit pattern needs the client
    # to echo this value in X-CSRF-TOKEN. It is useless without the
    # HttpOnly access cookie it is paired with.
    resp.set_cookie(
        current_app.config.get("JWT_ACCESS_CSRF_COOKIE_NAME", "csrf_access_token"),
        tokens.get("csrf_token", ""),
        max_age=access_max_age,
        httponly=False,
        secure=secure,
        samesite=samesite,
        path="/",
    )
    resp.set_cookie(
        current_app.config.get("JWT_REFRESH_COOKIE_NAME", "refresh_token"),
        tokens["refresh_token"],
        max_age=refresh_max_age,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
    )
    return resp


@bp.route("/register", methods=["POST"])
@limiter.limit("3 per hour")
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
    resp, code = api_ok(
        {
            "user": user.to_dict(),
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
        },
        "User created.",
        201,
    )
    # Also set JWT cookies so plain browser navigation (admin HTML pages) carries auth.
    # JS API calls keep using the Authorization header; tests use headers-only config.
    _set_auth_cookies(resp, tokens, remember)
    return resp, code


@bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
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
    instance_id = _scoped_instance_id(user, data.get("instance_id"))
    if instance_id is False:
        return api_error("No membership for this instance.", 403)
    tokens = auth.create_tokens(
        user.id, user.role.value, user.email, remember, instance_id
    )
    # Admin visibility for the navbar: global ADMIN, a site-wide grant, or
    # any instance-admin membership (instance admins otherwise never see
    # the Admin menu, although they can use the admin pages when scoped).
    from app.models import ROLE_INSTANCE_ADMIN, Membership

    user_payload = user.to_dict()
    user_payload["is_site_admin"] = Membership.is_site_admin(user.id)
    user_payload["admin_instance_ids"] = [
        str(m.instance_id)
        for m in Membership.query.filter_by(
            user_id=user.id, role=ROLE_INSTANCE_ADMIN
        ).all()
        if m.instance_id is not None
    ]
    resp, code = api_ok(
        {
            "user": user_payload,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
        }
    )
    # Also set JWT cookies so plain browser navigation (admin HTML pages) carries auth.
    _set_auth_cookies(resp, tokens, remember)
    return resp, code


@bp.route("/refresh", methods=["POST"])
@limiter.limit("20 per minute")
def refresh():
    # Body token (API clients) or the HttpOnly cookie (browser UI).
    refresh_token = request.json.get("refresh_token") if request.is_json else None
    if not refresh_token:
        refresh_token = request.cookies.get(
            current_app.config.get("JWT_REFRESH_COOKIE_NAME", "refresh_token")
        )
    if not refresh_token:
        return api_error("Refresh token required.", 400)

    data = request.get_json(silent=True) or {}
    instance_id = data.get("instance_id")
    if instance_id:
        from app.models import RefreshToken as RefreshTokenModel

        token_obj = RefreshTokenModel.verify_token(refresh_token)
        if not token_obj or not token_obj.is_valid():
            return api_error("Invalid or expired refresh token.", 401)
        from app.models import User as UserModel

        user = UserModel.query.get(token_obj.user_id)
        if _scoped_instance_id(user, instance_id) is False:
            return api_error("No membership for this instance.", 403)

    tokens = auth.refresh_access_token(refresh_token, instance_id)
    if not tokens:
        return api_error("Invalid or expired refresh token.", 401)

    resp, code = api_ok(tokens)
    _set_auth_cookies(resp, tokens)
    return resp, code


def _scoped_instance_id(user, raw):
    """Validate an optional login/refresh instance_id.

    Accepts either a UUID or an instance number (e.g. "90"). Returns the
    UUID string, None (unscoped legacy), or False (rejected).
    """
    if not raw:
        return None
    from app.models import Instance, Membership

    try:
        import uuid as uuid_mod

        iid = uuid_mod.UUID(str(raw))
    except (ValueError, TypeError):
        # Not a UUID — try looking up by instance number (e.g. "90").
        inst = Instance.query.filter_by(number=int(str(raw))).first()
        if inst is None:
            return False
        iid = inst.id
    if not Instance.query.get(iid):
        return False
    if Membership.is_site_admin(user.id):
        return str(iid)
    if Membership.get_role(user.id, iid) is None:
        return False
    return str(iid)


@bp.route("/me", methods=["GET"])
@token_required
def me(current_user):
    from flask import g

    return api_ok(
        {"user": current_user.to_dict(), "instance_id": getattr(g, "instance_id", None)}
    )


@bp.route("/me/settings", methods=["PATCH"])
@token_required
def update_user_settings(current_user):
    """Update user-specific settings.

    Deliberately does not accept `can_create_ideas`: that is an admin
    control, and letting users set it here made the restriction on idea
    creation self-service. Admins grant it via PATCH /admin/users/<id>.
    """
    data = request.get_json(silent=True) or {}

    if "can_create_ideas" in data:
        return api_error(
            "can_create_ideas is an admin setting; ask an administrator.",
            status_code=403,
        )

    return api_ok({"user": current_user.to_dict()})


@bp.route("/logout", methods=["POST"])
@token_required
def logout(current_user):
    """Log out and revoke the presented refresh token.

    Clearing cookies alone left the refresh token usable until it expired
    (7 days, 30 with "remember"), so a copied token survived logout.
    """
    data = request.get_json(silent=True) or {}
    raw_refresh = data.get("refresh_token") or request.cookies.get(
        current_app.config.get("JWT_REFRESH_COOKIE_NAME", "refresh_token")
    )
    if raw_refresh:
        auth.revoke_refresh_token(raw_refresh)

    # api_ok returns a (response, status) tuple; unset cookies on the
    # Response object itself (passing the tuple 500'd every logout).
    response, code = api_ok({"message": "Logged out successfully"})
    unset_jwt_cookies(response)
    return response, code
