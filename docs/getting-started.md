# Getting started with Brainstormer

## 1. Open the app

Start the app (see `docs/install-config.md`) and open:

- **Web UI:** http://127.0.0.1:8000
- **Flutter client:** same API, same login

## 2. Create an account

Register with an email and password (at least 8 characters):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "password123"}'
```

Then log in:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "password123"}'
```

Your access token is stored in the browser and refreshed automatically.

Google/Apple/Microsoft login is available where your instance admin has
configured it.

## 3. Home page

After login you land on **Home** (`/home`):

- **My ideas** — ideas you created, voted on or commented on.
- **Most popular** — highest voted ideas.
- **Most discussed** — ideas with the most comments.
- **Ideas not voted on** — ideas with zero votes yet.
- **Messages** — your inbox, plus a compose box to message an admin
  (admins can message any member).
- **Ideas in each phase** (admins only) — click a phase to see its ideas.

Child ideas show `"child of <parent reference code>"` next to their title.

## 4. Create an idea

Go to **All ideas** (`/ideas`) and create a new idea. You can optionally
make it a child of an existing SCALE-phase idea (enhancement or bugfix).

## 5. Move an idea through the lifecycle

Pipeline: `SPARK → SCOPE → MAP → SHIP → SCALE`, with `DROP`
(discarded), `FREEZE` (paused) and `ARCHIVE` (terminal).

Some moves require a document first — for example, `BUILD_CODE` needs a
Design doc. Use the **+ Doc** dropdown on a child row in the Scale tab
to generate a PRD, Design or Build document.

## 6. Releases (Scale phase)

When an idea reaches SCALE you can:

- Assign it to a **release** (group of ideas shipping together).
- Set **per-release AI defaults** (provider, model, temperature, skills,
  guides) on the AI Settings page.
- **Push the release to GitHub** (one push per release — further updates
  need a new release).

## 7. AI Settings (instance admin)

On the AI Settings page (`/admin/ai-configs`) you can configure, per
instance:

- **Provider defaults** — Ollama, OpenAI, Anthropic, Gemini, OpenCode.
- **Per-stage defaults** — Spark, Scope, Map, Ship, Scale: provider,
  model, temperature, top P, max tokens, skills, guidelines.
- **GitHub** — repo, branch, personal access token (encrypted at rest).
- **Build repos** — folders this instance builds code into.

## 8. Health

`GET /api/health` reports database, Redis and scheduler liveness.
`GET /api/ready` adds Ollama and worker checks.

## 9. Backup & Restore (admin)

Open **Admin → Backup & Restore** (`/admin/backup`).

- **Site admins** can back up the whole site, download a copy, restore a
  file, and switch the automatic daily backup on or off.
- **Instance admins** can download a backup of their own instance and
  restore it. Per-instance restores are always manual.

Restoring replaces data, so the page asks you to type a confirmation
(`RESTORE` for the whole site, the instance number for an instance)
after it checks the file. Keep a copy of the file somewhere safe: the
server's backup folder is not a substitute for an off-site copy.

## 10. Run over HTTPS (optional)

The container can serve HTTPS itself — no host reverse proxy needed.

1. Put a certificate and key in `certs/`:
   - `certs/server.crt` (full chain, PEM)
   - `certs/server.key` (PEM, unencrypted)
2. Point the app at them in `.env`:

   ```bash
   TLS_CERT_FILE=/certs/server.crt
   TLS_KEY_FILE=/certs/server.key
   ```

3. Restart the web container.

When both files are readable the app serves HTTPS on the normal port
(`https://127.0.0.1:8000`), redirects plain HTTP to HTTPS, sends HSTS,
and marks cookies `Secure`. If either file is missing the app falls
back to plain HTTP, so a typo cannot take the site offline.

For a local/self-signed certificate:

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout certs/server.key -out certs/server.crt \
  -subj "/CN=brainstormer.local"
```

Browsers warn about self-signed certificates until you trust them; see
`Guides/Guide_SecuringWithSSL.md` for the trust steps and for running a
private CA when you have several services.

If TLS is terminated by a reverse proxy *instead*, leave the two TLS
variables empty and set `TRUST_PROXY_HEADERS=True` so the app reads
`X-Forwarded-Proto` and still redirects/HSTS correctly.
