import json
import os
import random
import string
import uuid
from datetime import datetime, timezone

from flask import Blueprint, g, request
from flask_jwt_extended import get_jwt_identity
from flask_limiter.util import get_remote_address
from sqlalchemy import asc, desc, func, or_

from app.extensions import db, limiter
from app.models import (
    Comment,
    Idea,
    IdeaEdit,
    IdeaStatusHistory,
    PromptRun,
    PromptRunStatus,
    SecondaryActionResult,
    User,
    Vote,
)
from app.models.enums import IdeaStatus
from app.utils.decorators import (
    _membership_allows_admin,
    admin_required,
    require_permission,
    token_required,
)
from app.utils.responses import api_accepted, api_created, api_error, api_ok
from app.utils.tenancy import apply_scope, check_access, current_instance_role, stamp

bp = Blueprint("ideas", __name__)


def _get_user_vote(user_id: uuid.UUID, idea_id: uuid.UUID) -> int | None:
    """Get user's vote on an idea (1, -1, or None)."""
    vote = Vote.query.filter_by(user_id=user_id, idea_id=idea_id).first()
    return vote.value if vote else None


def _maybe_push_on_scale(idea):
    """Auto-push to GitHub when an idea enters Scale, if GitHub is configured."""
    from app.models import InstanceGitHubConfig

    if idea.status.value != "SCALE" or not idea.instance_id:
        return

    from app.models import InstanceGitHubConfig

    config = InstanceGitHubConfig.query.filter_by(instance_id=idea.instance_id).first()
    if not config or not config.pat:
        return

    from app.tasks.github_tasks import push_release_to_github

    # Enqueue as a one-off "release" for this idea
    push_release_to_github.delay(f"idea:{idea.id}")


def _resolve_build_target(idea, target_id):
    """Repo a BUILD_CODE run writes into, shared with the release pipeline.

    The Build tab may lazily create the idea's repo (named after its
    reference code) when the instance has no matching one. An explicit id
    that does not resolve never falls back — writing into a different repo
    than the caller asked for is worse than failing.
    """
    from app.services.build_targets import resolve_build_target

    target, _reason = resolve_build_target(
        idea, explicit_id=target_id, allow_create=True
    )
    return target


def _check_action_allowed(idea, action_type):
    """Check if a secondary action is allowed for this idea in its current state."""
    from app.models import IdeaStatus

    st = idea.status
    # Handle both enum members and string values from SQLAlchemy
    st_str = st.value if hasattr(st, "value") else str(st)
    # Only PRD_DOC, DESIGN_DOC, BUILD_CODE have stage gates.
    # Everything else (REFINE, COMPETITORS, etc.) is always allowed.
    if action_type == "PRD_DOC":
        return st_str not in ("SPARK", "DROP", "ARCHIVE")
    if action_type == "DESIGN_DOC":
        return st_str in ("MAP", "SHIP", "SCALE", "FREEZE")
    if action_type == "BUILD_CODE":
        return st_str in ("SHIP", "SCALE")
    return True


