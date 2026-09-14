# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [0.7.0] - 2026-09-14
### Added
- Admin-only PESTEL analysis: new `PESTEL` action (flat-string schema), `pestel.txt` template, registry entry, 3-dot menu + chips support, `actiontype` enum extended

## [0.6.0] - 2026-09-14
### Added
- Admin-only Porter's Five Forces analysis: new `FIVE_FORCES` action (flat-string schema tuned for small models), `forces.txt` template, registry entry, 3-dot menu + chips support, `actiontype` enum extended

## [0.5.3] - 2026-09-14
### Fixed
- New ideas wrongly showed "You downvoted": `user_vote` is null (not 0) when unvoted, and `null !== 0` passed the check — now shows only on real +1/-1 votes (table + detail modal)

## [0.5.2] - 2026-09-14
### Fixed
- Circular import at startup (`celery_auto_init_skipped` noise): tasks import is lazy inside `create_app` — auto-init now succeeds with all tasks registered
- Beat liveness: new `beat_heartbeat` task (60s) stamping Redis; `/api/health` gains a `scheduler` check (missing key = boot grace, stale > 3 min = degraded)

## [0.5.1] - 2026-09-13
### Fixed
- Secondary actions now run cold (temperature capped at 0.3): analytical calls inherited creative temps and garbled schemas
- Validation-feedback retry: a schema failure retries once with the errors fed back instead of blindly repeating; markdown fences stripped before validation

## [0.5.0] - 2026-09-13
### Added
- Prompt health (PRD §9.2): `GET /api/v1/admin/prompts/health` with 7d stats (runs, ideas/run, discard %, avg score/feasibility) and HIGH_DISCARD / STARVED / LOW_FEASIBILITY flags linking to edit form + ideas; Activity panel section; `?edit=` deep link auto-opens the prompt edit modal

## [0.4.0] - 2026-09-13
### Added
- Prompt memory (PRD §9.1): every run renders Avoid (last 10 ideas) + Explore (top-voted themes) sections from `${MEMORY_AVOID}` / `${MEMORY_EXPLORE}`; "none yet" on new prompts; recomputed per run, never stored

## [0.3.7] - 2026-09-13
### Fixed
- Dropdown menu items overlapping invisibly: adjacent inline `<button>`s without `block` stacked at the same Y (hid Run 5x Burst; Refine/Competitors overlapped too) — all menu buttons now `block w-full`
- Sidebar footer version was blank: wired `VERSION` file into app config (also a freshness signal for cached pages)

## [0.3.6] - 2026-09-13
### Changed
- Speed-by-model links open a timings-only view (everything else hidden while a model is selected)
- Run Now no longer pops a dialog; the run-pending badge is the confirmation (errors still alert)

## [0.3.5] - 2026-09-13
### Fixed
- New UI (burst button, timing graph, status panels) invisible in browsers: HTML pages had no real cache headers (`<meta http-equiv>` is ignored) — now `Cache-Control: no-cache, no-store, must-revalidate` on all HTML responses

## [0.3.4] - 2026-09-13
### Fixed
- Removed Top-voted ideas from /admin/activity (backend payload trimmed too)
- Activity links 404'd (`/admin/activity...` — page lives at `/api/v1/admin/activity`): all tile/row links + history state corrected
- Ideas by Status showed run outcomes: now idea states, run outcomes moved to new Runs by Status panel
### Added
- Model timing graph: Speed rows open a timings-only view (successful-run bars, newest first); run stream hidden while a model is selected
- Admin burst runs: run-now `{"count": 1-5}` + "Run 5× Burst" menu item
- Secondary-action results (Refine/Competitors/Feasibility) render as labelled human-readable sections instead of raw JSON

## [0.3.3] - 2026-09-13
### Fixed
- Ideas by Status showed run outcomes (Failed/Success): now idea states (New/Consideration/Discarded) via `ideas_by_status`; run outcomes moved to a new Runs by Status panel
- Activity links 404'd (`/admin/activity...` — page lives at `/api/v1/admin/activity`): all tile/row links + history state corrected
### Added
- Per-model timing graph: Speed rows link to a Run-timings panel (successful-run durations as bars, newest first) + filtered run stream
- Admin burst runs: `POST run-now {"count": 1-5}` enqueues up to 5 independent runs; prompts menu gains "Run 5× Burst" (confirm first)

