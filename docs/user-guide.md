# brainstormer — User guide

## Getting started

1. Start the app (see install-config.md) and open http://127.0.0.1:8000
   (or the Flutter client — same API, same login).
2. **Register** with an email and a password (at least 8 characters).
3. **Login** with the same credentials, optionally picking a workspace
   (instance) when you belong to several.
4. Your access token is stored securely and refreshed automatically;
   an expired session returns you to the login screen.

Google/Apple/Microsoft login is available where your instance admin
has configured it (same account links by verified email, with explicit
confirmation).

## API usage

All API responses follow:
- Success: `{"success": true, "data": ...}`
- Error: `{"success": false, "error": true, "message": ...}` (plus an
  `error_code` for machine handling, e.g. `ILLEGAL_TRANSITION`).

### Register
```bash
curl -X POST http://127.0.0.1:8000/api/v1/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "password123"}'
```

### Login (scoped to an instance with `instance_id`)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "password123"}'
```

### Get current user (authenticated)
```bash
curl http://127.0.0.1:8000/api/v1/me \
  -H "Authorization: Bearer <access_token>"
```

## Health check
`GET /api/health` reports liveness (database, Redis, scheduler);
`GET /api/ready` adds Ollama and worker checks.

## Lifecycle workflow (admin changes state, UI always confirms)

Pipeline: `SPARK → SCOPE → MAP → SHIP → SCALE`, with `DROP` (discarded),
`FREEZE` (on hold) and terminal `ARCHIVE` off to the side. Skip-level
moves are allowed (e.g. Spark straight to Map); illegal moves are
rejected with the allowed list. Every change writes status history.

1. New ideas arrive as **Spark**. Vote, comment, and run any secondary
   action except PRD creation.
2. Move the idea to **Scope** to create the **PRD** (admin: idea → run
   PRD, optional model/skills/guidelines/answers). Answer **open
   questions** to regenerate; comment in **Discussion** (per-document
   thread); **Edit** (admin) saves a corrected version. Every
   recreate/edit appends a new version — history is kept, threads stay
   pinned to their version.
3. Move to **Map** to **Generate Design** (requires an existing PRD).
   When the design is ready, move to **Ship**, then **Scale** once live.
4. Comments are filed per phase (`?phase=` filter); admins can tick
   **Ignore** on noise so it stays out of every AI context (invisible
   to normal users).
5. **Chat** with the AI about any idea (all phases); admins can apply
   **iterations** as new versions and **roll back** to any of them.

## Automatic duplicate handling

Scheduled and manual generations compare each new idea against existing
ideas in the same instance by embedding similarity. A generation
scoring >= 0.97 (`DEDUP_SIMILARITY_THRESHOLD`) is created **DROP**
instead of SPARK, so it stays out of the default filter, and no Slack
post is sent. The duplicate remains in the database with its embedding
(visible under All Statuses) for audit. Manual idea creation is never
auto-discarded.
