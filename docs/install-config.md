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
