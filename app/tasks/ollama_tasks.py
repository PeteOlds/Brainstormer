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

def _host_network_ip() -> str:
    """Best-effort LAN IP of this machine (never 127.x) for shareable URLs."""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
        finally:
            sock.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "localhost"

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


def _infer_entry_command(by_path: dict, known_port=None):
    """Guess a start command when the manifest has no Dockerfile/compose/package.json.

    Returns ``(start_command, port, note)`` or ``(None, None, None)``. Only
    fires on a recognisable Python entry file, so an unrelated manifest
    (README-only) stays unrunnable — and the build confirm refuses it
    rather than reporting a build nobody can start.
    """
    import re as _re

    def _module(rel: str) -> str:
        return rel[:-3].replace("/", ".") if rel.endswith(".py") else rel

    has_requirements = any(
        _re.search(r"(^|/)requirements[^/]*\.txt$", path or "") for path in by_path
    )
    for prefix in ("", "src/", "backend/", "app/", "api/"):
        for name in ("app.py", "main.py", "server.py", "run.py", "wsgi.py", "asgi.py"):
            rel = prefix + name
            text = by_path.get(rel)
            if text is None:
                continue
            text = str(text)
            mod = _module(rel)
            if "FastAPI(" in text or "fastapi import" in text:
                port = known_port or 8000
                note = f"Start command inferred from {rel} (FastAPI)."
                if not has_requirements:
                    note += (
                        "\nNo requirements.txt in this build — install uvicorn "
                        "and fastapi before running."
                    )
                return (
                    f"python3 -m uvicorn {mod}:app --host 0.0.0.0 --port {port}",
                    port,
                    note,
                )
            if _re.search(r"\bFlask\s*\(", text) or "flask import" in text:
                port = known_port or 5000
                note = f"Start command inferred from {rel} (Flask)."
                if not has_requirements:
                    note += (
                        "\nNo requirements.txt in this build — install flask "
                        "before running."
                    )
                if _re.search(r"(?m)^\s*app\s*=\s*Flask\s*\(", text):
                    return (
                        f"python3 -m flask --app {mod} run --host 0.0.0.0 --port {port}",
                        port,
                        note,
                    )
                return f"python3 {rel}", port, note
            # Canonical script names run as scripts even without a
            # __main__ guard; wsgi/asgi modules only when they have one.
            if name in ("app.py", "main.py", "server.py", "run.py") or "__main__" in text:
                return f"python3 {rel}", known_port, f"Start command inferred from {rel}."
    return None, None, None


