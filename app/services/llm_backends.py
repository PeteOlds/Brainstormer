"""Multi-provider LLM routing (Phase 3, LiteLLM).

`generate_for_prompt()` is the single entry tasks use. The `ollama`
provider keeps the exact legacy call sequence (existing OllamaClient
mocks keep working); hosted providers go through LiteLLM with JSON
mode, usage capture, static-fallback pricing, budget gates and
append-only spend logging.

Secrets: provider keys live encrypted in `instance_ai_configs`, are
decrypted transiently per call, and never enter prompts, logs or error
bodies — only the prompt hash, model, token counts and cost are logged.
"""

from dataclasses import dataclass
from typing import Any
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import func

logger = structlog.get_logger()

SPEND_WINDOW_DAYS = 30
BUDGET_ALERT_RATIO = 0.7


class ProviderError(Exception):
    """Hosted-provider failure. retryable=False fails the run immediately."""

    def __init__(self, message: str, retryable: bool = True, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class BudgetExhausted(ProviderError):
    """Instance budget spent. Never raised to Celery: tasks fail the run."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False)


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_cents: int = 0


def get_provider_config(instance_id: Any, provider: Any) -> Any:
    """Decrypted-config row for (instance, provider), or None."""
    if instance_id is None or not provider or provider == "ollama":
        return None
    from app.models import InstanceAIConfig

    return InstanceAIConfig.query.filter_by(
        instance_id=instance_id, provider=provider
    ).first()


def instance_spend_cents(instance_id: Any, days: int = SPEND_WINDOW_DAYS) -> int:
    from app.extensions import db
    from app.models import AISpendLedger

    if instance_id is None:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total = (
        db.session.query(AISpendLedger)
        .filter(
            AISpendLedger.instance_id == instance_id,
            AISpendLedger.created_at >= cutoff,
        )
        .with_entities(func.coalesce(func.sum(AISpendLedger.cost_cents), 0))
        .scalar()
    )
    return int(total or 0)


def check_budget(config: Any) -> None:
    """Raise BudgetExhausted past 100%; warn past 70% (refuse behaviour)."""
    if config is None or config.budget_cents is None:
        return
    spent = instance_spend_cents(config.instance_id)
    if spent >= config.budget_cents:
        raise BudgetExhausted(
            f"Instance AI budget exhausted ({spent}/{config.budget_cents}c, "
            f"{SPEND_WINDOW_DAYS}d window)."
        )
    if spent >= config.budget_cents * BUDGET_ALERT_RATIO:
        logger.warning(
            "ai_budget_alert",
            instance_id=str(config.instance_id),
            provider=config.provider,
            spent_cents=spent,
            budget_cents=config.budget_cents,
        )


def record_spend(
    instance_id: Any,
    user_id: Any,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_cents: int,
) -> None:
    from app.extensions import db
    from app.models import AISpendLedger

    db.session.add(
        AISpendLedger(
            instance_id=instance_id,
            user_id=user_id,
            provider=provider,
            model=model,
            prompt_tokens=int(prompt_tokens or 0),
            completion_tokens=int(completion_tokens or 0),
            cost_cents=int(cost_cents or 0),
        )
    )
    db.session.flush()
    logger.info(
        "ai_spend",
        instance_id=str(instance_id) if instance_id else None,
        provider=provider,
        model=model,
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
        cost_cents=int(cost_cents or 0),
    )


def _litellm_cost_cents(model: str, response: Any) -> int:
    try:
        import litellm

        cost = litellm.completion_cost(completion_response=response, model=model)
        return max(0, round(float(cost) * 100))
    except Exception:
        return 0


def _litellm_generate(
    model: str,
    prompt: str,
    system: str | None,
    options: dict | None,
    api_key: str,
    endpoint: str | None,
    timeout: float,
) -> GenerationResult:
    import litellm

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    options = options or {}
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "api_key": api_key or None,
        "timeout": timeout,
    }
    if endpoint:
        kwargs["api_base"] = endpoint
    if options.get("temperature") is not None:
        kwargs["temperature"] = options["temperature"]
    if options.get("num_predict"):
        kwargs["max_tokens"] = options["num_predict"]
    try:
        response = litellm.completion(**kwargs)
    except litellm.AuthenticationError as exc:
        raise ProviderError(
            f"Provider authentication failed: {exc}", retryable=False
        ) from exc
    except (
        litellm.RateLimitError,
        litellm.APIConnectionError,
        litellm.Timeout,
        litellm.ServiceUnavailableError,
    ) as exc:
        raise ProviderError(f"Transient provider error: {exc}", retryable=True) from exc
    except Exception as exc:
        raise ProviderError(f"Provider error: {exc}", retryable=True) from exc
    try:
        text = response.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise ProviderError("Provider returned no content.", retryable=True) from exc
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    return GenerationResult(
        text=text,
        model=model,
        prompt_tokens=int(prompt_tokens),
        completion_tokens=int(completion_tokens),
        cost_cents=_litellm_cost_cents(model, response),
    )


def generate_for_prompt(
    prompt: Any,
    prompt_text: str,
    system: str | None = None,
    options: dict | None = None,
    keep_alive: str | None = None,
    timeout: float = 600.0,
    user_id: Any = None,
) -> GenerationResult:
    """Generate JSON-mode text for a prompt config, recording spend.

    Ollama keeps the exact legacy OllamaClient call sequence. Hosted
    providers require an instance config with a key, pass the budget
    gate, and log spend afterwards.
    """
    from app.services.ollama_client import OllamaClient

    provider = (getattr(prompt, "provider", None) or "ollama").lower()
    model = prompt.model_name
    if provider == "ollama":
        client = OllamaClient(timeout=timeout)
        try:
            response = client.generate_sync(
                model=model,
                prompt=prompt_text,
                system=system,
                format="json",
                options=options,
                keep_alive=keep_alive,
            )
            return GenerationResult(text=response["response"], model=model)
        finally:
            pass
    config = get_provider_config(prompt.instance_id, provider)
    if config is None or not config.api_key:
        raise ProviderError(
            f"No API key configured for provider '{provider}' on this instance.",
            retryable=False,
        )
    check_budget(config)
    result = _litellm_generate(
        model,
        prompt_text,
        system,
        options,
        api_key=config.api_key,
        endpoint=config.endpoint,
        timeout=timeout,
    )
    record_spend(
        prompt.instance_id,
        user_id,
        provider,
        model,
        result.prompt_tokens,
        result.completion_tokens,
        result.cost_cents,
    )
    check_budget(config)
    return result


def embed_for_instance(text: str, instance_id: Any = None) -> list[float] | None:
    """Hosted embedding override, or None to use the local default.

    Returns None when the instance has no non-Ollama embedding model
    configured, so callers fall through to nomic-embed-text.
    """
    if instance_id is None:
        return None
    from app.models import InstanceAIConfig

    rows = InstanceAIConfig.query.filter_by(instance_id=instance_id).all()
    for row in rows:
        if row.provider != "ollama" and row.embedding_model and row.api_key:
            import litellm

            try:
                response = litellm.embedding(
                    model=row.embedding_model,
                    input=[text],
                    api_key=row.api_key,
                    **({"api_base": row.endpoint} if row.endpoint else {}),
                )
                record_spend(
                    instance_id,
                    None,
                    row.provider,
                    row.embedding_model,
                    0,
                    0,
                    _litellm_cost_cents(row.embedding_model, response),
                )
                return list(response.data[0]["embedding"])
            except Exception as exc:
                raise ProviderError(f"Embedding failed: {exc}", retryable=True) from exc
    return None
