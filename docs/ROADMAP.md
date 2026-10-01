# Brainstormer — Roadmap: completed vs outstanding

**Single source of truth for build status. Update on every build.**
**Version:** 0.42.0 · **Date:** 2026-10-01 · **Branch:** `feat/phase-0-backup` (unpushed)
**Health:** backend 304 passed / 80% coverage · Flutter 18 passed, analyze clean ·
bandit 0 high/medium · safety 0 vulns · prod healthy on Site 5 tenancy.

Spec baselines: `PRD_V2.md` (V2 scope), `docs/Design.md` (system design),
`Guardrail.md` (security rules). Guide statuses: `Guides/README.md`.

---

## A. Completed

### A.1 V1 baseline (pre-V2, `release/v0.26.9`)
Flask + Jinja/Alpine app: scheduled Ollama generation, votes, threaded
comments, 13 secondary actions (PRD/Design versioned docs), 7-state
lifecycle, Slack two-way sync, JWT + rotating refresh, admin dashboards.
Includes the `TODOS.md` items: manual idea creation (`can_create_ideas`),
per-user settings toggle, migration-head merge (chain is single-head —
the TODOS "cleanup" item is done), per-release VERSION/CHANGELOG entries.

### A.2 V2 planning docs (v0.27.0–v0.28.0)
- `PRD_V2.md`: 8-state pipeline, tenancy, providers, Flutter, roles,
  billing TBD, social, backup/restore, phased plan Phases 0–8.
- `docs/Design.md`: architecture, mermaid lifecycle, screens, data
  model, API contracts, build notes (LiteLLM / Riverpod / RLS
  defence-in-depth / Docker volume decisions locked).
- Guides review applied; SocialLogin + MultiTenantAI adopted-for-V2.

### A.3 Phase 0 — Safety net (v0.29.0)
Versioned JSON bundles (schema v1, manifest, SHA-256),
`backup-site / backup-instance / restore` CLI, zero-diff proof,
`backup-drill` CI.

### A.4 Phase 1 — Multi-tenancy (v0.30.0)
Instances + memberships (string roles, NULL = site-wide), `instance_id`
on all tenant tables, JWT claim (legacy tokens unscoped), membership
decorators, `/api/v1/instances`, copy-on-create (config only),
`init-tenancy / promote-site-admin / create-instance`, reserved 2–19,
Postgres RLS failsafe. **Live on production** (see A.11).

### A.5 Phase 2 — V2 lifecycle (v0.31.0)
8-state enum + transition matrix (`ILLEGAL_TRANSITION`), per-phase
comment threads, admin Ignore flag (AI-excluded, audited), stage-gated
actions, Jinja UI rewritten, transactional-safe enum migration with V1
map. Fixed latent `Comment.user` crash.

### A.6 Phase 3 — Providers (v0.32.0)
LiteLLM routing with Ollama parity, encrypted per-instance keys,
allowlists, rolling budgets (70% alert / 100% refuse-fast), spend
ledger, hosted embeddings override, spend dashboard, Guardrail opt-in.

### A.7 Phase 4 — Chat-to-AI (v0.33.0)
Prose turns all phases (JSON-mode escape hatch), versioned iterate +
rollback (audited), 3/min/user limit, per-instance switch, admin-only
iterate/override, hash-only logs.

### A.8 Phase 5 — Social login (v0.34.0)
Google/Apple/Microsoft OIDC (stateless PKCE, JWKS verify), verified-
email linking ceremony (409, never silent), JIT least-privilege,
immutable subject links, per-instance OAuth creds, member management
with last-admin/self guards.

### A.9 Phase 6 — Backup GA (v0.35.0)
Real per-instance export/restore (others untouched), `restore-instance`
CLI, self-service export download, daily scheduled backups with
write-verify, site-restore scope guard, RTO runbook.

### A.10 Phase 7 — Flutter (v0.36.0)
Feature-first Riverpod app (auth + picker, ideas + detail + chat,
prompts with provider routing, admin, settings), single ApiClient with
refresh, secure storage, tokens/dark mode, version footer, deep-link
parity, 10 tests + golden, release web build proven. `LEGACY_WEB_ENABLED`
flag (default on) with 410 retirement path.