def _extract_runtime_info(files: list) -> dict:
    """Infer how to run a built app from its manifest files.

    Inspects Dockerfile (EXPOSE/CMD), docker-compose (ports/image),
    package.json (start script) and .env.example (credentials) without
    executing anything. Returns only plain JSON-safe values so the
    result row can carry them straight to the UI instructions modal.
    """
    import json
    import re

    # Compose service names that conventionally serve the human UI
    # rather than the API. Matched case-insensitively, exact or as a
    # path segment of the build context (./frontend, ./client …).
    FRONTEND_HINTS = (
        "frontend",
        "ui",
        "client",
        "web",
        "www",
        "site",
        "dashboard",
        "portal",
        "app",
    )

    def _pub_ports(mapping):
        """Published (host, container) ports from one compose ports entry."""
        host, target = None, None
        if isinstance(mapping, int):
            target = mapping
        elif isinstance(mapping, str) and mapping.strip():
            parts = mapping.strip().strip("\"'").split(":")
            try:
                if len(parts) >= 2:
                    host = int(parts[-2])
                target = int(parts[-1])
            except ValueError:
                host = target = None
        elif isinstance(mapping, dict) and mapping.get("target") is not None:
            try:
                target = int(mapping["target"])
            except (TypeError, ValueError):
                target = None
            try:
                host = (
                    int(mapping["published"])
                    if mapping.get("published") is not None
                    else None
                )
            except (TypeError, ValueError):
                host = None
        return host, target

    def _looks_frontend(name, svc):
        low = str(name or "").lower()
        if low in FRONTEND_HINTS:
            return True
        build = svc.get("build") if isinstance(svc, dict) else None
        ctx = build.get("context") if isinstance(build, dict) else build
        if isinstance(ctx, str) and any(h in ctx.lower() for h in FRONTEND_HINTS):
            return True
        image = svc.get("image") if isinstance(svc, dict) else None
        if isinstance(image, str) and "nginx" in image.lower():
            return True
        return False

    info: dict = {
        "start_command": None,
        "app_url": None,
        "port": None,
        "frontend_url": None,
        "frontend_port": None,
        "credentials": None,
        "docker_image": None,
        "docker_compose_file": None,
        "run_notes": None,
    }
    by_path = {}
    for entry in files or []:
        if isinstance(entry, dict) and entry.get("path"):
            by_path[str(entry["path"])] = str(entry.get("content") or "")

    def _dockerfile():
        for path, content in by_path.items():
            if path == "Dockerfile" or path.endswith("/Dockerfile"):
                return content
        return None

    def _compose():
        for path, content in by_path.items():
            low = path.lower()
            if low.endswith("docker-compose.yml") or low.endswith(
                "docker-compose.yaml"
            ):
                return path, content
        return None, None

    port = None
    start_command = None
    dockerfile = _dockerfile()
    if dockerfile:
        match = re.search(r"(?m)^\s*EXPOSE\s+(\d+)", dockerfile)
        if match:
            try:
                port = int(match.group(1))
            except ValueError:
                pass
        match = re.search(r"(?m)^\s*CMD\s+(.+)$", dockerfile)
        if match:
            start_command = match.group(1).strip()

    compose_path, compose_content = _compose()
    docker_image = None
    frontend_port = None
    if compose_content:
        info["docker_compose_file"] = compose_path
        try:
            import yaml

            compose = yaml.safe_load(compose_content) or {}
        except Exception:
            compose = {}
        services = compose.get("services") or {}
        compose_host_seen = False
        if isinstance(services, dict):
            for _name, svc in services.items():
                if not isinstance(svc, dict):
                    continue
                for mapping in svc.get("ports") or []:
                    # Host side is what the user opens and what can
                    # collide: "HOST:CONTAINER" binds HOST, a bare port
                    # (or int) only names the container side.
                    host, target = _pub_ports(mapping)
                    if _looks_frontend(_name, svc):
                        if host and frontend_port is None:
                            frontend_port = host
                        continue
                    if host:
                        # A compose host binding is deployment truth: it
                        # overwrites a Dockerfile EXPOSE, first one wins
                        # across services — but keep scanning, a frontend
                        # service may still follow.
                        if not compose_host_seen:
                            port = host
                            compose_host_seen = True
                        break
                    if target and port is None:
                        # Expose-only form: no host binding to collide
                        # with, but still the port the app serves.
                        port = target
                if isinstance(svc.get("image"), str) and svc["image"].strip():
                    docker_image = svc["image"].strip()

    for path, content in by_path.items():
        if path.endswith("package.json"):
            try:
                pkg = json.loads(content)
                scripts = pkg.get("scripts") or {}
                if isinstance(scripts, dict) and scripts.get("start"):
                    start_command = start_command or str(scripts["start"])
            except (ValueError, AttributeError):
                pass
            break

    # No Dockerfile CMD / package.json start script: infer from the app's
    # own entry file so a plain Flask/FastAPI app still gets a runbook.
    inferred_note = None
    if not start_command:
        start_command, inferred_port, inferred_note = _infer_entry_command(
            by_path, port
        )
        if inferred_port:
            port = inferred_port

    credentials = None
    for path, content in by_path.items():
        low = path.lower()
        if low.endswith(".env.example") or low.endswith(".env.sample"):
            found = {}
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, _val = line.partition("=")
                key = key.strip()
                if key and (
                    "password" in key.lower()
                    or "secret" in key.lower()
                    or "user" in key.lower()
                    or "login" in key.lower()
                ):
                    found[key] = "<set via environment>"
            if found:
                credentials = found
                break

    notes = []
    if inferred_note:
        notes.append(inferred_note)
    # No "Start command:" note: the How-to-run panel already shows it as a
    # copyable Run row, and models restate it here verbatim (noise).
    # Browser step goes last: open the app only after starting it.
    app_url = None
    if credentials:
        notes.append("Default credentials: " + ", ".join(sorted(credentials)))
    if docker_image:
        notes.append(f"Docker image: {docker_image}")
    if compose_path:
        notes.append(f"Or run everything with Docker Compose using {compose_path} (install docker-compose-v2 first if `docker compose` is missing; create /var/log/opencode and copy .env.example to .env if needed).")
    if port:
        app_url = f"http://{_host_network_ip()}:{port}"
    frontend_url = None
    if frontend_port:
        frontend_url = f"http://{_host_network_ip()}:{frontend_port}"
        notes.append(f"Open {frontend_url} in your browser once it is running.")
    elif app_url:
        notes.append(f"Open {app_url} in your browser once it is running.")
    info.update(
        {
            "start_command": start_command,
            "app_url": app_url,
            "port": port,
            "frontend_url": frontend_url,
            "frontend_port": frontend_port,
            "credentials": credentials,
            "docker_image": docker_image,
            "run_notes": "\n".join(notes) if notes else None,
        }
    )
    return info


