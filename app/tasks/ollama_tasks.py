import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from celery.exceptions import Retry, SoftTimeLimitExceeded
from pydantic import ValidationError

from app.extensions import db
from app.models import Idea, IdeaStatus, PromptConfig, SecondaryActionResult
from app.schemas.ollama_schemas import validate_ollama_output
from app.services.ollama_client import OllamaClient, OllamaError
from app.services.prompt_templates import get_base_prompt, get_prompt_template
from app.tasks import BaseTask, celery, enqueue_generation
from app.utils.crypto import decrypt

# Build runtime/runbook/port helpers (moved to app.services.build_runtime for
# maintainability). Re-exported here so existing callers/tests keep working.
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




logger = structlog.get_logger()

# Secondary actions (PRD/Design/Build/analysis) get their own ceiling.
# Code builds on a CPU-only host routinely exceed the 600 s global
# default; idea generation keeps the short global limit so a stuck
# generation fails fast. Env-tunable for slower hosts.
SECONDARY_SOFT_TIME_LIMIT = int(os.environ.get("SECONDARY_SOFT_TIME_LIMIT", "1800"))
SECONDARY_TIME_LIMIT = int(os.environ.get("SECONDARY_TIME_LIMIT", "1860"))


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
                # Queue cutoff: explicit per-instance choice to retry later
                # (visible countdown) instead of failing the run.
                retry_after = getattr(e, "retry_after", None)
                if retry_after and not _final_attempt():
                    logger.info(
                        "ai_budget_queued",
                        prompt_id=prompt_config_id,
                        retry_after=retry_after,
                    )
                    raise self.retry(exc=e, countdown=retry_after)
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
    except Retry:
        # Budget-queue self.retry(): not a failure, hand back to Celery.
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





















# Map common import names to their pip package names.




