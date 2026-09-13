from flask import Blueprint, request, current_app
from sqlalchemy import func

from app.extensions import db
from app.models import PromptConfig
from app.utils.decorators import admin_required, token_required
from app.utils.responses import api_ok, api_error, api_created

bp = Blueprint("prompts", __name__)

SAMPLE_TOPIC = "a sustainable packaging startup for small cafes"


def _parse_temperature(value):
    """Parse + range-check temperature. Returns (temp, error_response)."""
    try:
        temperature = float(value)
    except (TypeError, ValueError):
        return None, api_error("Invalid temperature: must be a number", status_code=400)
    if not 0 <= temperature <= 2:
        return None, api_error("Invalid temperature: must be between 0 and 2", status_code=400)
    return temperature, None


def _parse_float_range(value, name, lo, hi, default):
    """Parse optional float field with range check. Returns (val, error)."""
    if value is None:
        return default, None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, api_error(f"Invalid {name}: must be a number", status_code=400)
    if not lo <= number <= hi:
        return None, api_error(f"Invalid {name}: must be between {lo} and {hi}", status_code=400)
    return number, None


def _parse_num_predict(value, default=1000):
    if value is None:
        return default, None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None, api_error("Invalid num_predict: must be an integer", status_code=400)
    if not 1 <= number <= 4096:
        return None, api_error("Invalid num_predict: must be between 1 and 4096", status_code=400)
    return number, None


def _parse_seed(value):
    """Seed is optional: null/empty = random each run."""
    if value is None or value == "":
        return None, None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None, api_error("Invalid seed: must be an integer or empty", status_code=400)
    if number < 0:
        return None, api_error("Invalid seed: must be 0 or greater", status_code=400)
    return number, None


def _parse_keep_alive(value, default="2h"):
    if value is None or value == "":
        return default, None
    text = str(value).strip()
    if len(text) > 20:
        return None, api_error("Invalid keep_alive: too long (max 20 chars)", status_code=400)
    return text, None


@bp.route("/prompts/test", methods=["POST"])
@admin_required
def test_prompt(user):
    """Run a prompt body once against Ollama without saving (admin only)."""
    import httpx

    data = request.get_json() or {}
    prompt_body = (data.get("prompt_body") or "").strip()
    model_name = (data.get("model_name") or "").strip()
    if not prompt_body:
        return api_error("Missing required field: prompt_body", status_code=400)
    if not model_name:
        return api_error("Missing required field: model_name", status_code=400)
    temperature, temp_error = _parse_temperature(data.get("temperature", 0.7))
    if temp_error:
        return temp_error

    prompt = prompt_body.replace("{{topic}}", SAMPLE_TOPIC).replace("{{ topic }}", SAMPLE_TOPIC)
    # num_predict keeps ad-hoc test runs bounded on CPU (full generations
    # run via Run Now / schedule with the task timeout instead).
    payload = {"model": model_name, "prompt": prompt, "stream": False,
               "options": {"temperature": temperature, "num_predict": 500}}
    import time as _time
    started = _time.monotonic()
    try:
        timeout = float(current_app.config.get("OLLAMA_TIMEOUT", 120))
        base_url = current_app.config["OLLAMA_BASE_URL"].rstrip("/")
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url}/api/generate", json=payload)
            response.raise_for_status()
            text = response.json().get("response", "")
        current_app.logger.info(
            "prompt_test_ok model=%s seconds=%.0f chars=%d",
            model_name, _time.monotonic() - started, len(text))
    except httpx.TimeoutException:
        current_app.logger.warning(
            "prompt_test_timeout model=%s seconds=%.0f",
            model_name, _time.monotonic() - started)
        return api_error(
            "Test run timed out — the model took too long. Try a smaller "
            "model (e.g. a 3b/7b/8b one) or a shorter prompt.", status_code=504)
    except Exception as e:
        return api_error(f"Test run failed: {str(e)}", status_code=502)

    return api_ok({"result": text[:4000], "model": model_name, "topic": SAMPLE_TOPIC})


