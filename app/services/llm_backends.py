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
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
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

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message, retryable=False)
        # Set when the instance chose the queue cutoff: tasks retry
        # after this many seconds instead of failing.
        self.retry_after = retry_after


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
        # Queue cutoff retries the Celery task later (fixed 1h delay;
        # the run error states this visibly). Refuse (default) fails fast.
        retry_after = 3600 if (config.cutoff_behaviour or "refuse") == "queue" else None
        raise BudgetExhausted(
            f"Instance AI budget exhausted ({spent}/{config.budget_cents}c, "
            f"{SPEND_WINDOW_DAYS}d window).",
            retry_after=retry_after,
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


def _proxy_url() -> str:
    import os

    from flask import current_app

    try:
        configured = current_app.config.get("LITELLM_PROXY_URL")
    except RuntimeError:
        configured = None
    raw = configured or os.getenv("LITELLM_PROXY_URL") or "http://litellm:4000"
    return raw.rstrip("/")


def _proxy_generate(
    model: str,
    prompt: str,
    system: str | None,
    options: dict | None,
    virtual_key: str,
    timeout: float,
    json_mode: bool = True,
) -> GenerationResult:
    """OpenAI-compatible chat via the LiteLLM proxy (virtual key only).

    The raw provider key lives server-side in LiteLLM; application
    memory only ever holds the virtual key.
    """
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, Any] = {"model": model, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    options = options or {}
    if options.get("temperature") is not None:
        payload["temperature"] = options["temperature"]
    if options.get("num_predict"):
        payload["max_tokens"] = options["num_predict"]
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{_proxy_url()}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {virtual_key}"},
            )
            if response.status_code == 401:
                raise ProviderError("Proxy rejected the virtual key.", retryable=False)
            response.raise_for_status()
            body = response.json()
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError("Proxy unreachable.", retryable=True) from exc
    try:
        text = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("Proxy returned no content.", retryable=True) from exc
    usage = body.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    return GenerationResult(
        text=text,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_cents=_proxy_cost_cents(model, prompt_tokens, completion_tokens),
    )


_pricing_override: dict = {}
_pricing_override_mtime: float | None = None


def refresh_pricing_cache() -> dict:
    """Reload finance-owned price overrides (never a live provider call).

    PRICING_OVERRIDE_PATH points at JSON:
    {"openai/gpt-4o-mini": {"input_cost_per_token": ..., "output_cost_per_token": ...}}.
    Overrides win over the bundled LiteLLM table; missing file means
    bundled prices. Returns the active override map.
    """
    import json as _json
    import os

    global _pricing_override, _pricing_override_mtime
    path = os.getenv("PRICING_OVERRIDE_PATH", "")
    if not path:
        _pricing_override, _pricing_override_mtime = {}, None
        return {}
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return dict(_pricing_override)
    if _pricing_override_mtime == mtime:
        return dict(_pricing_override)
    try:
        with open(path, encoding="utf-8") as fh:
            _pricing_override = dict(_json.load(fh))
        _pricing_override_mtime = mtime
    except (OSError, ValueError):
        pass
    return dict(_pricing_override)


def _model_price(model: str) -> tuple:
    overrides = refresh_pricing_cache()
    if model in overrides:
        info = overrides[model]
        return float(info.get("input_cost_per_token", 0)), float(
            info.get("output_cost_per_token", 0)
        )
    import litellm

    info = litellm.model_cost.get(model, {})
    return float(info.get("input_cost_per_token", 0)), float(
        info.get("output_cost_per_token", 0)
    )


def _proxy_cost_cents(model: str, prompt_tokens: int, completion_tokens: int) -> int:
    """Cost from override table, else bundled LiteLLM prices (offline)."""
    try:
        per_in, per_out = _model_price(model)
        return int(
            max(0, round((prompt_tokens * per_in + completion_tokens * per_out) * 100))
        )
    except Exception:
        return 0


