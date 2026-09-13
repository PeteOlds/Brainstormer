# Project Standards — Brainstormer

This project follows the global SDLC standards. In addition:

## Build Requirements
Every build must:
1. Run the full test suite (`pytest`, coverage >= 35% per pyproject.toml, aim for 80%+) before finishing
2. Update documentation that the change affects (README, AGENTS.md, docs/*)
3. Bump the semantic version in `VERSION` and add a CHANGELOG entry
   - patch for bug fixes, minor for new features, major for breaking changes
   - **Create CHANGELOG.md if it doesn't exist** (see Keep a Changelog format)

## Conventions
- Modular code: `app/models`, `app/routes`, `app/services`, `app/utils`
- Development inside the `venv/` virtual environment
- SQLite by default (`DATABASE_URL` env var overrides)
- Never commit `.env` or real secrets
- Semantic commit prefixes (feat:, fix:, docs:, refactor:, test:, chore:)
- **Security & Privacy**: All changes must pass `Guardrail.md` checklist
- **LLM Integration**: Follow the `ollama-integration`, `structured-output`, and `prompt-engineering` skills

## Project-Specific Requirements
- **Background Jobs**: Celery + Redis (see `celery-tasks` skill)
- **Ollama Client**: `app/services/ollama_client.py` with JSON enforcement; `@token_required` not `@admin_required` on `/ollama/models`
- **Prompt Templates**: File-based in `app/prompt_templates/` (not hardcoded)
- **Response Validation**: Pydantic schemas in `app/schemas/ollama_schemas.py`
- **Structured Logging**: structlog JSON format (production)
- **Metrics**: Prometheus counters/histograms for LLM latency, queue depth
- **Auth persistence**: Refresh token rotation with database-backed `RefreshToken` model; old tokens invalidated on rotation; "Remember Me" extends to 30 days

## Lessons Learned (Critical for Future Sessions)
- **Frontend bugs hide silently**: A broken `fetch` handler (missing `});`) causes form submits to reload the page with no feedback. Always check the browser devtools Console tab.
- **Cache invalidation matters**: `base_auth.html` had no `Cache-Control` headers, so incognito windows could still serve stale broken scripts. Add `<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">` and `<meta http-equiv="Pragma" content="no-cache">` and `<meta http-equiv="Expires" content="0">` to all auth templates.
- **Nested quotes in Jinja2 templates**: `JSON.stringify({email, password, remember: remember})` inside `body:` is fragile. Isolate the JSON string or use a template variable to avoid quote-escalation cycles.
- **Check both backend and frontend**: API returning `200` with valid tokens does not guarantee the UI works. The `/login` page had valid HTML but broken JavaScript — the `fetch` handler was never registered.
- **Test file quote bugs can mask real bugs**: `tests/ui/test_prompt_dropdown.py` had its own nested-quote syntax errors, which caused `pytest` collection failures and concealed the login issue. Keep test files syntactically clean.
- **Error boundaries must be reachable**: The `catch` block in the login handler does set the error box, but only if the `fetch` promise resolves. Because the `fetch` call was never properly closed, the entire handler was silently ignored, and the `catch` never ran — hence "no message given."
- **Test isolation is non-negotiable**: session-scoped fixtures sharing one `:memory:` SQLite DB caused order-dependent UNIQUE failures across the suite. Fixtures (`app`, `celery_app`) must be function-scoped so every test gets a fresh DB. Fixtures must be self-sufficient: no hardcoded seed rows (collide with tests inserting the same rows), no ORM objects passed across nested app contexts (DetachedInstanceError — pass ids/strings), mocked `.delay().id` must be a string (MagicMock breaks `job_id` commits).
- **`@patch` eats fixture slots**: a decorator-injected mock fills the first parameter after `self`, so `def test_x(self, celery_app)` under `@patch` receives the mock, not the fixture — name the mock parameter explicitly (`def test_x(self, mock_client, celery_app)`).
- **Naive vs aware datetimes**: SQLite returns naive datetimes for `DateTime(timezone=True)` columns. Any expiry/duration comparison must go through `ensure_aware()` (`app/models/types.py`) or it raises `TypeError` (broke refresh-token validation and run failure recording).

## Related Skills
- `api-rest` — endpoint/pagination/filtering patterns
- `auth-jwt` — authentication patterns
- `sqlalchemy-migrations` — database migrations
- `tdd` — test-driven development
- `flask-testing` — test fixtures
- `docker` — container patterns
- `ci-cd` — GitHub Actions pipeline
- `celery-tasks` — background jobs, retry, worker topology
- `ollama-integration` — local LLM client patterns
- `structured-output` — Pydantic validation of model responses
- `prompt-engineering` — file-based prompt templates

## Guardrails Reference
See `Guardrail.md` for non-negotiable security/privacy rules. Every PR must satisfy the checklist in §13.