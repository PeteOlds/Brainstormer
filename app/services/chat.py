"""Chat-to-AI orchestration (Phase 4).

Turns persist who/when/model/phase plus content hashes; logs carry
hashes only, never bodies or keys. Iterate writes versioned idea
updates (IdeaEdit audit + snapshots); rollback restores any iterate
snapshot, itself fully audited.
"""

from types import SimpleNamespace
from typing import Any

import structlog

from app.extensions import db
from app.models import ChatSession, ChatTurn, IdeaEdit
from app.models.chat import content_hash
from app.services.action_context import build_idea_context
from app.services.llm_backends import (
    BudgetExhausted,
    ProviderError,
    generate_for_prompt,
)
from app.services.prompt_templates import get_base_prompt

logger = structlog.get_logger()

HISTORY_TURNS = 10
HISTORY_CHARS = 4000
MESSAGE_MAX = 4000

EDITABLE_FIELDS = ("prompt_title", "raw_content", "structured_content")
STRUCTURED_CAPS = {
    "elevator_pitch": 500,
    "target_audience": 300,
    "core_value_proposition": 500,
    "monetization_strategy": 300,
}


class ChatError(ValueError):
    status_code = 400


class ChatNotFoundError(ChatError):
    status_code = 404


def resolve_route(idea: Any, model_override: Any = None) -> Any:
    """Provider/model/instance routing for an idea's chat turns.

    Follows the instance's stage config once per-stage settings land;
    until then the idea's own prompt is the config (admin override swaps
    the model within the same provider).
    """
    prompt = idea.prompt_config
    provider = (prompt.provider if prompt else None) or "ollama"
    model = model_override or (prompt.model_name if prompt else None) or "llama3:8b"
    return SimpleNamespace(
        provider=provider, model_name=model, instance_id=idea.instance_id
    )


def get_or_create_session(idea: Any, user: Any, model: str) -> Any:
    session = (
        ChatSession.query.filter_by(idea_id=idea.id, user_id=user.id)
        .order_by(ChatSession.created_at.desc())
        .first()
    )
    if session is None:
        session = ChatSession(
            idea_id=idea.id,
            user_id=user.id,
            instance_id=idea.instance_id,
            phase=idea.status.value,
            model_used=model,
        )
        db.session.add(session)
        db.session.flush()
    return session


def _history_text(session: Any) -> str:
    turns = (
        session.turns.filter(ChatTurn.kind == "chat")
        .order_by(ChatTurn.created_at.desc())
        .limit(HISTORY_TURNS)
        .all()
    )
    turns = list(reversed(turns))
    lines = []
    budget = HISTORY_CHARS
    for turn in reversed(turns):
        chunk = f"{turn.role.upper()}: {turn.content[:1000]}"
        if len(chunk) > budget:
            break
        lines.append(chunk)
        budget -= len(chunk)
    return "\n".join(reversed(lines))


