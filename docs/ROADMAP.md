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

Each record: the call, why it won, what was rejected, and a concrete
recommendation including the trigger that would justify revisiting.

### C1. Single database + `instance_id` (not schema- or DB-per-tenant)
Why: one Postgres to operate, one migration chain, cross-instance admin
queries stay trivial, and the team size does not justify sharding ops.
Per-instance restore is proven at the row level (zero-diff drill).
Rejected: schema-per-tenant (migration fan-out, RLS still needed) and
DB-per-tenant (backup/restore matrix, connection-pool sprawl).
Recommendation: **keep**. Revisit only if a tenant demands physical data
residency/isolation (regulated client) or single-tenant restore time
exceeds the 15-minute RTO — then migrate that tenant out, not the fleet.

### C2. Copy-on-create from Instance 1, never keys, never content
Why: new tenants boot with proven prompts/settings but zero data
leakage and zero credential sprawl; AI keys are the highest-value
secret and must be entered per instance by its own admin.
Rejected: live inheritance (a template edit could silently change
running tenants) and copying keys (blast radius across tenants).
Recommendation: **keep**. Revisit only to add an explicit, audited
"bulk-update children from template" operator tool — never silent sync.

### C3. Shared users + membership join (not per-instance user rows)
Why: one login identity across instances matches the social-login
reality (one Google account, many workspaces); email stays globally
unique; `slack_user_id`-style columns extend the same pattern.
Rejected: per-instance user rows (email collisions, password sprawl,
linking nightmares).
Recommendation: **keep**. If a tenant ever requires SSO-restricted
membership (only @client.com addresses), add it as a membership rule,
not a new identity model.

### C4. JWT `instance_id` claim optional during transition
Why: hard enforcement on day one would have broken every existing
client, the Jinja UI, and 200+ tests simultaneously. Optional claims
let scoping roll out route by route with back-compat.
Rejected: big-bang enforcement and dual-token schemes.
Recommendation: **finish the job** — require the claim (except
well-known public endpoints) once the Flutter client is the only
client (Phase 11/13). Until then, treat unscoped traffic as legacy in
reviews.

### C5. Server-side scoping enforces; RLS is a failsafe
Why: SQLite has no RLS, so the app layer must be correct anyway; RLS
policies then catch the bug classes app code cannot (stray queries,
ad-hoc psql). Permissive-when-unset keeps CLI/workers/migrations
working.
Rejected: RLS-only (SQLite path uncovered, ORM bypass risks) and no
RLS (one missed filter leaks a whole tenant).
Recommendation: **keep**. Measure RLS overhead under seed load before
declaring victory (open item B.17); if measurable, keep policies but
simplify them — never remove the layer.

### C6. Archive is terminal; skip-level moves allowed; no gates
Why: the business moves ideas non-linearly (Spark straight to Map
happens); gates would encode process guesses that rot. The matrix
prevents nonsense (nothing leaves Archive) while the UI confirm +
history row keeps humans honest.
Rejected: enforced linear pipeline and prerequisite gates.
Recommendation: **keep**. If audit ever shows chaotic jumps causing
harm, add per-transition *reasons* (free text), not gates.

### C7. LiteLLM library first, sidecar for virtual keys (not bespoke, not direct SDKs)
Why: one routing interface, OpenAI-compatible everywhere, offline
pricing tables, zero per-provider glue code. The sidecar adds physical
key isolation exactly where it matters (hosted keys) without
re-architecting the call path.
Rejected: bespoke per-provider clients (combinatorial maintenance) and
raw provider SDKs scattered through tasks.
Recommendation: **keep**. Revisit only if LiteLLM becomes a liability
(security advisory, pricing-table rot breaking budgets) — the
interface boundary makes swapping it a contained job.