def _write_confirmed_build(idea, build_target, build_root, run_id):
    """Write a previewed manifest to its target (confirm run, no LLM).

    Loads the current unwritten BUILD_CODE preview for this target, derives
    the runbook, then writes its stored files and appends a new version
    carrying the write report. A build with no runnable command is refused
    before anything is written, so "Built" always means runnable. Every
    failure marks the run failed with a plain message and returns.
    """
    from app.models import SecondaryActionResult
    from app.schemas.ollama_schemas import BuildCodeOutput
    from app.services.build_service import (
        BuildError,
        existing_repo_files,
        server_path,
        write_manifest,
    )
    from pydantic import ValidationError

    preview = SecondaryActionResult.query.filter_by(
        idea_id=idea.id, action_type="BUILD_CODE", is_current=True
    ).first()
    if (
        preview is None
        or preview.result_data.get("written")
        or str(preview.target_id or "") != str(build_target.id)
    ):
        _record_failure(
            run_id,
            "No pending preview for this target — run the build preview first.",
        )
        return
    try:
        manifest = BuildCodeOutput.model_validate(preview.result_data)
    except ValidationError as exc:
        _record_failure(run_id, f"Stored preview is corrupt: {exc}")
        return
    try:
        manifest_files = [f.model_dump() for f in manifest.files]
        manifest_paths = [f["path"] for f in manifest_files]
        # The preview is usually incremental: it only contains files the
        # model changed. Merge it over the repo on disk so runtime and
        # runbook derivation see the Dockerfile/compose/entry points that
        # already exist. The manifest still wins on conflicts.
        context = _merge_files(
            existing_repo_files(str(build_root)),
            manifest_files,
        )
        runtime = _extract_runtime_info(context, preferred_paths=manifest_paths)
        # Port check + compose/source rewrite happen BEFORE writing so the
        # on-disk files already publish a free host port.
        runtime, manifest_files, port_report = _allocate_build_port(
            runtime, manifest_files
        )
    except BuildError as exc:
        _record_failure(run_id, str(exc))
        return
    # Derive the runbook BEFORE writing: a build with no runnable command
    # is not runnable, so it must fail here rather than write files, report
    # success, and only refuse later at one-click run time.
    try:
        runbook = _derive_runbook(
            context,
            runtime.get("start_command"),
            server_path(str(build_root)),
            str(build_root),
            start_dir=runtime.get("start_dir"),
        )
    except Exception:
        runbook = None
    if not runbook or not runbook.get("run_argv"):
        _record_failure(
            run_id,
            "This build has no runnable entry point — no Dockerfile CMD, "
            "package.json start script, or recognised app file (app.py, "
            "main.py, …) to run. Nothing was written. Re-run the preview "
            "and ask for a runnable app with an entry point.",
        )
        return
    if runbook.get("command"):
        runtime["start_command"] = runbook["command"]
    # Ensure the app has a root route so "Open app" doesn't 404 for
    # non-technical users. Only inject if no existing root route.
    _inject_root_route(manifest_files)
    _ensure_requirements(manifest_files)
    try:
        written, skipped = write_manifest(
            build_root,
            manifest_files,
        )
    except BuildError as exc:
        _record_failure(run_id, str(exc))
        return
    report = [f"wrote {w['path']} ({w['bytes']} B)" for w in written]
    report += [f"skipped {s['path']}: {s['reason']}" for s in skipped]
    report += port_report
    # Seed the Test tab from what was actually written (the model's checks
    # plus deterministic UI/endpoint coverage). Nested transaction: a
    # seeding failure must never roll back a good build.
    try:
        from app.services.build_tests import derive_build_tests, seed_idea_tests

        with db.session.begin_nested():
            seeded = seed_idea_tests(
                idea,
                derive_build_tests(
                    manifest_files,
                    runtime,
                    [t.model_dump() for t in manifest.tests],
                    runbook,
                ),
            )
        report.append(
            "tests: "
            f"{seeded['created']} added, {seeded['updated']} updated, "
            f"{seeded['removed']} removed"
        )
    except Exception:
        logger.exception("build_test_seed_failed", idea_id=str(idea.id))
    current = SecondaryActionResult.query.filter_by(
        idea_id=idea.id, action_type="BUILD_CODE", is_current=True
    ).all()
    next_version = max([r.version for r in current], default=0) + 1
    for r in current:
        r.is_current = False
    db.session.add(
        SecondaryActionResult(
            idea_id=idea.id,
            action_type="BUILD_CODE",
            model_used=preview.model_used,
            provider_used=preview.provider_used,
            result_data={
                **preview.result_data,
                "written": True,
                "target_name": build_target.name,
                "target_path": str(build_root),
                "target_host_path": server_path(str(build_root)),
                "runbook": runbook,
                "write_report": report,
                **{k: v for k, v in runtime.items() if v is not None},
            },
            version=next_version,
            is_current=True,
            skills_used=list(preview.skills_used or []) or None,
            guidelines_used=list(preview.guidelines_used or []) or None,
            target_id=str(build_target.id),
            target_name=build_target.name,
            instance_id=idea.instance_id,
        )
    )
    db.session.commit()
    logger.info(
        "build_written",
        idea_id=str(idea.id),
        target=build_target.name,
        files=len(written),
    )
    run = None
    if run_id:
        from app.models import PromptRun

        try:
            run = db.session.get(PromptRun, uuid.UUID(str(run_id)))
        except (ValueError, TypeError):
            run = None
    if run is not None:
        run.mark_success()
        db.session.commit()


