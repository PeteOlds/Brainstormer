import json
import uuid
from datetime import datetime, timezone, timedelta

import structlog
from pydantic import ValidationError

from app.tasks import celery, BaseTask
from app.services.ollama_client import OllamaClient
from app.services.prompt_templates import get_base_prompt, get_prompt_template
from app.schemas.ollama_schemas import validate_ollama_output
from app.extensions import db
from app.models import PromptConfig, Idea, IdeaStatus, SecondaryActionResult
from app.utils.crypto import decrypt

logger = structlog.get_logger()


class OllamaError(Exception):
    pass


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


def _generation_options(prompt_config) -> dict:
    """Ollama options dict from a prompt config (null-safe fallbacks)."""
    options = {
        "temperature": prompt_config.temperature if prompt_config.temperature is not None else 0.7,
        "top_p": prompt_config.top_p if prompt_config.top_p is not None else 0.9,
        "repeat_penalty": (prompt_config.repeat_penalty
                           if prompt_config.repeat_penalty is not None else 1.1),
        "num_predict": prompt_config.num_predict or 1000,
    }
    if getattr(prompt_config, "seed", None) is not None:
        options["seed"] = prompt_config.seed
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
    recent = (Idea.query.filter_by(prompt_config_id=prompt_config.id)
              .order_by(Idea.created_at.desc()).limit(limit_avoid).all())
    avoid_lines = [f"- {i.reference_code}: {_idea_pitch(i)[:120]}" for i in recent]
    avoid = "\n".join(avoid_lines) if avoid_lines else "none yet"

    top = (Idea.query.filter(Idea.prompt_config_id == prompt_config.id,
                             Idea.status != IdeaStatus.DISCARDED)
           .order_by(Idea.net_score.desc(), Idea.created_at.desc())
           .limit(limit_explore).all())
    explore_lines = [f"- {i.reference_code}: {_idea_pitch(i)[:120]}"
                     for i in top if _idea_pitch(i)]
    explore = "\n".join(explore_lines) if explore_lines else "none yet"
    return avoid, explore


def _record_failure(run_id: str | None, error) -> None:
    """Mark a run FAILED even if the session was poisoned by a failed flush.

    A failed flush (e.g. duplicate reference_code) puts the session into a
    state where any further commit raises PendingRollbackError. Rolling back
    first lets mark_failed persist instead of orphaning the run as RUNNING.

    Pass the exception object (not str): exceptions with empty messages
    (e.g. httpx ConnectTimeout) otherwise record a useless "Unknown error".
    """
    from app.models import PromptRun

    if isinstance(error, BaseException):
        text = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
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


@celery.task(bind=True, base=BaseTask, name="app.tasks.ollama_tasks.generate_idea",
             autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3)
def generate_idea(self, prompt_config_id: str, run_id: str | None = None):
    """Generate an idea from a prompt configuration."""
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
        logger.warning("prompt_not_found_or_inactive", prompt_config_id=prompt_config_id)
        run = _get_run()
        if run is not None:
            run.mark_failed("Prompt not found or inactive")
            db.session.commit()
        return

    run = _get_run()
    if run is not None:
        run.mark_running()
        db.session.commit()

    def _final_attempt():
        max_retries = self.max_retries if self.max_retries is not None else 0
        return self.request.retries >= max_retries

    client = OllamaClient(timeout=600.0)
    try:
        # Render prompt
        base_prompt = get_base_prompt()
        refine_template = get_prompt_template("REFINE")
        user_prompt = refine_template.render(ORIGINAL_IDEA_CONTENT="")  # Initial generation has no original idea
        
        # For initial generation, we use a different prompt.
        # The admin's prompt_body is the theme: without it every prompt
        # generates generic ideas (the body used to be silently ignored).
        from app.services.prompt_templates import PromptTemplate
        initial_prompt = PromptTemplate("initial")
        avoid, explore = _prompt_memory(prompt_config)
        prompt_text = initial_prompt.render(
            PROMPT_CONTEXT=prompt_config.prompt_body or "",
            MEMORY_AVOID=avoid,
            MEMORY_EXPLORE=explore)
        
        # Call Ollama with the prompt's generation params.
        response = client.generate_sync(
            model=prompt_config.model_name,
            prompt=prompt_text,
            system=base_prompt,
            format="json",
            options=_generation_options(prompt_config),
            keep_alive=prompt_config.keep_alive or "2h",
        )
        
        # Validate response
        structured = validate_ollama_output("REFINE", response["response"])
        
        # Create idea
        idea = Idea(
            reference_code=_generate_reference_code(),
            prompt_title=prompt_config.title,
            raw_content=response["response"],
            structured_content=structured.model_dump(),
            prompt_config_id=prompt_config.id,
            status="NEW",
        )
        db.session.add(idea)
        
        # Update prompt config
        prompt_config.last_run_at = datetime.now(timezone.utc)
        if prompt_config.cron_expression:
            # TODO: Use croniter
            prompt_config.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=prompt_config.interval_minutes)
        else:
            prompt_config.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=prompt_config.interval_minutes)
        
        db.session.flush()  # assign idea.id before linking the run
        if run is not None:
            run.mark_success(idea.id)
        db.session.commit()

        logger.info("idea_generated", idea_id=str(idea.id), prompt_id=str(prompt_config.id))

        # Slack Phase 3a: best-effort post, never blocks generation.
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
            logger.warning("slack_hook_failed", error=f"{type(e).__name__}: {str(e)[:200]}")

        # Generate and store embedding for the new idea (Phase 9.3)
        try:
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            # Combine title and content for richer embedding
            text_for_embedding = f"{idea.prompt_title}\n\n{idea.raw_content}"
            embedding = embedding_service.generate_embedding_sync(text_for_embedding)
            embedding_service.store_embedding(idea.id, embedding)
        except Exception as e:
            logger.warning("embedding_generation_failed", idea_id=str(idea.id), error=str(e))

    except json.JSONDecodeError as e:
        # One retry with stricter prompt
        if self.request.retries == 0:
            logger.warning("json_decode_failed_retrying", prompt_id=prompt_config_id, error=str(e))
            raise self.retry(exc=e, countdown=5)
        logger.error("json_decode_failed_final", prompt_id=prompt_config_id, error=str(e))
        if run is not None:
            run.mark_failed(f"Invalid model output: {e}")
            db.session.commit()
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
        client.close()


