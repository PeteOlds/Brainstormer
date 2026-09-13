# Security & Privacy Guardrails — Brainstormer

Non-negotiable rules for every code change. Treat as a checklist during PR review.

---

## 1. Authentication & Authorization

| Rule | Enforcement |
|------|-------------|
| All API routes require valid JWT (except `/health`, `/api/v1/auth/*`) | `@jwt_required()` decorator + integration tests |
| Role checks on every admin endpoint | `@require_role('ADMIN')` custom decorator |
| Tokens: 15-min access, 7-day refresh, HS256, rotated on login | `auth-jwt` skill config |
| Failed login: generic error, rate-limited (5/min/IP) | Flask-Limiter + unit test |
| Passwords: bcrypt, 12 rounds, never logged | `werkzeug.security` + bandit rule |

---

## 2. Input Validation & Sanitisation

| Rule | Enforcement |
|------|-------------|
| Every request body validated via Pydantic/marshmallow schema | Schema per endpoint, 400 on failure |
| SQLAlchemy ORM only — **no raw SQL** | Bandit `B608` + code review |
| Prompt bodies from admin panel sanitised before Ollama call | Strip control chars, max 10k chars, reject JSON control sequences |
| File uploads: not in MVP — if added later, type/mime/size validation + virus scan | Future gate |

---

## 3. Ollama / LLM Safety

| Rule | Enforcement |
|------|-------------|
| **Never** send user-controlled strings directly into system prompt | Template with `{{PLACEHOLDER}}` only |
| All Ollama calls use `"format": "json"` + schema validation on response | `pydantic` model per action type |
| Timeout: 30s generate, 120s chat — kill worker on exceed | Celery `task_soft_time_limit` |
| Retry once on malformed JSON with stricter system prompt | Worker logic + dead-letter queue |
| Log prompt *hash* only — never full prompt or response | Structured logging, `DEBUG` level only |
| Model allowlist: only models returned by `GET /ollama/models` | Config validation on prompt create |

---

## 4. Data Privacy

| Rule | Enforcement |
|------|-------------|
| **No external API calls** — Ollama runs locally only | Network egress blocked in Docker/host firewall |
| SQLite/Postgres on local disk — no managed cloud DB | `DATABASE_URL` starts with `sqlite:///` or `postgresql://localhost` |
| Votes/ideas never leave the server — no analytics, no telemetry | Code review, no `requests`/`httpx` to external hosts |
| Admin prompt configs stored encrypted at rest (Fernet) | `cryptography` + key from env |
| Session cookies: `HttpOnly`, `Secure`, `SameSite=Strict` | Flask config |

---

## 5. Rate Limiting & DoS Protection

| Endpoint | Limit |
|----------|-------|
| `POST /api/v1/auth/login` | 5 req/min/IP |
| `POST /api/v1/prompts/*/run-now` | 1 req/5min/user |
| `POST /api/v1/ideas/*/actions` | 3 req/min/user |
| `POST /api/v1/ideas/*/vote` | 30 req/min/user |
| All other API | 100 req/min/IP |

Implemented via Flask-Limiter with Redis backend.

---

## 6. Logging & Audit (No PII)

| Event | Log Level | Fields |
|-------|-----------|--------|
| Auth success/failure | INFO/WARNING | `user_id`, `ip`, `user_agent` (no password) |
| Prompt create/update/delete | INFO | `admin_id`, `prompt_id`, `action` |
| Idea generated | INFO | `idea_id`, `prompt_id`, `model`, `latency_ms` |
| Vote cast | INFO | `idea_id`, `user_id`, `direction` |
| Secondary action queued/completed | INFO | `idea_id`, `action_type`, `job_id`, `status` |
| Ollama error | ERROR | `model`, `error_type`, `retry_count` (no prompt content) |

**Never log**: prompt bodies, idea content, votes detail, IP in production without consent.

---

## 7. Secrets Management