def _record_turn(
    session: Any,
    role: str,
    kind: str,
    content: str,
    model: Any = None,
    result: Any = None,
    snapshot_before: Any = None,
    snapshot_after: Any = None,
) -> Any:
    turn = ChatTurn(
        session_id=session.id,
        instance_id=session.instance_id,
        role=role,
        kind=kind,
        content=content,
        content_hash=content_hash(content),
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
        model_used=model,
        prompt_tokens=getattr(result, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(result, "completion_tokens", 0) or 0,
        cost_cents=getattr(result, "cost_cents", 0) or 0,
    )
    db.session.add(turn)
    db.session.flush()
    logger.info(
        "chat_turn",
        session_id=str(session.id),
        idea_id=str(session.idea_id),
        user_id=str(session.user_id),
        role=role,
        kind=kind,
        model=model,
        content_hash=turn.content_hash,
        prompt_tokens=turn.prompt_tokens,
        completion_tokens=turn.completion_tokens,
        cost_cents=turn.cost_cents,
    )
    return turn


def chat_turn(idea: Any, user: Any, message: str, model_override: Any = None) -> Any:
    """One conversational turn: no idea changes, reply in prose."""
    from app.models import require_entitlement

    route = resolve_route(idea, model_override)
    if route.provider != "ollama":
        require_entitlement(idea.instance_id, "hosted_ai")
    session = get_or_create_session(idea, user, route.model_name)
    system = get_base_prompt() + (
        "\nYou are brainstorming conversationally about the idea below. "
        "Reply in plain prose (never JSON). Ground every claim in the "
        "provided context; ignored comments are already excluded."
    )
    supporting = build_idea_context(idea)
    history = _history_text(session)
    prompt_text = (
        f"### IDEA CONTEXT\n{supporting}\n\n"
        + (f"### CONVERSATION SO FAR\n{history}\n\n" if history else "")
        + f"### USER\n{message}"
    )
    _record_turn(session, "user", "chat", message, route.model_name)
    result = generate_for_prompt(
        route,
        prompt_text,
        system=system,
        options={"temperature": 0.7},
        timeout=120.0,
        user_id=user.id,
        json_mode=False,
    )
    reply = _record_turn(
        session, "assistant", "chat", result.text, route.model_name, result
    )
    db.session.commit()
    return session, reply


def _validate_content_updates(updates: dict) -> dict:
    """Same rules as the admin content editor (twin: keep in sync)."""
    if not isinstance(updates, dict) or not updates:
        raise ChatError("content must be a non-empty object.")
    unknown = [k for k in updates if k not in EDITABLE_FIELDS]
    if unknown:
        raise ChatError(f"Unknown content fields: {', '.join(unknown)}.")
    cleaned: dict = {}
    if "prompt_title" in updates:
        title = updates["prompt_title"]
        if not isinstance(title, str) or not title.strip():
            raise ChatError("prompt_title must not be empty.")
        if len(title.strip()) > 200:
            raise ChatError("prompt_title must be 200 characters or fewer.")
        cleaned["prompt_title"] = title.strip()
    if "raw_content" in updates:
        body = updates["raw_content"]
        if not isinstance(body, str) or not body.strip():
            raise ChatError("raw_content must not be empty.")
        cleaned["raw_content"] = body.strip()
    if "structured_content" in updates:
        sc = updates["structured_content"]
        if not isinstance(sc, dict):
            raise ChatError("structured_content must be an object.")
        unknown_sc = [k for k in sc if k not in STRUCTURED_CAPS]
        if unknown_sc:
            raise ChatError(f"Unknown structured fields: {', '.join(unknown_sc)}.")
        fields = {}
        for key, cap in STRUCTURED_CAPS.items():
            if key not in sc:
                continue
            val = sc[key]
            if not isinstance(val, str) or not val.strip():
                raise ChatError(f"{key} must be a non-empty string.")
            if len(val.strip()) > cap:
                raise ChatError(f"{key} must be {cap} characters or fewer.")
            fields[key] = val.strip()
        if not fields:
            raise ChatError("structured_content must include at least one known field.")
        cleaned["structured_content"] = fields
    if not cleaned:
        raise ChatError("Nothing to update.")
    return cleaned


def _snapshot(idea: Any) -> dict:
    sc = idea.structured_content
    return {
        "prompt_title": idea.prompt_title,
        "raw_content": idea.raw_content,
        "structured_content": dict(sc) if isinstance(sc, dict) else sc,
    }


def _apply_snapshot(idea: Any, user: Any, snapshot: dict, prefix: str) -> list:
    """Restore fields from a snapshot, auditing each change. Returns edits."""
    edits = []
    current = _snapshot(idea)
    for field in EDITABLE_FIELDS:
        if field not in snapshot:
            continue
        new_value = snapshot[field]
        if field == "structured_content" and isinstance(new_value, dict):
            updated = dict(current[field]) if isinstance(current[field], dict) else {}
            for key, val in new_value.items():
                if updated.get(key) == val:
                    continue
                edits.append(
                    IdeaEdit(
                        idea_id=idea.id,
                        editor_id=user.id,
                        field=f"{prefix}.structured_content.{key}",
                        old_value=updated.get(key),
                        new_value=val,
                    )
                )
                updated[key] = val
            idea.structured_content = updated
        else:
            if current[field] == new_value:
                continue
            edits.append(
                IdeaEdit(
                    idea_id=idea.id,
                    editor_id=user.id,
                    field=f"{prefix}.{field}",
                    old_value=current[field],
                    new_value=new_value,
                )
            )
            setattr(idea, field, new_value)
    for edit in edits:
        if getattr(edit, "instance_id", None) is None and idea.instance_id is not None:
            edit.instance_id = idea.instance_id
        db.session.add(edit)
    return edits


def iterate_idea(
    idea: Any,
    user: Any,
    content: dict,
    message: Any = None,
    model_override: Any = None,
) -> Any:
    """Apply explicit content updates as a versioned iteration."""
    from app.utils.tenancy import stamp

    cleaned = _validate_content_updates(content)
    route = resolve_route(idea, model_override)
    session = get_or_create_session(idea, user, route.model_name)
    before = _snapshot(idea)
    if message:
        _record_turn(session, "user", "iterate", message, route.model_name)
    _apply_snapshot(idea, user, cleaned, prefix="iterate")
    after = _snapshot(idea)
    turn = _record_turn(
        session,
        "assistant",
        "iterate",
        message or "Applied content iteration.",
        route.model_name,
        snapshot_before=before,
        snapshot_after=after,
    )
    db.session.commit()
    return session, turn


def rollback_turn(idea: Any, user: Any, turn_id: Any) -> Any:
    """Restore an iterate turn's before-snapshot (fully audited)."""
    from app.utils.tenancy import stamp

    turn = db.session.get(ChatTurn, turn_id)
    if turn is None:
        raise ChatNotFoundError("Turn not found.")
    session = db.session.get(ChatSession, turn.session_id)
    if session is None or session.idea_id != idea.id:
        raise ChatNotFoundError("Turn does not belong to this idea.")
    if turn.kind != "iterate" or not turn.snapshot_before:
        raise ChatError("Only iterate turns with snapshots can be rolled back.")
    route = resolve_route(idea)
    current = _snapshot(idea)
    _apply_snapshot(idea, user, dict(turn.snapshot_before), prefix="rollback")
    restored = _snapshot(idea)
    rollback = _record_turn(
        session,
        "assistant",
        "rollback",
        f"Rolled back to the state before turn {turn.id}.",
        route.model_name,
        snapshot_before=current,
        snapshot_after=restored,
    )
    db.session.commit()
    return rollback