@bp.route("/prompts/test-stream", methods=["POST"])
@admin_required
def test_prompt_stream(user):
    """Stream a one-off test run (SSE) so long generations show progress."""
    import httpx
    from flask import Response, stream_with_context

    data = request.get_json() or {}
    prompt_body = (data.get("prompt_body") or "").strip()
    model_name = (data.get("model_name") or "").strip()
    if not prompt_body:
        return api_error("Missing required field: prompt_body", status_code=400)
    if not model_name:
        return api_error("Missing required field: model_name", status_code=400)
    temperature, temp_error = _parse_temperature(data.get("temperature", 0.7))
    if temp_error:
        return temp_error

    prompt = prompt_body.replace("{{topic}}", SAMPLE_TOPIC).replace("{{ topic }}", SAMPLE_TOPIC)
    # Keep ad-hoc tests short: a sanity sample, not a full generation.
    payload = {"model": model_name, "prompt": prompt, "stream": True,
               "options": {"temperature": temperature, "num_predict": 250}}
    base_url = current_app.config["OLLAMA_BASE_URL"].rstrip("/")
    timeout = float(current_app.config.get("OLLAMA_TIMEOUT", 120))

    def generate():
        import json as _json
        import time as _time
        started = _time.monotonic()
        try:
            with httpx.stream("POST", f"{base_url}/api/generate",
                              json=payload, timeout=timeout) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = _json.loads(line)
                    except ValueError:
                        continue
                    token = chunk.get("response", "")
                    if token:
                        yield f"data: {_json.dumps({'token': token})}\n\n"
                    if chunk.get("done"):
                        current_app.logger.info(
                            "prompt_test_stream_ok model=%s seconds=%.0f",
                            model_name, _time.monotonic() - started)
                        yield "data: [DONE]\n\n"
                        return
        except Exception as e:
            current_app.logger.warning(
                "prompt_test_stream_error model=%s seconds=%.0f error=%s",
                model_name, _time.monotonic() - started, str(e)[:100])
            yield f"data: {_json.dumps({'error': str(e)[:200]})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@bp.route("/prompts", methods=["GET"])
@token_required
def list_prompts(user):
    """List all prompt configurations."""
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 20, type=int)
    is_active = request.args.get("is_active", type=lambda x: x.lower() == "true")

    query = PromptConfig.query
    if is_active is not None:
        query = query.filter(PromptConfig.is_active == is_active)

    query = query.order_by(PromptConfig.created_at.desc())
    pagination = query.paginate(page=page, per_page=limit, error_out=False)

    return api_ok({
        # include_prompt=True: the list table shows a body snippet and the
        # edit modal needs the full body (non-admin detail view already
        # exposes prompt_body, so this adds no new exposure).
        "prompts": [p.to_dict(include_prompt=True, include_stats=True) for p in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    })


@bp.route("/prompts", methods=["POST"])
@admin_required
def create_prompt(user):
    """Create a new prompt configuration."""
    data = request.get_json() or {}

    # Validate required fields
    required = ["title", "prompt_body", "interval_minutes", "model_name"]
    for field in required:
        if not data.get(field):
            return api_error(f"Missing required field: {field}", status_code=400)

    # interval_minutes arrives as a string from HTML selects — coerce it.
    # "custom" means a cron expression drives the schedule; fall back to
    # daily for the initial next_run_at calculation.
    raw_interval = data.get("interval_minutes")
    if isinstance(raw_interval, str) and raw_interval.strip().lower() == "custom":
        if not data.get("cron_expression"):
            return api_error("Custom interval requires a cron_expression", status_code=400)
        interval_minutes = 1440
    else:
        try:
            interval_minutes = int(raw_interval)
        except (TypeError, ValueError):
            return api_error("Invalid interval_minutes: must be a number of minutes", status_code=400)
        if interval_minutes <= 0:
            return api_error("Invalid interval_minutes: must be positive", status_code=400)

    temperature, temp_error = _parse_temperature(data.get("temperature", 0.7))
    if temp_error:
        return temp_error
    top_p, err = _parse_float_range(data.get("top_p", 0.9), "top_p", 0, 1, 0.9)
    if err:
        return err
    repeat_penalty, err = _parse_float_range(
        data.get("repeat_penalty", 1.1), "repeat_penalty", 0, 2, 1.1)
    if err:
        return err
    num_predict, err = _parse_num_predict(data.get("num_predict", 1000))
    if err:
        return err
    seed, err = _parse_seed(data.get("seed"))
    if err:
        return err
    keep_alive, err = _parse_keep_alive(data.get("keep_alive", "2h"))
    if err:
        return err

    # Check max active prompts (10)
    active_count = PromptConfig.query.filter(PromptConfig.is_active == True).count()
    if data.get("is_active", True) and active_count >= 10:
        return api_error("Maximum of 10 active prompts allowed", status_code=409, error_code="MAX_ACTIVE_PROMPTS")

    prompt = PromptConfig(
        title=data["title"],
        prompt_body=data["prompt_body"],
        interval_minutes=interval_minutes,
        cron_expression=data.get("cron_expression"),
        model_name=data["model_name"],
        temperature=temperature,
        top_p=top_p,
        repeat_penalty=repeat_penalty,
        num_predict=num_predict,
        seed=seed,
        keep_alive=keep_alive,
        is_active=data.get("is_active", True),
        created_by_id=user.id,
    )

    # Calculate next_run_at
    from datetime import datetime, timezone, timedelta
    if prompt.cron_expression:
        # TODO: Use croniter for cron expressions
        prompt.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=prompt.interval_minutes)
    else:
        prompt.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=prompt.interval_minutes)

    db.session.add(prompt)
    db.session.commit()

    return api_created(prompt.to_dict(include_prompt=True, include_stats=True))


