# Design — Brainstormer V2

**Status:** Draft for review (decisions locked 2026-09-29).
**Implements:** `PRD_V2.md` (whole-V2 scope).
**Decisions locked:** LiteLLM proxy · Riverpod state management ·
defence-in-depth Postgres RLS · Docker volume / filesystem backups ·
fresh mermaid diagrams (this document replaces the missing status image).
**Baseline:** v0.27.1. Related: `PRD_V2.md`, `docs/architecture.md` (V1, stale),
`docs/erd.md` (V1, stale — §4 supersedes it for V2), `Guardrail.md`,
`Guides/` (SocialLogin + MultiTenantAIConnectivity Adopted-for-V2).

> Conventions (from `AGENTS.md`, non-negotiable in build): GUID PKs
> (`app/models/types.py`), `ensure_aware()` for all datetime maths, whole-document
> JSON writes (never in-place mutation), content-free structlog, JSON-mode +
> Pydantic validation on every LLM call, ORM-only queries, Alembic-only
> migrations. On any conflict with `AGENTS.md`/`Guardrail.md`, those win.

---

## 1. Architecture

### 1.1 System shape

```mermaid
flowchart TD
    subgraph Client["Flutter app (web + mobile, Riverpod)"]
        UI[Dumb widgets]
        CTL[Controllers / providers]
        NET[Single ApiClient + refresh]
        SEC[Secure storage: tokens]
        UI --> CTL --> NET --> SEC
    end
    subgraph Backend["Flask API (API-only, no Jinja)"]
        RT[Routes / blueprints]
        SVC[Services layer]
        PRX[Provider interface]
    end
    subgraph AI["LLM plane (LiteLLM proxy)"]
        LITE[LiteLLM proxy]
        OLL[Ollama local]
        OP[OpenAI] AN[Anthropic] GM[Gemini]
    end
    NET -->|HTTPS/JSON envelope| RT --> SVC --> PRX --> LITE
    LITE --> OLL & OP & AN & GM
    RT --> PG[(PostgreSQL 16 + RLS)]
    RT --> RD[(Redis 7: broker/backend/limiter)]
    SVC --> WQ[Celery: llm-serial x1 + default x4 + beat]
    BK[Backup volume / filesystem] --- PG
```

- **Frontend:** single Flutter codebase (web + mobile). Dumb widgets;
  all logic in Riverpod controllers; all network through one `ApiClient`
  (refresh + error parsing); tokens in secure storage, never localStorage.
  Feature-first layout `lib/features/<auth|ideas|prompts|admin|chat|settings>/`
  plus `lib/core/<network|theme|tokens>/`. The Flask app is **not**
  restructured — it stays layer-based (`app/models|routes|services|utils`).
- **Backend:** Flask becomes API-only. All Jinja/Alpine routes removed
  (old UI routes return 410 with a pointer to Flutter); `index.html` deleted.
  Response envelope `{success, data|message}` unchanged.
- **LLM plane (LiteLLM, decided):** every generation, embedding, model-list
  and chat call routes via the provider interface to a LiteLLM proxy, which
  standardises shapes and applies per-instance routing by virtual key.
  `OllamaClient` survives as one provider backend (local route, not a special
  case). JSON-mode + Pydantic guarantees hold on every route.
- **Data:** PostgreSQL 16 (prod) / SQLite (dev/test). RLS is defence-in-depth
  on Postgres (policies mirror server-side scoping; SQLite path relies on
  server checks only — it has no RLS). Redis keeps DB 0/1/2 (+3 testing).
- **Jobs:** Celery keeps the serial-vs-parallel split; queue names stay
  `ollama` + `default` unless a rename proves trivially safe.
- **Backups:** Docker volume / filesystem target: site bundle
  (`.tar.gz`: per-instance JSON + manifest + checksum) and single-instance
  JSON, produced by `flask backup-site / backup-instance / restore` CLI.

### 1.2 Request scoping