def _rewrite_compose_host_port(files: list, old: int, new: int) -> tuple[list, int]:
    """Point a compose manifest's published host ports at ``new``.

    Only entries publishing ``old`` are touched; the container side is
    never changed, so the app's own code keeps working unmodified.
    Returns (files, changed_count). Unparseable compose files are left
    alone (0 changes) rather than risked.
    """
    try:
        import yaml
    except ImportError:
        return files, 0
    changed = 0
    out = []
    for entry in files or []:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        low = str(entry.get("path") or "").lower()
        if not (
            low.endswith("docker-compose.yml") or low.endswith("docker-compose.yaml")
        ):
            out.append(entry)
            continue
        try:
            compose = yaml.safe_load(entry.get("content") or "") or {}
        except Exception:
            out.append(entry)
            continue
        if not isinstance(compose, dict):
            out.append(entry)
            continue
        touched = False
        services = compose.get("services") or {}
        if isinstance(services, dict):
            for _name, svc in services.items():
                if not isinstance(svc, dict) or not isinstance(svc.get("ports"), list):
                    continue
                rewritten = []
                for mapping in svc["ports"]:
                    if isinstance(mapping, int) and mapping == old:
                        # Expose-only form pins nothing: pin HOST:new so
                        # the URL we show actually reaches the app.
                        rewritten.append(f"{new}:{mapping}")
                        touched = True
                    elif isinstance(mapping, str) and mapping.strip():
                        raw = mapping.strip()
                        quote = ""
                        if raw[:1] in "\"'" and raw[-1:] == raw[:1]:
                            quote = raw[:1]
                            raw = raw[1:-1]
                        parts = raw.split(":")
                        try:
                            if len(parts) >= 2 and int(parts[-2]) == old:
                                parts[-2] = str(new)
                                rewritten.append(quote + ":".join(parts) + quote)
                                touched = True
                            elif len(parts) == 1 and int(parts[0]) == old:
                                rewritten.append(quote + f"{new}:{parts[0]}" + quote)
                                touched = True
                            else:
                                rewritten.append(mapping)
                        except ValueError:
                            rewritten.append(mapping)
                    elif isinstance(mapping, dict):
                        try:
                            if (
                                mapping.get("published") is not None
                                and int(mapping["published"]) == old
                            ):
                                mapping = dict(mapping, published=new)
                                touched = True
                        except (TypeError, ValueError):
                            pass
                        rewritten.append(mapping)
                    else:
                        rewritten.append(mapping)
                svc["ports"] = rewritten
        if touched:
            try:
                entry = dict(
                    entry,
                    content=yaml.safe_dump(
                        compose, sort_keys=False, default_flow_style=False
                    ),
                )
                changed += 1
            except Exception:
                pass
        out.append(entry)
    return out, changed