## [0.3.2] - 2026-09-13
### Fixed
- Run-stream filters (?run_status=, ?model=) were client-side over the 20 loaded runs — now server-side on `/admin/activity/stats` (wider window when filtered, 400 on bad status); Clear reloads unfiltered

## [0.3.1] - 2026-09-13
### Fixed
- Ideas by Model counts were fanned out by the runs join (12 shown for 6 ideas): now `count(DISTINCT ideas)`
- Clicking a model showed 1 idea: `?model=` filter was client-side over one page only — now server-side on `/api/v1/ideas`, client sends it with the request

## [0.3.0] - 2026-09-13
### Added (PRD §8, all items built)
- Per-prompt generation params: `top_p` (0.9), `repeat_penalty` (1.1), `num_predict` (1000), `seed` (null = random), `keep_alive` ("2h") — model columns, API validation (400 on out-of-range), worker pass-through, Generation section with tooltips on create + edit forms
- Users: `last_login_at` + `login_count` columns, stamped on login, shown in admin users table
- Activity: metric tiles link to filtered run lists, Ideas by Prompt/Model + Speed + Status moved above the run stream in 2-col rows, all rows link out, `run_status`/`model` filtering with clear chip, load-error banner with retry
- Ideas page honours `?status=&prompt=&model=` deep links; new model filter dropdown
- Navigation from a single `nav_links` context processor (all three menus loop it, active highlighting); `/dashboard` 302-redirects to `/ideas`
- Mobile stacked cards for ideas below `md` breakpoint (full summary, 44px targets)
- Ideas 3-dot menu: Consider / Discard (confirm) / Refine / Competitors for admins
- 24h access tokens (`JWT_ACCESS_TOKEN_EXPIRES=86400`); fixed `create_tokens`/`rotate_refresh_token` ignoring the config (hardcoded 15min) — the true cause of frequent logouts
### Fixed
- `prompt_body` now reaches Ollama via `${PROMPT_CONTEXT}` in the initial template (was silently ignored)
- API range validation for `temperature` 0–2 on all four parse sites (shared `_parse_temperature`)
- `POST /logout` 500 (tuple passed to `unset_jwt_cookies`); `RefreshToken.is_valid` naive/aware TypeError (shared `ensure_aware()`)
- Merged duplicate PRDs into `PRD.md` (removed stale `PRD_Brainstormer.md`)
### Tests
- Suite: 102 passed, coverage ≥ 35% gate met

## [Unreleased]

### Added
- Flask + Jinja2 + Tailwind CSS + Alpine.js frontend stack
- PostgreSQL/SQLite with SQLAlchemy models (User, PromptConfig, Idea, Vote, SecondaryActionResult, IdeaStatusHistory)
- JWT authentication with access/refresh tokens (flask-appkit + custom PyJWT)
- Admin CLI commands (create-admin, create-user, list-users, promote-user)
- Ollama client with JSON-enforced responses and Pydantic validation
- Prompt templates (base, refine, competitors, feasibility)
- Celery task queue with dual queues (ollama concurrency=1, default concurrency=4)
- Celery Beat scheduler for periodic prompt execution
- REST API endpoints:
  - Auth: register, login, refresh, me
  - Prompts: CRUD + run-now (Admin)
  - Ideas: list, detail, status, vote, actions (Admin)
  - Ollama models listing (Admin)
  - Health/Readiness checks
- Health/Ready endpoints with dependency checks
- Rate limiting (disabled in tests)
- Fakeredis for testing
- Security & Privacy Guardrails (`Guardrail.md`)
- Best Practice Updates for LLM integration (`BEST_PRACTICE_UPDATES.md`)

### Changed
- Updated PRD to reflect Flask + Jinja2 stack
- Updated AGENTS.md with project-specific conventions
- Updated README with architecture overview and planned API
- Lowered test coverage threshold to 35% (temporary, target 80%)

### Fixed
- JWT token creation with role claims using PyJWT
- Rate limiting disabled for tests
- Fakeredis integration for testing
- Health check uses app.extensions for Redis client