Every request resolves `(user, instance, membership-role)` from the JWT
(`sub` + `instance_id` claim) plus a membership check. Cross-instance access
→ 403/404 without leaking existence. Scheduler, health, activity, prompt
health, similarity, Slack mapping and spend queries are all instance-scoped.

---

## 2. Lifecycle states

Fresh diagram (normative with `PRD_V2.md` §5.2; admin-only moves, UI confirms
every change, no gates, Archive reversible):

```mermaid
stateDiagram-v2
    [*] --> Spark: new idea
    Spark --> Scope
    Spark --> Map
    Spark --> Drop
    Spark --> Freeze
    Scope --> Map
    Scope --> Ship
    Scope --> Drop
    Scope --> Freeze
    Map --> Scope
    Map --> Ship
    Map --> Drop
    Map --> Freeze
    Map --> Archive
    Ship --> Scale: live (normal path)
    Ship --> Scope
    Ship --> Map
    Ship --> Drop
    Ship --> Freeze
    Ship --> Archive
    Scale --> Scope
    Scale --> Map
    Scale --> Ship
    Scale --> Drop
    Scale --> Freeze
    Scale --> Archive
    Drop --> Scope
    Drop --> Map
    Drop --> Ship
    Drop --> Scale
    Drop --> Freeze
    Drop --> Archive
    Freeze --> Scope
    Freeze --> Map
    Freeze --> Ship
    Freeze --> Scale
    Freeze --> Drop
    Freeze --> Archive
    Archive --> [*]
```

V1→V2 migration: `NEW→Spark`, `CONSIDERATION→Scope`, `HOLD→Freeze`,
`DESIGN→Map` iff a current PRD exists else `Scope`, `BUILD→Ship`,
`COMPLETE→Archive`, `DISCARDED→Drop`; unknowns → Scope. History backfilled
one row per idea. Postgres enum surgery follows the 0.23.0 precedent
(`ADD VALUE` outside a transaction; expand-and-contract, down scripts verified
in CI, production rolls forward).

---

## 3. Screens (Flutter)

Ported from the Jinja pages, plus V2-new screens. Shared shell: versioned
footer with build number (golden rule), instance switcher, dark mode.

| Screen | Purpose | Key components / states |
|--------|---------|-------------------------|
| Instance picker (new) | Choose active instance after login | List with roles; loading/empty (single-membership auto-enter)/error |
| Ideas (from `/ideas`) | Main list | Filters (status/sort/search/prompt/model/phase), table + mobile cards, vote buttons (44px), bulk bar (admin), pagination; loading/empty/error |
| Idea detail (from modal) | Tabs per action + overview | Voting, status change (admin, always-confirm), per-phase comment thread with phase chips + Ignore tickbox (admin), PRD Q&A, doc editor (save-as-new-version), Chat tab |
| Chat-to-AI (new) | Iterate the idea conversationally | Message list, composer, model label, rollback control per versioned edit; rate-limit + disabled states |
| Prompts (from `/prompts`) | Prompt CRUD + test + run-now | Provider + model pickers (per-instance allowlist), SSE test stream, active toggle; admin-gated |
| Admin dashboard / users / activity (from `/admin*`) | Stats, health, users, runs | Stat cards, breakdown bars with deep links, run timeline, prompt-health flags; ADMIN only |
| Instance AI settings (new) | Providers, keys, budgets, chat toggle | Provider rows (key entry, never echoed), model allowlists, budget + cutoff behaviour, cost dashboard; Instance Admin only |
| Social/OAuth config (new) | Per-instance Google/Apple/Microsoft credentials | Provider rows, encrypted-secret entry, verified badge; Instance Admin only |
| Backups (new) | Export/restore | Site-wide bundle (Site Admin) + own-instance JSON (Instance Admin); checksum + restore drill status |

**Design tokens** (derived from the current Tailwind config, no hardcoding):
font `Inter, system-ui, sans-serif`; primary blue
`50 #eff6ff / 100 #dbeafe / 500 #3b82f6 / 600 #2563eb / 700 #1d4ed8`;
surfaces slate + white with `dark:` variants; 44px minimum touch targets;
spacing scale `AppSpacing.{xs,sm,md,lg}`. Controllers own all state; widgets
≤ 150 lines with sub-widget extraction; `const` constructors; `dispose()`
all controllers/subscriptions.

