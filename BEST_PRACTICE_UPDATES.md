# Suggested Updates to OpenCode Best Practice Guide

Based on gaps identified in the Brainstormer PRD vs current Best Practices.

---

## 1. New Section: Background Job Processing (Add after Section 10)

### 10.x Background Workers & Task Queues

**When to use**: Long-running operations (LLM calls, report generation, email, webhooks) that exceed HTTP timeout.

#### Recommended Stack
| Component | Library | Purpose |
|-----------|---------|---------|
| Queue | Redis + Celery | Reliable, scalable, supports priorities/retries |
| Scheduler | Celery Beat / APScheduler | Cron-style recurring tasks |
| Monitoring | Flower / Celery Prometheus Exporter | Visibility into queue health |

#### Project Structure
```
app/
├── tasks/
│   ├── __init__.py          # Celery app factory
│   ├── base.py              # Base task class with retry/timeout
│   ├── ollama_tasks.py      # LLM generation tasks
│   └── maintenance_tasks.py # Cleanup, aggregation
├── workers/
│   └── ollama_worker.py     # Dedicated worker process entrypoint
```

#### Celery Config Pattern (`app/tasks/__init__.py`)
```python
from celery import Celery
from celery.signals import task_failure, task_retry
import structlog

logger = structlog.get_logger()

def create_celery(app=None):
    celery = Celery(
        "brainstormer",
        broker=app.config["CELERY_BROKER_URL"],
        backend=app.config["CELERY_RESULT_BACKEND"],
        include=["app.tasks.ollama_tasks"],
    )
    celery.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_soft_time_limit=120,      # SIGTERM after 120s
        task_time_limit=150,           # SIGKILL after 150s
        worker_prefetch_multiplier=1,  # Critical for GPU/CPU bound LLM tasks
        task_routes={
            "app.tasks.ollama_tasks.*": {"queue": "ollama"},
            "app.tasks.maintenance_tasks.*": {"queue": "default"},
        },
    )

    # Retry policy for Ollama tasks
    celery.conf.task_annotations = {
        "app.tasks.ollama_tasks.generate_idea": {
            "autoretry_for": (ConnectionError, TimeoutError, OllamaError),
            "retry_backoff": True,
            "retry_backoff_max": 300,
            "retry_jitter": True,
            "max_retries": 3,
        }
    }

    if app:
        celery.init_app(app)

    return celery


class BaseTask(celery.Task):
    """Base task with structured logging and error context."""
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "task_failed",
            task_id=task_id,
            task_name=self.name,
            args=args,
            kwargs=kwargs,
            exc_info=exc,
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)


@task_failure.connect
def log_task_failure(sender=None, exception=None, **kwargs):
    logger.error("celery_task_failure", sender=sender, exception=str(exception))
```

#### Ollama Task Pattern (`app/tasks/ollama_tasks.py`)
```python
from app.tasks import celery, BaseTask
from app.services.ollama_client import OllamaClient, OllamaError
from app.models.idea import Idea
from app.extensions import db
import json

@celery.task(bind=True, base=BaseTask, name="app.tasks.ollama_tasks.generate_idea")
def generate_idea(self, prompt_config_id: str):
    """Generate idea from prompt config. Retries on Ollama failure."""
    from app.models.prompt_config import PromptConfig

    prompt_config = PromptConfig.query.get(prompt_config_id)
    if not prompt_config or not prompt_config.is_active:
        logger.warning("prompt_not_found_or_inactive", prompt_config_id=prompt_config_id)
        return

    client = OllamaClient()
    try:
        response = client.generate(
            model=prompt_config.model_name,
            prompt=prompt_config.prompt_body,
            format="json",  # Enforce structured output
            options={"temperature": prompt_config.temperature or 0.7},
        )
        structured = json.loads(response["response"])

        idea = Idea(
            reference_code=generate_reference_code(),
            prompt_title=prompt_config.title,
            raw_content=response["response"],
            structured_content=json.dumps(structured),
            prompt_config_id=prompt_config.id,
            status="NEW",
        )
        db.session.add(idea)
        prompt_config.last_run_at = datetime.utcnow()
        prompt_config.next_run_at = calculate_next_run(prompt_config.interval_minutes)
        db.session.commit()

        logger.info("idea_generated", idea_id=idea.id, prompt_id=prompt_config.id)

    except json.JSONDecodeError as e:
        # One retry with stricter prompt
        if self.request.retries == 0:
            logger.warning("json_decode_failed_retrying", prompt_id=prompt_config_id, error=str(e))
            stricter_prompt = prompt_config.prompt_body + "\n\nOUTPUT MUST BE VALID JSON ONLY."
            raise self.retry(exc=e, args=[prompt_config_id], kwargs={"override_prompt": stricter_prompt})
        logger.error("json_decode_failed_final", prompt_id=prompt_config_id)
        raise

    except OllamaError as e:
        logger.error("ollama_error", prompt_id=prompt_config_id, error=str(e))
        raise
```

