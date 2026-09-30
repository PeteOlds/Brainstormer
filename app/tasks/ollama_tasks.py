import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from pydantic import ValidationError

from app.extensions import db
from app.models import Idea, IdeaStatus, PromptConfig, SecondaryActionResult
from app.schemas.ollama_schemas import validate_ollama_output
from app.services.ollama_client import OllamaClient, OllamaError
from app.services.prompt_templates import get_base_prompt, get_prompt_template
from app.tasks import BaseTask, celery
from app.utils.crypto import decrypt

logger = structlog.get_logger()


class _AbortAction(Exception):
    """Run already marked failed inside; unwind without Celery retry."""


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
    for key in ("temperature", "top_p", "num_predict"):
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


def _record_failure(run_id: str | None, error) -> None:
    """Mark a run FAILED even if the session was poisoned by a failed flush.

    A failed flush (e.g. duplicate reference_code) puts the session into a
    state where any further commit raises PendingRollbackError. Rolling back
    first lets mark_failed persist instead of orphaning the run as RUNNING.

    Pass the exception object (not str): exceptions with empty messages
    (e.g. httpx ConnectTimeout) otherwise record a useless "Unknown error".
    Include Ollama response body if available for diagnosis.
    """
    from app.models import PromptRun

    if isinstance(error, BaseException):
        text = (
            f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
        )
        # Include Ollama response body if available
        if isinstance(error, OllamaError) and error.response_body:
            text += f" | Body: {error.response_body[:500]}"
    else:
        text = str(error) if error else "Unknown error"
    db.session.rollback()
    run = None
    if run_id:
        try:
            run = db.session.get(PromptRun, uuid.UUID(str(run_id)))
        except (ValueError, TypeError):
            run = None
    if run is not None:
        run.mark_failed(text)
        db.session.commit()


