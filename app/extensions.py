import redis
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address)
talisman = Talisman()
redis_client = None


def init_extensions(app):
    """Initialize all extensions with the Flask app."""
    global redis_client
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    
    # Initialize limiter with app config
    limiter.init_app(app)
    
    redis_client = redis.from_url(app.config["REDIS_URL"], decode_responses=True)
    app.extensions["redis_client"] = redis_client

    # Talisman CSP configuration
    # Note: 'unsafe-eval' in script-src is REQUIRED by Alpine.js, which evaluates
    # x-data/@click/x-text expressions via new Function(). Without it every
    # Alpine component fails silently (buttons dead, x-show frozen). Removing
    # Alpine would allow dropping 'unsafe-eval'.
    #
    # Inline <script> blocks are allowed by per-request nonce, not
    # 'unsafe-inline': an injected script tag (the stored-XSS path) carries
    # no nonce and is refused by the browser even if escaping ever fails.
    csp = {
        "default-src": "'self'",
        "script-src": "'self' 'unsafe-eval' https://cdn.jsdelivr.net https://cdn.tailwindcss.com",
        "style-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://fonts.googleapis.com",
        "font-src": "'self' data: https://fonts.gstatic.com",
        "img-src": "'self' data: https:",
        "connect-src": "'self'",
        "frame-ancestors": "'none'",
    }
    talisman.init_app(
        app,
        content_security_policy=csp,
        content_security_policy_nonce_in=["script-src"],
        force_https=app.config.get("FORCE_HTTPS", False),
        strict_transport_security=app.config.get("FORCE_HTTPS", False),
        strict_transport_security_max_age=int(
            app.config.get("HSTS_MAX_AGE", 31536000)
        ),
        strict_transport_security_include_subdomains=True,
        session_cookie_secure=app.config.get("FORCE_HTTPS", False),
    )