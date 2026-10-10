# Project Standards — Brainstormer

Flask + Celery + Ollama idea pipeline. SQLite dev/tests, **PostgreSQL prod**.
This file + global SDLC standards apply. User rule: **no markdown files
(`*.md`), passwords, or AI instructions in commits** — so `CHANGELOG.md`
updates stay in the working tree only.

## Build Requirements
Every build must:
1. Run the full test suite before finishing (`pytest`, `--cov-fail-under=35` per `pyproject.toml`)
2. Bump `VERSION` (patch fixes, minor features, major breaking) — changelog entry in tree, never committed
3. Never push to `main`; never commit `.env` or secrets; semantic prefixes (`feat:`, `fix:`, …)

## Commands
```bash
source venv/bin/activate
pytest                                # full suite (~2.5 min)
pytest tests/unit/ -q --no-cov        # fast subset
pytest path/to/test.py -k "name" -q --no-cov
black --check <changed-files>         # repo is NOT black-clean; match surrounding style, don't reformat whole files
```
```bash
# Migrations (model changes ALWAYS need one — SQLite create_all masks missing migrations)
flask db migrate -m "msg"             # needs reachable DB; fails without one
docker exec brainstormer-web flask db upgrade    # apply on prod
docker exec brainstormer-web flask db stamp <rev> # only for enum ADD VALUE (can't run in txn)
```
Enum values (`ideastatus`, `actiontype`): `ALTER TYPE … ADD VALUE` via **psql autocommit only**, then `stamp`. Never expect `upgrade` to run them.

## Live Topology (this host — Docker, not local processes)
- `brainstormer-web` (host network, `:8000`, hypercorn `--reload`), `brainstormer-worker-ollama`, `brainstormer-worker-opencode`, `brainstormer-worker-default`, `brainstormer-beat`, postgres + redis. `ps` shows container processes on host PIDs — there is only ONE worker set.
- All app containers bind-mount the repo: **web/templates reload live; task/model/schema code needs `docker restart brainstormer-worker-*`**.
- Containers were launched with plain `docker run` (no compose plugin installed): recreate (never just edit) via `docker inspect` flags; snapshot with `docker commit` before risky changes. Fresh `pip install` at boot can resolve deps differently — prefer snapshot images over base-image relaunches.
- Host Ollama at `127.0.0.1:11434` (GTX 1050 Ti); workers use `OLLAMA_BASE_URL=http://127.0.0.1:11434`. Embedding models ONLY support `/api/embeddings` (400 on `/api/generate`).
- Queues must be empty before restarts: check `/api/ready` (`queue_depth_*`); `/api/ready` worker counts double-count (`active`+`reserved` maps) — `default: 2` with one node is normal.