#### Running Workers
```bash
# Dedicated Ollama worker (concurrency=1 to prevent VRAM contention)
celery -A app.tasks worker -Q ollama -c 1 --loglevel=info

# Default worker for other tasks
celery -A app.tasks worker -Q default -c 4 --loglevel=info

# Scheduler (single instance)
celery -A app.tasks beat --loglevel=info
```

---

## 2. New Section: LLM Integration Patterns (Add after Background Jobs)

### 10.y Local LLM Integration (Ollama)

#### Client Wrapper (`app/services/ollama_client.py`)
```python
import httpx
import structlog
from typing import Any
from pydantic import BaseModel

logger = structlog.get_logger()

class OllamaError(Exception):
    pass

class GenerateRequest(BaseModel):
    model: str
    prompt: str
    format: str = "json"
    stream: bool = False
    options: dict = {}

class GenerateResponse(BaseModel):
    response: str
    done: bool
    context: list[int] | None = None

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def list_models(self) -> list[dict]:
        resp = await self._client.get(f"{self.base_url}/api/tags")
        resp.raise_for_status()
        return resp.json().get("models", [])

    async def generate(self, **kwargs) -> dict:
        request = GenerateRequest(**kwargs)
        resp = await self._client.post(
            f"{self.base_url}/api/generate",
            json=request.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return GenerateResponse(**resp.json()).model_dump()

    async def close(self):
        await self._client.aclose()

    # Sync wrapper for Celery tasks
    def generate_sync(self, **kwargs) -> dict:
        import asyncio
        return asyncio.run(self.generate(**kwargs))
```

#### Prompt Template System (`app/services/prompt_templates.py`)
```python
from string import Template
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "prompt_templates"

class PromptTemplate:
    def __init__(self, name: str):
        self.template = (TEMPLATES_DIR / f"{name}.txt").read_text()

    def render(self, **kwargs) -> str:
        # Safe substitution - missing keys left as {{KEY}}
        return Template(self.template).safe_substitute(kwargs)

# Usage
REFINE_TEMPLATE = PromptTemplate("refine")
prompt = REFINE_TEMPLATE.render(ORIGINAL_IDEA_CONTENT=idea.raw_content)
```

#### Template Files (`app/prompt_templates/refine.txt`)
```
You are an expert startup advisor and product strategist...

### RAW BUSINESS IDEA:
{{ORIGINAL_IDEA_CONTENT}}

---
### INSTRUCTIONS:
...

### OUTPUT JSON SCHEMA:
{
  "elevator_pitch": "...",
  "target_audience": "...",
  "core_value_proposition": "...",
  "monetization_strategy": "..."
}
```

#### Response Validation (`app/schemas/ollama_schemas.py`)
```python
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class RefineOutput(BaseModel):
    elevator_pitch: str = Field(..., min_length=10, max_length=500)
    target_audience: str = Field(..., min_length=5, max_length=300)
    core_value_proposition: str = Field(..., min_length=10, max_length=500)
    monetization_strategy: str = Field(..., min_length=5, max_length=300)

class Competitor(BaseModel):
    name: str
    description: str
    advantage_over_idea: str

class CompetitorsOutput(BaseModel):
    direct_competitors: List[Competitor]
    indirect_competitors: List[str]
    differentiator: str
    barriers_to_entry: List[str]

class FeasibilityScore(BaseModel):
    score: int = Field(..., ge=1, le=10)
    reasoning: str

class FeasibilityOutput(BaseModel):
    overall_score: float = Field(..., ge=1.0, le=10.0)
    scores: dict[str, FeasibilityScore]
    verdict: str  # "RECOMMENDED" | "PROCEED WITH CAUTION" | "HIGH RISK"

# Validation in task
def validate_ollama_output(action_type: str, raw_json: str) -> BaseModel:
    schema_map = {
        "REFINE": RefineOutput,
        "COMPETITORS": CompetitorsOutput,
        "FEASIBILITY_SCORE": FeasibilityOutput,
    }
    model = schema_map[action_type]
    return model.model_validate_json(raw_json)
```