@celery.task(bind=True, base=BaseTask, name="app.tasks.ollama_tasks.run_secondary_action",
             autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def run_secondary_action(self, idea_id: str, action_type: str, model_override: str = None, run_id: str | None = None):
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

    def _retries_so_far():
        try:
            return self.request.retries or 0
        except AttributeError:
            return 0  # direct call outside a worker (tests)

    def _call_and_validate(prompt_text):
        import re
        response = client.generate_sync(
            model=model,
            prompt=prompt_text,
            system=base_prompt,
            format="json",
            options=options,
            keep_alive=keep_alive,
        )
        text = (response["response"] or "").strip()
        # Strip markdown fences small models love to add.
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return validate_ollama_output(action_type, text)

    try:
        # Get prompt template
        prompt_template = get_prompt_template(action_type)
        user_prompt = prompt_template.render(ORIGINAL_IDEA_CONTENT=idea.raw_content)
        base_prompt = get_base_prompt()
        model = model_override or idea.prompt_config.model_name if idea.prompt_config else "llama3:8b"
        prompt_config = idea.prompt_config

        # Analytical actions run cold: precision over creativity. Cap the
        # prompt's temperature at 0.3 (a lower setting is respected).
        options = _generation_options(prompt_config) if prompt_config else None
        if options is None:
            options = {"temperature": 0.3}
        else:
            options["temperature"] = min(options.get("temperature", 0.3), 0.3)
        keep_alive = (prompt_config.keep_alive
                      if prompt_config and prompt_config.keep_alive else "2h")

        # Call Ollama (same generation params as scheduled runs when known).
        try:
            validated = _call_and_validate(user_prompt)
        except ValidationError as e:
            # One strict retry: show the model its schema errors. Blind
            # autoretry below would just repeat the identical prompt.
            if _retries_so_far() > 0:
                raise
            logger.warning("validation_failed_retrying", idea_id=idea_id,
                           action_type=action_type, error=str(e)[:500])
            strict_prompt = (
                user_prompt
                + "\n\nYour previous output FAILED validation with these errors:\n"
                + str(e)[:1500]
                + "\nOutput ONLY valid JSON matching the schema. No prose, no markdown fences.")
            validated = _call_and_validate(strict_prompt)

        # Store result
        result = SecondaryActionResult(
            idea_id=idea.id,
            action_type=action_type,
            model_used=model,
            result_data=validated.model_dump(),
        )
        db.session.add(result)

        # If feasibility score, update idea
        if action_type == "FEASIBILITY_SCORE":
            idea.feasibility_score = validated.overall_score

        db.session.commit()
        if run is not None:
            run.mark_success()
            db.session.commit()
        logger.info("secondary_action_completed", idea_id=idea_id, action_type=action_type)

    except json.JSONDecodeError as e:
        if self.request.retries == 0:
            logger.warning("json_decode_failed_retrying", idea_id=idea_id, action_type=action_type, error=str(e))
            raise self.retry(exc=e, countdown=5)
        logger.error("json_decode_failed_final", idea_id=idea_id, action_type=action_type, error=str(e))
        if run is not None:
            run.mark_failed(f"Invalid model output: {e}")
            db.session.commit()
        raise
    except Exception as e:
        logger.error("secondary_action_error", idea_id=idea_id, action_type=action_type, error=str(e))
        # Roll back first: a failed commit above poisons the session, and
        # without this mark_failed raises PendingRollbackError, orphaning
        # the run as RUNNING. _final_attempt() is checked before touching
        # the session: any query on a poisoned session raises.
        if _final_attempt():
            _record_failure(run_id, e)
        raise
    finally:
        client.close()


@celery.task(base=BaseTask, name="app.tasks.ollama_tasks.check_due_prompts")
def check_due_prompts():
    """Check for due prompts and enqueue generation tasks."""
    from datetime import datetime, timezone, timedelta
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
            stale.mark_failed("Orphaned: no live job (worker restarted or queue purged)")
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
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="schedule")
        db.session.add(run)
        db.session.commit()
        job = generate_idea.delay(str(prompt.id), run_id=str(run.id))
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
    from app.services.embedding_service import get_embedding_service

    svc = get_embedding_service()
    return svc.backfill_embeddings(batch_size=batch_size)