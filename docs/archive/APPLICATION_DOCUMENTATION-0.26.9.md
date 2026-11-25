# Brainstormer — Full Application Documentation (archived)

> Historical snapshot of v0.26.9. Do not treat it as the current spec.
> Current behaviour is recorded in `PRD_V2.md`, `docs/Design.md`,
> `Guardrail.md`, `AGENTS.md` and `ReleaseNotes.md`.

**Version:** 0.26.9 (`VERSION`, 2026-09-27)
**Purpose:** AI-driven business idea generator and evaluator. Automatically generates ideas via a local LLM (Ollama), supports voting, threaded discussion, structured analysis documents, and Slack collaboration.
**Audience for this document:** developers iterating on the codebase or replatforming it (e.g. to another language/framework).
**Stack:** Flask 3 + SQLAlchemy + Flask-Migrate (Alembic) + Celery + Redis + Ollama + Jinja2/Tailwind (CDN)/Alpine.js. SQLite by default, PostgreSQL in production. See `requirements.txt`, `Dockerfile`, `docker-compose.yml`.

Related docs: `PRD.md` (product spec, 1384 lines), `docs/architecture.md`, `docs/erd.md`, `docs/install-config.md`, `docs/user-guide.md`, `Guardrail.md` (security rules), `AGENTS.md` (project standards), `CHANGELOG.md` (Keep a Changelog).

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Data Model](#3-data-model)
4. [Functions — Backend API and Logic](#4-functions--backend-api-and-logic)
5. [Screens — Frontend](#5-screens--frontend)
6. [Design Decisions](#6-design-decisions)
7. [Tests](#7-tests)
8. [Configuration, Deployment, Operations](#8-configuration-deployment-operations)
9. [Replatforming Guide](#9-replatforming-guide)
10. [Appendices](#10-appendices)

---

## 1. System Overview

### 1.1 What it does

1. **Prompt configs** (admin-defined): title + encrypted body + schedule (interval minutes / cron) + model + generation params + optional Slack channel. Max 10 active.
2. **Scheduler** (Celery Beat, every 60 s): finds due prompts, enqueues `generate_idea` on the `ollama` queue (concurrency 1, GPU-safe) — or the dedicated `opencode` queue for OpenCode-provider prompts.
3. **Generation** (Celery worker): renders `prompt_templates/initial.txt` with memory sections (avoid recent 10, explore top-3 voted), calls Ollama `/api/generate` with `format: json`, validates against the `REFINE` Pydantic schema, creates an `Idea`, generates an embedding (`nomic-embed-text` via `/api/embeddings`), dedups (cosine ≥ 0.97 → auto-DISCARD, no Slack), otherwise posts to Slack.
4. **Evaluation:** users vote (±1, toggle), comment (threaded), run 13 secondary analysis actions (competitors, feasibility, forces, PESTEL, Brief, design doc, VRIO, 3Cs, market sizing, canvas, hypothesis test, GTM, refine). Brief/design docs are versioned, editable (admin), with per-document comment threads and PRD open-question Q&A.
5. **Tracking:** 7-state lifecycle (NEW → CONSIDERATION / HOLD / DESIGN / BUILD / COMPLETE, plus DISCARDED), status history audit, admin health/activity dashboards, system settings.

### 1.2 Roles

| Role | Capabilities |
|------|--------------|
| Anonymous | `/login`, `/register`, `/api/health`, `/api/ready` only |
| USER | View ideas/prompts (list), vote, comment, create manual ideas (if `can_create_ideas`), list actions, run read-only endpoints, `/ollama/models` |
| ADMIN | All of USER plus: prompt CRUD + test + run-now, idea status change + bulk status + content edit, run secondary actions, edit PRD/design docs, user management, activity/stats/health, settings |

Auth: JWT access (short-lived) + DB-backed rotating refresh tokens; "Remember Me" extends refresh to 30 days (else 7). See §6.5.

### 1.3 Repository layout

```
app/__init__.py            # create_app() factory
app/config.py              # development / production / testing configs
app/extensions.py          # db, migrate, jwt, limiter, talisman, redis_client
app/cli.py                 # flask create-admin / create-user / list-users / promote-user
app/models/                # User, RefreshToken, PromptConfig, PromptRun, Idea,
                           # Vote, Comment, IdeaEdit, SecondaryActionResult,
                           # IdeaStatusHistory, SlackPost, SlackEvent, SystemSettings
                           # types.py (GUID, ensure_aware), enums.py
app/routes/                # pages, health, auth, ollama, prompts, ideas, admin
app/services/              # ollama_client, prompt_templates, secondary_actions,
                           # action_context, embedding_service, discovery, slack_service
app/schemas/               # ollama_schemas.py (13 Pydantic models + validator)
app/utils/                 # decorators (token_required/admin_required), auth (JWT),
                           # crypto (Fernet), markdown, responses (api_* envelope)
app/tasks/                 # __init__ (celery + BaseTask), ollama_tasks, maintenance_tasks
app/prompt_templates/      # 15 x .txt (base, initial, + 13 action templates)
app/templates/             # base.html, base_auth.html, index.html (orphaned),
                           # auth/, ideas/dashboard.html, prompts/, admin/,
                           # partials/, admin_settings_template.py
app/static/js/alpine.min.js# only vendored asset; CSS via Tailwind CDN
app/guidelines/            # guideline docs injected into runs
run.py / wsgi.py / asgi.py / celery_worker.py / celery_beat.py / slack_listener.py
migrations/versions/       # 23 Alembic revisions
tests/                     # 7 test files, 207 tests (see §7)
docs/                      # architecture, erd, install-config, user-guide + this file
```

---

## 2. Architecture

### 2.1 Runtime topology

```
Browser (Jinja + Alpine + fetch, JWT in localStorage)
  │  HTTPS (TLS at proxy in prod)
  ▼
Flask web (gunicorn x2 prod / hypercorn dev :8000)
  ├─► PostgreSQL 16 (prod) / SQLite (dev/test)
  ├─► Redis 7 (DB 0 broker, 1 backend, 2 rate-limit, 3 testing)
  ├─► Ollama (:11434, /api/generate + /api/embeddings + /api/tags)
  └─► Celery: worker-ollama (-Q ollama -c 1) + worker-default (-Q default -c 4) + beat
Slack Socket-Mode listener (slack_listener.py, separate process) ─► same DB
```

Compose services (`docker-compose.yml`): `postgres`, `redis`, `ollama`, `web`, `worker-ollama`, `worker-default`, `scheduler`. Dev compose bind-mounts source and exposes 5432/6379/11434/8000.

### 2.2 App factory (`app/__init__.py:create_app()`)

1. Resolve `FLASK_ENV` → config class (`development`/`production`/`testing`/`default`).
2. `init_extensions(app)`: SQLAlchemy, Migrate, JWTManager, Limiter, `redis.from_url`, Talisman CSP.
3. Read `VERSION` file → `app.config["VERSION"]`.
4. Lazy `init_celery(app)` (avoids circular import; workers also auto-`create_app()` on `app.tasks` import).
5. Import models (register with SQLAlchemy), register blueprints (see §4.1), JSON 404/500 handlers, `register_cli`.
6. `after_request`: `Cache-Control: no-cache, no-store, must-revalidate` on all `text/html` (lesson learned: stale cached JS hid a broken login handler; meta tags alone are not enough).
7. `context_processor`: `_nav_links()` — single nav source (`Ideas → pages.ideas`, `Prompts → pages.prompts`).

### 2.3 Key request flows

**Generate idea:** Beat `check_due_prompts` (60 s) → reconcile orphans (>45 min PENDING/RUNNING → FAILED) → due active prompts without live runs → `generate_idea.delay(prompt_id, run_id)` on `ollama` queue → worker: mark RUNNING → model preflight → render initial+base → `generate_sync(format=json)` → `validate_ollama_output(REFINE)` → create Idea + bump `last/next_run_at` → embedding → dedup check → Slack post or auto-discard. JSON errors retry once; Ollama errors auto-retry (max 3, backoff ≤ 300 s); final failure recorded via `_record_failure`.

**Secondary action:** `POST /ideas/<id>/actions {action_type, ...}` (admin) → DESIGN gate (PRD/DESIGN_DOC require DESIGN status; DESIGN_DOC requires a current Brief) → 409 CONFIRMATION_REQUIRED for REFINE/PRD when 0 comments and <3 prior actions unless `confirm: true` → `run_secondary_action.delay` → cold temp (≤0.3), num_predict floor 4000 (8000 complex) → template + `build_idea_context` (idea + comments + prior docs + votes, 8k chars) + answers + skills/guidelines (6k budget) → `_call_and_validate` (strip fences, strict retry on ValidationError) → `_drop_answered_questions` (fuzzy 0.8) for PRD/DESIGN → versioned `SecondaryActionResult` (flip `is_current`) → feasibility score copied to idea.

**Vote:** `POST /ideas/<id>/vote {direction: 1|-1}` → toggle off if same, flip if different → SQLAlchemy event listeners patch `Idea.upvotes/downvotes/net_score` incrementally (full recompute available via `recalculate_vote_counts`).

**Refresh:** `POST /api/v1/refresh {refresh_token}` → verify hash → create replacement → `old.revoke(replaced_by=new)` → return new pair (chain auditable).

---

## 3. Data Model

Conventions (critical for replatforming):

- **PKs:** `GUID()` TypeDecorator (`app/models/types.py`) — PostgreSQL native `UUID(as_uuid=True)`, otherwise `CHAR(36)` with `uuid.UUID ↔ str` conversion, `default=uuid.uuid4`. All PKs/FKs use it.
- **Timestamps:** `DateTime(timezone=True)`, written as `datetime.now(timezone.utc)`. SQLite returns **naive** datetimes — always compare via `ensure_aware(dt)` (treats naive as UTC) or `TypeError` results.
- **JSON columns:** plain `db.JSON` (`structured_content`, `embedding`, `result_data`, `answers`, settings blobs). **Never mutate in place** — build a fresh dict and assign, or SQLAlchemy skips the UPDATE.
- **Soft delete:** ideas are discarded via `status=DISCARDED`, comments via `is_deleted` (masked as `[deleted]`), never hard-deleted except via admin user delete / prompt delete (cascades runs).

### 3.1 Tables

| Model / Table | Key fields | Relationships / notes |
|---|---|---|
| `User` (`users`) `app/models/user.py` | `id, email unique indexed, password_hash(128), name(100), role Enum(UserRole) default USER, is_active, last_login_at nullable, login_count default 0, slack_user_id(20) unique nullable, can_create_ideas default True, created_at/updated_at` | `record_login()`, `set_password()`, `check_password()`, `to_dict()` |
| `RefreshToken` (`refresh_tokens`) | `id, user_id FK indexed, token_hash(128) sha256 indexed, is_revoked, created_at, expires_at, revoked_at nullable, replaced_by_id self-FK nullable` | Self-ref `replaced_by`; `is_valid()` (not revoked + `ensure_aware(expires_at) > now`); `revoke(replaced_by)`; `create_token()` returns `(raw, obj)`; `verify_token(raw)` |
| `PromptConfig` (`prompt_configs`) | `id, title(200), _prompt_body Text Fernet-encrypted, interval_minutes, cron_expression(100) nullable, model_name(100), temperature .7, top_p .9, repeat_penalty 1.1, num_predict 1000, seed nullable, keep_alive "2h", slack_channel(80) nullable, is_active, last_run_at, next_run_at indexed, created_by_id FK, created_at/updated_at` | `created_by → User`; `ideas` dynamic; `runs` dynamic cascade delete-orphan; `prompt_body` property encrypt/decrypt; `run_stats()`; `to_dict(include_prompt, include_stats)` |
| `PromptRun` (`prompt_runs`) | `id, prompt_config_id FK nullable indexed (null = follow-up), action_type(30) nullable, triggered_by default "manual", job_id(100) nullable, idea_id FK nullable, status Enum(PENDING/RUNNING/SUCCESS/FAILED) indexed, error Text, started_at/finished_at, duration_seconds, created_at` | `mark_running/success(idea_id)/failed(error)` (uses `ensure_aware`); `display_title`; `to_dict()` |
| `Idea` (`ideas`) | `id, reference_code(20) unique indexed (IDEA-XXXX sequential), prompt_title(200), raw_content Text, structured_content JSON, status Enum IdeaStatus default NEW indexed, upvotes/downvotes/comments_count/net_score indexed, feasibility_score nullable, embedding JSON nullable, prompt_config_id FK nullable indexed, created_at indexed/updated_at` | `votes/comments/actions/status_history` dynamic cascade delete-orphan; `excerpt()` prefers elevator_pitch/summary; `to_dict(include_content, user_vote)`; `update_vote_counts()`; `actions_run` |
| `Vote` (`votes`) | `id, user_id FK CASCADE indexed, idea_id FK CASCADE indexed, value SmallInteger ±1, created/updated_at` | `uq_user_idea_vote(user_id, idea_id)`; `after_insert/delete/update` listeners patch idea counters |
| `Comment` (`comments`) | `id, idea_id FK CASCADE indexed, user_id FK CASCADE indexed, parent_id self-FK nullable indexed, body Text (≤2000 enforced in routes), is_deleted, scope(20) default "idea" ("idea"\|"doc"), action_result_id FK nullable indexed, created/updated_at` | Self-ref `replies` cascade; `to_dict(author, children)`; listeners adjust `Idea.comments_count` on top-level non-deleted insert/delete; `before_update` handles soft-delete/restore |
| `IdeaEdit` (`idea_edits`) | `id, idea_id FK CASCADE indexed, editor_id FK CASCADE indexed, field(50), old/new_value Text, edited_at` | Admin edit audit; `to_dict(editor_name)` |
| `SecondaryActionResult` (`secondary_action_results`) | `id, idea_id FK CASCADE indexed, action_type Enum ActionType, model_used(100), result_data JSON NOT NULL, executed_at indexed, version default 1, is_current indexed, edited_by_id FK nullable, answers JSON nullable` | Rerun/edit appends new row + flips `is_current`; `to_dict()` exposes `output=result_data` |
| `IdeaStatusHistory` (`idea_status_history`) | `id, idea_id FK CASCADE indexed, changed_by_id FK CASCADE, old/new_status Enum, changed_at indexed` | `to_dict()` |
| `SlackPost` (`slack_posts`) | `id, idea_id FK CASCADE indexed, channel_id(20), message_ts(30), created_at` | `uq_slack_post(channel_id, message_ts)` maps Slack msg → idea |
| `SlackEvent` (`slack_events`) | `event_id(60) PK, received_at` | Idempotency for retried Slack events |
| `SystemSettings` (`system_settings`) | `id, platform/location/ai_connections JSON default {}, created/updated_at` | Singleton via `get_instance()`; `to_dict()`, `update_*` (plain assign) |

### 3.2 Enums (`app/models/enums.py`; duplicates exist in `user.py`, `prompt_run.py`, `prompt_config.py` — canonical is `enums.py`)

- `IdeaStatus`: NEW, CONSIDERATION, HOLD, DESIGN, BUILD, COMPLETE, DISCARDED
- `PromptRunStatus`: PENDING, RUNNING, SUCCESS, FAILED
- `UserRole`: ADMIN, USER
- `PromptStatus`: active, paused
- `ActionType` (13): REFINE, COMPETITORS, FEASIBILITY_SCORE, FIVE_FORCES, PESTEL, PRD_DOC, VRIO, THREE_CS, MARKET_SIZING, BUSINESS_MODEL_CANVAS, HYPOTHESIS_TEST, GTM_STRATEGY, DESIGN_DOC

ER diagram: see `docs/erd.md`. Migrations: 23 Alembic revisions in `migrations/versions/` (initial → design status → run actions → generation params → embeddings → comments/counts → edits/audit → doc threads/versions/answers → PRD/forces/PESTEL → BUILD replaces DEVELOPMENT → login tracking → system settings → heads merge).

---

## 4. Functions — Backend API and Logic

Envelope: all API responses use `app/utils/responses.py` — `api_ok / api_error / api_created / api_accepted / api_no_content` → `{success, data|message}`. Auth decorators (`app/utils/decorators.py`): `token_required` (any active user, injects `user` as first arg), `admin_required` (role ADMIN, else 403).

### 4.1 Blueprints and endpoints

**`pages`** (`app/routes/pages.py`, no prefix, public HTML):

| Method | Path | Handler |
|---|---|---|
| GET | `/` | redirect `pages.login` |
| GET | `/dashboard` | redirect `pages.ideas` (legacy alias) |
| GET | `/ideas` | `ideas/dashboard.html` |
| GET | `/prompts` | `prompts/list.html` |
| GET | `/prompts/create` | `prompts/create.html` (admin-gated in JS) |
| GET | `/login`, `/register` | `auth/*.html` |

**`health`** (`app/routes/health.py`):

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/health` | none | Liveness: DB + Redis + scheduler (beat heartbeat); 200 healthy / 503 degraded |
| GET | `/api/ready` | none | Above + Ollama sync check + Celery inspect queue depths/workers |

**`auth`** (`app/routes/auth.py`, prefix `/api/v1`):

| Method | Endpoint | Auth | Body / notes |
|---|---|---|---|
| POST | `/register` | none | `{email, password[, name, remember]}` → 201 `{user, access, refresh}` + cookies; 400/409 |
| POST | `/login` | none | `{email, password[, remember]}` → stamps `last_login_at/login_count`, tokens + cookies |
| POST | `/refresh` | none (body token) | `{refresh_token}` → rotated pair or 400/401 |
| GET | `/me` | token | current user incl. `can_create_ideas` |
| PATCH | `/me/settings` | token | `{can_create_ideas: bool}` |
| POST | `/logout` | token | clears JWT cookies |

Cookies: `access_token` (max-age from `JWT_ACCESS_TOKEN_EXPIRES`), `refresh_token` (7 d, 30 d if remember), HttpOnly, Secure/SameSite per config.

**`ollama`** (`app/routes/ollama.py`, prefix `/api/v1`):

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| GET | `/ollama/models` | `token_required` (deliberately NOT admin-only) | 15 s timeout client, proxies Ollama `/api/tags` |

**`prompts`** (`app/routes/prompts.py`, prefix `/api/v1`):

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| POST | `/prompts/test` | admin | `{prompt_body, model_name[, temperature]}` one-shot non-streaming (num_predict 500), `{{topic}}` → sample; 504 on timeout |
| POST | `/prompts/test-stream` | admin | SSE (`data: {token}` / `[DONE]` / `{error}`), num_predict 250 |
| GET | `/prompts` | token | `?page, limit, is_active`; includes prompt body + stats |
| POST | `/prompts` | admin | title/prompt_body/interval_minutes/model_name required; validates temp 0–2, top_p 0–1, repeat 0–2, num_predict 1–4096, seed ≥ 0, keep_alive ≤ 20, slack `#name`/CID; max 10 active (409); `"custom"` interval → 1440 + cron |
| GET | `/prompts/<uuid>` | token | admin full + stats; non-admin only `{id, title, prompt_body}` |
| PATCH | `/prompts/<uuid>` | admin | same validators; recalc `next_run_at` on interval change; active-limit check |
| POST | `/prompts/<uuid>/run-now` | admin | `{count: 1–5}` → N `PromptRun(manual)` + `generate_idea.delay`; 202 `{job_id, run, runs}` |
| DELETE | `/prompts/<uuid>` | admin | cascades runs |

**`ideas`** (`app/routes/ideas.py`, prefix `/api/v1`, ~758 lines):

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| GET | `/ideas` | token | `?page, limit, status (…\|ACTIVE_ONLY\|ALL), sort_by (votes/-votes/-created_at/created_at), search, prompt_config_id, model`; per-row `user_vote` |
| POST | `/ideas` | token + `can_create_ideas` | manual idea; title ≤ 200; random `IDEA-XXXX`; no embedding/dedup |
| GET | `/ideas/<id>/similar` | token | `?threshold=.85, limit=10`; 404 if no embedding |
| GET | `/ideas/<id>` | token | `{idea(include_content), actions, edit_history}` + admin-only `generation_seconds` |
| PATCH | `/ideas/<id>/status` | admin | `{status}` + `IdeaStatusHistory` row |
| PATCH | `/ideas/bulk-status` | admin | `{idea_ids[], status}` → `{updated_count, total_selected}` |
| POST | `/ideas/<id>/vote` | token | `{direction: 1\|-1}` toggle/flip; returns counts |
| GET | `/actions` | token | registry list |
| GET | `/discovery` | admin | `{skills, guidelines}` live lists |
| POST | `/ideas/<id>/actions` | admin | `{action_type[, model_override, confirm, skills[], guidelines[], answers[]]}`; DESIGN + PRD gates + 409 CONFIRMATION_REQUIRED; enqueues `run_secondary_action`, 202 |
| GET | `/ideas/<id>/actions` | token | versioned results |
| GET/POST | `/actions/<result_id>/comments` | token | per-document thread (scope=doc) |
| PATCH | `/actions/<result_id>` | admin | PRD/DESIGN_DOC only; Pydantic re-validate → new version |
| GET/POST | `/ideas/<id>/comments` | token | idea-scope tree; POST validates ≤ 2000, parent same idea |
| PATCH/DELETE | `/comments/<id>` | token (author\|admin) | edit (not if deleted); delete = soft-delete + reparent children |
| PATCH | `/ideas/<id>` | admin | `{prompt_title, raw_content, structured_content}`; per-field `IdeaEdit` audit; `raw_content = json(structured)` |

**`admin`** (`app/routes/admin.py`, ~550 lines; `admin_pages_bp` no prefix + `admin_api_bp` `/api/v1`):

- Pages (all `admin_required` Jinja): `GET /admin` (dashboard), `GET /admin/users` (search/page/limit), `PATCH/DELETE /admin/users/<uuid>`, `POST /admin/users/create`, `GET /admin/prompts` (reuses prompts list), `GET /admin/activity`, `GET /admin/settings` (renders `SETTINGS_TEMPLATE` via `render_template_string`).
- API (all `admin_required`): `GET /admin/prompts/health` (7-day runs/ideas/discard/avg + flags HIGH_DISCARD > 70 % / STARVED / LOW_FEAS < 5); `GET /admin/activity/stats` (`?run_status, model, page, limit` → recent/pending runs, queues, workers_alive, performance, popularity, ideas_by_model/prompt/status, model_timings, prompt_health); `GET /admin/stats` (totals); `GET /admin/settings`, `PATCH /admin/settings/platform|location|ai_connections`.

### 4.2 Services (`app/services/`)

| File | Purpose / key functions |
|---|---|
| `ollama_client.py` | `OllamaClient(base_url, timeout=120)`: `list_models()/list_models_sync()`, `is_model_available()`, `_build_payload(...)`, `embeddings(model, prompt)` → `/api/embeddings` (must use for embed models), `generate()/generate_sync()` → `/api/generate` (fresh sync client per call), `close()`; `OllamaError(msg, status, body)` |
| `prompt_templates.py` | `PromptTemplate(name)` loads `PROMPT_TEMPLATES_DIR/<name>.txt` via `string.Template.safe_substitute`; `get_base_prompt()`, `get_refine/competitors/feasibility_prompt()`, `get_prompt_template(action_type)` (13 keys → files) |
| `secondary_actions.py` | `ACTION_REGISTRY` — 13 entries `{key, label, description, template, done_label}`; `list_actions()`, `get_action(key)` case-insensitive, `is_known_action()` |
| `action_context.py` | `build_idea_context(idea, max_chars=8000)`: structured fields + newest comments (500 ch) + doc discussions + prior analyses + votes; truncates with marker |
| `embedding_service.py` | `embedding_text(idea)` = title + excerpt(500); `EmbeddingService` (model `nomic-embed-text`, dim 768, threshold .85): `generate_embedding[_sync]`, `store_embedding`, `cosine_similarity`, `find_similar_to_embedding`, `find_similar_ideas`, `find_near_duplicates(.95)`, `backfill_embeddings(batch)`; `get_embedding_service()` |
| `discovery.py` | `_repo_root/skill_dirs/guidelines_dir`, `_parse_frontmatter`, `list_skills()`, `list_guidelines()`, `read_skill_body(name)`, `read_guideline(name)` |
| `slack_service.py` | `get_client(token)`, `idea_blocks(idea, base_url)`, `post_idea(...)`, `get_or_provision_user` (email match → USER + slack_user_id), `apply_slack_vote`, `mark_event_seen`, `handle_reaction_event`, `mirror_comment_to_thread`, `handle_thread_reply`, `is_own_message`, `process_slack_event` — all best-effort, never block generation |
| `opencode_backend.py` | `opencode_generate(model, prompt, system, options, timeout, json_mode, workspace, endpoint)`: runs `opencode run --format json` as an argv-only subprocess in a throwaway sandbox (or `OPENCODE_WORKSPACE_DIR` for Site-Admin `repo` mode), parses the NDJSON event stream (`_parse_events`) for text + tokens + cost, maps `error` events to `ProviderError` (retryable by `isRetryable`/5xx), kills the process group on timeout; curated env, read-only agent, shared server identity. Attach mode (`endpoint` or `OPENCODE_SERVER_URL`): `--attach <url> --dir <server-dir>`; `--agent` never sent (servers reject project-local agents); sandbox `--dir` = `<OPENCODE_SERVER_SANDBOX_ROOT>/<uuid>`, created via the shared `<OPENCODE_SANDBOX_ROOT>` (fail loud if unset) |

### 4.3 Schemas (`app/schemas/ollama_schemas.py`)

13 Pydantic output models (Refine, Competitors, Feasibility, FiveForces, Pestel, PRD, DesignDoc, VRIO, ThreeCs, MarketSizing, BusinessModelCanvas, HypothesisTest, GTMStrategy) + `Verdict` enum. `_ACTION_SCHEMAS` map; `_coerce_scalar_lists` (list/dict → string join for small-model slop); `get_action_schema()`, `validate_ollama_output(action, raw_json)` (validate → coerce-retry → raise first ValidationError; JSON errors preserved for Celery retry).

### 4.4 Prompt templates (`app/prompt_templates/`, 15 files)

Loader: `string.Template`, `${PLACEHOLDER}` + `safe_substitute`. Action templates use `${ORIGINAL_IDEA_CONTENT}` (+ `${SUPPORTING_MATERIAL}` injected by task); `initial.txt` uses `${PROMPT_CONTEXT}/${MEMORY_AVOID}/${MEMORY_EXPLORE}`.

| File | Lines | Output |
|---|---|---|
| `base.txt` | 2 | system prompt: expert advisor, JSON-only, no prose |
| `initial.txt` | 23 | ONE unique idea as REFINE JSON (theme + avoid/explore memory) |
| `refine.txt` | 19 | elevator_pitch / target_audience / core_value / monetisation |
| `competitors.txt` | 21 | direct[] / indirect[] / differentiator / barriers[] |
| `feasibility.txt` | 24 | overall float + 3×{score, reasoning} + verdict enum |
| `forces.txt` | 31 | Porter's 5 + attractiveness + risks[] / recs[] |
| `pestel.txt` | 33 | 6 macro + opportunities / threats / recs[] |
| `prd_doc.txt` | 33 | 7 sections + open_questions[≤ 5]; answers-aware |
| `design_doc.txt` | 25 | architecture / screens / data_model / api_contracts / build_notes + questions; needs PRD |
| `vrio.txt` | 21 | value / rarity / imitability / organisation + implication + recs[] |
| `three_cs.txt` | 20 | customer / competitor / company + alignment + recs[] |
| `market_sizing.txt` | 21 | tam / sam / som + summary_table + assumptions[] |
| `business_model_canvas.txt` | 27 | 9 blocks + vulnerabilities[] + experiments[] |
| `hypothesis_test.txt` | 20 | assumptions_matrix + hypotheses[] / experiments[] / roadmap[] |
| `gtm_strategy.txt` | 22 | 6 pillars + launch_roadmap[] |

### 4.5 Background tasks (`app/tasks/`)

`__init__.py`: `celery = Celery("brainstormer")`; `BaseTask` pushes Flask app context, logs `task_failed/task_retry`; `init_celery(app)` (broker/backend redis /0//1, JSON, UTC, acks_late, prefetch 1, soft 600 s / hard 660 s, routes `ollama_tasks.* → ollama` else `default`, beat `check-due-prompts` + `beat-heartbeat` every 60 s).

`ollama_tasks.py` (~640 lines): helpers `_generate_reference_code()` (sequential max+1), `_generation_options(cfg)`, `_idea_pitch/_prompt_memory(10/3)`, `_record_failure(run_id, exc)`; `generate_idea(prompt_id, run_id)` (max 3 retries); `run_secondary_action(idea_id, action, model_override, run_id, extra_context)` (max 2); `check_due_prompts()`; `backfill_embeddings(batch=10)`.

`maintenance_tasks.py`: `cleanup_old_discarded(days=90)` (stub, `not_implemented`); `recalculate_vote_counts()`; `update_next_run_times()`; `beat_heartbeat` + `write/check_beat_heartbeat` (Redis `brainstormer:beat_heartbeat`, 180 s grace).

Queues: `ollama` (concurrency 1) vs `default` (concurrency 4). Dev: `celery -A app.tasks worker -Q ollama -c 1`, `-Q default -c 4`, `beat`. Prod: `celery_worker.py` / `celery_beat.py`. `enqueue_generation(task, args, kwargs, provider)` keeps Ollama on the legacy `.delay()` path and sends OpenCode runs to a dedicated serial `opencode` queue (concurrency 1) with longer soft/hard limits.

### 4.6 Utilities and CLI

- `utils/auth.py`: `create_tokens(user_id, role, email, remember)` (PyJWT HS256 access + DB refresh 30/7 d), `decode_token×2`, `rotate/refresh_access_token`.
- `utils/crypto.py`: `get_fernet/encrypt/decrypt` (Fernet, 32 B handling) — prompt bodies encrypted when `ENCRYPT_PROMPTS=True`.
- `utils/markdown.py`: `render_markdown_safe()` (bleach allowlist), `render_markdown_to_text()`.
- `utils/responses.py`: response envelope helpers.
- `cli.py`: `create-admin / create-user / list-users / promote-user` via `register_cli(app)`.
- `slack_listener.py`: Socket-Mode listener (separate process) → `process_slack_event`.

---

## 5. Screens — Frontend

**Stack:** server-rendered Jinja2 + TailwindCSS (CDN) + Alpine.js (vendored `app/static/js/alpine.min.js`, `defer`) + vanilla `fetch`. Dark-mode `dark:` classes present. No build step, no SPA router. Dynamic data via `/api/v1/...` JSON with JWT from `localStorage`. `app/static/css/` is empty; styling is Tailwind CDN + inline `tailwind.config` (Inter font + primary blue) + Google Fonts + Chart.js CDN (loaded, barely used).

**Routes → templates:**

```
/ → 302 → /login
/dashboard → 302 → /ideas
/ideas → ideas/dashboard.html (main app)
/prompts → prompts/list.html
/prompts/create → prompts/create.html (admin-gated in JS)
/login → auth/login.html
/register → auth/register.html
/admin → admin/dashboard.html (ADMIN)
/admin/users → admin/users.html (ADMIN, server-paginated)
/admin/prompts → prompts/list.html (ADMIN view)
/admin/activity → admin/activity.html (ADMIN)
/admin/settings → render_template_string(SETTINGS_TEMPLATE) (ADMIN)
index.html is ORPHANED (demo hitting legacy /api/auth/*) — no route renders it.
```

Nav source: `_nav_links()` context processor (`Ideas`, `Prompts`); sidebar/navbar/dropdown all loop over it.

### 5.1 Shell templates

**`base.html`** (app shell, blocks `title/head/content/scripts`): `partials/_navbar.html` (sticky) + flex [`_sidebar.html` (desktop `lg:block w-64`) + `<main>` + flashes] + `partials/_footer.html`. Global JS: `getToken()` (`localStorage.access_token`); `authFetch()` (injects `Bearer` + JSON, on 401 wipes tokens → `/login`); `streamPromptTest()` (SSE `POST /api/v1/prompts/test-stream`); footer script `updateNavbarFromToken()` (`#guest-area` vs `#user-area`, `#nav-username`, `#nav-admin-link` for ADMIN) + `wireLogoutButton()` (`POST /api/v1/logout` best-effort → clear → `/login`) + `storage` listener for multi-tab sync. No-cache meta + HTTP header on all HTML.

**`base_auth.html`**: minimal shell for login/register (no nav/sidebar/Alpine); centred card styles.

**`partials/_navbar.html`**: logo + `Brainstormer` → `/`; centre `nav_links` loop with `aria-current`; right: server-authenticated Alpine dropdown, else `#guest-area` (Sign in/up) + hidden `#user-area` toggled by JS (the common JWT case).

**`partials/_sidebar.html`**: desktop-only sticky nav + `Brainstormer v{{ config.VERSION }}` footer.

**`partials/_flashes.html`**: Alpine toast stack, auto-dismiss 5 s, colour by category.

**`partials/_footer.html`**: `© 2026 Brainstormer` + build stamp; dead `#` Privacy/Terms/Contact links.

### 5.2 Auth screens

**`auth/login.html`** (`POST /api/v1/login`): centred card, `#error-box`/`#success-box`, `#login-form` (email prefilled `admin@example.com`, password `admin123`, `remember_me`, spinner submit). JS: disable → `fetch` → store `access_token/refresh_token/user` → success → `/ideas` (600 ms); fail → error box + re-enable. Demo hint in footer.

**`auth/register.html`** (`POST /api/v1/register`): same pattern; fields name (optional), email, password (min 8); stores same three keys → `/ideas`.

### 5.3 Ideas dashboard (`ideas/dashboard.html`, ~1300 lines, `/ideas`, `x-data="ideasApp()"`)

The main screen. Desktop table + mobile cards + detail modal + 4 auxiliary modals.

- **Header:** `Ideas Dashboard`, `<total> matching / <totalIdeas> total` (grand total via `limit=1`), `Updated <lastUpdated> · auto-refreshes`, `Create Idea` (if `canCreateIdeas` from `/me`), `Refresh` (spins while loading).
- **Filters (server-side):** status (`ACTIVE_ONLY` default = excludes DISCARDED, `""` = All, NEW/DISCARDED/CONSIDERATION/DESIGN/BUILD/COMPLETE/HOLD), sort (newest/oldest/votes), search text, prompt dropdown, model dropdown (derived from prompts). `$watch` → page 1 + reload. Deep links: `?status&prompt=<id|title>&model&idea=<id>` (from admin links).
- **Table (desktop):** Ref (mono `reference_code`) / Timestamp (`timeAgo` + full on hover) / Prompt pill / Summary (`line-clamp-2` fade, `Read full idea →`, emerald `✓ Label` chips for completed actions) / Status pill / Comments / Votes (▲/net/▼, 44 px buttons, `voteLoading` disables) / kebab (`View Details`; admin: `Change Status` select, `Discard`, per-action `runAction` with `(done_label)` if done). Empty state + loading row.
- **Mobile cards:** full summary, ref + status + 💬, prompt pill + time, vote row + `Details`.
- **Pagination:** `Showing X to Y of Z`, Prev/Next → `GET /ideas?page&limit&sort_by&status&search&prompt_config_id&model`. Auto-refresh 30 s + `visibilitychange` when no modal open.
- **Admin bulk bar:** fixed amber bar when rows selected → `bulkStatus` + Apply/Clear → confirm → `PATCH /ideas/bulk-status`.
- **Detail modal:** ref + status + close; meta (prompt link, generated date + admin `generation_seconds`, votes · comments); tabs (`Idea` + pinned `Refine Idea` + one `Analysis` tab + lifecycle tabs `Brief` → `Design` → `Build` → `Tests`, per-tab spinner, admin `+ New`). Every other action from `/actions` (registry `category: analysis`) shares the single `Analysis` tab: a chip row lists stored analyses newest first and the panel shows the selected document (date, Copy MD, .md). New actions group themselves from the registry. The old `Prompt` tab is gone from the strip — the prompt link lives in the modal meta row. Overview tab (rendered HTML, voting, admin status select + `Edit content` incl. structured fields + edit history, threaded comments with Reply/Edit/Delete); action tabs (rendered output + PRD/DESIGN extras: version label, Recreate/Edit, doc threads, PRD Q&A `Answer & regenerate`); doc editor (`Save as new version`).
- **Run Action dialog:** model select (idea default + Ollama models), skills checkboxes (DESIGN status only, from discovery), guidelines → `POST /ideas/<id>/actions`.
- **Create Idea modal:** title (200 ch) + content + optional structured fields → `POST /ideas` → opens new idea.
- **Confirm modal:** reusable Refine/PRD confirm.

JS helpers: `prettySummary/prettyContent/prettyActionOutput`, `timeAgo/formatDate/formatDuration`, `getStatusClass/getVoteClass`, `vote/changeStatus/confirmDiscard/runAction`, `actionChips/lifecycleTabs/analysisTabs/ensureAnalysisSelection/selectAnalysisTab/selectTab`, `docVersionLabel/startDocEdit/saveDocEdit`, `loadActions/loadUserSettings/checkAdmin` (`/admin/stats` → isAdmin, `/me` → user/canCreateIdeas).

### 5.4 Prompt screens

**`prompts/list.html`** (`/prompts`, `initPromptsPage()`): header + admin `Create Prompt`; status filter (All/Active/Paused) + title/body search (client-side); table Title+snippet / Interval (`360→6h`, `1440→Daily`, `10080→Weekly`) + cron / Model pill / Active toggle (PATCH) / Last/Next Run / Runs (`run_count` + `Run pending…` + `N failed`) / kebab (admin: Edit, Run Now, Run 5x Burst + confirm → Activity page, Delete; non-admin: View). Client pagination (10/page). Create/Edit modal: Title*, body* (mono, JSON note), interval select (6 h/12 h/Daily/Weekly/custom→cron), model select (from `/ollama/models`, badges 🚀<3 GB 🐇3–7 GB 🐢>7 GB, default `gemma3:latest` else smallest), temperature + generation grid (Top P, Repeat Penalty, Max Tokens, Seed, Keep Alive, Slack channel) with `?` tooltips, Active checkbox, Test output/error, Cancel / `Test Prompt` (SSE, 5-min abort) / Save (`POST`/`PATCH`). Guards: no token → `/login`; non-admin hides create; deep-link `?edit=<id>`; 30 s poll.

**`prompts/create.html`** (`/prompts/create`, `createPromptForm()`): standalone page version of the same form (Basic / Schedule & Model / Slack / Generation / Try it out); same model logic/badges/defaults/SSE/payload; requires admin (`/admin/stats` else → `/ideas`); success → `/ideas`. (Note: back-link points at `/ideas`, likely bug.)

### 5.5 Admin screens (all ADMIN; 403 → `/ideas`)

**`admin/dashboard.html`** (`/admin`, vanilla JS): 4 stat cards (`/admin/stats`); Quick Actions → users/prompts/activity/settings; System Health rows (Ollama/DB/Redis ← `/api/ready`, Workers ← counts); breakdown bar rows (`ideas.by_status/model/prompt`, clickable → `/ideas?status|model|prompt=`).

**`admin/users.html`** (`/admin/users`, server-rendered + vanilla JS): Jinja `pagination.items` (email/name, role select, active toggle, `last_login_at`, `login_count`, `created_at`, Deactivate; self-row disabled); server pagination (`?page&search`); debounced search; `PATCH /admin/users/<id> {role|is_active}`, `DELETE`, `POST /admin/users/create` (modal via `innerHTML`).

**`admin/activity.html`** (`/admin/activity`, `activityApp()`): live ops view. Header `Live · auto-refreshes` + error banner + Retry. 5 tiles (Total runs, Success rate, Avg generation, Pending amber, Failed red + `Last:` error; tiles link `?run_status=`). Active filter pill + Clear. Workers/queues strip. Panels (bars clickable): Ideas by Prompt (ideas+votes + ✓/✗ split), by Model, by Status, Runs by Status, Speed by model, Model drill-down (`?model=`), Prompt health (7 d runs/ideas + amber FLAGS with `Edit prompt` → `/prompts?edit=` + `View ideas`, else Healthy), Recent runs timeline (→ `/ideas?idea=` or `?prompt=`, 20/page), Live now (Queued…/Running… cards). 30 s poll.

**Admin settings** (`admin_settings_template.py:SETTINGS_TEMPLATE` via `render_template_string` at `/admin/settings`): 3 Alpine `settingsForm(section)` cards — Platform (Title* 250 ch, Description 1000 ch, type checkboxes), Location (Country list), AI Connections (placeholder). `GET /admin/settings` → `PATCH …/platform|location|ai_connections` + toast.

### 5.6 Navigation, guards, API patterns

- **Unauthenticated:** `/` → `/login` → (`/register`) → tokens in `localStorage` → `/ideas`.
- **Authenticated:** navbar (Ideas, Prompts; user menu) + sidebar + version footer. `Admin Panel` only for ADMIN. Admin also gets `/admin*`.
- **Cross-links:** prompt pill → `?prompt=`; activity tiles/bars → self `?run_status|model=` or `/ideas?prompt|model|status|idea=`; run rows → idea modal or prompt ideas; health flags → `/prompts?edit=` + `/ideas?prompt=`.
- **Guards:** every Alpine page checks `localStorage.access_token` → `/login`; `authFetch` 401 → wipe + `/login`; admin pages probe `/admin/stats` → `/ideas`; no auto-refresh interceptor (expiry → login).
- **`fetch` conventions:** `authFetch` everywhere except login/register (plain `fetch`) and settings (raw `fetch` + manual `Bearer`). Always `Authorization: Bearer`, JSON bodies. Envelope `{success, data}` unwrapped as `data.data || data`. `alert()` for prompt/user failures, inline boxes for auth/test-run, toasts in settings; `confirm()` for delete/burst/deactivate; `AbortController` 5-min test-stream timeout; 30 s polling + `visibilitychange`.

---

## 6. Design Decisions

### 6.1 Database

`DATABASE_URL` (required env). `pool_pre_ping`, `pool_size 5`, `max_overflow 10`, `pool_recycle 300`. Testing overrides to `sqlite:///:memory:` with empty engine options. Prod compose: `postgres:16-alpine` + `postgres_data`. Migrations via Alembic/Flask-Migrate only — never `db.create_all()` in production (Guardrail §9).

### 6.2 GUIDs

`app/models/types.py:GUID` — `TypeDecorator impl=CHAR(36) cache_ok=True`; Postgres → `UUID(as_uuid=True)`, else `CHAR(36)`; converts `uuid.UUID ↔ str` on SQLite. Replatform: use native UUID (Postgres) / TEXT/CHAR(36) (SQLite) with string serialisation at the boundary.

### 6.3 Datetimes

SQLite ignores `DateTime(timezone=True)` and returns naive. `ensure_aware(dt)` treats naive as UTC. Every expiry/duration comparison must go through it (`RefreshToken.is_valid`, run durations, heartbeat grace). Replatform: store UTC ISO-8601 / timestamptz; parse as aware.

### 6.4 JSON columns

Plain `db.JSON`, never mutated in place — build a fresh dict and assign. Affects `structured_content`, `embedding`, `result_data`, `answers`, settings blobs. Replatform: JSONB (Postgres) / JSON TEXT (SQLite) with whole-document writes.

### 6.5 Authentication

`app/utils/auth.py` over `flask-appkit` + PyJWT HS256: `create_tokens(user_id, role, email, remember)` — access claims `sub/role/email/exp/iat` (default 900 s; compose sets 86400), refresh `secrets.token_urlsafe(32)` stored as SHA-256, 30/7 d. `rotate_refresh_token` revokes old and links `replaced_by`. `token_required` / `admin_required` verify JWT, reject inactive (401) / non-admin (403). JWT location headers+cookies (testing headers-only), Secure/SameSite=Strict/CSRF cookies. Passwords bcrypt; login stamps `login_count/last_login_at`. Note: `RefreshToken.create_token` currently hardcodes 7 d internally (remember handled in `auth.py`).

### 6.6 Background jobs

Celery + Redis (§4.5). `BaseTask` app context; structured `on_failure/on_retry` logs. Timeouts 600/660 s (CPU Ollama); the `opencode` queue uses longer soft/hard limits (1560/1620 s). `acks_late`, `reject_on_worker_lost`, prefetch 1. Beat: `check-due-prompts` + `beat-heartbeat` every 60 s; health checks beat via Redis key with 180 s grace (missing = healthy fresh boot). Replatform: any queue with delayed/periodic support (Sidekiq, Hangfire, BullMQ, Cloud Tasks + Scheduler) preserving the `ollama`-serial / `opencode`-serial vs `default`-parallel split.

### 6.7 LLM integration

`OllamaClient` (httpx): `list_models` (`/api/tags`), `generate` (`/api/generate`, always `format: json`), `embeddings` (`/api/embeddings` — must use for embed models). File-based prompts (`*.txt`, `{{PLACEHOLDER}}` only, never raw user strings in system prompt). Pydantic validation per action with lenient coerce-retry; JSON errors re-raised for Celery retry; single strict retry on ValidationError; dead-letter on exhaustion; `latency_ms` logging; prompt bodies Fernet-encrypted at rest; log hash only. Model allowlist from `/ollama/models`. Adding an action = template + schema + registry entry. Replatform: swap `OllamaClient` for any OpenAI-compatible `/chat/completions` (response_format json_object) or hosted LLM; keep template + schema + validator triple.

### 6.8 Observability

`structlog` in slack/embedding/tasks (`get_logger()`), JSON in prod; never bodies/content. Events: auth, prompt CRUD, idea generated (`idea_id/prompt_id/model/latency_ms`), vote, action queued/completed (`job_id/status`), Ollama errors (`model/error_type/retry`). Prometheus: `prometheus-client` dependency present; LLM-latency/queue-depth counters are a stated requirement but no direct `Counter/Histogram` usage was found — health endpoints expose queue depths via Celery inspect. Treat metrics as partially implemented.

### 6.9 Security (Guardrail.md, 14 sections)

JWT on all API except health + `/api/v1/auth/*`-equivalent; role checks; generic login errors + 5/min/IP; bcrypt 12; Pydantic per endpoint (400); ORM only (no raw SQL, `B608`); prompt bodies sanitised (strip control, 10 k max); placeholders-only LLM; 30/120 s timeouts; one retry + DLQ; local-only Ollama (egress blocked), no analytics; Fernet prompts; HttpOnly/Secure/Strict cookies; Redis Flask-Limiter (login 5/min/IP, run-now 1/5 min/user, actions 3/min/user, vote 30/min/user, default 100/min/IP); secrets from `.env` (gitignored, 32+ chars, rotated 90/180 d); pinned deps, `safety` + `bandit -r app/` in CI; Alembic-only indexed FKs; CSRF token, no inline `<script>` (Talisman; note `unsafe-eval` required for Alpine), Jinja autoescape, `bleach.clean` markdown; non-root read-only rootfs, `/health` checks, TLS at proxy, daily dumps + quarterly restore test. PR checklist + `guardrails.yml` CI (`bandit`, `safety`, `pytest --cov-fail-under=80`, no-external-calls / no-secrets checks).

---

## 7. Tests

### 7.1 Suite (7 files + `conftest.py`, 207 tests)

| File | Count | Type | Covers |
|---|---|---|---|
| `tests/test_auth.py` | 8 | smoke/auth | register success/duplicate/short-password, login success/wrong-pass, `/me` 401/with-token, `login_count` + `last_login_at` |
| `tests/test_health.py` | 4 | smoke/health | `/api/health` healthy (mocked redis+scheduler), degraded 503, 404 route, `/ideas` HTML `Cache-Control: no-cache` |
| `tests/integration/test_api_endpoints.py` | 82 | integration | auth incl. refresh/logout; prompts incl. slack-channel, temp range, max-active, run-now, burst, delete; `/ollama/models`; ideas list/filter/search/sort/pagination/counts/actions-run; comments thread/validation/edit/delete-reparent; idea-edits audit; votes; secondary actions incl. forces/PESTEL/PRD-with-answers/rerun/gating; stats/health/activity; doc threads |
| `tests/unit/test_models.py` | 12 | unit | User/PromptConfig/Idea/Vote/SecondaryActionResult/ActionType/StatusHistory defaults, constraints, serialisation |
| `tests/unit/test_services.py` | 59 | unit | `OllamaClient` (list/generate/payload), prompt templates, `render_markdown_safe/to_text` (bleach allowlist), Pydantic Refine/Competitors/Feasibility + `Verdict` |
| `tests/tasks/test_ollama_tasks.py` | 30 | tasks (eager) | `_generation_options`, `_prompt_memory` (avoid/explore), reference-code increment, generation with memory, mocked Ollama JSON + retry, failure recording |
| `tests/ui/test_prompt_dropdown.py` | 12 | ui/API-backed | admin login, `GET/POST /prompts` contract for the frontend dropdown |

`pytest.ini` is empty; real config in `pyproject.toml`: `testpaths=["tests"]`, `addopts="--cov=app --cov-report=term-missing --cov-fail-under=35 -q"`, `asyncio_mode=auto`, ignore `sqlalchemy.*` DeprecationWarnings. Coverage omits factory/config/extensions/CLI/utils/models-init/routes-init/services-init/tasks-init/schemas-init; aim 80 %+ (AGENTS.md), gate 35 %.

### 7.2 Fixtures (`tests/conftest.py`)

Function-scoped `app` (`create_app("testing")`, `db.create_all()` → yield → `remove()` + `drop_all()`: fresh `:memory:` DB per test) and `celery_app` (same + eager Celery); `client` (`app.test_client()`); `session`; `user_with_token` (`test@example.com`/`password123` + `create_tokens`); `auth_headers`; `admin_user` (`admin@test.com`/ADMIN); `admin_prompt` (fixture PromptConfig owned by admin); `auth_user` (via register); `admin_client` (`admin@example.com` login wrapped in `_AuthHeaderClient` which auto-injects `Authorization` on all verbs).

Testing config: `sqlite:///:memory:`, Redis DB 3, `CELERY_TASK_ALWAYS_EAGER` + `EAGER_PROPAGATES`, `RATELIMIT_ENABLED=False`, JWT headers-only, no CSRF.

### 7.3 Running

```bash
source venv/bin/activate
pytest                          # all tests
pytest tests/unit/              # unit only
pytest tests/integration/       # integration only
pytest -k "test_name"           # single test
black app tests && isort app tests && mypy app   # lint/format/typecheck
```

### 7.4 Lessons that must survive replatforming

- Fixtures must be **function-scoped** with a fresh DB per test; session scope caused order-dependent UNIQUE collisions. No hardcoded seed rows; re-query ORM objects per context (no detached instances); mocked `.delay().id` must be a string.
- `@patch` fills the first parameter after `self` — name the mock explicitly.
- Broken `fetch` handlers (missing `});`) silently reload with no feedback — check devtools Console; keep test files syntactically clean (a quote bug once masked the login bug).
- Auth templates carry no-cache meta **and** the server sends real `Cache-Control` headers on all HTML.
- Nested quotes in Jinja2 (`JSON.stringify({…})` inside `body:`) are fragile — isolate the JSON string.

---

## 8. Configuration, Deployment, Operations

### 8.1 Environment

Required: `SECRET_KEY`, `DATABASE_URL`, `JWT_SECRET_KEY`, `FERNET_KEY`. Defaults: Redis `redis://localhost:6379`, Ollama `http://localhost:11434` timeout 120, `APP_BASE_URL :8000`, JWT access 900 s / refresh 7 d, `JWT_TOKEN_LOCATION=[headers,cookies]`, Strict cookies + CSRF, `ENCRYPT_PROMPTS=True`, `PROMPT_TEMPLATES_DIR=app/prompt_templates`. Dev: debug, non-secure cookies. Prod: secure cookies. See `.env.example`, `docs/install-config.md`.

### 8.2 Commands (see AGENTS.md)

```bash
source venv/bin/activate
python run.py
celery -A app.tasks worker -Q ollama -c 1 --loglevel=info
celery -A app.tasks worker -Q default -c 4 --loglevel=info
celery -A app.tasks beat --loglevel=info
flask db migrate -m "message" && flask db upgrade
flask create-admin / create-user / list-users / promote-user
```

### 8.3 Containers

`Dockerfile` (multi-stage, `python:3.12-slim`, non-root `appuser`): dev target `hypercorn --reload asgi:app`; prod `gunicorn -w 2 wsgi:app`, port 8000. Prod compose: postgres/redis/ollama health-gated, web waits on all three (`curl /api/health`), workers wait on redis+ollama. Secrets via `${DB_PASSWORD/JWT_SECRET_KEY/FERNET_KEY/SECRET_KEY}` — never committed.

### 8.4 Operations

Health: `/api/health` (DB+Redis+beat) and `/api/ready` (+Ollama + Celery inspect). Admin dashboards: `/admin` (stats/health/breakdowns), `/admin/activity` (runs, queues, workers, prompt health), `/admin/prompts/health` (JSON flags). Maintenance tasks: vote recompute, next-run repair, discard cleanup (stub), beat heartbeat. Backups: daily dumps + quarterly restore test (Guardrail §11).

---

## 9. Replatforming Guide

### 9.1 Functional scope to port (minimum viable parity)

1. Auth: register/login/refresh(rotation chain)/logout/me + `can_create_ideas`; role gate; remember-me 30 d.
2. Prompts: CRUD + validators + 10-active cap + test (SSE stream) + run-now (1–5) + due scheduler (60 s) + orphan reconciler.
3. Ideas: list (status/sort/search/prompt/model/pagination + `user_vote`) + manual create + detail (+ `generation_seconds` for admin) + status/bulk-status (+ history) + content edit (+ per-field audit).
4. Votes: toggle/flip, one per user/idea, live counters.
5. Comments: threaded, ≤ 2000 chars, soft-delete with reparenting, idea- vs doc-scope.
6. Actions: 13-item registry; run with DESIGN/PRD gates + confirmation flow; versioned results; PRD/DESIGN edit (re-validate); feasibility → idea score; answers-aware PRD/DESIGN with fuzzy question-drop; skills/guidelines injection.
7. Discovery: live skills/guidelines lists for the run dialog.
8. Embeddings: generate on create, cosine similarity search (threshold .85, default limit 10), near-dup .95 lookup, backfill job, auto-discard at .97.
9. Slack: post new ideas (Block Kit), map msg → idea, reaction votes, thread replies ↔ comments, idempotent events, provision-by-email.
10. Admin: stats, activity/stats, prompt health flags, users CRUD, settings singleton (platform/location/ai_connections).
11. Health: liveness + readiness with DB/Redis/scheduler/Ollama/worker checks.

### 9.2 Suggested service mapping

| Current | Replatform equivalent |
|---|---|
| Flask blueprints | Controllers/routers per domain (auth, prompts, ideas, actions, admin, health, pages) |
| SQLAlchemy + Alembic | Any ORM + migrations (EF Core, Prisma, Drizzle, Django ORM); keep GUID PKs, indexed FKs, JSONB |
| Celery + Redis + Beat | BullMQ / Hangfire / Sidekiq / Cloud Tasks + Scheduler; keep `ollama`-serial vs `default`-parallel queues |
| OllamaClient | Adapter over OpenAI-compatible `chat/completions` (JSON mode) + embeddings endpoint |
| `*.txt` templates + Pydantic | Versioned prompt files + schema validation (Zod/Pydantic-equivalent/JSON Schema) |
| Jinja + Alpine | Any SSR (Razor, Thymeleaf, Next.js) + fetch; or SPA — preserve deep links (`?status&prompt&model&idea`, `?run_status`, `?edit=`) |
| structlog + health | Structured JSON logs + `/health` + `/ready` |
| Fernet prompt bodies | AES-GCM / KMS envelope encryption |
| Flask-Limiter + Talisman | Rate-limit middleware + CSP headers |

### 9.3 Pitfalls (from AGENTS.md lessons)

- UUID handling differs per DB — normalise at the boundary.
- Naive vs aware datetimes — store/parse UTC-aware everywhere.
- JSON columns need whole-document writes + change tracking.
- Test isolation: fresh DB per test, no shared seeds, no cross-context entities.
- Frontend/API contract is envelope-based (`{success, data}`); guards are token-presence + 401-redirect + admin probe — preserve or document deviations.
- `unsafe-eval` CSP is currently required by Alpine — revisit if changing frontend.
- `index.html` is dead code; do not port it. `cleanup_old_discarded` is a stub; decide retention policy explicitly.

### 9.4 Migration checklist

- [ ] Schema + 23-migration equivalent applied; GUID/JSON/timezone behaviour verified.
- [ ] Auth flows + rotation + remember-me + guards covered by ported `test_auth` + integration tests.
- [ ] Prompt validators + active cap + SSE test + run-now + scheduler + orphan handling covered.
- [ ] Ideas/votes/comments/actions semantics (gates, versions, threads, audits) covered by ported integration tests.
- [ ] Embeddings + thresholds (.85/.95/.97) + backfill verified.
- [ ] Slack idempotency + vote/thread mapping verified (or explicitly descoped).
- [ ] Admin dashboards + health flags + settings verified.
- [ ] Rate limits, CSP/CSRF, encryption, no-external-calls, PII-free logs re-applied per Guardrail checklist.
- [ ] Coverage gate + `bandit`/`safety` (or equivalent SAST/SCA) in CI.
- [ ] Docs updated (`README`, `docs/*`, CHANGELOG, version bump per AGENTS.md build requirements).

---

## 10. Appendices

### A. Full API quick reference

```
POST /api/v1/register  POST /api/v1/login  POST /api/v1/refresh
GET  /api/v1/me  PATCH /api/v1/me/settings  POST /api/v1/logout
GET  /api/v1/ollama/models
POST /api/v1/prompts/test  POST /api/v1/prompts/test-stream
GET  /api/v1/prompts  POST /api/v1/prompts
GET|PATCH|DELETE /api/v1/prompts/<uuid>  POST /api/v1/prompts/<uuid>/run-now
GET  /api/v1/ideas?status&sort_by&search&prompt_config_id&model&page&limit
POST /api/v1/ideas  GET /api/v1/ideas/<id>  PATCH /api/v1/ideas/<id>
GET  /api/v1/ideas/<id>/similar?threshold&limit
PATCH /api/v1/ideas/<id>/status  PATCH /api/v1/ideas/bulk-status
POST /api/v1/ideas/<id>/vote
GET  /api/v1/actions  GET /api/v1/discovery
POST /api/v1/ideas/<id>/actions  GET /api/v1/ideas/<id>/actions
GET|POST /api/v1/actions/<result_id>/comments  PATCH /api/v1/actions/<result_id>
GET|POST /api/v1/ideas/<id>/comments  PATCH|DELETE /api/v1/comments/<id>
GET  /api/v1/admin/stats  GET /api/v1/admin/activity/stats
GET  /api/v1/admin/prompts/health
GET|PATCH /api/v1/admin/settings  PATCH /api/v1/admin/settings/platform|location|ai_connections
PATCH|DELETE /api/v1/admin/users/<uuid>  POST /api/v1/admin/users/create
GET  /api/health  GET /api/ready
```

### B. Key files

| Purpose | File |
|---|---|
| App factory + extensions | `app/__init__.py`, `app/extensions.py` |
| Config | `app/config.py` |
| Auth decorators | `app/utils/decorators.py` |
| GUID + datetime helpers | `app/models/types.py` |
| Ollama client | `app/services/ollama_client.py` |
| Prompt loader | `app/services/prompt_templates.py` |
| Action registry | `app/services/secondary_actions.py` |
| Celery tasks | `app/tasks/ollama_tasks.py`, `app/tasks/maintenance_tasks.py` |
| Pydantic schemas | `app/schemas/ollama_schemas.py` |
| Prompt files | `app/prompt_templates/*.txt` |
| Test fixtures | `tests/conftest.py` |
| Product spec / security / standards | `PRD.md`, `Guardrail.md`, `AGENTS.md` |

### C. Glossary

- **Prompt config:** scheduled idea-generation recipe (admin-owned).
- **Prompt run:** one execution attempt (PENDING → RUNNING → SUCCESS/FAILED).
- **Idea:** generated or manual entry with `IDEA-XXXX` reference code.
- **Secondary action:** structured analysis document generated from an idea (13 types).
- **Discovery:** live Opencode skills/guidelines injected into DESIGN-stage runs.
- **Dedup:** cosine-similarity near-duplicate detection (auto-discard ≥ 0.97).
- **Beat heartbeat:** Redis key proving the scheduler is alive (180 s grace).

---

*Generated from the codebase at v0.26.9. Verify against `PRD.md`, `docs/*`, and the test suite (`pytest`) before replatforming.*
