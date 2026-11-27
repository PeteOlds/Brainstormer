# Brainstormer

Flask + Celery + Ollama idea pipeline. SQLite for dev/tests, PostgreSQL in prod.

## Commands

```bash
source venv/bin/activate
pytest                              # full suite (~4 min, coverage gate 35%)
pytest tests/unit/ -q --no-cov      # fast subset
pytest path/to/test.py -k name -q --no-cov
python scripts/check_no_external_calls.py
```

Restart containers after any `.py` change:

```bash
docker restart brainstormer-web brainstormer-worker-default brainstormer-worker-ollama brainstormer-worker-opencode brainstormer-beat
```

Template changes reload live; Python changes do not.

## Flutter web

The app served at `/` is a Flutter web bundle from `flutter/build/web`. Rebuild it with:

```bash
./scripts/build_web.sh
```

Never use plain `flutter build web`. The script passes `--no-web-resources-cdn`, which is required: the default build points CanvasKit at `www.gstatic.com`, and the app's CSP (`script-src`/`connect-src 'self'`) blocks it, leaving a blank page with console errors. With the flag, CanvasKit is served same-origin from `build/web/canvaskit/`.

`flutter/build/` is git-ignored, so rebuild after pulling or changing Dart code.

## Migrations

Model changes need an Alembic migration. SQLite `create_all()` hides missing migrations.

```bash
flask db migrate -m "msg"           # needs a reachable DB
docker exec brainstormer-web flask db upgrade
docker exec brainstormer-web flask db heads
docker exec brainstormer-web flask db stamp <rev>   # enum ADD VALUE only
```

Enum values (`ideastatus`, `actiontype`) need `ALTER TYPE ... ADD VALUE` via psql autocommit, then `stamp`. Do not expect `upgrade` to run them. There can be multiple heads; check before upgrading.

## Live topology

- Containers use host networking; app is on `:8000`.
- Workers are not auto-started. If builds/releases never complete, start the worker containers manually with `-Q default`, `-Q ollama`, `-Q opencode`, and beat.
- Use `127.0.0.1`, not `postgres`, in `DATABASE_URL` for host-network workers.
- Check `/api/ready` before restarts; queues should be empty.
- Ollama is at `127.0.0.1:11434`; embedding models use `/api/embeddings` only.
- OpenCode runs on a dedicated serial `opencode` queue. Declare it in `task_queues` and start its worker with `-Q opencode`. Use `enqueue_generation()`, never `.delay()` directly for possibly-OpenCode runs.
- OpenCode auth: CLI reads `OPENCODE_PASSWORD`/`OPENCODE_SERVER_PASSWORD`; password is in `~/.config/opencode/service.json` on the server host.
- Workers run as uid 1000. Generated files must stay user-owned.
- Build roots and `/builds` must be bind-mounted into web and workers.
- Container paths never reach users: translate with `server_path()`/`container_path()`.

## Tests

- Tests use in-memory SQLite and eager Celery.
- Auth tests use headers, so cookie navigation is not covered.
- SQLite masks Postgres enum/column gaps; verify prod schema after migration/task changes.
- `tests/ui/` is API-only despite its name. Verify template changes in headless Chromium; an HTTP 200 is not UI proof.
- Pagination is server-side: use `total`/`pages`, never re-slice.
- Do not touch real Redis in tests.

## Architecture gotchas

- App factory: `create_app()`; use `init_celery_app=False` for scripts.
- `GUID` and `ensure_aware()` for SQLite naive datetimes.
- JSON columns are never mutated in place.
- Idea lifecycle is V2: `SPARK SCOPE MAP SHIP SCALE DROP FREEZE ARCHIVE`.
- Stage gates: PRD after SPARK, Design after MAP, BUILD_CODE after SHIP/SCALE plus an existing Design doc.
- Secondary actions: registry -> prompt template -> Pydantic schema -> `run_secondary_action`. Run dialog sends overrides via `extra`.
- PRD/DESIGN_DOC are versioned with `is_current`; never deleted.
- Build instructions are derived in `_extract_runtime_info`, `_allocate_build_port`, and `_derive_runbook`; do not trust model prose. No runbook means no write: the confirm run refuses instead of marking a build Built that cannot start.
- Supervision pids are container-local; status is health-first and Stop runs as a worker task.
- `git stash` is broken in this repo; use a patch file instead.

## Build and release

- Run the full test suite before committing. If tests cannot run or failures are pre-existing, document why.
- Bump `VERSION` for every build (semantic: patch for fixes, minor for features, major for breaking).
- Update `ReleaseNotes.md` on every release: add version/date and list features and bug fixes shipped.
- Keep `docs/ROADMAP.md` as outstanding work only — no completed items. Every item must have a unique ID and belong to a phased release; remove items when shipped and record them in `ReleaseNotes.md`.

## Git

- `main` is protected: no direct commits or pushes. These project rules override the global agent defaults.
- Work on short-lived, issue-scoped branches (`feat/`, `fix/`, `agent/`) in a `git worktree`; one slice per branch, atomic commits at verified checkpoints, squash merge via PR. Tag a stable point before risky refactors.
- Semantic commit prefixes.
- Commit code, tests, migrations, `VERSION`, and release records: include `ReleaseNotes.md` (and `docs/ROADMAP.md` when outstanding work changes) in the release commit. Keep `CHANGELOG.md` working-tree only unless a release explicitly requires it. Never commit `.env`, secrets, or private keys (e.g. `certs/`).
- Bump `VERSION` for every build: patch, minor, or major.
- Full session/branch/PR workflow: `docs/opencode-workflow.md`.

## Verification

```bash
python scripts/check_no_external_calls.py
pytest
```