---

## 3. New Section: Structured Output Enforcement (Add to LLM Integration)

### 10.z JSON Mode & Validation

| Requirement | Implementation |
|-------------|----------------|
| **Always** use `format: "json"` in Ollama request | Client wrapper enforces |
| Validate response against Pydantic schema | `validate_ollama_output()` |
| Retry once with stricter prompt on parse failure | Celery task `autoretry` + custom logic |
| Log raw response on validation failure (DEBUG only) | Structured logging |
| Dead-letter queue for repeated failures | Celery `task_reject_on_worker_lost` + custom consumer |

---

## 4. Updates to Section 4: Testing Strategies

### Add to 4.1 Test Types

#### Background Task Tests
```python
# tests/unit/test_ollama_tasks.py
import pytest
from unittest.mock import patch, MagicMock
from app.tasks.ollama_tasks import generate_idea

@patch("app.tasks.ollama_tasks.OllamaClient")
def test_generate_idea_success(mock_client, app, prompt_config):
    mock_client.return_value.generate_sync.return_value = {
        "response": '{"elevator_pitch": "Test", "target_audience": "Devs", "core_value_proposition": "Speed", "monetization_strategy": "SaaS"}',
        "done": True,
    }

    generate_idea(prompt_config.id)

    idea = Idea.query.filter_by(prompt_config_id=prompt_config.id).first()
    assert idea is not None
    assert idea.status == "NEW"
    assert json.loads(idea.structured_content)["elevator_pitch"] == "Test"

@patch("app.tasks.ollama_tasks.OllamaClient")
def test_generate_idea_json_retry(mock_client, app, prompt_config):
    # First call returns invalid JSON, second returns valid
    mock_client.return_value.generate_sync.side_effect = [
        {"response": "not json", "done": True},
        {"response": '{"elevator_pitch": "Test", "target_audience": "Devs", "core_value_proposition": "Speed", "monetization_strategy": "SaaS"}', "done": True},
    ]

    generate_idea(prompt_config.id)

    assert mock_client.return_value.generate_sync.call_count == 2
```

#### Integration Test for Full Pipeline
```python
# tests/integration/test_idea_pipeline.py
def test_full_idea_generation_flow(client, admin_headers, prompt_config):
    # 1. Create prompt
    resp = client.post("/api/v1/prompts", json={...}, headers=admin_headers)
    assert resp.status_code == 201

    # 2. Trigger run-now
    resp = client.post(f"/api/v1/prompts/{prompt_id}/run-now", headers=admin_headers)
    assert resp.status_code == 202

    # 3. Wait for worker (test uses eager mode)
    # 4. Verify idea appears
    resp = client.get("/api/v1/ideas", headers=admin_headers)
    assert resp.json["total"] == 1
```

### Update Coverage Targets
| Type | Coverage Target | Notes |
|------|-----------------|-------|
| Unit | 80%+ business logic | Include task logic |
| Integration | 70%+ API endpoints | Include task triggering |
| Background Tasks | 90%+ task logic | Critical for LLM pipeline |
| E2E | Critical paths only | Idea generation → vote → action |

---

## 5. Updates to Section 8: Quality Assurance

### Add to 8.1 Pre-Commit Checks
```bash
# New checks
- run `celery -A app.tasks inspect ping` (verify worker connectivity in CI)
- run `pytest tests/unit/test_ollama_tasks.py` (task logic)
- run `bandit -r app/services/ollama_client.py` (LLM client security)
```

### Add to 8.2 Code Review Checklist
```markdown
### LLM-Specific Review
- [ ] All Ollama calls use `format: "json"`
- [ ] Response validated against Pydantic schema
- [ ] Retry logic with exponential backoff configured
- [ ] No user input in system prompt (template only)
- [ ] Timeouts configured (soft/hard)
- [ ] Concurrency limited for GPU-bound tasks
- [ ] Prompt templates in `app/prompt_templates/` not hardcoded
```

---

## 6. New Section: Observability for LLM Workloads (Add after Section 11)

### 11.x LLM Observability

