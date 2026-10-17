# Brainstormer

AI-Driven Business Idea Generator & Evaluator

A Flask + SQLite web application with local Ollama LLM integration for automated business idea generation, evaluation, and tracking. Includes Scale-phase collaboration (child ideas, releases, builds), GitHub integration, in-app messaging, and a user homepage.

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
celery -A app.tasks worker -Q opencode -c 1 --loglevel=info
celery -A app.tasks worker -Q default -c 4 --loglevel=info
celery -A app.tasks beat --loglevel=info
```

Open http://127.0.0.1:5000

## What's New

### Scale-Phase Collaboration (Idea → Release → Build)

Once an idea reaches **SCALE** status, users can:

- **Add child ideas** — enhancements or bug fixes linked to the parent app
- **Group into releases** — batch children together for coordinated builds
- **Run actions per child** — PRD, Design, and Build Code on individual ideas
- **Write builds** — write confirmed code manifests directly to the app's repo
- **Mark release done** — bulk-complete all children (SHIP/DROP), auto-generates release notes
- **Publish to GitHub** — push build output to a per-instance GitHub repo

### In-App Messaging (Phase 4: Talk)

Users and admins can exchange messages within the app:

- Users → Instance Admins: feedback, suggestions, questions
- Admins → Users: announcements, responses, forwarded feedback
- Read receipts and unread badges on the homepage
- Share links to ideas and comments within messages
- Two-way Slack bridging (where configured)

### User Homepage

New users land on `/home` with:

- **My ideas** — ideas you created, voted on, or commented on
- **Most popular** — highest-voted ideas
- **Most discussed** — highest-commented ideas
- **Messages** — in-app messaging with admin
- **Ideas in each phase** — admin-only analytics dashboard

## Testing

```bash
source venv/bin/activate
pytest
```

Coverage must stay at or above 80%.

```bash
# E2E tests (requires running instance at http://localhost:8000)
python tests/ui/test_scale_e2e.py
```

## Documentation

- [Architecture](docs/architecture.md)
- [ERD](docs/erd.md)
- [Install & configuration](docs/install-config.md)
- [User guide](docs/user-guide.md)
- [Security & Privacy Guardrails](Guardrail.md)
- [Product Requirements](PRD.md)
- [Roadmap](docs/ROADMAP.md)

## API Reference

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

- `GET /api/v1/ideas` — paginated, filterable list (`?mine=true` for user's ideas)
- `GET /api/v1/ideas/{id}` — full detail with family context (parent/children)
- `PATCH /api/v1/ideas/{id}/status` — update status (Admin)
- `POST /api/v1/ideas/{id}/vote` — `{direction: 1|-1}`
- `POST /api/v1/ideas/{id}/actions` — `{action_type}` (Admin: PRD_DOC, DESIGN_DOC, BUILD_CODE, etc.)
- `GET /api/v1/ideas/{id}/actions` — action results history
- `GET /api/v1/ideas/{id}/children` — child ideas (enhancements/bugfixes)
- `POST /api/v1/ideas` — create idea (optionally `parent_id` + `child_kind` for Scale children)
- `GET /api/v1/ideas/phase-counts` — ideas per lifecycle stage (admin analytics)

### Child Ideas & Releases (Scale Phase)

- `GET /api/v1/ideas/{parent_id}/children` — paginated child list
- `GET /api/v1/ideas/{parent_id}/releases` — release list (newest first)
- `POST /api/v1/ideas/{parent_id}/releases` — create release
- `PATCH /api/v1/releases/{id}` — update release (name, status, target_date, notes)
- `PATCH /api/v1/releases/{id}/assign` — move child ideas into release
- `PATCH /api/v1/releases/{id}/unassign` — move children back to "No release"
- `POST /api/v1/releases/{id}/complete` — bulk-complete children (SHIP/DROP), auto-notes
- `POST /api/v1/releases/{id}/notes` — regenerate release notes
- `DELETE /api/v1/releases/{id}` — delete empty release
- `POST /api/v1/releases/{id}/run-action` — run action on all children (PRD_DOC, DESIGN_DOC, BUILD_CODE)
- `POST /api/v1/releases/{id}/github-push` — push build output to GitHub (admin)

### Build Targets & GitHub

- `GET /api/v1/instances/{id}/build-targets` — registered build repos
- `POST /api/v1/instances/{id}/build-targets` — register a build repo
- `DELETE /api/v1/instances/{id}/build-targets/{id}` — delete build repo
- `GET /api/v1/instances/{id}/github-config` — GitHub push settings (admin)
- `PUT /api/v1/instances/{id}/github-config` — set GitHub repo + PAT (admin)
- `DELETE /api/v1/instances/{id}/github-config` — remove GitHub settings

### In-App Messaging (Phase 4)

- `GET /api/v1/messages` — inbox/sent messages (paginated)
- `GET /api/v1/messages/unread-count` — unread badge count
- `POST /api/v1/messages` — send message (users→admins, admins→members)
- `GET /api/v1/messages/admins` — messageable admins (picker)
- `PATCH /api/v1/messages/{id}/read` — mark as read
- `DELETE /api/v1/messages/{id}` — delete own message (admin: any)

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
- **Task Queue**: Celery + Redis (separate queues for Ollama, OpenCode vs default)
- **Ollama Workers**: Dedicated concurrency=1 to prevent GPU contention
- **OpenCode Provider**: CLI-backed agentic generation on its own serial queue (shared server identity; sandbox by default)
- **Prompt Templates**: File-based, version-controlled, JSON-enforced outputs
- **Response Validation**: Pydantic schemas for all LLM responses

## Security & Privacy

- **Zero external calls** — Ollama runs locally, no telemetry
- **Encrypted prompt configs** — Fernet at rest
- **Encrypted GitHub PATs** — Fernet at rest (per-instance)
- **Structured logging** — No PII, prompt hashes only
- **Rate limiting** — Per-endpoint, per-user/IP
- **CSP + Talisman** — Secure headers, no inline scripts