**Deep links preserved:** `/ideas?status&prompt&model&idea`,
activity `?run_status&model`, prompts `?edit=`. Single `ApiClient` handles
401 → refresh-or-login; admin probe pattern unchanged.

---

## 4. Data model

New tables first; then alterations. All PKs GUID, all timestamps UTC
(`ensure_aware`), JSON whole-document writes, FKs indexed.

### 4.1 New tables

| Table | Fields (types) | Constraints / notes |
|-------|----------------|---------------------|
| `instances` | `id GUID PK, name(200), start_date nullable, end_date nullable, is_free bool default true, status(20) default active, created_at/updated_at` | IDs 2–19 reserved (no rows except Site 5 seed path); Instance 1 template. Start/End/Free stored, **not enforced** in V2 |
| `memberships` | `id GUID PK, user_id FK→users, instance_id FK→instances, role string(20), created_at` | Unique `(user_id, instance_id)`; string-backed role (`SITE_ADMIN`/`INSTANCE_ADMIN`/`USER`) so future roles need no enum migration |
| `tenant_oauth_configs` | `id GUID PK, instance_id FK, provider_name(20), encrypted_secret Text, created/updated_at` | Unique `(instance_id, provider_name)`; AES-256-GCM at rest |
| `instance_ai_configs` | `id GUID PK, instance_id FK, provider(20), encrypted_key Text, endpoint(255) nullable, model_allowlist JSON default [], budget_cents nullable, cutoff_behaviour(20) default refuse, chat_enabled bool default false` | Unique `(instance_id, provider)`; keys never copied from Instance 1, never returned to non-admins |
| `chat_sessions` | `id GUID PK, idea_id FK, user_id FK, instance_id FK, phase(20), model_used(100), created_at` | One session per (idea, user) per phase run; history bounded by token budget in code |
| `chat_turns` | `id GUID PK, session_id FK, role(10), content_hash(64), created_at` | Full content versioned via `IdeaEdit` on iterate; prompt hash logged, bodies never in logs |
| `ai_spend_ledger` | `id GUID PK, instance_id FK, user_id FK, provider(20), model(100), prompt_tokens int, completion_tokens int, cost_cents int, created_at indexed` | Written by proxy callbacks; local-Ollama rows carry zero cost but keep tags |

### 4.2 Altered tables

| Table | Change | Migration notes |
|-------|--------|-----------------|
| `users` | add `global_subject_id(255) nullable unique` | Backfilled on first social link; password users unaffected; email stays globally unique |
| `comments` | add `phase(20) nullable indexed`, `is_ignored bool default false` | Backfill `phase='Scope'`; composite `(instance_id, idea_id, phase)` index — deliberate required-by-filter exception to the no-speculative-indexes rule |
| `ideas`, `prompt_configs`, `prompt_runs`, `votes`, `idea_edits`, `secondary_action_results`, `idea_status_history`, `slack_posts` | add `instance_id FK→instances indexed` | Site 5 backfill for all existing rows incl. users; copy-on-create copies prompts/settings/templates/skills/guidelines only |
| `prompt_configs` | add `provider(20) default ollama` | Allowlist validated per instance |
| `ideas.status` | V1 enum → `SPARK/SCOPE/MAP/SHIP/SCALE/DROP/FREEZE/ARCHIVE` | PRD_V2 §5.3 map; Postgres `ADD VALUE` outside transaction (0.23.0 precedent) |
| `system_settings` | per-instance rows (`instance_id FK`) | Replaces singleton; Instance 1 row is the copy source |

### 4.3 RLS (defence-in-depth, Postgres only)

Row policies on all `instance_id` tables: `USING (instance_id =
current_setting('app.instance_id')::uuid)` for reads/writes, with the server
setting the variable per request from the verified JWT claim. RLS is a
failsafe — **server-side membership checks remain the enforcement layer**
(and the only layer on SQLite). Service/beat roles bypass via dedicated
grants; every policy ships with a negative test (cross-instance 403/404).