def _pretty_cmd(value) -> str:
    """Model commands into runnable host commands.

    Joins real and stringified lists ('["python", "app.py"]' →
    'python app.py') and rewrites the bare `python` interpreter to
    `python3` (host shells lack `python`; venvs provide `python3`).
    """
    import json as _json
    import re as _re

    if isinstance(value, (list, tuple)):
        text = " ".join(str(v) for v in value)
    elif isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = _json.loads(value)
            text = (
                " ".join(str(v) for v in parsed) if isinstance(parsed, list) else value
            )
        except ValueError:
            text = value
    else:
        text = value if isinstance(value, str) else ""
    return _re.sub(r"(^|&&\s*|;\s*|\|\s*|\)\s*)python(?=\s|$)", r"\1python3", text)


def _derive_runbook(
    files: list, start_command, host_root: str, container_root: str | None = None
) -> dict | None:
    """Derive verified paste-and-run commands from a build manifest.

    Resolves the entry point (``python -m pkg.mod``, ``python app.py``,
    ``uvicorn pkg.mod:app``) against the manifest's file list to find the
    directory the command must run in, and pairs it with a venv setup step
    when a pip requirements file ships (bare hosts refuse system pip via
    PEP 668). Returns ``{"setup", "setup_fallback", "run", "workdir"}``
    with absolute host paths (the fallback installs the same packages
    unpinned, for newer Pythons the old pins no longer build on), plus
    container-native ``run_argv``/``setup_argv``/``pip_argv`` for the
    supervised runner when ``container_root`` is given (host paths do not
    exist inside worker containers). Returns None when the command cannot
    be resolved (callers fall back to the raw fields).
    """
    import os as _os
    import re as _re

    if not host_root or not start_command:
        return None
    cmd = _pretty_cmd(start_command).strip()
    if not cmd:
        return None
    paths = [
        str(e.get("path") or "").replace("\\", "/").lstrip("./")
        for e in files or []
        if isinstance(e, dict) and e.get("path")
    ]
    if not paths:
        return None

    def _resolve_module(mod: str) -> str | None:
        mod_path = mod.replace(".", "/")
        for cand in (mod_path + ".py", mod_path + "/__init__.py"):
            hit = next((p for p in paths if p == cand or p.endswith("/" + cand)), None)
            if hit is not None:
                return hit[: len(hit) - len(cand)].rstrip("/")
        return None

    _RUNNERS = {"uvicorn", "gunicorn", "hypercorn", "daphne"}

    def _resolve_dir() -> str | None:
        # `python[3] -m dotted.mod ...` or `python[3] script.py ...`
        m = _re.search(
            r"(?:^|&&\s*|;\s*)\s*python3?\s+(?:-m\s+([\w.]+)|([\w./-]+\.pyw?))(?:\s|$)",
            cmd,
        )
        if m and m.group(1):
            mod = m.group(1)
            if mod.split(".")[0] in _RUNNERS:
                # Runner invocation (`python -m uvicorn pkg.mod:app`):
                # the app Plugins is the `dotted:app` argument, not the runner.
                appm = _re.search(r"([\w.]+):\S+", cmd)
                if not appm:
                    return None
                return _resolve_module(appm.group(1))
            if mod.split(".")[0] == "flask":
                # `python -m flask --app pkg.mod run`: --app names the app.
                appm = _re.search(r"--app[\s=]+([\w.]+)", cmd)
                if not appm:
                    return ""  # CLI discovery from the workdir
                return _resolve_module(appm.group(1).split(":")[0])
            return _resolve_module(mod)
        if m and m.group(2):
            script = m.group(2).lstrip("./")
            hit = next(
                (p for p in paths if p == script or p.endswith("/" + script)), None
            )
            if hit is None:
                return None
            # Run from the target root with the manifest-relative script
            # path (never cd into its dir: that would double the path).
            return ""
        # `uvicorn|gunicorn dotted.mod:app ...`
        m = _re.search(
            r"(?:^|&&\s*|;\s*)\s*(?:uvicorn|gunicorn|hypercorn|daphne)\s+([\w.]+):\S+",
            cmd,
        )
        if m:
            mod_path = m.group(1).replace(".", "/") + ".py"
            hit = next(
                (p for p in paths if p == mod_path or p.endswith("/" + mod_path)), None
            )
            if hit is None:
                return None
            return hit[: len(hit) - len(mod_path)].rstrip("/")
        # `flask --app pkg.mod run ...` (bare CLI, no python prefix)
        m = _re.search(r"(?:^|&&\s*|;\s*)\s*flask\b[^&;]*--app[\s=]+([\w.]+)", cmd)
        if m:
            return _resolve_module(m.group(1).split(":")[0])
        # `npm start`, `npm run dev`, `node server.js`, `npx ...`
        m = _re.search(r"(?:^|&&\s*|;\s*)\s*(?:npm|npx|yarn|pnpm|node)\b", cmd)
        if m:
            pkg = next(
                (p for p in paths if p == "package.json" or p.endswith("/package.json")),
                None,
            )
            if pkg is None:
                return None
            return pkg[: -len("package.json")].rstrip("/")
        return None

    appdir = _resolve_dir()
    if appdir is None:
        return None
    workdir = (
        host_root.rstrip("/") if not appdir else host_root.rstrip("/") + "/" + appdir
    )
    quoted = f'cd "{workdir}"'
    pretty = _pretty_cmd(start_command).strip()
    import shlex as _shlex

    try:
        args = _shlex.split(pretty, posix=True)
    except ValueError:
        args = None
    if args:
        # `cd /dir && cmd` (models sometimes paste their own cd): workdir
        # already covers the cd, so drop it and keep the real head.
        while len(args) > 2 and args[0] == "cd" and "&&" in args:
            args = args[args.index("&&") + 1:]
    head = _os.path.basename(args[0]) if args else ""
    node_cmd = head in ("npm", "npx", "yarn", "pnpm", "node")
    # Display commands are pasted on the reader's own machine, while the
    # supervised process owns `.venv` inside its container. A separate
    # folder for the pasteable setup means running it can never replace
    # the supervised interpreter with one the container cannot execute
    # (seen live: a host-built 3.14 venv broke the next Start).
    dvenv = ".venv-local"
    setup = None
    req = next(
        (p for p in paths if _re.search(r"(^|/)requirements[^/]*\.txt$", p or "")),
        None,
    )
    if req is not None:
        rel = _os.path.relpath(req, appdir) if appdir else req
        if not rel.startswith(".."):
            setup = (
                f"{quoted} && rm -rf {dvenv} && python3 -m venv {dvenv} "
                f"&& . {dvenv}/bin/activate && {dvenv}/bin/pip install -r {rel}"
            )
    use_venv = setup is not None
    # Node projects install their own way; only when no venv already owns
    # the setup step (a manifest with both is a Python app with a frontend).
    npm_pkg = next(
        (p for p in paths if p == "package.json" or p.endswith("/package.json")),
        None,
    )
    npm_setup = None
    if node_cmd and npm_pkg is not None and not use_venv:
        npm_setup = f"{quoted} && npm install"
        setup = npm_setup
    # Supervised processes run inside worker containers, where host paths
    # do not exist: argv uses the container twin when one was provided.
    # Display strings above stay host-native for pasting.
    cworkdir = None
    if container_root:
        cworkdir = (
            container_root.rstrip("/")
            if not appdir
            else container_root.rstrip("/") + "/" + appdir
        )
    eworkdir = cworkdir or workdir
    evenv = eworkdir.rstrip("/") + "/.venv" if use_venv else ""
    # Bare interpreter for the setup-less case: the runner resolves it
    # against its own PATH (absolute host paths do not exist there).
    epython = evenv + "/bin/python" if use_venv else "python3"
    venv_dir = workdir.rstrip("/") + "/.venv" if use_venv else ""
    venv_python = venv_dir + "/bin/python" if use_venv else "/usr/bin/python3"
    run_argv = None
    if args:
        rest = args[1:]
        if _re.match(r"^python3?(\.\d+)?$", head):
            run_argv = [epython] + rest
        elif head in _RUNNERS:
            # Bare runner (`uvicorn pkg.mod:app`): invoke it as a module so
            # the venv (or the runner's PATH) interpreter resolves it.
            run_argv = [epython, "-m", head] + rest
        elif head == "flask":
            run_argv = [epython, "-m", "flask"] + rest
        elif head in ("npm", "npx", "yarn", "pnpm", "node"):
            run_argv = [head] + rest
    setup_argv = (
        ["python3", "-m", "venv", "--upgrade", evenv]
        if use_venv
        else (["npm", "install"] if npm_setup else [])
    )
    pip_argv = [evenv + "/bin/pip", "install", "-r", rel] if use_venv else []
    # Fallback for newer Pythons the pinned versions no longer build on:
    # same packages, unpinned. Parsed from the requirements content so it
    # can never name something the manifest does not use.
    setup_fallback = None
    pip_fallback_argv = []
    if use_venv:
        req_entry = next(
            (
                e
                for e in files or []
                if isinstance(e, dict) and str(e.get("path") or "") == req
            ),
            None,
        )
        names = []
        for line in str((req_entry or {}).get("content") or "").splitlines():
            line = line.split("#", 1)[0].split(";", 1)[0].strip()
            m = _re.match(r"^([A-Za-z0-9_.-]+(?:\[[^\]]*\])?)", line)
            if m and not line.startswith("-"):
                names.append(m.group(1))
        if names:
            # Unpinned installs work on newer Pythons where the old pins
            # no longer build (e.g. pydantic-core on 3.14). Make that the
            # primary, paste-and-run command; keep the pinned one as the
            # reproducibility fallback.
            pinned = setup
            setup = (
                f"{quoted} && rm -rf {dvenv} && python3 -m venv {dvenv} "
                f"&& . {dvenv}/bin/activate && {dvenv}/bin/pip install "
                + " ".join(names)
            )
            setup_fallback = pinned
            pip_fallback_argv = [evenv + "/bin/pip", "install"] + names
    if run_argv is None:
        # No safe argv (non-python command without installable requirements):
        # the raw fields stay the only source.
        return None
    if use_venv:
        # Display form stays pasteable; argv form is resolved by the
        # runner inside its own container (absolute host python paths do
        # not exist there).
        run = f"{quoted} && . {dvenv}/bin/activate && {cmd}"
    else:
        run = f"{quoted} && {cmd}"
    return {
        "setup": setup,
        "setup_fallback": setup_fallback,
        "run": run,
        "workdir": workdir,
        "workdir_container": cworkdir,
        "venv_dir": venv_dir,
        "setup_argv": setup_argv,
        "pip_argv": pip_argv,
        "pip_fallback_argv": pip_fallback_argv,
        "run_argv": run_argv,
    }


