# brainstormer — Install & configuration

## Prerequisites
- Python 3.10+
- pip

## Install

```bash
git clone <repo-url> brainstormer
cd brainstormer
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

## Configure

```bash
cp .env.example .env
```

Edit `.env`:
- `SECRET_KEY` — set a long random string (required for JWT + sessions)
- `DATABASE_URL` — defaults to SQLite; use `mysql+pymysql://...` for MySQL

## Run (development)

```bash
source venv/bin/activate
python run.py        # http://127.0.0.1:5000
```

## Run (production, gunicorn)

```bash
gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
```

## Tests

```bash
source venv/bin/activate
pytest
```

Coverage is reported and must stay >= 80%.

## Database migrations
After changing models, use Flask-Migrate:

```bash
flask db migrate -m "describe change"
flask db upgrade
```

## Live Deployment Topology (this host)

Containers are started manually (no compose in prod). All app containers use
**host networking** with **loopback backends** — immune to bridge-IP drift:

- `brainstormer-postgres` (bridge net kept for DNS peers) + `-p 127.0.0.1:5432:5432`
- `brainstormer-redis` + `-p 127.0.0.1:6379:6379`
- `brainstormer-web`, `brainstormer-worker-ollama`, `brainstormer-worker-default`:
  `--network host`, `DATABASE_URL=postgresql://app:PASS@127.0.0.1:5432/brainstormer`,
  `REDIS_URL=redis://127.0.0.1:6379`, `OLLAMA_BASE_URL=http://127.0.0.1:11434`
  (Ollama runs natively on the host, not in Docker).
- `brainstormer-beat` stays on `brainstormer-network` with service names.
- All with `--restart unless-stopped` and bind mount `/mnt/General/OpenCode/brainstormer:/app`.

Do NOT move app containers to bridge networking: the host firewall blocks
bridge→host hairpin traffic, so workers lose Ollama (httpx ConnectTimeout).
Loopback ports are bound to 127.0.0.1 only — not exposed to the LAN.
Web port 8000 is reachable on the LAN via host networking.

## Opencode skills mounts (run dialog)

Web + both workers need read access to host skill dirs (containers cannot
see `/home` otherwise). Recreate preserves everything via
`docker inspect` (image, env, cmd, restart policy) plus:

```bash
-v /home/pete/.agents/skills:/opencode-skills/agents:ro \
-v /home/pete/.opencode/skills:/opencode-skills/opencode:ro \
-e SKILLS_DIRS=/opencode-skills/agents:/opencode-skills/opencode
```

Guidelines live in repo `guidelines/*.md` (visible via the `/app` bind
mount, no extra config). Never `docker rm` without a verified replacement
running: launch `<name>-new` alongside where ports allow, verify, then swap.

## Enum migrations need psql autocommit

`ALTER TYPE ... ADD VALUE` cannot run inside a transaction block, so
`flask db upgrade` FAILS on enum-value migrations. Procedure:

```bash
# 1. each ADD VALUE in its own autocommit session (psql does this)
# 2. flask db stamp <revision>   # mark applied without running
# 3. flask db upgrade             # remaining migrations
```

Exception: the V2 lifecycle migration (`f1a2b3c4d5e6`) rebuilds the
`ideastatus` type (create new → convert with CASE → drop → rename) and
runs fine inside one transaction — no psql workaround needed. It maps
V1 values per PRD_V2 §5.3, promoting SCOPE ideas with a current PRD to
MAP.

## Backups (Phase 0)

Take a backup before every upgrade (golden rule). Encrypted blobs travel
as-is — restoring requires the same `FERNET_KEY`.

```bash
flask backup-site --output /backups/site-$(date +%F).json
flask restore --input /backups/site-2026-09-29.json --yes
flask backup-instance --output /backups/instance.json   # whole-DB export until Phase 1
```

Bundles are versioned JSON with a manifest and SHA-256 checksum; `restore`
refuses corrupt or newer-schema files. Zero-diff proof: back up, restore,
back up again — per-table fingerprints must match
(`pytest tests/integration/test_backup.py`, plus the `backup-drill` CI job).

## Tenancy ops (Phase 1)

First-time tenancy setup on production (after a verified backup):