@celery.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.ollama_tasks.generate_idea",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def generate_idea(
    self,
    prompt_config_id: str,
    run_id: str | None = None,
    instance_id: str | None = None,
):
    """Generate an idea from a prompt configuration.

    instance_id scopes the run to one instance: the prompt must belong to
    it, and the run, idea and follow-on rows inherit it. None keeps the
    legacy unscoped behaviour.
    """
    from app.models import PromptRun

    def _get_run():
        if not run_id:
            return None
        try:
            return db.session.get(PromptRun, uuid.UUID(str(run_id)))
        except (ValueError, TypeError):
            return None

    prompt_config = PromptConfig.query.get(prompt_config_id)
    if not prompt_config or not prompt_config.is_active:
        logger.warning(
            "prompt_not_found_or_inactive", prompt_config_id=prompt_config_id
        )
        run = _get_run()
        if run is not None:
            run.mark_failed("Prompt not found or inactive")
            db.session.commit()
        return
    if (
        instance_id is not None
        and prompt_config.instance_id is not None
        and str(prompt_config.instance_id) != str(instance_id)
    ):
        logger.warning(
            "prompt_instance_mismatch",
            prompt_config_id=prompt_config_id,
            instance_id=instance_id,
        )
        run = _get_run()
        if run is not None:
            run.mark_failed("Prompt belongs to another instance")
            db.session.commit()
        return
    run = _get_run()
    if (
        run is not None
        and run.instance_id is None
        and prompt_config.instance_id is not None
    ):
        run.instance_id = prompt_config.instance_id

    if run is not None:
        run.mark_running()
        db.session.commit()

    def _final_attempt():
        max_retries = self.max_retries if self.max_retries is not None else 0
        return self.request.retries >= max_retries

    client = OllamaClient(timeout=600.0)
    model = prompt_config.model_name
    provider = (prompt_config.provider or "ollama").lower()
    # Spark stage config wins over the prompt; absent rows change nothing.
    from app.models import resolve_stage as _resolve_stage

    spark_cfg = _resolve_stage(prompt_config.instance_id, "SPARK")
    if spark_cfg.get("model_name"):
        model = spark_cfg["model_name"]
    if spark_cfg.get("provider"):
        provider = spark_cfg["provider"].lower()
    hosted = provider != "ollama"
    logger.info(
        "ollama_task_start",
        task="generate_idea",
        base_url=None if hosted else client.base_url,
        model=model,
        provider=provider,
        prompt_id=prompt_config_id,
    )

    # Pre-flight: verify model exists in this Ollama instance (local only;
    # hosted keys prove themselves at call time).
    if not hosted and not client.is_model_available(model):
        err_msg = f"Model '{model}' not installed at {client.base_url}"
        logger.error(
            "ollama_model_missing",
            base_url=client.base_url,
            model=model,
            prompt_id=prompt_config_id,
        )
        run = _get_run()
        if run is not None:
            run.mark_failed(err_msg)
            db.session.commit()
        return

    try:
        # Render prompt
        base_prompt = get_base_prompt()
        refine_template = get_prompt_template("REFINE")
        user_prompt = refine_template.render(
            ORIGINAL_IDEA_CONTENT=""
        )  # Initial generation has no original idea

        # For initial generation, we use a different prompt.
        # The admin's prompt_body is the theme: without it every prompt
        # generates generic ideas (the body used to be silently ignored).
        from app.services.prompt_templates import PromptTemplate

        initial_prompt = PromptTemplate("initial")
        avoid, explore = _prompt_memory(prompt_config)
        prompt_text = initial_prompt.render(
            PROMPT_CONTEXT=prompt_config.prompt_body or "",
            MEMORY_AVOID=avoid,
            MEMORY_EXPLORE=explore,
        )

        # Hosted providers route via LiteLLM (budget gates, spend log);
        # Ollama keeps the exact legacy call sequence.
        if hosted:
            from types import SimpleNamespace

            from app.services.llm_backends import (
                BudgetExhausted,
                ProviderError,
                generate_for_prompt,
            )

            options = _generation_options(prompt_config, spark_cfg)
            route = SimpleNamespace(
                provider=provider,
                model_name=model,
                instance_id=prompt_config.instance_id,
            )
            try:
                result = generate_for_prompt(
                    route,
                    prompt_text,
                    system=base_prompt,
                    options=options,
                    keep_alive=prompt_config.keep_alive or "2h",
                    timeout=600.0,
                )
            except BudgetExhausted as e:
                logger.error("ai_budget_exhausted", prompt_id=prompt_config_id)
                run = _get_run()
                if run is not None:
                    run.mark_failed(str(e))
                    db.session.commit()
                return
            except ProviderError as e:
                if not e.retryable:
                    run = _get_run()
                    if run is not None:
                        run.mark_failed(str(e))
                        db.session.commit()
                    return
                raise
            raw_text = result.text
        else:
            # Call Ollama with the prompt's generation params.
            try:
                response = client.generate_sync(
                    model=model,
                    prompt=prompt_text,
                    system=base_prompt,
                    format="json",
                    options=_generation_options(prompt_config, spark_cfg),
                    keep_alive=prompt_config.keep_alive or "2h",
                )
            except OllamaError as e:
                logger.error(
                    "ollama_generate_failed",
                    base_url=client.base_url,
                    model=model,
                    status=e.status_code,
                    body=e.response_body,
                )
                raise
            raw_text = response["response"]

        # Validate response
        structured = validate_ollama_output("REFINE", raw_text)

        # Create idea
        idea = Idea(
            reference_code=_generate_reference_code(),
            prompt_title=prompt_config.title,
            raw_content=raw_text,
            structured_content=structured.model_dump(),
            prompt_config_id=prompt_config.id,
            instance_id=prompt_config.instance_id,
            status="SPARK",
        )
        db.session.add(idea)

        # Update prompt config
        prompt_config.last_run_at = datetime.now(timezone.utc)
        if prompt_config.cron_expression:
            # TODO: Use croniter
            prompt_config.next_run_at = datetime.now(timezone.utc) + timedelta(
                minutes=prompt_config.interval_minutes
            )
        else:
            prompt_config.next_run_at = datetime.now(timezone.utc) + timedelta(
                minutes=prompt_config.interval_minutes
            )

        db.session.flush()  # assign idea.id before linking the run
        if run is not None:
            run.mark_success(idea.id)
        db.session.commit()

        logger.info(
            "idea_generated", idea_id=str(idea.id), prompt_id=str(prompt_config.id)
        )

        # Generate and store embedding for the new idea (Phase 9.3),
        # then auto-discard near-duplicates so users are never asked
        # about the same idea twice.
        duplicate_of = None
        duplicate_score = None
        try:
            from app.services.embedding_service import (
                embedding_text,
                get_embedding_service,
            )

            embedding_service = get_embedding_service()
            embedding = embedding_service.generate_embedding_sync(
                embedding_text(idea), instance_id=idea.instance_id
            )
            embedding_service.store_embedding(idea.id, embedding)
            try:
                dedup_threshold = float(os.getenv("DEDUP_SIMILARITY_THRESHOLD", "0.97"))
            except ValueError:
                dedup_threshold = 0.97
            matches = embedding_service.find_similar_to_embedding(
                embedding,
                threshold=dedup_threshold,
                limit=1,
                exclude_id=idea.id,
                instance_id=idea.instance_id,
            )
            if matches:
                duplicate_of, duplicate_score = matches[0]
                idea.status = "DROP"
                db.session.commit()
                logger.info(
                    "idea_auto_discarded",
                    idea_id=str(idea.id),
                    reference_code=idea.reference_code,
                    duplicate_of=duplicate_of.reference_code,
                    score=round(float(duplicate_score), 4),
                )
        except Exception as e:
            logger.warning(
                "embedding_generation_failed", idea_id=str(idea.id), error=str(e)
            )

        if duplicate_of is None:
            # Slack Phase 3a: best-effort post, never blocks generation.
            # Duplicates stay silent: nothing new to announce.
            try:
                from flask import current_app

                from app.services import slack_service

                channel = (prompt_config.slack_channel or "").strip()
                if channel:
                    slack_service.post_idea(
                        channel,
                        idea.to_dict(),
                        current_app.config.get("APP_BASE_URL", "http://localhost:8000"),
                    )
            except Exception as e:
                logger.warning(
                    "slack_hook_failed", error=f"{type(e).__name__}: {str(e)[:200]}"
                )

    except json.JSONDecodeError as e:
        # One retry with stricter prompt
        if self.request.retries == 0:
            logger.warning(
                "json_decode_failed_retrying", prompt_id=prompt_config_id, error=str(e)
            )
            raise self.retry(exc=e, countdown=5)
        logger.error(
            "json_decode_failed_final", prompt_id=prompt_config_id, error=str(e)
        )
        if run is not None:
            run.mark_failed(f"Invalid model output: {e}")
            db.session.commit()
        raise
    except OllamaError:
        # Re-raise OllamaError so autoretry can handle it; _record_failure will include body on final attempt
        raise
    except Exception as e:
        logger.error("ollama_error", prompt_id=prompt_config_id, error=str(e))
        # Only record FAILED on the final attempt; intermediate failures
        # keep the run in RUNNING while autoretry keeps trying.
        # _record_failure rolls back first so a poisoned session (failed
        # flush) cannot orphan the run as RUNNING via PendingRollbackError.
        # NOTE: _final_attempt() is checked before touching the session:
        # any query (even re-fetching the run) on a poisoned session raises.
        if _final_attempt():
            _record_failure(run_id, e)
        raise
    finally:
        if not hosted:
            client.close()


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