@celery.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.ollama_tasks.run_secondary_action",
    autoretry_for=(Exception,),
    dont_autoretry_for=(SoftTimeLimitExceeded, _AbortAction),
    retry_backoff=True,
    max_retries=2,
    # Code builds on a CPU-only host routinely exceed the 600 s global
    # default (a single qwen2.5-coder:3b write can take 10+ minutes).
    # Give secondary actions their own generous ceiling; the global
    # default stays short so a stuck idea-generation task still fails fast.
    soft_time_limit=SECONDARY_SOFT_TIME_LIMIT,
    time_limit=SECONDARY_TIME_LIMIT,
)
def run_secondary_action(
    self,
    idea_id: str,
    action_type: str,
    model_override: str = None,
    run_id: str | None = None,
    extra_context: dict | None = None,
    provider_override: str | None = None,
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

    # Per-request ceiling for write-type actions (builds/code generation).
    # Must stay below the task's soft limit so the task reports a clean
    # timeout instead of being killed mid-request.
    client = OllamaClient(timeout=1500.0)
    # Explicit run args always win; the prompt (or the built-in default)
    # only fills what the caller left blank.
    model = model_override or (
        idea.prompt_config.model_name if idea.prompt_config else "llama3:8b"
    )
    provider_cfg = idea.prompt_config
    provider = (provider_cfg.provider or "ollama").lower() if provider_cfg else "ollama"
    # Stage config wins over the prompt (explicit run args already won
    # above via model_override); absent rows change nothing. Release
    # config (Scale-phase releases) wins over stage config.
    from app.models import resolve_release, resolve_stage

    stage_cfg = resolve_stage(idea.instance_id, idea.status.value)
    release_cfg = resolve_release(idea)
    merged_cfg = {
        **stage_cfg,
        **{k: v for k, v in release_cfg.items() if v is not None},
    }
    if not model_override and merged_cfg.get("model_name"):
        model = merged_cfg["model_name"]
    if merged_cfg.get("provider"):
        provider = merged_cfg["provider"].lower()
    if provider_override:
        # Explicit run choice wins over stage and prompt config.
        provider = provider_override.lower()
    # OpenCode model ids are "provider/model". A stored display name
    # ("Beam Free") or stale cached selection would make the CLI reject the
    # run; normalise to the id form.
    if provider == "opencode" and model and "/" not in str(model):
        model = "opencode/" + str(model).strip().lower().replace(" ", "-")
    hosted = provider != "ollama"
    # A model override on a hosted idea is a litellm model id; on a
    # prompt-less idea the override alone cannot imply a provider — unless
    # the caller explicitly chose one via provider_override.
    if model_override and not provider_cfg and not provider_override:
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

    # Pre-flight: verify model exists in this Ollama instance (local only).
    # Skipped for BUILD_CODE confirms: they write a stored manifest and
    # never touch a model.
    _build_confirm = action_type == "BUILD_CODE" and bool(
        (extra_context or {}).get("confirm_build", False)
    )
    try:
        _model_available = hosted or _build_confirm or client.is_model_available(model)
    except Exception as exc:
        # Unreachable Ollama fails the run with a clear message instead of
        # orphaning it as RUNNING through silent autoretry exhaustion.
        logger.error(
            "ollama_unreachable",
            base_url=client.base_url,
            model=model,
            action_type=action_type,
            idea_id=idea_id,
        )
        run = _get_run()
        if run is not None:
            run.mark_failed(f"Ollama unreachable at {client.base_url}: {exc}")
            db.session.commit()
        return
    if not _model_available:
        err_msg = f"Model '{model}' not installed at {client.base_url}"
        if "/" in (model or "") and provider == "ollama":
            # Classic stale-dialog shape: a hosted model id (e.g.
            # 'opencode/...') sent without its provider_override, so the
            # run fell back to the local engine. Say so plainly.
            err_msg += (
                " — the model name looks like a hosted-provider model; "
                "re-run with that provider selected, not local Ollama."
            )
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
                retry_after = getattr(e, "retry_after", None)
                if retry_after and _retries_so_far() == 0:
                    logger.info(
                        "ai_budget_queued",
                        idea_id=idea_id,
                        action_type=action_type,
                        retry_after=retry_after,
                    )
                    raise self.retry(exc=e, countdown=retry_after)
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

        # BUILD_CODE target resolution happens before the prompt is built:
        # an existing app repo is context the model must see, and a confirm
        # run never reaches generation at all.
        build_target = None
        build_root = None
        build_confirm = False
        if action_type == "BUILD_CODE":
            import uuid as uuid_mod

            from app.models import InstanceBuildTarget
            from app.services.build_service import BuildError, resolve_target

            build_confirm = bool((extra_context or {}).get("confirm_build", False))
            try:
                build_target = InstanceBuildTarget.query.filter_by(
                    id=uuid_mod.UUID(str((extra_context or {}).get("target_id"))),
                    instance_id=idea.instance_id,
                ).first()
            except (ValueError, TypeError, AttributeError):
                build_target = None
            if build_target is None:
                # A preview can fall back to an unambiguous single repo (the
                # UI often has no target to send). A confirm never guesses:
                # it writes a stored manifest, which must match its repo.
                candidates = InstanceBuildTarget.query.filter_by(
                    instance_id=idea.instance_id
                ).all()
                if not build_confirm and len(candidates) == 1:
                    build_target = candidates[0]
                else:
                    names = ", ".join(sorted(t.name for t in candidates)) or "none"
                    _record_failure(
                        run_id,
                        "No build repo selected. Registered repos for this "
                        f"instance: {names}. Pick one on the Build tab or add "
                        "one in Admin → AI Settings.",
                    )
                    return
            try:
                build_root = resolve_target(build_target)
            except BuildError as exc:
                _record_failure(run_id, str(exc))
                return
            if build_confirm:
                _write_confirmed_build(idea, build_target, build_root, run_id)
                return

        # Build supporting material for all secondary actions (they all now use it)
        from app.services.action_context import build_idea_context

        supporting_material = build_idea_context(idea)
        if action_type == "BUILD_CODE":
            # Release children build into the app's existing repo. Without
            # its files the model writes a standalone app and overwrites
            # every earlier child (and any hand-applied fix). Cap the
            # snapshot so a large repo cannot crowd out the design.
            from app.services.build_service import existing_repo_snapshot

            snapshot = existing_repo_snapshot(build_root)
            if snapshot:
                supporting_material += "\n\n" + snapshot
                logger.info(
                    "build_repo_context_injected",
                    idea_id=idea_id,
                    target=build_target.name,
                    chars=len(snapshot),
                )

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
            (extra_context or {}).get("skills") or merged_cfg.get("skills") or []
        )
        guideline_names = (
            (extra_context or {}).get("guidelines")
            or merged_cfg.get("guidelines")
            or []
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
        # Model/provider/prompt_config come from the canonical resolution
        # above (explicit run args win); do NOT re-derive them here — a
        # duplicate ternary once silently discarded model_override for
        # prompt-less ideas while the log line above showed the right values.
        prompt_config = provider_cfg

        # Analytical actions run cold: precision over creativity. Cap the
        # prompt's temperature at 0.3 (a lower setting is respected).
        # Stage config overrides the prompt values before the cap.
        options = (
            _generation_options(prompt_config, merged_cfg) if prompt_config else None
        )
        if options is None:
            options = {"temperature": 0.3}
            # Prompt-less ideas (children, manual ideas) still honour the
            # release/stage panel for params.
            for key in ("top_p", "num_predict"):
                if merged_cfg.get(key) is not None:
                    options[key] = merged_cfg[key]
        chosen_temp = merged_cfg.get("temperature")
        if chosen_temp is None:
            chosen_temp = options.get("temperature", 0.3)
        options["temperature"] = min(chosen_temp, 0.3)
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
        if action_type == "BUILD_CODE":
            # Manifests dwarf other outputs: raise the floor so file
            # contents are not cut off mid-object (schema caps apply too).
            min_tokens = 16000
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

        # Store result. PRD/DESIGN_DOC/BUILD_CODE are versioned: supersede the
        # current version instead of deleting history, so per-document
        # comment threads stay pinned to their version.
        if action_type == "BUILD_CODE" and build_target is not None:
            validated.target_name = build_target.name
            validated.target_path = str(build_root)
            from app.services.build_service import server_path

            validated.target_host_path = server_path(str(build_root))
        if action_type in ("PRD_DOC", "DESIGN_DOC", "BUILD_CODE"):
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
            provider_used=provider,
            result_data=validated.model_dump(),
            version=next_version,
            is_current=True,
            answers=(
                _accumulate_answers(idea.id, action_type, answers) or None
                if action_type in ("PRD_DOC", "DESIGN_DOC")
                else answers or None
            ),
            skills_used=list(dict.fromkeys(skill_names)) or None,
            guidelines_used=list(dict.fromkeys(guideline_names)) or None,
            target_id=(
                str(build_target.id)
                if action_type == "BUILD_CODE" and build_target is not None
                else None
            ),
            target_name=(
                build_target.name
                if action_type == "BUILD_CODE" and build_target is not None
                else None
            ),
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
    except Retry:
        # Budget-queue self.retry(): not a failure, hand back to Celery.
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
        # Expired/suspended instances stop generating (reads stay open).
        from app.utils.tenancy import instance_expired

        if prompt.instance_id is not None and instance_expired(prompt.instance_id):
            continue
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
        job = enqueue_generation(
            generate_idea,
            [str(prompt.id)],
            {
                "run_id": str(run.id),
                "instance_id": str(prompt.instance_id) if prompt.instance_id else None,
            },
            prompt.provider,
        )
        run.job_id = job.id
        # Advance the schedule at enqueue time, not only on success. A run
        # whose worker died never completes, and the prompt would otherwise
        # stay due: every reconcile (45 min) would queue another run.
        prompt.next_run_at = datetime.now(timezone.utc) + timedelta(
            minutes=prompt.interval_minutes
        )
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
