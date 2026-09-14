import os
from flask import Flask, jsonify

from .config import config, Config
from .extensions import db, migrate, limiter, talisman, init_extensions
# NOTE: `from .tasks import init_celery` must stay lazy (inside create_app
# below). A top-level import re-triggers this module mid-execution via the
# app.tasks auto-init, causing a circular import that left workers silently
# half-initialized.


def create_app(config_name: str | None = None, init_celery_app: bool = True):
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    
    # Handle both string config names and config classes
    if isinstance(config_name, str):
        app.config.from_object(config[config_name])
    else:
        app.config.from_object(config_name)

    init_extensions(app)

    # Build version for the UI footer (also a freshness signal: if the
    # footer shows an old version, the browser is rendering cached HTML).
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", "VERSION")) as f:
            app.config["VERSION"] = f.read().strip()
    except OSError:
        app.config["VERSION"] = "dev"
    
    if init_celery_app:
        from .tasks import init_celery
        init_celery(app)

    # Import models so SQLAlchemy knows about them
    from .models import (  # noqa: F401
        User,
        PromptConfig,
        Idea,
        Vote,
        SecondaryActionResult,
        IdeaStatusHistory,
    )

    # Register blueprints
    from .routes.pages import bp as pages_bp
    from .routes.health import bp as health_bp
    from .routes.auth import bp as auth_bp
    from .routes.ollama import bp as ollama_bp
    from .routes.prompts import bp as prompts_bp
    from .routes.ideas import bp as ideas_bp
    from .routes.admin import bp as admin_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix="/api/v1")
    app.register_blueprint(ollama_bp, url_prefix="/api/v1")
    app.register_blueprint(prompts_bp, url_prefix="/api/v1")
    app.register_blueprint(ideas_bp, url_prefix="/api/v1")
    app.register_blueprint(admin_bp, url_prefix="/api/v1")

    # API error handlers
    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Not Found", "message": "Resource not found."}), 404

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify({"error": "Internal Server Error", "message": "An unexpected error occurred."}), 500

    # CLI commands
    from .cli import register_cli
    register_cli(app)

    @app.after_request
    def _no_cache_pages(response):
        """HTML pages must never be served stale from browser cache.

        <meta http-equiv> tags are ignored by most browsers; only real
        headers work. (Stale pages hid new UI for days with no errors.)
        """
        ctype = response.headers.get("Content-Type", "")
        if ctype.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.context_processor
    def _nav_links():
        """Single source of truth for nav links (PRD §8.2).

        Sidebar, header and user dropdown all loop over this — add or
        remove a link once here and it changes everywhere.
        """
        return {
            "nav_links": [
                {
                    "label": "Ideas",
                    "endpoint": "pages.ideas",
                    "icon": ("M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3"
                             "m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547"
                             "A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386"
                             "l-.548-.547z"),
                },
                {
                    "label": "Prompts",
                    "endpoint": "pages.prompts",
                    "icon": ("M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"
                             "M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012-2"),
                },
            ]
        }

    return app