### A.11 Production cutover (no version bump)
pg_dump safety net → 9 migrations → 400 ideas mapped
(363 DROP, 25 SPARK, 10 SCOPE, 1 MAP, 1 SHIP) → 2101 rows to Site 5,
7 memberships, admin@example.com site admin → all containers restarted,
`/api/health` healthy.

### A.12 Restore drill on prod data (no version bump)
2623 rows restored to scratch in 11.5s, **zero diff across 23 tables**,
RTO recorded in `docs/install-config.md`. Also surfaced: fresh
`flask db upgrade` from zero fails on a pre-existing enum migration
(documented; production path unaffected).

### A.13 Selected follow-ups (v0.38.0–v0.42.0)
- Per-stage AI config: `stage_ai_configs` + API, resolution order
  explicit > stage > prompt > defaults (generation, actions, chat).
- Proxy virtual keys: LiteLLM sidecar in compose, encrypted virtual
  keys, `provision-proxy-key` CLI, app-side budget/entitlement/spend
  enforcement preserved.
- Offline + local notifications: TTL cache with stale fallback,
  connectivity banner, digests (FCM pending credentials, documented).
- Staging smoke: `flutter/integration_test/app_test.dart`, verified
  headless (device/Chrome required on CI).
- Coverage 35% → **80%**; fixed real `cosine_similarity` crash.
- User guide rewritten for V2.

---

## B. Outstanding (sorted by suggested phase)

### Phase 9 — Users, roles, enforcement
1. **Iterate for normal users** (matrix grants edit-own; content edit
   and chat-iterate are admin-only today).
2. **Developer/Deployment/BA role matrix** (schema ready: string roles,
   no migration needed).
3. **Start/End/Free enforcement semantics** (block vs read-only vs
   scheduler pause). Dates recorded, unenforced.

### Phase 10 — AI platform hardening
4. **DLP/PII masking layer** before hosted providers.
5. **Proxy DB persistence** beyond the documented setup step.
6. **Embeddings via proxy** (direct-library path only today).
7. **Pricing auto-sync** (static fallback tables today).
8. **Queue/degrade budget cutoffs** (refuse only today).

### Phase 11 — Flutter completion
9. **Remote push (FCM)**: needs Firebase credentials + backend
   device-token endpoint (local notifications ship meanwhile).
10. **`integration_test` on devices** in CI (needs Chrome/device farm).
11. **Freezed codegen** for models (hand-written today).
12. **Push/offline hardening** beyond the v0.40.0 baseline.

### Phase 12 — Billing
13. **Payment provider + pricing** (entitlements are site-admin managed
    until then; framework + Free baselines already enforce `hosted_ai`).

### Phase 13 — Cutover and ops
14. **`LEGACY_WEB_ENABLED=False` flip** once Flutter ships to users.
15. **Sites 2–19 creation** + Instance 1 template seeding review.
16. **Branch PR and merge** (`feat/phase-0-backup`, 20+ commits, unpushed).
17. **RLS performance measurement** under seed load (Design open Q).
18. **Golden git-lfs threshold** decision as goldens grow.
19. **Backup volume sizing review** (no retention by policy; monitor).
20. **Fresh-DB migrate fix** for the historical enum migration
    (workaround documented; production unaffected).

### Housekeeping (no phase; do anytime)
21. Uncommitted tree dirt: own/stash-or-commit AGENTS.md, PRD.md,
    docs/erd.md edits; confirm `guidelines/.gitkeep` deletion;
    add/ignore TODOS.md, APPLICATION_DOCUMENTATION.md, status image.
22. `TODOS.md` itself is stale (V1-era session notes) — archive or refresh.
23. Coverage 80% → 85%+ on the next feature build (don't let it slip).

---

## C. Standing decisions (do not relitigate without cause)

Single DB + `instance_id` · copy-on-create (never keys) · shared users
+ memberships · JWT claim optional until Phase 5 switcher · server-side
scoping enforces, RLS is failsafe · Archive terminal · skip-level moves
allowed · LiteLLM (in-process first, sidecar for virtual keys) ·
Riverpod + repository pattern · no-Jinja restructure · backups before
every upgrade with proven restore · no data loss, ever.
