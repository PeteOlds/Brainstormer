import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from celery.exceptions import Retry, SoftTimeLimitExceeded
from pydantic import ValidationError

from app.extensions import db
from app.models import Idea, IdeaStatus, PromptConfig, SecondaryActionResult
from app.schemas.ollama_schemas import validate_ollama_output
from app.services.build_runtime import (
    _allocate_build_port,
    _derive_runbook,
    _ensure_requirements,
    _extract_runtime_info,
    _host_network_ip,
    _infer_entry_command,
    _inject_root_route,
    _merge_files,
    _pretty_cmd,
    _rewrite_compose_host_port,
    _rewrite_source_port,
)
from app.services.ollama_client import OllamaClient, OllamaError
from app.services.prompt_templates import get_base_prompt, get_prompt_template
from app.tasks import BaseTask, celery, enqueue_generation
from app.utils.crypto import decrypt

logger = structlog.get_logger()
SECONDARY_SOFT_TIME_LIMIT = int(os.environ.get("SECONDARY_SOFT_TIME_LIMIT", "1800"))
SECONDARY_TIME_LIMIT = int(os.environ.get("SECONDARY_TIME_LIMIT", "1860"))


def _answer_question(entry: str) -> str:
    """Normalized question text from a stored "Q: ...\\nA: ..." answer."""
    first = str(entry).splitlines()[0] if str(entry).strip() else ""
    q = first[2:].strip() if first.startswith("Q:") else first.strip()
    return " ".join(q.lower().split())


def _accumulate_answers(idea_id, action_type, new_answers):
    """Union of prior versions' answers with the new ones (PRD/DESIGN_DOC).

    Answers used to be stored per-version, so each rerun displayed only its
    own submission and earlier answers "disappeared" from the current
    version. The new version now carries everything answered so far, so the
    current document always shows the full Q&A history. Repeats (same
    question) keep the newest text.
    """
    from app.models import SecondaryActionResult

    keyed: dict = {}
    unkeyed: list = []
    prior = SecondaryActionResult.query.filter_by(
        idea_id=idea_id, action_type=action_type
    ).all()
    for row in prior:
        for entry in row.answers or []:
            key = _answer_question(entry)
            if key:
                keyed.setdefault(key, entry)
            elif str(entry).strip():
                unkeyed.append(entry)
    for entry in new_answers or []:
        key = _answer_question(entry)
        if key:
            keyed[key] = entry
        elif str(entry).strip():
            unkeyed.append(entry)
    return list(keyed.values()) + unkeyed


def _drop_answered_questions(validated, idea_id, action_type):
    """Remove regenerated open questions already answered on prior versions.

    Stored answers look like "Q: <question>\\nA: <answer>". A new question
    matching an answered one (SequenceMatcher >= 0.8) is dropped, so users
    are never asked the same thing twice. Returns the (possibly copied)
    validated model; an empty list is valid (means: nothing left unclear).
    """
    from difflib import SequenceMatcher

    from app.models import SecondaryActionResult

    questions = list(getattr(validated, "open_questions", None) or [])
    if not questions:
        return validated

    answered = []
    prior = SecondaryActionResult.query.filter_by(
        idea_id=idea_id, action_type=action_type
    ).all()
    for row in prior:
        for entry in row.answers or []:
            first_line = str(entry).splitlines()[0] if str(entry).strip() else ""
            q = (
                first_line[2:].strip()
                if first_line.startswith("Q:")
                else first_line.strip()
            )
            if q:
                answered.append(q)
    if not answered:
        return validated

    def _is_repeat(q):
        qn = " ".join(str(q).lower().split())
        return any(
            SequenceMatcher(None, qn, " ".join(a.lower().split())).ratio() >= 0.8
            for a in answered
        )

    kept = [q for q in questions if not _is_repeat(q)]
    if len(kept) != len(questions):
        logger.info(
            "open_questions_deduped",
            idea_id=str(idea_id),
            action_type=action_type,
            dropped=len(questions) - len(kept),
        )
        validated = validated.model_copy(update={"open_questions": kept})
    return validated


