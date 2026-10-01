import structlog
from flask import Blueprint, current_app, request

from app.extensions import db, limiter
from app.models import Instance, Membership, OAuthIdentity, TenantOAuthConfig, User
from app.utils import auth as auth_utils
from app.utils.responses import api_error, api_ok

logger = structlog.get_logger()

bp = Blueprint("oauth", __name__)


def _redirect_uri(provider: str) -> str:
    base = current_app.config.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/v1/oauth/{provider}/callback"


def _instance_or_404(raw):
    import uuid as uuid_mod

    try:
        iid = uuid_mod.UUID(str(raw))
    except (ValueError, TypeError):
        return None, api_error("instance_id is required and must be a UUID.", 400)
    instance = Instance.query.get(iid)
    if instance is None:
        return None, api_error("Instance not found.", 404)
    return instance, None


def _scoped_pair(user, instance_id):
    from app.models import ROLE_USER

    membership = Membership.query.filter_by(
        user_id=user.id, instance_id=instance_id
    ).first()
    if membership is None:
        # Just-in-time onboarding: least privilege, elevation needs an admin.
        membership = Membership(
            user_id=user.id, instance_id=instance_id, role=ROLE_USER
        )
        db.session.add(membership)
        logger.info(
            "social_jit_onboard",
            user_id=str(user.id),
            instance_id=str(instance_id),
            role=ROLE_USER,
        )
    user.record_login()
    db.session.commit()
    tokens = auth_utils.create_tokens(
        user.id, user.role.value, user.email, False, str(instance_id)
    )
    return tokens, membership


@bp.route("/oauth/<provider>/start", methods=["GET"])
@limiter.limit("5 per minute")
def oauth_start(provider):
    """Begin login: returns the provider authorisation URL (open in browser)."""
    from app.services import social_auth as social

    provider = (provider or "").lower()
    if provider not in social.PROVIDER_META:
        return api_error("Unknown provider.", 404)
    instance, err = _instance_or_404(request.args.get("instance_id"))
    if err:
        return err
    config = TenantOAuthConfig.query.filter_by(
        instance_id=instance.id, provider_name=provider
    ).first()
    if config is None:
        return api_error("Social login is not configured for this instance.", 400)
    try:
        bundle = social.build_start_url(
            provider, instance.id, config.client_id, _redirect_uri(provider)
        )
    except social.SocialError as exc:
        return api_error(str(exc), 400)
    logger.info("social_login_start", provider=provider, instance_id=str(instance.id))
    return api_ok(bundle)


@bp.route("/oauth/<provider>/callback", methods=["GET"])
@limiter.limit("5 per minute")
def oauth_callback(provider):
    """Provider redirect target: verify, then log in, link-pending, or onboard."""
    import uuid as uuid_mod

    from app.services import social_auth as social

    provider = (provider or "").lower()
    if provider not in social.PROVIDER_META:
        return api_error("Unknown provider.", 404)
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return api_error("code and state are required.", 400)
    try:
        instance_id = uuid_mod.UUID(social.read_state(state, provider)["instance_id"])
    except social.SocialError as exc:
        return api_error(str(exc), 400)
    config = TenantOAuthConfig.query.filter_by(
        instance_id=instance_id, provider_name=provider
    ).first()
    if config is None or not config.client_secret:
        return api_error("Social login is not configured for this instance.", 400)
    try:
        profile, _ = social.exchange_code(
            provider,
            code,
            state,
            config.client_id,
            config.client_secret,
            _redirect_uri(provider),
        )
    except social.SocialError as exc:
        return api_error(str(exc), 400)

    identity = OAuthIdentity.query.filter_by(
        provider=profile.provider, subject=profile.subject
    ).first()
    if identity is not None:
        user = User.query.get(identity.user_id)
        if user is None or not user.is_active:
            return api_error("Account is disabled.", 403)
        tokens, _ = _scoped_pair(user, instance_id)
        logger.info(
            "social_login_complete",
            provider=provider,
            instance_id=str(instance_id),
            user_id=str(user.id),
        )
        return api_ok({"user": user.to_dict(), **tokens})

    user = User.query.filter_by(email=profile.email).first()
    if user is not None:
        if not user.is_active:
            return api_error("Account is disabled.", 403)
        link_token = social.linking_token(
            user.id, profile.provider, profile.subject, profile.email, instance_id
        )
        logger.info(
            "social_link_required",
            provider=provider,
            instance_id=str(instance_id),
            user_id=str(user.id),
        )
        return api_error(
            "This email already has an account. Confirm to link your social login.",
            status_code=409,
            errors={
                "linking_token": link_token,
                "email": profile.email,
                "provider": profile.provider,
            },
            error_code="LINKING_REQUIRED",
        )

    import secrets as secrets_mod

    user = User(email=profile.email, name=profile.name)
    user.set_password(secrets_mod.token_urlsafe(32))
    db.session.add(user)
    db.session.flush()
    db.session.add(
        OAuthIdentity(
            user_id=user.id,
            provider=profile.provider,
            subject=profile.subject,
            email=profile.email,
        )
    )
    tokens, _ = _scoped_pair(user, instance_id)
    logger.info(
        "social_signup_complete",
        provider=provider,
        instance_id=str(instance_id),
        user_id=str(user.id),
    )
    return api_ok({"user": user.to_dict(), **tokens}, "Account created.", 201)


@bp.route("/oauth/link", methods=["POST"])
@limiter.limit("5 per minute")
def oauth_link():
    """Explicit confirmation linking a social identity to an account."""
    from app.services import social_auth as social

    data = request.get_json(silent=True) or {}
    if data.get("confirm") is not True:
        return api_error("Explicit confirmation is required: pass confirm=true.", 400)
    if not data.get("linking_token"):
        return api_error("linking_token is required.", 400)
    try:
        link = social.read_linking_token(data["linking_token"])
    except social.SocialError as exc:
        return api_error(str(exc), 400)
    user = User.query.get(link["sub"])
    if user is None or not user.is_active:
        return api_error("Account is disabled.", 403)
    existing = OAuthIdentity.query.filter_by(
        provider=link["provider"], subject=link["subject"]
    ).first()
    if existing is not None and str(existing.user_id) != str(user.id):
        return api_error("This social identity is already linked elsewhere.", 409)
    if existing is None:
        db.session.add(
            OAuthIdentity(
                user_id=user.id,
                provider=link["provider"],
                subject=link["subject"],
                email=link.get("email"),
            )
        )
    import uuid as uuid_mod

    tokens, _ = _scoped_pair(user, uuid_mod.UUID(link["instance_id"]))
    logger.info(
        "social_link_complete",
        provider=link["provider"],
        instance_id=link["instance_id"],
        user_id=str(user.id),
    )
    return api_ok({"user": user.to_dict(), **tokens})