| Secret | Source | Rotation |
|--------|--------|----------|
| `JWT_SECRET_KEY` | `.env` (32+ chars, generated) | 90 days |
| `FERNET_KEY` (prompt encryption) | `.env` | 180 days |
| `REDIS_URL` | `.env` | N/A |
| `DATABASE_URL` | `.env` | N/A |

- `.env` in `.gitignore` — **never committed**
- `.env.example` with dummy values committed
- CI fails if `.env` detected in repo (git-secrets hook)

---

## 8. Dependency Hygiene

| Rule | Tool |
|------|------|
| Pin all deps in `requirements.txt` + `requirements-dev.txt` | `pip-tools` |
| `safety check` in CI on every PR | GitHub Actions |
| `bandit -r app/` in CI | GitHub Actions |
| No `git+` or editable installs in prod requirements | Code review |
| Update deps monthly via Dependabot PRs | GitHub config |

---

## 9. Database Safety

| Rule | Enforcement |
|------|-------------|
| Migrations via Alembic only — **no `db.create_all()` in prod** | `sqlalchemy-migrations` skill |
| All FKs indexed | Migration review |
| Soft deletes for `ideas` (`status = 'DISCARDED'`) — no hard delete | Model constraint |
| Audit log on every status change (`idea_status_history`) | Trigger + model |

---

## 10. Frontend (Jinja2 + Tailwind) Safety

| Rule | Enforcement |
|------|-------------|
| All forms: CSRF token (`{{ csrf_token() }}`) | `Flask-WTF` + template audit |
| No inline `<script>` — CSP `script-src 'self'` | `Flask-Talisman` |
| User-rendered content (idea summary) escaped by default | Jinja2 autoescape + `|safe` only on admin-sanitised markdown |
| Admin markdown preview: `bleach.clean(..., tags=ALLOWED_TAGS)` | Utility function + test |

---

## 11. Deployment Guardrails

| Requirement | Check |
|-------------|-------|
| Docker image: non-root user, read-only rootfs | `Dockerfile` `USER appuser` + `security_opt` |
| Health endpoint: `/health` returns 200 only if DB + Redis + Ollama reachable | Integration test |
| Zero-downtime deploy: `preStop` hook + readiness probe | K8s/Render/Railway config |
| TLS termination at reverse proxy (Caddy/Traefik) — app HTTP only | Infra config |
| Backups: SQLite `.dump` daily, Postgres `pg_dump` daily + point-in-time | Cron + verify restore quarterly |

---

## 12. Incident Response (Minimal)

- **Breach**: Rotate `JWT_SECRET_KEY`, invalidate all sessions, notify admins via email
- **Ollama compromise**: Block egress, wipe prompt configs, re-pull models
- **Data loss**: Restore from latest verified backup, replay audit log for votes

---

## 13. PR Checklist (Copy into PR Template)

```markdown
## Security & Privacy Checklist
- [ ] No raw SQL / f-string queries
- [ ] All new endpoints have `@jwt_required()` + role check
- [ ] Input validated via Pydantic schema
- [ ] Ollama calls use JSON format + response validation
- [ ] No secrets in code / logs / commit history
- [ ] Rate limiter configured for new endpoints
- [ ] `bandit` and `safety` pass locally
- [ ] Tests cover auth, validation, error paths
- [ ] No external network calls introduced
- [ ] CSP/Talisman headers not weakened
```

---

## 14. Enforcement Automation

```yaml
# .github/workflows/guardrails.yml
on: [pull_request]
jobs:
  guardrails:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements-dev.txt
      - run: bandit -r app/ -f json -o bandit.json || true
      - run: safety check --json --output safety.json || true
      - run: pytest --cov=app --cov-fail-under=80
      - run: python scripts/check_no_external_calls.py  # custom grep for requests/httpx/urllib
      - run: python scripts/check_no_secrets.py         # git-secrets / detect-secrets
```

---

*Guardrails are living rules. Update when threats change. Every change requires PR + approval.*