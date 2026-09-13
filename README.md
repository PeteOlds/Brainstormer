# Brainstormer

AI-Driven Business Idea Generator & Evaluator

A Flask + SQLite web application with local Ollama LLM integration for automated business idea generation, evaluation, and tracking.

## Quickstart

Prerequisites: Python 3.10+, Redis, Ollama (local).

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements-dev.txt

# 3. Configure
cp .env.example .env   # then edit SECRET_KEY, JWT_SECRET_KEY, FERNET_KEY

# 4. Start Redis (required for Celery)
redis-server

# 5. Start Ollama (required for LLM)
ollama serve

# 6. Run database migrations
flask db upgrade

# 7. Run the dev server
python run.py

# 8. In separate terminals, start workers:
celery -A app.tasks worker -Q ollama -c 1 --loglevel=info
celery -A app.tasks worker -Q default -c 4 --loglevel=info
celery -A app.tasks beat --loglevel=info
```

Open http://127.0.0.1:5000

## Testing

```bash
source venv/bin/activate
pytest
```

Coverage must stay at or above 80%.

## Documentation

- [Architecture](docs/architecture.md)
- [ERD](docs/erd.md)
- [Install & configuration](docs/install-config.md)
- [User guide](docs/user-guide.md)
- [Security & Privacy Guardrails](Guardrail.md)
- [Product Requirements](PRD.md)

## API (Planned)

### Authentication

- `POST /api/v1/auth/register` — `{email,password,name}` → `{user, access_token, refresh_token}`
- `POST /api/v1/auth/login` — `{email,password}` → `{user, access_token, refresh_token}`
- `POST /api/v1/auth/refresh` — `refresh_token` → new `access_token`
- `GET /api/v1/auth/me` — `Authorization: Bearer <token>`

### Prompt Configuration (Admin)

- `GET /api/v1/prompts` — list all prompts
- `POST /api/v1/prompts` — create prompt
- `PATCH /api/v1/prompts/{id}` — update prompt
- `POST /api/v1/prompts/{id}/run-now` — trigger immediate generation

### Ideas & Dashboard

- `GET /api/v1/ideas` — paginated, filterable list
- `GET /api/v1/ideas/{id}` — full detail + action history
- `PATCH /api/v1/ideas/{id}/status` — update status (Admin)
- `POST /api/v1/ideas/{id}/vote` — `{direction: 1|-1}`
- `POST /api/v1/ideas/{id}/actions` — `{action_type: REFINE|COMPETITORS|FEASIBILITY_SCORE}` (Admin)
- `GET /api/v1/ideas/{id}/actions` — action results history

### Ollama Models

- `GET /api/v1/ollama/models` — list installed models (Admin)

### Health

- `GET /api/health` — liveness (DB + Redis + Ollama)
- `GET /api/ready` — readiness (queue depth, worker status)

## Versioning

This project uses [Semantic Versioning](https://semver.org/). See
[CHANGELOG.md](CHANGELOG.md) and [VERSION](VERSION).

## Architecture Overview

```
Client (Web/PWA) → API Gateway (Flask) → Redis Queue → Celery Workers → Local Ollama
                                    ↓
                              PostgreSQL/SQLite
```

Key components:
- **API Layer**: Flask blueprints, JWT auth, rate limiting
- **Task Queue**: Celery + Redis (separate queues for Ollama vs default)
- **Ollama Workers**: Dedicated concurrency=1 to prevent GPU contention
- **Prompt Templates**: File-based, version-controlled, JSON-enforced outputs
- **Response Validation**: Pydantic schemas for all LLM responses

## Security & Privacy

- **Zero external calls** — Ollama runs locally, no telemetry
- **Encrypted prompt configs** — Fernet at rest
- **Structured logging** — No PII, prompt hashes only
- **Rate limiting** — Per-endpoint, per-user/IP
- **CSP + Talisman** — Secure headers, no inline scripts
