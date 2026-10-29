from flask import Blueprint, current_app, request

from app.utils.decorators import token_required
from app.utils.responses import api_ok, api_error
from app.services.ollama_client import OllamaClient
from app.utils.tenancy import current_instance_id

bp = Blueprint("ollama", __name__)


# Curated model ids for hosted providers that have no server-side catalog.
# Used only when an instance has no allowlist configured, so the dropdown
# is never empty for non-technical users. Admins can still restrict via the
# per-instance allowlist (which overrides this list).
_HOSTED_MODEL_CATALOGUE = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
        "o3-mini",
    ],
    "anthropic": [
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-opus-latest",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ],
    "gemini": [
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.0-pro",
    ],
}


@bp.route("/ollama/models", methods=["GET"])
@token_required
def list_models(user):
    """List available models.

    `?provider=` selects a hosted allowlist for the request instance
    (keys never involved); default stays the local Ollama `/api/tags`.
    `unrestricted` is true when no allowlist narrows the choice: any model
    id is accepted (validation only enforces non-empty allowlists).
    """
    from app.models import InstanceAIConfig

    provider = (request.args.get("provider") or "ollama").strip().lower()
    if provider != "ollama":
        instance_id = current_instance_id()
        allowlist = []
        endpoint = None
        if instance_id is not None:
            config = InstanceAIConfig.query.filter_by(
                instance_id=instance_id, provider=provider
            ).first()
            allowlist = list((config.model_allowlist if config else None) or [])
            endpoint = (config.endpoint if config else None) or None
        if allowlist:
            return api_ok(
                {"models": allowlist, "provider": provider, "unrestricted": False}
            )
        # No allowlist: anything goes (validation enforces nothing), but
        # the dropdown still needs options so non-technical users can pick
        # instead of typing a model id.
        #   - opencode: the LAN server's own catalog (authenticated).
        #   - openai/anthropic/gemini: a curated catalogue of the common
        #     hosted models (admins can still narrow via the allowlist).
        models: list = []
        if provider == "opencode":
            from app.services.opencode_backend import list_server_models

            server_url = endpoint or current_app.config.get("OPENCODE_SERVER_URL") or ""
            models = list_server_models(server_url, provider=provider)
        elif provider in _HOSTED_MODEL_CATALOGUE:
            models = list(_HOSTED_MODEL_CATALOGUE[provider])
        return api_ok({"models": models, "provider": provider, "unrestricted": True})
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