## Architecture Notes
- App factory `app/__init__.py:create_app()` (lazy extensions; `init_celery_app=False` for scripts). Configs in `app/config.py`; testing = in-memory SQLite + eager Celery + **headers-only JWT** (cookie navigation untested).
- Auth decorators `app/utils/decorators.py` (`token_required`/`admin_required`, `user` first arg). `GUID` + `ensure_aware()` in `app/models/types.py` (SQLite naive datetimes → `TypeError` without it). JSON columns: never mutate in place.
- Idea pipeline statuses: `NEW CONSIDERATION HOLD DESIGN BUILD COMPLETE DISCARDED` (`app/models/enums.py`). List pagination is **server-side** — frontend must use `total`/`pages`, never re-slice. `ACTIVE_ONLY` excludes DISCARDED.
- Secondary actions: registry (`app/services/secondary_actions.py`) → template (`app/prompt_templates/*.txt`, `${SUPPORTING_MATERIAL}`) → Pydantic schema (`app/schemas/ollama_schemas.py`) → `run_secondary_action`. Run dialog sends `model_override`/`skills`/`guidelines` via `extra`. PRD/DESIGN_DOC are versioned (`is_current`), never deleted.
- Discovery: opencode skills from `SKILLS_DIRS` (`*/SKILL.md` frontmatter) via read-only container mounts; guidelines from repo `guidelines/*.md`. Rescanned per request, no DB.
- **OpenCode provider** (`app/services/opencode_backend.py`): shared server identity (no per-instance key; the CLI reads the worker user's `~/.local/share/opencode/auth.json`). Sandbox mode runs in a throwaway empty dir with a read-only agent; `repo` mode (Site-Admin only, `opencode_workspace` on `InstanceAIConfig`) uses `OPENCODE_WORKSPACE_DIR`. Routed to the dedicated serial `opencode` queue (`enqueue_generation`) with longer time limits. `OPENCODE_SANDBOX_AGENT=""` disables `--agent` (OpenCode's free tier rejects it). Attach mode (instance `endpoint` or `OPENCODE_SERVER_URL`): `opencode run --attach <url> --dir <server-dir>` against the LAN server; `--agent` never sent (servers reject project-local agents); sandbox `--dir` maps via `OPENCODE_SANDBOX_ROOT` ↔ `OPENCODE_SERVER_SANDBOX_ROOT` (same shared dir, here the repo bind mount). Worker needs the CLI binary mounted (`/opt/opencode`, `OPENCODE_BIN`) + loopback `CELERY_*` env (`.env` bridge hostnames don't resolve on host net). Never serves embeddings.

## Frontend Rules (Alpine + Jinja, `ideas/dashboard.html` ~2k lines)
- **One `x-data="ideasApp()"` scope must wrap content AND all modals**; nested `x-data` is isolated (no parent access) — use parent state (e.g. `dropdownOpenId`), never nest scopes.
- **API 200 proves nothing about UI.** Verify every template change in headless Chromium (binaries cached: `~/.cache/ms-playwright/chromium-1234/...`; `/tmp/pwvenv` pattern with file-backed SQLite seed). There is no E2E suite — `tests/ui/` is API-only despite the name.
- Dynamic-key `x-model` (`obj[fn().key]`) silently drops writes; bind stable item objects/arrays instead. `x-show` on elements inside unexpanded `x-if` never appears — prefer `x-if` for conditional blocks.
- Status dropdowns/colors/idea lists must stay in sync by hand (4 selects + `getStatusClass` + activity `dotClass`/`ideaStatuses`).

## What the Suite Cannot Catch (verify live)
SQLite masks Postgres enum/column/table gaps; header-auth tests miss cookie navigation; mocked `OllamaClient` misses real API shapes/endpoints; fixtures never exceed one page (pagination paths untested); small-model output garbage (lists/dicts/truncation) needs recorded-payload contract tests. After any model/migration/task change: check prod (`information_schema`, `pg_enum`, `alembic_version`, row counts) — data is never at risk from additive migrations, but code ships ahead of schema.

## Test Patterns
- Function-scoped `app`/`celery_app` fixtures, fresh in-memory DB each test; no hardcoded seed collisions; no ORM objects across contexts (pass ids); mocked `.delay().id` must be a string; `@patch` fills the first param after `self` — name mocks explicitly.
- Never touch real Redis in tests (shared DB; stale keys poison later suites).
- Auth: `admin_client` (header wrapper), `auth_user` (register+login), `admin_user`/`admin_prompt` seeds.

## Key Files
| Purpose | File |
|---|---|
| Ideas dashboard (list + modals + all JS) | `app/templates/ideas/dashboard.html` |
| Admin activity (runs, charts) | `app/templates/admin/activity.html` |
| Ideas/status/vote/actions/comments API | `app/routes/ideas.py` |
| Admin pages + activity stats | `app/routes/admin.py` |
| Discovery (skills/guidelines) | `app/services/discovery.py` |
| Rich action context | `app/services/action_context.py` |
| Embeddings + similarity | `app/services/embedding_service.py` |
| Prompt template files | `app/prompt_templates/*.txt` (+ repo `guidelines/*.md`) |
| Migrations (single head — verify) | `migrations/versions/` |

## Related Skills
`api-rest`, `auth-jwt`, `sqlalchemy-migrations`, `tdd`, `flask-testing`, `docker`, `ci-cd`, `celery-tasks`, `ollama-integration`, `structured-output`, `prompt-engineering`. Guardrails: `Guardrail.md` §13 every PR.

## Git Rules (hard-won here)
- `git stash` is broken in this repo (root-owned dirs make pop fail and roll back the tree — recover via `git show stash@{0}:path > path`, never pop blindly).
- Commit code/tests/migrations/`VERSION` only; leave all `*.md`, `TODOS.md`, guideline content uncommitted. Scan staged diff for secrets before committing.