---

## 5. API contracts

Envelope `{success, data|message}` throughout. Auth: `Authorization: Bearer`
JWT (access) + rotating refresh in body; social flows mint the same pair —
provider tokens never reach clients. New endpoints marked ★.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/v1/register`, `/login`, `/refresh`, `/logout` | as V1 | Unchanged mechanics |
| GET/PATCH | `/api/v1/me`, `/api/v1/me/settings` | token | Unchanged |
| ★ GET | `/api/v1/instances` | token | Memberships with roles |
| ★ POST | `/api/v1/instances/<id>/switch` | token | Returns JWT scoped to that instance (membership required) |
| ★ POST/GET | `/api/v1/instances` | SITE_ADMIN | Create (copies Instance 1 config, empty keys); get |
| ★ GET/PATCH | `/api/v1/instances/<id>/ai-config` | instance admin | Keys write-only (never read back); allowlists, budgets, `cutoff_behaviour`, `chat_enabled` |
| ★ GET | `/api/v1/instances/<id>/spend` | instance admin | Prompt/completion tokens, daily spend (own instance) |
| ★ GET/PUT | `/api/v1/instances/<id>/oauth` | instance admin | Per-provider encrypted secrets + verified badge |
| ★ GET | `/oauth/<provider>/start?instance=<id>` | none | PKCE + `state` carries tenant; 5/min/IP |
| ★ GET | `/oauth/<provider>/callback` | none | Verified-email + explicit-confirm linking; JIT least-privilege; mints standard pair |
| GET/POST/PATCH/DELETE | `/api/v1/prompts…` | as V1 | + `provider` field; allowlist per instance |
| GET/POST | `/api/v1/ideas`, `/ideas/<id>`… | token | + `phase` filter on list; status transitions validated against §2 matrix (400 otherwise) + always-confirm client-side |
| GET/POST | `/ideas/<id>/comments` | token | + `?phase=`; `is_ignored` admin-write-only, hidden from users |
| ★ POST/GET | `/ideas/<id>/chat` | token | All phases (feature-flagged per instance); 3/min/user default; iterate writes versioned `IdeaEdit` |
| ★ POST | `/ideas/<id>/chat/rollback` | token | Restore any prior version |
| POST/GET/PATCH | `/ideas/<id>/actions`… | as V1 | Gating rewritten per stage (Spark minus PRD, Scope plus PRD, Map design docs); ignored comments excluded from context |
| GET | `/api/health`, `/api/ready` | none | + per-instance + provider checks; build number in payload |
| CLI | `flask backup-site/backup-instance/restore`, `create-admin…` | shell | Site bundle tarball + per-instance JSON + manifest + checksum |

Rate limits (extends Guardrail §5): login/social-start 5/min/IP, run-now
1/5min/user, actions + chat 3/min/user, votes 30/min/user, default 100/min/IP.

---

## 6a. Backup & Restore (UI) (2026-10-24, implemented 2026-10-25)

- Page: `/admin/backup` (`app/templates/admin/backup.html`, Alpine
  `backupApp()`), linked from the Admin dashboard.
- API (`app/routes/backup.py`, all admin-gated):
  - `GET  /api/v1/admin/backup` — instances you can admin, stored files
    (site admins), automation flag.
  - `POST /api/v1/admin/backup/site/run` — write a timestamped site file to
    `BACKUP_DIR` now.
  - `GET  /api/v1/admin/backup/site/download` — fresh export as a download.
  - `GET  /api/v1/admin/backup/files/<name>` — download a stored file.
  - `POST /api/v1/admin/backup/site/verify|restore` — upload, verify
    (schema + SHA-256), then restore after typing `RESTORE`.
  - `POST /api/v1/instances/<id>/backup/verify|restore` — per-instance
    equivalent; confirmation is the instance number.
  - `GET  /api/v1/instances/<id>/export` — existing instance download.
  - `PUT  /api/v1/admin/backup/settings` — site backup automation on/off
    (stored in `SystemSettings.platform.site_backup_automated`).
- Scope: instance admins (their instances, manual only) + site admins
  (whole site, automated daily job respects the toggle).
- Restores are synchronous with staged UI progress; no worker/DB race.
- CLI remains the automation path for scripts; the UI is for people.
- Tests: `tests/integration/test_backup_ui.py` (9 cases, real bundles).

## 6b. Archive UX (2026-10-24, implemented 2026-10-25)

- Archive is reversible (amends C5, 2026-10-26): any live stage can archive;
  restore returns the idea to the stage it left.
- The raw `ARCHIVE` option is gone from every status dropdown. Cards and the
  detail modal show **"Archive this idea"** (only for stages the matrix allows;
  already archived) with a plain-language confirmation.
- Bulk bar has a separate **"Archive selected"** button.
- Restore: "Restore to <stage>" uses `archived_from` (latest ARCHIVE row in
  status history). Archived ideas are read-only for secondary actions.
- Terminal/low-level transitions stay admin-only (`isAdmin`); non-admins
  never see them.
- Skip-level moves remain allowed (C5).

## 6c. Self-contained TLS (2026-10-24, implemented 2026-10-25)

- TLS terminated inside the container: `docker-entrypoint.sh` appends
  `--certfile/--keyfile` to gunicorn (or hypercorn) when both
  `TLS_CERT_FILE` and `TLS_KEY_FILE` are readable. Empty/unreadable files
  fall back to plain HTTP, so a misconfiguration never takes the site down.
- `./certs` is mounted read-only at `/certs` in compose. Any PEM pair works
  (self-signed for a local install, full chain for a public domain).
- A readable pair implies `FORCE_HTTPS`: Talisman redirects HTTP→HTTPS,
  sends HSTS for one year (`HSTS_MAX_AGE`), and `SESSION_COOKIE_SECURE` /
  `JWT_COOKIE_SECURE` are forced on.
- Reverse-proxy deployments leave the TLS vars empty and set
  `TRUST_PROXY_HEADERS=True` (ProxyFix, one trusted hop).
- Cert provisioning documented in `docs/getting-started.md` §10 and
  `Guides/Guide_SecuringWithSSL.md` (self-signed for dev, Let's Encrypt for prod).
- Minimal host config: only a cert/key volume mount.
- Tests: `tests/unit/test_tls_config.py` (defaults stay HTTP, TLS implies
  redirect/HSTS/Secure cookies, ProxyFix is opt-in, entrypoint passthrough).

## 6d. Flutter cutover (2026-10-24)

- Hard flip: set `LEGACY_WEB_ENABLED=False` after Flutter parity verified.
- Monitor 2 weeks with zero P1s, then delete Jinja templates a release later.
- 410 path remains coded and tested.

Order riskiest-first (mirrors `PRD_V2.md` §15):

1. **Phase 0 safety net:** versioned JSON export schema v1 + manifest +
   checksum; backup/restore CLI; restore drill in CI (backup → wipe →
   restore zero-diff on scratch DB). Stub: scheduler/retention policies.
2. **Phase 1 tenancy:** `instances` + `memberships` + `instance_id` rollout
   with Site 5 backfill (riskiest migration — expand-and-contract, rehearsed
   on a prod-schema copy); JWT `instance_id` claim; cross-instance negative
   tests; RLS policies as failsafe. Defer: custom roles (string column ready).
3. **Phase 2 lifecycle:** enum surgery (Postgres `ADD VALUE` outside txn) +
   §5.3 data map; `phase`/`is_ignored` columns; transition-matrix enforcement
   + tests; context-builder exclusion. Stub: nothing — all specified.
4. **Phase 3 providers:** LiteLLM proxy + Ollama backend parity; virtual keys;
   tagging; DLP; budgets/cutoffs + dashboards; streaming usage; tenant-scoped
   cache. Defer: pricing-table auto-sync (static tables first).
5. **Phase 4 chat:** sessions/turns + versioned iterate + rollback; budgets
   charged to instance ledger. Defer: prompt-cache warming.
6. **Phase 5 social:** OAuth configs + PKCE/state + JIT + linking ceremony;
   instance picker/switcher; tenant-tagged auth telemetry.
7. **Phase 6 backup GA:** scheduled site backups to the Docker volume,
   per-instance JSON self-service, timed RTO drill.
8. **Phase 7 Flutter:** Riverpod + repository pattern, tokens, ApiClient,
   screens per §3, goldens on locked-OS Linux CI (`dart format`,
   `flutter analyze`, coverage gate; goldens in git-lfs if large). Old routes
   410. Defer: push, offline cache.
9. **Phase 8 billing/hardening:** entitlement framework once candidates
   confirm; full Guardrail re-audit (bandit/safety/SAST), coverage toward 80%.

What to stub or defer (explicit): Start/End/Free enforcement, payment
provider, Developer/Deployment/BA matrix, push/offline, cache warming,
pricing auto-sync.

---

## 6e. Build runbook derivation (2026-11-01)

- A build is only written and marked Built when a runbook (supervised
  `run_argv`) can be derived; otherwise the confirm run fails with a plain
  message and nothing is written. "Built" therefore always means runnable.
- `_extract_runtime_info` derives the start command from, in order: a
  Dockerfile `CMD`, a `package.json` `start` script, then inference from the
  manifest's own entry file (`app.py`, `main.py`, `server.py`, `run.py`, or the
  same under `src/`, `backend/`, `app/`, `api/`). Flask and FastAPI are bound
  to `0.0.0.0` on 5000/8000 so the URL works from other machines; a missing
  `requirements.txt` is called out in the run notes.
- `_derive_runbook` builds `run_argv` for `python …`, bare `uvicorn`/
  `gunicorn`/`hypercorn`/`daphne`, `flask run`, and `npm`/`npx`/`yarn`/`pnpm`/
  `node` (with `npm install` as the setup step). Anything else stays
  underivable and is refused at confirm time.
- Builds target a repo named after the idea (`IDEA-1234`) when one exists,
  before falling back to the last-used/only repo; the run dialog warns when
  the selected repo belongs to a different idea.
- The pasteable `setup`/`run` strings build `.venv-local`, never `.venv`.
  `.venv` belongs to the supervised process inside its worker container, and
  a host-built venv (different Python) cannot be executed there — pasting the
  old commands used to break the next Start. Supervision keeps using
  `.venv` via `setup_argv`/`run_argv`.
- Scale tab: `/releases` returns a pseudo "No release yet" entry (`id: null`)
  for unassigned children, so release cards and "Move to…" menus iterate
  `realReleases()` (id-bearing only). The unassigned bucket renders once, in
  its own block.
- Tests: `tests/integration/test_build.py` (`TestBuildRuntimeInfo`,
  `TestDeriveRunbook`, `TestBuildTargetResolution`, `TestBuildTask`);
  `tests/ui/test_scale_e2e.py` guards the single listing.

## 6f. AI selection controls (2026-11-02)

- Every surface that picks a model renders the same control pair:
  `templates/partials/ai_controls.html` (markup) + `static/js/ai_controls.js`
  (behaviour). Surfaces: Admin → AI Settings stage defaults (the reference),
  the run dialog, the per-release override on a SCALE idea, and the prompt
  editor.
- Model fields are `<select>` lists of the provider's catalogue with a
  "Custom model…" escape hatch that reveals a text input. A saved model that
  is no longer in the catalogue is shown through that same input rather than
  reading as "inherit". `AIControls.fetchModels()` is the single catalogue
  call and `selectValue()`/`isCustom()` the single rule for what a saved id
  means.
- Skills and Guidelines are multiselect dropdowns (button with a count that
  expands an inline checkbox list). The release override stores arrays end to
  end: no comma splitting, so names containing commas survive.
- Tests: `tests/ui/test_ai_controls.py` (release override, run dialog, Admin →
  AI Settings) plus the `/admin/ai` smoke page.

## 6g. Build → Test tab (2026-11-03)

- A written BUILD_CODE seeds `idea_tests` rows (`source="build"`). The UI
  check comes first: every runnable build gets an e2e check naming the URL
  and what should be visible, because that is the step reviewers skip.
- Sources for the checklist: the model's `tests` list in the manifest (the
  prompt requires 3-8 checks, at least one e2e UI check), then deterministic
  coverage inferred from the files (Flask/FastAPI/Express routes, dependency
  installs, container build, generated test suite).
- `app/services/build_tests.py` owns derivation and seeding. Seeding is
  idempotent by name within `source="build"`: status/coverage/last-run are
  preserved on re-build, stale generated checks are pruned, manual rows are
  never touched. The build write report records the counts.
- The table shipped in v0.74.0 without a migration; Postgres answered every
  `/tests` request with 500 until the `ii0b1c2d3e4f` migration created it.
  New model columns need a migration even though SQLite `create_all()` hides
  the gap.
- Backfill: `scripts/backfill_build_tests.py [--dry-run] [--idea REF]`.

## 6h. One-action release run (2026-11-04, implemented 2026-11-04)

A release card on the Scale tab can run every child through
PRD → Design → Build → Test in one action. The step-by-step phase buttons
remain for manual control.

- **State** lives on `releases` (`pipeline_status`, `pipeline_phase`,
  `pipeline_state` JSON, timestamps, error). The JSON tracks each child per
  phase (`pending`, `running`, `preview_ready`, `writing`, `done`, `skipped`,
  `failed`) plus run ids and a short report.
- **Drive**: a short Celery tick (`app.tasks.release_tasks.release_pipeline_tick`,
  default queue) advances one step and schedules the next tick. Each tick
  polls the run it started; no long-lived task holds the release.
- **Status moves** walk SPARK → SCOPE → MAP → SHIP one legal step at a time
  and record `IdeaStatusHistory` against the user who started the run.
- **Docs** are generated only when the child has no current PRD/Design.
- **Builds** are sequential: preview (LLM) → confirm write (deterministic),
  one child at a time. Each preview sees the repo snapshot
  (`existing_repo_snapshot`, capped at 30k chars) so later fixes extend
  earlier ones. Children with a current written build for the release repo
  are skipped. Every build goes through one resolver
  (`app.services.build_targets`): the release's explicit repo, a repo
  named after the release, the child's reference code, the parent idea's
  reference code, the last repo used, the instance's only repo, then a
  lazily created repo named after the root idea. The release preflights
  every child's repo before spending PRD/Design calls.
- **Tests**: the write seeds the checklist as usual; the Test phase is a
  safety net for older builds and never runs checks automatically.
- **Failure policy**: continue and report. The release is marked `done`
  (children at SHIP, notes regenerated) only when nothing failed; otherwise
  it stays `in_progress` with `pipeline_status=failed` and reasons per child.
  Starting again keeps finished work and retries the rest.
- **Stop** sets `stopping`; the next tick stops without starting a new step.
  Work already written is kept.
- **Assignment**: `PATCH /releases/<id>/assign` already took a list; the UI
  now exposes multi-select so several children can join a release at once.

## 7. Open questions

1. RLS performance on hot tables (ideas/comments) — measure under seed load;
   keep policies simple; index `(instance_id, ...)` leftmost.
2. LiteLLM deployment shape (sidecar vs shared service) and virtual-key
   issuance flow in Phase 3.
3. Golden-file storage (git-lfs threshold) once Flutter lands.
4. Backup volume sizing/rotation (no retention policy required — monitor
   only).
5. Deferred items from `PRD_V2.md` §14 (enforcement semantics, payments,
   role matrix, push/offline) — tracked, not blocking.

---

*Traceability: §1←PRD_V2 §3§7 + MultiTenantAIConnectivity; §2←PRD_V2 §5;
§3←PRD_V2 §9 + Flutter/UITesting/ProjectOverview guides; §4←PRD_V2 §3§4§6 +
SocialLogin/Database guides; §5←PRD_V2 §4§7§8§11 + SocialLogin guide;
§6←PRD_V2 §15 + Upgrades guide; §7←PRD_V2 §14.*