BUILD_STAGE_INSTRUCTIONS = {
    1: (
        "CHECKPOINT 1 of 3 — data and happy path. Implement the schema/data "
        "layer, core service logic and one end-to-end happy-path check. Do "
        "not spend effort on visual polish; keep the file list minimal."
    ),
    2: (
        "CHECKPOINT 2 of 3 — screens and routes. Keep every existing route "
        "and behaviour intact; add the screens/endpoints the design calls "
        "for and wire them to the data layer built earlier."
    ),
    3: (
        "CHECKPOINT 3 of 3 — hardening. Preserve the existing app and add "
        "edge cases, empty/error states and the remaining checks. Return "
        "only the files you add or change, with complete contents."
    ),
}


def build_stage_instruction(stage: Any) -> str:
    """Instruction text for a checkpoint number (1–3, default 1)."""
    try:
        value = int(stage)
    except (TypeError, ValueError):
        value = 1
    return BUILD_STAGE_INSTRUCTIONS.get(value, BUILD_STAGE_INSTRUCTIONS[1])


def _generate_reference_code() -> str:
    """Generate a unique reference code like IDEA-XXXX."""
    # Max over codes parsed in Python (the ideas table is tiny). Do NOT
    # `order_by(Idea.id)`: ids are random UUIDs, so that returned an
    # arbitrary row and re-issued an existing code (IDEA-0005) on every
    # insert -> UniqueViolation, poisoned session, orphaned RUNNING runs.
    # Non-numeric codes (if any) are skipped rather than resetting to 0001.
    nums = []
    for (code,) in db.session.query(Idea.reference_code).all():
        if not code:
            continue
        try:
            nums.append(int(code.split("-")[1]))
        except (ValueError, IndexError):
            continue
    if nums:
        return f"IDEA-{max(nums) + 1:04d}"
    return "IDEA-0001"


def _generation_options(prompt_config, stage_cfg=None) -> dict:
    """Generation options dict (null-safe fallbacks).

    Stage config wins over the prompt for temperature/top_p/num_predict;
    absent rows change nothing.
    """
    options = {
        "temperature": (
            prompt_config.temperature if prompt_config.temperature is not None else 0.7
        ),
        "top_p": prompt_config.top_p if prompt_config.top_p is not None else 0.9,
        "repeat_penalty": (
            prompt_config.repeat_penalty
            if prompt_config.repeat_penalty is not None
            else 1.1
        ),
        "num_predict": prompt_config.num_predict or 1000,
    }
    if getattr(prompt_config, "seed", None) is not None:
        options["seed"] = prompt_config.seed
    # Context size is deliberately opt-in: local models share VRAM with the
    # rest of the machine, so an unset value keeps Ollama's own default.
    configured_ctx = getattr(prompt_config, "num_ctx", None)
    if configured_ctx is not None:
        options["num_ctx"] = configured_ctx
    for key in ("temperature", "top_p", "num_predict", "num_ctx"):
        if stage_cfg and stage_cfg.get(key) is not None:
            options[key] = stage_cfg[key]
    return options


def _idea_pitch(idea) -> str:
    """One-line summary of an idea for memory sections."""
    sc = idea.structured_content
    if isinstance(sc, dict):
        return (sc.get("elevator_pitch") or "").strip()
    if isinstance(sc, str):
        try:
            return (json.loads(sc).get("elevator_pitch") or "").strip()
        except (ValueError, AttributeError):
            return ""
    return ""


def _prompt_memory(prompt_config, limit_avoid=10, limit_explore=3):
    """Avoid/explore memory for a prompt (PRD §9.1).

    Recomputed per run, never stored: recent titles to steer away from,
    top-voted themes to explore. "none yet" keeps new prompts unaffected.
    """
    recent = (
        Idea.query.filter_by(prompt_config_id=prompt_config.id)
        .order_by(Idea.created_at.desc())
        .limit(limit_avoid)
        .all()
    )
    avoid_lines = [f"- {i.reference_code}: {_idea_pitch(i)[:120]}" for i in recent]
    avoid = "\n".join(avoid_lines) if avoid_lines else "none yet"

    top = (
        Idea.query.filter(
            Idea.prompt_config_id == prompt_config.id,
            Idea.status != IdeaStatus.DROP,
        )
        .order_by(Idea.net_score.desc(), Idea.created_at.desc())
        .limit(limit_explore)
        .all()
    )
    explore_lines = [
        f"- {i.reference_code}: {_idea_pitch(i)[:120]}" for i in top if _idea_pitch(i)
    ]
    explore = "\n".join(explore_lines) if explore_lines else "none yet"
    return avoid, explore