@celery.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.ollama_tasks.run_secondary_action",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def run_secondary_action(
    self,
    idea_id: str,
    action_type: str,
    model_override: str = None,
    run_id: str | None = None,
    extra_context: dict | None = None,
):
    """Run a secondary action on an existing idea."""
    from app.models import PromptRun

    def _get_run():
        if not run_id:
            return None
        try:
            return db.session.get(PromptRun, uuid.UUID(str(run_id)))
        except (ValueError, TypeError):
            return None

    def _final_attempt():
        max_retries = self.max_retries if self.max_retries is not None else 0
        return self.request.retries >= max_retries

    idea = Idea.query.get(idea_id)
    if not idea:
        logger.warning("idea_not_found", idea_id=idea_id)
        run = _get_run()
        if run is not None:
            run.mark_failed("Idea not found")
            db.session.commit()
        return

    run = _get_run()
    if run is not None:
        run.mark_running()
        db.session.commit()

    client = OllamaClient(timeout=600.0)
    model = (
        model_override or idea.prompt_config.model_name
        if idea.prompt_config
        else "llama3:8b"
    )
    provider_cfg = idea.prompt_config
    provider = (provider_cfg.provider or "ollama").lower() if provider_cfg else "ollama"
    # Stage config wins over the prompt (explicit run args already won
    # above via model_override); absent rows change nothing.
    from app.models import resolve_stage

    stage_cfg = resolve_stage(idea.instance_id, idea.status.value)
    if not model_override and stage_cfg.get("model_name"):
        model = stage_cfg["model_name"]
    if stage_cfg.get("provider"):
        provider = stage_cfg["provider"].lower()
    hosted = provider != "ollama"
    # A model override on a hosted idea is a litellm model id; on a
    # prompt-less idea the override alone cannot imply a provider.
    if model_override and not provider_cfg:
        hosted = False
        provider = "ollama"
    logger.info(
        "ollama_task_start",
        task="run_secondary_action",
        base_url=None if hosted else client.base_url,
        model=model,
        provider=provider,
        action_type=action_type,
        idea_id=idea_id,
    )

    # Pre-flight: verify model exists in this Ollama instance (local only)
    if not hosted and not client.is_model_available(model):
        err_msg = f"Model '{model}' not installed at {client.base_url}"
        logger.error(
            "ollama_model_missing",
            base_url=client.base_url,
            model=model,
            action_type=action_type,
            idea_id=idea_id,
        )
        run = _get_run()
        if run is not None:
            run.mark_failed(err_msg)
            db.session.commit()
        return

    def _retries_so_far():
        try:
            return self.request.retries or 0
        except AttributeError:
            return 0  # direct call outside a worker (tests)

    def _call_and_validate(prompt_text):
        import re

        if hosted:
            from types import SimpleNamespace

            from app.services.llm_backends import (
                BudgetExhausted,
                ProviderError,
                generate_for_prompt,
            )

            shim = SimpleNamespace(
                provider=provider,
                model_name=model,
                instance_id=idea.instance_id,
            )
            try:
                result = generate_for_prompt(
                    shim,
                    prompt_text,
                    system=base_prompt,
                    options=options,
                    timeout=600.0,
                )
            except BudgetExhausted as e:
                run = _get_run()
                if run is not None:
                    run.mark_failed(str(e))
                    db.session.commit()
                raise _AbortAction(str(e))
            except ProviderError as e:
                if not e.retryable:
                    run = _get_run()
                    if run is not None:
                        run.mark_failed(str(e))
                        db.session.commit()
                    raise _AbortAction(str(e))
                raise
            text = (result.text or "").strip()
        else:
            try:
                response = client.generate_sync(
                    model=model,
                    prompt=prompt_text,
                    system=base_prompt,
                    format="json",
                    options=options,
                    keep_alive=keep_alive,
                )
            except OllamaError as e:
                logger.error(
                    "ollama_generate_failed",
                    base_url=client.base_url,
                    model=model,
                    action_type=action_type,
                    status=e.status_code,
                    body=e.response_body,
                )
                raise
            text = (response["response"] or "").strip()
        # Strip markdown fences small models love to add.
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return validate_ollama_output(action_type, text)

    try:
        # Get prompt template
        prompt_template = get_prompt_template(action_type)

        # Build supporting material for all secondary actions (they all now use it)
        from app.services.action_context import build_idea_context

        supporting_material = build_idea_context(idea)

        user_prompt = prompt_template.render(
            ORIGINAL_IDEA_CONTENT=idea.raw_content,
            SUPPORTING_MATERIAL=supporting_material,
        )
        # Rerun answers (PRD_DOC open questions): appended verbatim so the
        # model regenerates with the human's input. Ignored if empty.
        answers = (extra_context or {}).get("answers") or []
        if answers:
            numbered = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(answers))
            user_prompt += (
                "\n\n### USER ANSWERS (use these to resolve open questions):\n"
                + numbered
            )
        # Selected opencode skills + guideline docs (admin run dialog).
        # Injected after the brief so they steer generation; capped so a
        # large selection cannot blow the context window.
        skill_names = (
            (extra_context or {}).get("skills") or stage_cfg.get("skills") or []
        )
        guideline_names = (
            (extra_context or {}).get("guidelines") or stage_cfg.get("guidelines") or []
        )
        if skill_names or guideline_names:
            from app.services.discovery import read_guideline, read_skill_body

            injection_budget = 6000
            chunks = []
            for name in list(dict.fromkeys(skill_names))[:20]:
                body = (read_skill_body(name) or "")[:injection_budget]
                if not body:
                    continue
                chunks.append(f"Skill '{name}':\n{body}")
                injection_budget -= len(chunks[-1])
                if injection_budget <= 0:
                    break
            for name in list(dict.fromkeys(guideline_names))[:20]:
                if injection_budget <= 0:
                    break
                body = (read_guideline(name) or "")[:injection_budget]
                if not body:
                    continue
                chunks.append(f"Guideline '{name}':\n{body}")
                injection_budget -= len(chunks[-1])
            if chunks:
                user_prompt += (
                    "\n\n### SELECTED SKILLS & GUIDELINES "
                    "(follow these while generating):\n" + "\n\n".join(chunks)
                )
            logger.info(
                "action_context_injected",
                idea_id=idea_id,
                action_type=action_type,
                skills=skill_names,
                guidelines=guideline_names,
            )
        base_prompt = get_base_prompt()
        model = (
            model_override or idea.prompt_config.model_name
            if idea.prompt_config
            else "llama3:8b"
        )
        prompt_config = idea.prompt_config

        # Analytical actions run cold: precision over creativity. Cap the
        # prompt's temperature at 0.3 (a lower setting is respected).
        # Stage config overrides the prompt values before the cap.
        options = (
            _generation_options(prompt_config, stage_cfg) if prompt_config else None
        )
        if options is None:
            options = {"temperature": 0.3}
        else:
            options["temperature"] = min(options.get("temperature", 0.3), 0.3)
        # Secondary outputs (competitor lists, 7-section PRDs) are far longer
        # than ideas: floor output tokens at 4000 so generation isn't cut off
        # mid-object (truncated JSON fails validation unrecoverably). A higher
        # per-prompt setting is respected.
        # Complex actions (BMC, GTM, Hypothesis, Market Sizing, Competitors)
        # need more tokens. Five Forces and PESTEL also run long on verbose
        # models (truncated JSON observed in prod) — same floor.
        complex_actions = {
            "BUSINESS_MODEL_CANVAS",
            "GTM_STRATEGY",
            "HYPOTHESIS_TEST",
            "MARKET_SIZING",
            "COMPETITORS",
            "FIVE_FORCES",
            "PESTEL",
        }
        min_tokens = 8000 if action_type in complex_actions else 4000
        options["num_predict"] = max(options.get("num_predict") or 0, min_tokens)
        keep_alive = (
            prompt_config.keep_alive
            if prompt_config and prompt_config.keep_alive
            else "2h"
        )

        # Call Ollama (same generation params as scheduled runs when known).
        try:
            validated = _call_and_validate(user_prompt)
        except ValidationError as e:
            # One strict retry: show the model its schema errors. Blind
            # autoretry below would just repeat the identical prompt.
            if _retries_so_far() > 0:
                raise
            logger.warning(
                "validation_failed_retrying",
                idea_id=idea_id,
                action_type=action_type,
                error=str(e)[:500],
            )
            strict_prompt = (
                user_prompt
                + "\n\nYour previous output FAILED validation with these errors:\n"
                + str(e)[:1500]
                + "\nOutput ONLY valid JSON matching the schema. No prose, no markdown fences."
            )
            validated = _call_and_validate(strict_prompt)

        # Drop re-asked questions: anything already answered on a prior
        # version must not come back (models repeat them despite prompt
        # instructions). Deterministic, independent of model compliance.
        if action_type in ("PRD_DOC", "DESIGN_DOC"):
            validated = _drop_answered_questions(validated, idea.id, action_type)

        # Store result. PRD/DESIGN_DOC are versioned: supersede the
        # current version instead of deleting history, so per-document
        # comment threads stay pinned to their version.
        if action_type in ("PRD_DOC", "DESIGN_DOC"):
            current = SecondaryActionResult.query.filter_by(
                idea_id=idea.id, action_type=action_type, is_current=True
            ).all()
            next_version = max([r.version for r in current], default=0) + 1
            for r in current:
                r.is_current = False
        else:
            next_version = 1
        result = SecondaryActionResult(
            idea_id=idea.id,
            action_type=action_type,
            model_used=model,
            result_data=validated.model_dump(),
            version=next_version,
            is_current=True,
            answers=answers or None,
            instance_id=idea.instance_id,
        )
        db.session.add(result)

        # If feasibility score, update idea
        if action_type == "FEASIBILITY_SCORE":
            idea.feasibility_score = validated.overall_score

        db.session.commit()
        if run is not None:
            run.mark_success()
            db.session.commit()
        logger.info(
            "secondary_action_completed", idea_id=idea_id, action_type=action_type
        )

    except json.JSONDecodeError as e:
        if self.request.retries == 0:
            logger.warning(
                "json_decode_failed_retrying",
                idea_id=idea_id,
                action_type=action_type,
                error=str(e),
            )
            raise self.retry(exc=e, countdown=5)
        logger.error(
            "json_decode_failed_final",
            idea_id=idea_id,
            action_type=action_type,
            error=str(e),
        )
        if run is not None:
            run.mark_failed(f"Invalid model output: {e}")
            db.session.commit()
        raise
    except OllamaError:
        # Re-raise OllamaError so autoretry can handle it; _record_failure will include body on final attempt
        raise
    except _AbortAction:
        # Budget/config failures already recorded on the run; just stop.
        return
    except Exception as e:
        logger.error(
            "secondary_action_error",
            idea_id=idea_id,
            action_type=action_type,
            error=str(e),
        )
        # Roll back first: a failed commit above poisons the session, and
        # without this mark_failed raises PendingRollbackError, orphaning
        # the run as RUNNING. _final_attempt() is checked before touching
        # the session: any query on a poisoned session raises.
        if _final_attempt():
            _record_failure(run_id, e)
        raise
    finally:
        if not hosted:
            client.close()