def _allocate_build_port(runtime: dict, files: list) -> tuple[dict, list, list]:
    """Give a confirmed build a free host port, rewriting host-side refs.

    Checks ``runtime['port']`` against this machine. When busy, allocates
    the next free port and rewrites the app URL, explicit ``--port`` flags
    in the start command, and compose published ports (container side
    untouched). Returns (runtime, files, report_lines) in plain language
    for non-technical users. Never raises: worst case the conflict is
    recorded in the notes and the original port kept.
    """
    from app.services.build_service import allocate_port, port_in_use

    report = []
    try:
        port = int(runtime.get("port")) if runtime.get("port") else None
    except (TypeError, ValueError):
        port = None
    try:
        fport = (
            int(runtime.get("frontend_port")) if runtime.get("frontend_port") else None
        )
    except (TypeError, ValueError):
        fport = None
    try:
        busy = port_in_use(port) if port else False
    except Exception:
        busy = False
    try:
        fbusy = port_in_use(fport) if fport else False
    except Exception:
        fbusy = False
    if not busy and not fbusy:
        return runtime, files, report
    if fbusy:
        # Same for the frontend/dashboard port: the UI URL must open
        # something, so a busy dashboard port moves too.
        import re

        fnew, _ = allocate_port(fport)
        if fnew == fport:
            line = (
                f"Dashboard port {fport} is already in use and no free "
                "port was found nearby — stop the other program first."
            )
        else:
            files, _ = _rewrite_compose_host_port(files, fport, fnew)
            runtime = dict(
                runtime, frontend_port=fnew, frontend_url=f"http://{_host_network_ip()}:{fnew}"
            )
            existing = runtime.get("run_notes")
            if isinstance(existing, str) and existing:
                runtime["run_notes"] = re.sub(
                    r"((?:localhost|127\.0\.0\.1|\d{1,3}(?:\.\d{1,3}){3}))" + r":" + str(fport) + r"\b",
                    lambda m: f"{_host_network_ip()}:{fnew}",
                    existing,
                )
            line = (
                f"Dashboard port {fport} is already in use, so the dashboard "
                f"moved to port {fnew} — the Open link below already uses {fnew}."
            )
        runtime["run_notes"] = "\n".join(
            [n for n in [runtime.get("run_notes"), line] if n]
        )
        report.append(line)
    if not busy:
        return runtime, files, report
    new_port, _changed = allocate_port(port)
    if new_port == port:
        line = (
            f"Port {port} is already in use on this machine and no free "
            "port was found nearby — stop the other program first, then run."
        )
        runtime["run_notes"] = "\n".join(
            [n for n in [runtime.get("run_notes"), line] if n]
        )
        report.append(line)
        return runtime, files, report
    old, new = port, new_port
    runtime = dict(runtime, port=new, port_requested=old, port_changed=True)
    url = runtime.get("app_url")
    if isinstance(url, str) and f":{old}" in url:
        import re

        runtime["app_url"] = re.sub(
            r"(://[^/:]+)" + r":" + str(old) + r"(?=/|$)",
            r"\g<1>" + f":{new}",
            url,
            count=1,
        )
    cmd = runtime.get("start_command")
    cmd_rewritten = False
    if isinstance(cmd, str) and cmd:
        import re

        # Separator class covers `--port 8000`, `--port=8000` and the
        # Dockerfile-CMD JSON-array form `"--port", "8000"`.
        rewritten, n = re.subn(
            r"(--port)([\"',\s=]+)" + str(old) + r"\b",
            lambda m: m.group(1) + m.group(2) + str(new),
            cmd,
        )
        if not n:
            rewritten, n = re.subn(
                r"(PORT=|localhost:|127\.0\.0\.1:)" + str(old) + r"\b",
                lambda m: m.group(1) + str(new),
                cmd,
            )
        if n:
            runtime["start_command"] = rewritten
            cmd_rewritten = True
    files, compose_rewritten = _rewrite_compose_host_port(files, old, new)
    # Notes prose written before allocation names the old port (model and
    # extractor output); point localhost URLs at the new one BEFORE
    # appending the allocation notice (which must keep naming the old).
    existing_notes = runtime.get("run_notes")
    if isinstance(existing_notes, str) and existing_notes:
        import re

        runtime["run_notes"] = re.sub(
            r"((?:localhost|127\.0\.0\.1|\d{1,3}(?:\.\d{1,3}){3}))" + r":" + str(old) + r"\b",
            lambda m: f"{_host_network_ip()}:{new}",
            existing_notes,
        )
    line = (
        f"Port {old} is already in use on this machine, so this build was "
        f"set to port {new} — the commands below already use {new}."
    )
    if not cmd_rewritten and not compose_rewritten and cmd:
        line += (
            " The start command does not name its port, so if the app itself "
            f"fixes its port, change that setting to {new} as well."
        )
    runtime["run_notes"] = "\n".join([n for n in [runtime.get("run_notes"), line] if n])
    report.append(line)
    if compose_rewritten:
        report.append(
            f"docker-compose.yml now publishes {new} on this machine "
            f"(the app inside still uses {old})."
        )
    return runtime, files, report


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
    from app.services.build_service import BuildError, server_path, write_manifest
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
        runtime = _extract_runtime_info(manifest_files)
        # Port check + compose rewrite happen BEFORE writing so the
        # on-disk compose file already publishes a free host port.
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
            manifest_files,
            runtime.get("start_command"),
            server_path(str(build_root)),
            str(build_root),
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
        # BUILD_CODE target resolution, fail fast before spending on the LLM.
        # The confirm run skips generation entirely (writes the stored
        # preview manifest instead) — see _write_confirmed_build below.
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