```bash
flask db upgrade                                    # instances, memberships, instance_id, RLS
flask init-tenancy                                  # Instances 1 + 5, rows to Site 5, memberships
flask promote-site-admin ops@example.com            # site-wide grant
flask create-instance --number 20 --name "Acme"     # copies Instance 1 config
```

Login scoping is optional per token: `POST /api/v1/login` accepts
`instance_id` (403 without membership); tokens without the claim keep the
legacy unscoped behaviour. Numbers 2–19 (except 5) are reserved and the
API/CLI refuse them.

## Provider configuration (Phase 3)

Hosted providers (OpenAI/Anthropic/Gemini via LiteLLM) are per-instance
opt-in. Keys are Fernet-encrypted in `instance_ai_configs`, write-only
over the API, and never copied between instances. Entering a key opts
that instance into egress to that provider only; empty means local-only.

```bash
# Prompts select a provider (default ollama) and a litellm model id:
# POST /api/v1/prompts {"provider": "openai", "model_name": "openai/gpt-4o-mini", ...}
# Per-instance config + spend (instance admin):
# PUT /api/v1/instances/<id>/ai-configs {"provider": "openai", "key": "sk-...",
#   "model_allowlist": ["openai/gpt-4o-mini"], "budget_cents": 5000}
# GET /api/v1/instances/<id>/spend
```

Budgets cover a rolling 30-day window: 70% logs an alert, 100% fails
runs fast (`refuse`; queue/degrade arrive later). Spend rows are
append-only in `ai_spend_ledger` and included in site backups.

Phase 10 additions: DLP masking (emails, phones, API-key shapes, JWTs)
runs on every hosted prompt before send (counts logged, values never);
`queue` cutoff retries the Celery task in 1h instead of failing;
`degrade` falls back to the configured local model (logged loudly);
embeddings route through the proxy when the config uses one; pricing
reads `PRICING_OVERRIDE_PATH` JSON first (finance-owned, hot-reloaded
on change), else the bundled LiteLLM table.

## Chat-to-AI (Phase 4)

```bash
# Chat about an idea (all phases, any signed-in user):
# POST /api/v1/ideas/<id>/chat {"message": "..."}
# History: GET /api/v1/ideas/<id>/chat
# Versioned iteration + rollback (admin only):
# POST /api/v1/ideas/<id>/chat/iterate {"content": {"prompt_title": "..."}}
# POST /api/v1/ideas/<id>/chat/rollback {"turn_id": "..."}
```
3/min/user rate limit. Per-instance switch: once an instance has AI
config rows, at least one needs `chat_enabled: true` or chat returns
403 `CHAT_DISABLED` (pure-Ollama instances without rows stay open).
Turns persist content for history/rollback; logs carry hashes only.

## Restore drills and RTO (Phase 6)

Scheduled site backups run daily via beat (`scheduled_site_backup`
→ `BACKUP_DIR`, default `./backups`, on the Docker backup volume).
Every file is verified by re-read on write. No auto-pruning: monitor
disk, never delete silently.

Drill (quarterly, and before every upgrade):

```bash
flask backup-site --output /backups/pre-upgrade.json
# prove restore on a scratch database, time it:
time flask restore --input /backups/pre-upgrade.json --yes   # against scratch DB
flask backup-instance --instance-id 5 --output /backups/site5.json
flask restore-instance --input /backups/site5.json --yes     # scratch DB
```

RTO record (scratch SQLite, 14 rows: export 0.04s, restore 0.03s —
sub-second at this scale; re-measure on production data and log here):

| Date | Scope | Rows | Restore time | Operator |
|------|-------|------|--------------|----------|
| 2026-09-29 | site (drill) | 14 | 0.03s | automated |
| 2026-09-30 | site (PROD drill, scratch DB) | 2623 | 11.5s | drill |
| _next drill_ | | | | |

Known limitation (pre-existing): a fresh `flask db upgrade` from zero
fails on the historical BUILD/DEVELOPMENT enum migration (new enum
values cannot be used in the same transaction). New databases: build
schema with `db.create_all()` (dev) or apply enum migrations via the
psql-autocommit procedure above, then `flask db upgrade`. Upgrades of
existing databases (the production path) are unaffected.