def provision_virtual_key(models: list, alias: str) -> str:
    """Issue a proxy virtual key (master-key auth, never logged)."""
    import os

    from flask import current_app

    try:
        master = current_app.config.get("LITELLM_MASTER_KEY")
    except RuntimeError:
        master = None
    master = master or os.getenv("LITELLM_MASTER_KEY", "")
    if not master:
        raise ProviderError("LITELLM_MASTER_KEY is not configured.", retryable=False)
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                f"{_proxy_url()}/key/generate",
                json={"models": models, "key_alias": alias},
                headers={"Authorization": f"Bearer {master}"},
            )
            response.raise_for_status()
            key = response.json().get("key")
    except Exception as exc:
        raise ProviderError("Proxy key provisioning failed.", retryable=True) from exc
    if not key:
        raise ProviderError("Proxy returned no key.", retryable=True)
    return str(key)


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
    json_mode: bool = True,
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
        "api_key": api_key or None,
        "timeout": timeout,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
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
    json_mode: bool = True,
) -> GenerationResult:
    """Generate text for a prompt config, recording spend.

    Ollama keeps the exact legacy OllamaClient call sequence. Hosted
    providers require an instance config with a key, pass the budget
    gate, and log spend afterwards. json_mode=False returns free prose
    (used by Chat); structured actions always use JSON mode.
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
                format="json" if json_mode else None,
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
    from app.models import EntitlementError, require_entitlement

    try:
        require_entitlement(prompt.instance_id, "hosted_ai")
    except EntitlementError as exc:
        raise ProviderError(str(exc), retryable=False) from exc
    try:
        check_budget(config)
    except BudgetExhausted as exc:
        # Degrade is explicit per-instance choice: answer quality changes
        # are logged loudly, never silently.
        if (config.cutoff_behaviour or "refuse") == "degrade" and config.degrade_model:
            from app.services.ollama_client import OllamaClient as _OllamaClient

            logger.warning(
                "ai_budget_degrade",
                instance_id=str(prompt.instance_id),
                provider=provider,
                fallback_model=config.degrade_model,
            )
            local = _OllamaClient(timeout=timeout)
            try:
                response = local.generate_sync(
                    model=config.degrade_model,
                    prompt=prompt_text,
                    system=system,
                    format="json" if json_mode else None,
                    options=options,
                    keep_alive=keep_alive,
                )
                return GenerationResult(
                    text=response["response"], model=config.degrade_model
                )
            finally:
                pass
        raise
    # DLP: mask PII before anything leaves for a hosted provider
    # (local Ollama path above is untouched). Counts only in logs.
    from app.services.dlp import mask_text

    prompt_text, masked = mask_text(prompt_text)
    if system:
        system, sys_masked = mask_text(system)
        masked.update(sys_masked)
    if masked:
        logger.info(
            "dlp_masked",
            instance_id=str(prompt.instance_id),
            provider=provider,
            counts=masked,
        )
    if config.use_proxy and config.virtual_key:
        result = _proxy_generate(
            model,
            prompt_text,
            system,
            options,
            virtual_key=config.virtual_key,
            timeout=timeout,
            json_mode=json_mode,
        )
    else:
        result = _litellm_generate(
            model,
            prompt_text,
            system,
            options,
            api_key=config.api_key,
            endpoint=config.endpoint,
            timeout=timeout,
            json_mode=json_mode,
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
            if row.use_proxy and row.virtual_key:
                return _proxy_embed(text, instance_id, row)
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


def _proxy_embed(text: str, instance_id: Any, row: Any) -> list[float]:
    """Embeddings through the proxy (virtual key, spend-logged)."""
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{_proxy_url()}/embeddings",
                json={"model": row.embedding_model, "input": [text]},
                headers={"Authorization": f"Bearer {row.virtual_key}"},
            )
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        raise ProviderError(f"Proxy embedding failed: {exc}", retryable=True) from exc
    try:
        embedding = body["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("Proxy returned no embedding.", retryable=True) from exc
    usage = body.get("usage") or {}
    record_spend(
        instance_id,
        None,
        row.provider,
        row.embedding_model,
        int(usage.get("prompt_tokens") or 0),
        0,
        _proxy_cost_cents(row.embedding_model, int(usage.get("prompt_tokens") or 0), 0),
    )
    return list(embedding)
