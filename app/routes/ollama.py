from flask import Blueprint, current_app

from app.utils.decorators import token_required
from app.utils.responses import api_ok, api_error
from app.services.ollama_client import OllamaClient

bp = Blueprint("ollama", __name__)


@bp.route("/ollama/models", methods=["GET"])
@token_required
def list_models(user):
    """List available Ollama models."""
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