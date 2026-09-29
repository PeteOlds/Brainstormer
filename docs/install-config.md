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