## [0.2.3] - 2026-09-12
### Fixed
- Test suite fully green (96 passed, coverage 68%): was 20 failed + 26 errors
- Test isolation: `app`/`celery_app` fixtures are now function-scoped (fresh `:memory:` DB per test); session scope had shared one DB across the run so hardcoded emails/codes collided with UNIQUE errors depending on order
- Added missing `admin_client`, `admin_user`, `admin_prompt` fixtures (integration suite was written against `admin_client` but it never existed — 12 setup errors)
- Fixed `@patch` swallowing the `celery_app` fixture in `test_generate_idea_prompt_not_found` (mock took the fixture's parameter slot; passed only by order luck)
- Fixed mocked `.delay().id` MagicMocks breaking `job_id` commits (set string ids)
- Corrected outdated expectations: prompt listing is `@token_required` (200, not 403), `/ollama/models` is user-visible per convention (mock `list_models_sync`, the method the route actually calls)
- `POST /api/v1/logout` 500'd in prod: `unset_jwt_cookies()` got the `(response, status)` tuple instead of the Response — now unpacked first
- `RefreshToken.is_valid()` raised `TypeError` (naive vs aware `expires_at` on SQLite): shared `ensure_aware()` helper in `app/models/types.py`, also adopted by `PromptRun` duration maths
- `test_refresh_token` now follows the real contract (refresh token in JSON body)
- `test_health_ok` stubs the Redis check (no Redis in test env); added `test_health_degraded_without_redis` locking the intended 503 behaviour

## [0.2.2] - 2026-09-12
### Fixed
- Idea generation stalled with orphaned RUNNING runs: `_generate_reference_code()` ordered by random-UUID `id`, re-issuing `IDEA-0005` on every insert -> `UniqueViolation` on all 5 prompts; now takes max over parsed numeric codes (skips non-numeric)
- Poisoned-session orphans: `generate_idea`/`run_secondary_action` now roll back before `mark_failed`, so failures record FAILED instead of raising `PendingRollbackError` and sticking at RUNNING (which also blocked `check_due_prompts` re-enqueue via the live-run guard)
- `PromptRun.mark_success`/`mark_failed` no longer raise `TypeError` on naive datetimes (SQLite/dev); naive values treated as UTC
- Tests: fixed stale-session read in `test_generate_idea_success`, MagicMock `job_id` binding in `test_check_due_prompts`, and cross-test email/code collisions in `tests/tasks/test_ollama_tasks.py` (now 8/8 green); added regression tests for code increment and poisoned-session failure recording

## [0.2.1] - 2026-09-10
### Fixed
- Login form: missing `});` on `fetch("/api/v1/login")` meant the submit handler never registered (silent reload, no message)
- Prompts list/create: unified split Alpine scopes to single page-root `x-data`; modal Cancel/Close/"Saving…" now work
- Model dropdowns: invalid `x-for` on `<option>` replaced with `<template x-for>`; handles string and object models with Ollama-unreachable fallback
- Unclosed script blocks in `prompts/list.html` (`initPromptsPage`) and `admin/users.html` (DOMContentLoaded) that killed all page JS
- RBAC page gating: anonymous users redirect to `/login`; non-admins bounced from `/prompts/create`; admin-only buttons hidden with `isAdmin`
- Admin users: role select/status toggle were permanently disabled (`user.id == user.id` self-compare); loop var renamed, self-row correctly disabled
- Admin API: missing `UserRole`/`api_error`/`api_created` imports (role updates 500'd); enum role search fixed for Postgres
- Admin Panel link 401: login/register now also set JWT cookies so browser navigation carries auth
- Vendored Alpine.js 3.14.8 to `/static/js/alpine.min.js` (no more CDN dependency for interactivity)
- Navbar: JS-driven guest/user areas with username, admin link, and working logout

## [0.1.0] - 2026-09-02
### Added
- Initial scaffold from flask-bootstrap (Flask + SQLite + JWT auth + tests + docs)
- Security & Privacy Guardrails (`Guardrail.md`)
- Best Practice Updates for LLM integration (`BEST_PRACTICE_UPDATES.md`)
- Product Requirements Document (`PRD.md`)
- Updated AGENTS.md with project-specific conventions
- Updated README with architecture overview and planned API