@bp.route("/prompts/<uuid:prompt_id>", methods=["GET"])
@token_required
def get_prompt(user, prompt_id):
    """Get a single prompt configuration."""
    prompt = PromptConfig.query.get_or_404(prompt_id)
    # Users (non-admin) only see title and answer/body
    if user.role.value != 'ADMIN':
        return api_ok({
            'id': str(prompt.id),
            'title': prompt.title,
            'prompt_body': prompt.prompt_body,
        })
    return api_ok(prompt.to_dict(include_prompt=True, include_stats=True))


@bp.route("/prompts/<uuid:prompt_id>", methods=["PATCH"])
@admin_required
def update_prompt(user, prompt_id):
    """Update a prompt configuration."""
    prompt = PromptConfig.query.get_or_404(prompt_id)
    data = request.get_json() or {}

    # Update fields
    if "title" in data:
        prompt.title = data["title"]
    if "prompt_body" in data:
        prompt.prompt_body = data["prompt_body"]
    if "interval_minutes" in data:
        try:
            new_interval = int(data["interval_minutes"])
        except (TypeError, ValueError):
            return api_error("Invalid interval_minutes: must be a number of minutes", status_code=400)
        if new_interval <= 0:
            return api_error("Invalid interval_minutes: must be positive", status_code=400)
        prompt.interval_minutes = new_interval
        # Recalculate next_run_at
        from datetime import datetime, timezone, timedelta
        prompt.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=prompt.interval_minutes)
    if "temperature" in data:
        prompt.temperature, temp_error = _parse_temperature(data["temperature"])
        if temp_error:
            return temp_error
    if "top_p" in data:
        prompt.top_p, err = _parse_float_range(data["top_p"], "top_p", 0, 1, 0.9)
        if err:
            return err
    if "repeat_penalty" in data:
        prompt.repeat_penalty, err = _parse_float_range(
            data["repeat_penalty"], "repeat_penalty", 0, 2, 1.1)
        if err:
            return err
    if "num_predict" in data:
        prompt.num_predict, err = _parse_num_predict(data["num_predict"])
        if err:
            return err
    if "seed" in data:
        prompt.seed, err = _parse_seed(data["seed"])
        if err:
            return err
    if "keep_alive" in data:
        prompt.keep_alive, err = _parse_keep_alive(data["keep_alive"])
        if err:
            return err
    if "cron_expression" in data:
        prompt.cron_expression = data["cron_expression"]
    if "model_name" in data:
        prompt.model_name = data["model_name"]
    if "is_active" in data:
        # Check max active limit
        if data["is_active"] and not prompt.is_active:
            active_count = PromptConfig.query.filter(PromptConfig.is_active == True).count()
            if active_count >= 10:
                return api_error("Maximum of 10 active prompts allowed", status_code=409, error_code="MAX_ACTIVE_PROMPTS")
        prompt.is_active = data["is_active"]

    db.session.commit()
    return api_ok(prompt.to_dict(include_prompt=True, include_stats=True))


@bp.route("/prompts/<uuid:prompt_id>/run-now", methods=["POST"])
@admin_required
def run_prompt_now(user, prompt_id):
    """Trigger immediate generation(s) for a prompt.

    Optional JSON body {"count": n} (1-5, default 1) enqueues a burst of
    independent runs, bypassing the schedule. Each run gets its own
    PromptRun row; the single-worker ollama queue executes them in order.
    """
    from app.models import PromptRun

    prompt = PromptConfig.query.get_or_404(prompt_id)
    data = request.get_json(silent=True) or {}
    try:
        count = int(data.get("count", 1))
    except (TypeError, ValueError):
        return api_error("Invalid count: must be an integer", status_code=400)
    if not 1 <= count <= 5:
        return api_error("Invalid count: must be between 1 and 5", status_code=400)

    # Record the runs first so the UI can show them as pending immediately.
    from app.tasks.ollama_tasks import generate_idea
    runs = []
    for _ in range(count):
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        job = generate_idea.delay(str(prompt.id), run_id=str(run.id))
        run.job_id = job.id
        db.session.commit()
        runs.append(run)

    first = runs[0]
    return api_ok({
        "job_id": first.job_id,
        "run": first.to_dict(),
        "runs": [r.to_dict() for r in runs],
        "status": "PENDING",
        "message": f"{count} generation(s) enqueued for processing.",
    }, status_code=202)


@bp.route("/prompts/<uuid:prompt_id>", methods=["DELETE"])
@admin_required
def delete_prompt(user, prompt_id):
    """Delete a prompt configuration."""
    prompt = PromptConfig.query.get_or_404(prompt_id)
    db.session.delete(prompt)
    db.session.commit()
    return api_ok({"message": "Prompt deleted successfully"})