### C8. Riverpod + repository pattern; Flutter owns UI, Flask stays layered
Why: dumb widgets + testable controllers; one ApiClient kills the
scattered raw-http class of bugs; restructuring Flask to feature
folders would churn a working backend for aesthetics.
Rejected: Bloc (heavier ceremony than the app needs), GetX (service
locator anti-patterns), restructuring Flask.
Recommendation: **keep**. Adopt freezed codegen once models stabilise
(open item B.11) — hand-written `fromJson` is tech debt with a number.

### C9. Backup before every upgrade, proven by restore; no retention policy
Why: the only backup that counts is a restored one; the zero-diff
drill caught real bugs (listener double-counts, `onupdate` drift)
before production ever depended on them. No auto-pruning because
silent deletion is how data loss happens.
Rejected: backup-without-drill and time-based auto-pruning.
Recommendation: **keep**, and assign a human to watch disk (the one
weakness of no-retention). Revisit retention only with an explicit
signed-off policy + tested prune job — never a cron one-liner.

### C10. Legacy Jinja stays live behind `LEGACY_WEB_ENABLED`
Why: killing the only working UI before Flutter proves itself in
users' hands would be self-harm. The 410 path is coded, tested, and
one env var away.
Rejected: hard cutover with the Flutter release.
Recommendation: **flip to False after two weeks of Flutter production
use with zero P1s**, then delete the templates a release later. Do not
let both UIs live indefinitely — dual maintenance is where parity
goes to die.

### C11. Entitlements manual (site admin) until payments exist
Why: building billing against an unconfirmed provider/pricing would
produce the wrong abstraction. The framework (keys, baselines, gates,
402s) is real and already enforcing `hosted_ai`; wiring a provider
later is a CRUD-plus-webhook job, not a redesign.
Rejected: building Stripe/Paddle integration on guesses.
Recommendation: **keep**. When choosing a provider, require: webhook
idempotency story, test-mode end-to-end (grant → gate → revoke), and
proration semantics — then map plans onto entitlement keys 1:1.

### C12. No data loss, ever; expand-and-contract; roll forward in production
Why: soft states instead of deletes, audit trails on status/content/
flag/rollback changes, reversible migrations with down scripts for CI,
and production recovery that rolls forward (revert containers, old
code ignores new columns) — because true DB rollback destroys the
writes that happened after deploy.
Rejected: hard deletes, `db.create_all()` in prod, down-migrations as
a production strategy.
Recommendation: **keep permanently**. Any proposal involving
`DROP`, data backfill without a backup drill, or `:latest` tags is
rejected by default.

### C13. Budgets refuse-fast; static pricing tables
Why: an unbounded LLM bill is the scariest failure mode in the
system. Refuse is the only cutoff with honest semantics today; static
tables are offline, deterministic, and auditable per call.
Rejected: queue/degrade cutoffs (degrade silently changes answer
quality — a correctness issue disguised as a billing feature) and
live pricing sync (network dependency inside the money path).
Recommendation: **keep refuse as the default forever**. Add queue
only as an explicit per-instance choice with visible UX ("queued for
budget release"), never silently. Revisit pricing sync if a provider
changes prices mid-contract and finance complains — with a cached
table + TTL, never a live call.

### C14. Social linking: verified email + explicit confirm; JIT least-privilege
Why: silent account merging is a takeover vector; unverified emails
are attacker-controlled. The 409 + confirm-token ceremony makes the
user prove intent, and JIT users land with the fewest privileges.
Rejected: auto-merge on email match and admin-approval queues (toil
with no security gain over explicit user confirm).
Recommendation: **keep**. If phishing-resistant auth becomes a
requirement, add WebAuthn as a second factor on the shared identity —
do not rebuild the linking ceremony.

### C15. Monorepo: Flutter client lives in `flutter/`
Why: one checkout builds the whole system; version parity between
`VERSION` and `pubspec.yaml` is checkable in CI; backend contract
changes and client adaptations land in one PR.
Rejected: separate repo (version skew, cross-repo PRs for every API
change).
Recommendation: **keep** until the mobile release cadence diverges
from the backend (e.g. app-store review trains) — then split with a
versioned API compatibility matrix, not before.
