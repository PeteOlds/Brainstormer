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