#### Metrics to Emit (Prometheus)
```python
from prometheus_client import Counter, Histogram, Gauge

OLLAMA_REQUESTS = Counter("ollama_requests_total", "Total Ollama requests", ["model", "action", "status"])
OLLAMA_LATENCY = Histogram("ollama_latency_seconds", "Ollama request latency", ["model", "action"])
OLLAMA_QUEUE_DEPTH = Gauge("ollama_queue_depth", "Pending Ollama tasks", ["queue"])
IDEA_GENERATED = Counter("ideas_generated_total", "Ideas generated", ["prompt_id", "status"])
```

#### Structured Logging (structlog)
```python
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),  # Production: JSON
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Usage in tasks
logger = structlog.get_logger()

logger.info(
    "ollama_request",
    model=model,
    action=action_type,
    prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:8],
    latency_ms=latency,
    tokens=token_count,
)
```

#### Health Checks
```python
# app/views/health.py
@bp.route("/health")
def health():
    checks = {
        "database": check_db(),
        "redis": check_redis(),
        "ollama": check_ollama(),  # Must respond within 5s
    }
    status = 200 if all(checks.values()) else 503
    return jsonify({"status": "healthy" if status == 200 else "degraded", "checks": checks}), status
```

---

## 7. Updates to Section 13: Environment-Specific Configurations

### Add to 13.1 Configuration Variables

```python
# config.py additions

class Config:
    # ... existing ...

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_DEFAULT_TIMEOUT: int = 120
    OLLAMA_MAX_CONCURRENT: int = 1  # Worker concurrency

    # Security
    JWT_SECRET_KEY: str  # Required, no default
    FERNET_KEY: str      # Required, 32-byte base64
    RATE_LIMIT_STORAGE_URL: str = "redis://localhost:6379/2"

    # Prompt encryption
    ENCRYPT_PROMPTS: bool = True

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///dev.db"
    OLLAMA_BASE_URL = "http://host.docker.internal:11434"  # Docker Mac/Windows

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "postgresql://user:pass@localhost/brainstormer"
    # All secrets from env
```

---

## 8. Updates to Section 14: Cloud Deployment

### Add Railway/Render Deployment for Workers

```yaml
# railway.toml (or render.yaml)
[services.web]
  build.command = "pip install -r requirements.txt"
  start.command = "gunicorn -w 4 -b 0.0.0.0:$PORT run:app"
  healthcheck.path = "/health"

[services.ollama-worker]
  build.command = "pip install -r requirements.txt"
  start.command = "celery -A app.tasks worker -Q ollama -c 1 --loglevel=info"
  # No healthcheck path - worker doesn't serve HTTP

[services.default-worker]
  build.command = "pip install -r requirements.txt"
  start.command = "celery -A app.tasks worker -Q default -c 4 --loglevel=info"

[services.scheduler]
  build.command = "pip install -r requirements.txt"
  start.command = "celery -A app.tasks beat --loglevel=info"
```

---

## 9. New Skill Recommendations

Add these to available skills for this project:

| Skill | Purpose |
|-------|---------|
| `celery-tasks` | Celery patterns for Flask (retry, routing, monitoring) |
| `ollama-integration` | Local LLM client, prompt templates, JSON validation |
| `structured-output` | Pydantic schemas for LLM response validation |
| `prompt-engineering` | Template system, versioning, A/B testing prompts |

---

## 10. Summary: New Files to Create

```
app/
├── tasks/
│   ├── __init__.py
│   ├── base.py
│   ├── ollama_tasks.py
│   └── maintenance_tasks.py
├── services/
│   ├── ollama_client.py
│   └── prompt_templates.py
├── schemas/
│   └── ollama_schemas.py
├── prompt_templates/
│   ├── refine.txt
│   ├── competitors.txt
│   └── feasibility.txt
└── workers/
    └── ollama_worker.py

tests/
├── unit/
│   ├── test_ollama_tasks.py
│   ├── test_ollama_client.py
│   └── test_prompt_templates.py
└── integration/
    └── test_idea_pipeline.py

.github/workflows/
└── guardrails.yml

scripts/
├── check_no_external_calls.py
└── check_no_secrets.py
```

---

## Priority Order for Implementation

1. **Guardrail.md** → Security baseline (done)
2. **Flask bootstrap** → Project structure, venv, tests, AGENTS.md
3. **Celery + Redis** → Background job infrastructure
4. **Ollama client + templates** → LLM integration with JSON enforcement
5. **Prompt config CRUD + scheduler** → Admin features
6. **Ideas API + voting** → Core dashboard
7. **Secondary actions** → Refine/Competitors/Feasibility
8. **Observability** → Metrics, logging, health checks
9. **CI/CD + Deployment** → Automated pipeline