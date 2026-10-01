from flask import Blueprint, current_app, request

from app.utils.decorators import token_required
from app.utils.responses import api_ok, api_error
from app.services.ollama_client import OllamaClient
from app.utils.tenancy import current_instance_id

bp = Blueprint("ollama", __name__)


@bp.route("/ollama/models", methods=["GET"])
@token_required
def list_models(user):
    """List available models.

    `?provider=` selects a hosted allowlist for the request instance
    (keys never involved); default stays the local Ollama `/api/tags`.
    """
    from app.models import InstanceAIConfig

    provider = (request.args.get("provider") or "ollama").strip().lower()
    if provider != "ollama":
        instance_id = current_instance_id()
        allowlist = []
        if instance_id is not None:
            config = InstanceAIConfig.query.filter_by(
                instance_id=instance_id, provider=provider
            ).first()
            allowlist = list((config.model_allowlist if config else None) or [])
        return api_ok({"models": allowlist, "provider": provider})
    try:
        # Short timeout: this backs UI dropdowns. A hung upstream must never
        # pin a server thread for minutes (see: threadpool exhaustion stalls).
        # Heavy generation keeps the long client default via /prompts/test.
        client = OllamaClient(current_app.config["OLLAMA_BASE_URL"], timeout=15.0)
        models = client.list_models_sync()
        client.close()
        return api_ok({"models": models})
    except Exception as e:
        return api_error(f"Failed to fetch models: {str(e)}", status_code=500)