@celery.task(base=BaseTask, name="app.tasks.ollama_tasks.check_due_prompts")
def check_due_prompts():
    """Check for due prompts and enqueue generation tasks."""
    from datetime import datetime, timedelta, timezone

    from app.models import PromptRun, PromptRunStatus

    now = datetime.now(timezone.utc)

    # Reconcile orphans: runs whose worker died or whose job was lost stay
    # PENDING/RUNNING forever and lie on the dashboard. A healthy run is
    # picked up in seconds and finishes within the task time limit.
    try:
        stale_pending = PromptRun.query.filter(
            PromptRun.status.in_([PromptRunStatus.PENDING, PromptRunStatus.RUNNING]),
            PromptRun.created_at < now - timedelta(minutes=45),
        ).all()
        for stale in stale_pending:
            stale.mark_failed(
                "Orphaned: no live job (worker restarted or queue purged)"
            )
        if stale_pending:
            db.session.commit()
            logger.info("reconciled_orphaned_runs", count=len(stale_pending))
    except Exception as e:
        logger.warning("orphan_reconcile_failed", error=str(e))
        db.session.rollback()

    due_prompts = PromptConfig.query.filter(
        PromptConfig.is_active == True,
        PromptConfig.next_run_at <= now,
    ).all()

    from app.models import PromptRun, PromptRunStatus

    enqueued = 0
    for prompt in due_prompts:
        # Skip prompts that already have a live run: without this, every
        # 60s tick re-enqueues them and the queue grows without bound.
        live = PromptRun.query.filter(
            PromptRun.prompt_config_id == prompt.id,
            PromptRun.status.in_([PromptRunStatus.PENDING, PromptRunStatus.RUNNING]),
        ).count()
        if live:
            continue
        run = PromptRun(
            prompt_config_id=prompt.id,
            triggered_by="schedule",
            instance_id=prompt.instance_id,
        )
        db.session.add(run)
        db.session.commit()
        job = generate_idea.delay(
            str(prompt.id),
            run_id=str(run.id),
            instance_id=str(prompt.instance_id) if prompt.instance_id else None,
        )
        run.job_id = job.id
        db.session.commit()
        enqueued += 1

    logger.info("checked_due_prompts", due=len(due_prompts), enqueued=enqueued)


@celery.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.ollama_tasks.backfill_embeddings",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
)
def backfill_embeddings(self, batch_size: int = 10) -> dict:
    """Generate embeddings for all ideas that don't have them.

    Returns stats: {"processed": int, "succeeded": int, "failed": int}
    """
    import asyncio

    from app.services.embedding_service import get_embedding_service

    svc = get_embedding_service()
    return asyncio.run(svc.backfill_embeddings(batch_size=batch_size))