def _enqueue_action(idea, action_type, extra=None):
    """Enqueue a secondary action task."""
    from app.models import PromptRun, PromptRunStatus
    from app.services.action_context import build_idea_context
    from app.tasks.ollama_tasks import run_secondary_action

    context = build_idea_context(idea)
    extra = dict(extra or {})
    # Validate provider_override up front so a bad value (or an
    # unconfigured OpenCode instance) fails fast with a 400 instead of a
    # queued, failing run.
    provider_override = extra.get("provider_override")
    if provider_override is not None:
        from app.models import PROVIDERS, InstanceAIConfig
        from app.utils.tenancy import current_instance_id

        if provider_override not in PROVIDERS:
            return (
                None,
                None,
                f"Invalid provider: must be one of {', '.join(PROVIDERS)}.",
            )
        if provider_override != "ollama":
            iid = current_instance_id()
            config = None
            if iid is not None:
                config = InstanceAIConfig.query.filter_by(
                    instance_id=iid, provider=provider_override
                ).first()
            if config is None:
                return (
                    None,
                    None,
                    f"Provider '{provider_override}' is not configured for "
                    "this instance.",
                )
            model_override = extra.get("model_override")
            allowlist = (config.model_allowlist if config else None) or []
            if allowlist and model_override and model_override not in allowlist:
                return (
                    None,
                    None,
                    f"Model '{model_override}' is not in this instance's "
                    f"{provider_override} allowlist.",
                )
    if action_type == "BUILD_CODE":
        from app.services.build_targets import resolve_build_target

        target, reason = resolve_build_target(
            idea,
            explicit_id=extra.get("target_id"),
            allow_create=True,
        )
        if target is None:
            return (
                None,
                None,
                "No build repo selected. "
                f"{reason or 'Add one in Admin → AI Settings.'}",
            )
        extra["target_id"] = str(target.id)

    # Resolve the provider up front so the run lands on the right queue:
    # OpenCode tasks must go to the dedicated serial `opencode` queue with
    # its longer time limits; Ollama stays on `ollama`.
    try:
        from app.models import resolve_release, resolve_stage

        stage_cfg = resolve_stage(
            idea.instance_id, getattr(idea.status, "value", idea.status)
        )
        release_cfg = resolve_release(idea)
        merged = {
            **stage_cfg,
            **{k: v for k, v in release_cfg.items() if v is not None},
        }
        provider = (
            extra.get("provider_override") or merged.get("provider") or "ollama"
        ).lower()
    except Exception:
        provider = (extra.get("provider_override") or "ollama").lower()

    # Create a PromptRun row so the run is trackable in the admin activity
    # page and the frontend can poll for completion. The task marks it
    # RUNNING when it starts and SUCCESS/FAILED when it finishes.
    run = PromptRun(
        instance_id=idea.instance_id,
        action_type=action_type,
        triggered_by="manual",
        idea_id=idea.id,
        status=PromptRunStatus.PENDING,
        job_type="ai",
        provider=provider,
        model=extra.get("model_override")
        or merged.get("model_name")
        or merged.get("model"),
        queue="opencode" if provider == "opencode" else "ollama",
    )
    db.session.add(run)
    db.session.commit()

    from app.tasks import enqueue_generation

    result = enqueue_generation(
        run_secondary_action,
        [str(idea.id), action_type],
        {
            "model_override": extra.get("model_override"),
            "extra_context": extra,
            "run_id": str(run.id),
            "provider_override": extra.get("provider_override"),
        },
        provider,
    )
    return result.id, str(run.id), None


def _chat_rate_key():
    """Rate-limit key for chat: per user per idea."""
    return f"chat:{get_jwt_identity()}"


def _chat_gate(idea):
    """Check chat rate limits and return (allowed, error_message_or_None).

    Rate limit: 3 messages per minute per idea per user. Fails open if Redis
    is unavailable.
    """
    from app.extensions import redis_client

    key = f"chat:{get_jwt_identity()}:{idea.id}"
    try:
        current = redis_client.get(key)
    except Exception:
        # Redis unavailable: fail open
        return True, None
    if current:
        count = int(current)
        limit = 3
        if count >= limit:
            return (
                False,
                "Rate limit exceeded. Please wait before sending another message.",
            )
    return True, None


def _chat_provider_error(err):
    """Format a provider error into a user-friendly message."""
    msg = str(err)
    if "timeout" in msg.lower():
        return "The AI provider took too long to respond. Please try again."
    if "rate limit" in msg.lower():
        return "The AI provider is rate-limited. Please try again shortly."
    if "connection" in msg.lower():
        return "Cannot connect to the AI provider. Please check your connection."
    return f"AI error: {msg}"


def _chat_enabled_for(instance_id):
    """Chat is opt-in per instance once it has AI configs.

    An instance with no AI config rows keeps the default (on). Otherwise an
    admin must have enabled chat on at least one provider config.
    """
    from app.models import InstanceAIConfig

    rows = InstanceAIConfig.query.filter_by(instance_id=instance_id).all()
    if not rows:
        return True
    return any(r.chat_enabled for r in rows)