Target RTO on current production size: under 15 minutes including
verification. Instance restores never touch other instances (proven by
`test_instance_restore_round_trip_leaves_others_alone`).

## Billing entitlements (Phase 8)

Payment provider and pricing are unconfirmed, so billing is manual:
Site Admins grant entitlements; the Free flag sets baselines.

```bash
flask set-entitlement --instance 20 --key hosted_ai            # grant
flask set-entitlement --instance 20 --key hosted_ai --revoke   # revoke
# GET /api/v1/instances/<id>/entitlements                     # read (instance admin+)
# PUT /api/v1/instances/<id>/entitlements                     # write (site admin)
```

Keys: `core` (always), `hosted_ai` (enforced on hosted generation and
chat), `chat`, `extra_guides`, `custom_deploy` (resolvable, wiring
later). Free instances baseline to `core`; paid to everything.
Suspended instances (`status != active`) are refused everywhere.
Start/End dates are recorded and surfaced, enforcement TBD.

## Roles and instance lifecycle enforcement (Phase 9)

Membership roles: `USER`, `DEVELOPER` (+ run actions, discovery),
`BA` (+ doc edits, comment flags), `DEPLOYMENT` (+ actions, status
changes, doc edits), `INSTANCE_ADMIN` (everything in-instance),
`SITE_ADMIN` (global grant). Legacy `ADMIN` users bypass the matrix.

Authors edit their own ideas (content + chat iterate); generated
ideas (`created_by_id` NULL) stay admin-edited. Expired or suspended
instances (`status`, `start_date`/`end_date`) reject all writes with
`INSTANCE_INACTIVE` while reads keep working; the scheduler skips
their prompts automatically.

## Per-stage AI config (item 18)

Each active stage (Spark/Scope/Map/Ship/Scale) may override provider,
model, temperature/top_p/num_predict and default skills/guidelines:

```bash
# PUT /api/v1/instances/<id>/stage-config
# {"stage": "SPARK", "provider": "ollama", "model_name": "llama3:8b",
#  "temperature": 0.7, "skills": [], "guidelines": []}
# GET /api/v1/instances/<id>/stage-config   (all five stages)
```

Resolution everywhere: explicit run arguments > stage row > prompt
values > hardcoded defaults. Unset rows change nothing; chat follows
the stage model unless an admin overrides it.

## Social login (Phase 5)

Per-instance OAuth credentials (instance admin), global identity links:

```bash
# PUT /api/v1/instances/<id>/oauth {"provider": "google", "client_id": "...", "client_secret": "..."}
# Login: GET /api/v1/oauth/<provider>/start?instance_id=<id> -> open auth_url
#   -> provider redirects to /api/v1/oauth/<provider>/callback -> tokens (201/200),
#      409 LINKING_REQUIRED (existing email: confirm via POST /api/v1/oauth/link),
#      or 400 (unverified email, bad state, misconfiguration)
# Members: GET/PATCH/DELETE /api/v1/instances/<id>/members[/<user_id>]
```

Register `APP_BASE_URL/api/v1/oauth/<provider>/callback` at each
provider. Apple: paste a generated client-secret JWT (rotation happens
at Apple, then update here). Link-by-verified-email needs explicit
`confirm: true`; JIT onboarders get the least-privilege USER role.
OAuth endpoints share the 5/min/IP login rate limit.

## LiteLLM proxy sidecar (item 10)

Raw provider keys live only in the proxy; the app holds virtual keys.

```bash
# One-time: create the proxy database, set LITELLM_MASTER_KEY, start up
psql -c "CREATE DATABASE litellm;"
docker compose up -d litellm   # or manual equivalent per topology above
# Per instance+provider (needs the direct API key configured first):
flask provision-proxy-key --instance 20 --provider openai --models openai/gpt-4o-mini
# Then enable proxy mode (refuses without a provisioned key):
# PUT /api/v1/instances/<id>/ai-configs {"provider": "openai", "use_proxy": true}
```

Budgets, spend logging and entitlements stay enforced in the app on
every proxied call. Manual-container parity: run the same
`ghcr.io/berriai/litellm:main-latest` image with
`litellm_config.yaml`, `LITELLM_MASTER_KEY` and
`DATABASE_URL=postgresql://app:PASS@127.0.0.1:5432/litellm`.
