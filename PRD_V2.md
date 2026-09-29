# PRD V2 — Brainstormer Multi-Tenant, Multi-Provider, Flutter Replatform

**Status:** Approved for planning (decisions locked 2026-09-29).
**Supersedes:** `PRD.md` (V1, single-tenant Flask + Jinja + Ollama-only).
**Current baseline:** v0.27.0, documented in `docs/APPLICATION_DOCUMENTATION.md`.
**Related:** `docs/architecture.md`, `docs/erd.md`, `Guardrail.md`, `AGENTS.md`.
**Design:** `docs/Design.md` (whole-V2 system design implementing this PRD).
**Guides baseline:** `Guides/` catalogue — `Guide_SocialLogin.md` and
`Guide_MultiTenantAIConnectivity.md` are Adopted-for-V2 (see `Guides/README.md`).
On any conflict, `AGENTS.md`/`Guardrail.md` win.

> Terminology (locked): **Site** = the whole system across all tenants.
> **Instance** = one tenant. **Multi-tenant** = the architecture.

---

## 1. Context and goals

V1 is a single-tenant, web-only (Flask + Jinja2/Alpine), Ollama-only idea pipeline:
scheduled prompts → generation → votes/comments → 13 secondary actions → 7-state
lifecycle (`NEW, CONSIDERATION, HOLD, DESIGN, BUILD, COMPLETE, DISCARDED`).

V2 delivers:

1. Clearer, mature pipeline with distinct **Spark → Scope → Map → Ship → Scale**
   phases plus **Drop / Freeze / Archive** off-track states.
2. AI providers beyond Ollama: **OpenAI, Anthropic, Gemini, local** (Ollama stays).
3. **Flutter** frontend replacing all Jinja/Alpine (complete replatform, web +
   mobile from one codebase).
4. **Multi-tenant** architecture (single DB + `instance_id`).
5. Expanded **roles** (Site Admin, Instance Admin, User now; Developer,
   Deployment, BA later).
6. **Paid capabilities** (TBD, candidates in §10).
7. **Social login** (Google, Apple, Microsoft).
8. **Backup/export/restore**: full backup for Site Admin, per-instance JSON for
   Instance Admins.

Out of scope for V2: payment processing provider selection, enforcement
semantics of Start/End/Free dates, retention policies (explicitly not required).

---

## 2. Golden rules (non-negotiable)

1. **No update causes data loss.** Every schema/data migration is
   reversible-tested on a copy, runs only after a verified backup (§11), and
   preserves all Ideas, Votes, Comments, Runs, docs and history.
2. **Mandatory backup before each upgrade, with ability to restore (rollback).**
   Upgrade runbooks must include backup → migrate → verify → rollback steps.
3. **Build number always available.** `VERSION` file remains the source of
   truth; surfaced in the Flutter footer on every screen, in `GET /api/health`
   (and `/api/ready`), and in admin settings. Fixes prior typo ("availabel").
4. **Instance defaults come from Instance 1 (copy-on-create, not live
   inheritance).** New instances copy config from Instance 1 at creation time;
   later edits to Instance 1 do not propagate.

---

## 3. Multi-tenancy model

- **Strategy:** single database, `instance_id` column on all tenant-scoped
  tables (Ideas, PromptConfigs, PromptRuns, Comments, Votes, IdeaEdits,
  SecondaryActionResults, IdeaStatusHistory, SlackPosts, SystemSettings or its
  per-instance successor, embeddings).
- **Instance 1** is the template instance. New instances copy from it.
- **Copy-on-create inventory (locked):** Prompts, SystemSettings
  (platform/location), prompt templates, skills, guidelines. **Excluded:**
  Users, Ideas, Votes, Comments, Runs. **AI keys are never copied** — each
  instance starts with empty provider keys that the Instance Admin must enter.
- **Reserved IDs:** Instances 2–19 are reserved for future testing and to
  present the impression of an established user base. They are **not created
  yet** (except Site 5 below); IDs must not be reused for other purposes.
- **Site 5** receives **all existing production data**, including Ideas,
  Prompts, Comments, Votes, Runs, docs, history **and Users**. A new **Site
  Admin** user is created separately (not migrated).
- **Instance attributes** (Name, Start Date, End Date, Free) are **placeholders
  only** in V2. Stored but not enforced; enforcement semantics are a later
  decision (see §14).
- **Request scoping:** every API call resolves the instance from the
  authenticated membership (JWT `instance_id` claim + membership check);
  cross-instance access returns 403/404 without leaking existence.
  Similarity/dedup, scheduler due-checks, prompt health, activity stats and
  Slack mappings are all **within-instance only**.

---

## 4. Users, roles and memberships

- **Identity model (locked): shared `User` table + membership join.**
  One login identity can belong to many instances with a per-instance role.
  Social IDs (Google, Apple, Microsoft) attach to the shared identity
  (same pattern as the existing `slack_user_id` column, extended per
  provider). Email is globally unique on the shared table.
- **V2 roles:** `SITE_ADMIN` (whole site: create instances, full backups,
  manage memberships), `INSTANCE_ADMIN` (one instance: prompts, AI config,
  status changes, secondary actions, users within that instance), `USER`.
  Current V1 `ADMIN` maps to `INSTANCE_ADMIN` for Site 5 members; the new
  Site Admin is the only `SITE_ADMIN`.
- **Future roles** (Developer, Deployment, BA, …) are deferred — schema must
  allow new enum values without migration pain (string-backed role on the
  membership, not a Postgres enum append).
- **Social login:** Google, Apple, Microsoft, per `Guides/Guide_SocialLogin.md`
  (Adopted-for-V2). Schema: `tenants` registry; `tenant_oauth_configs`
  (`tenant_id`, `provider_name`, `encrypted_secret`, unique
  `(tenant_id, provider_name)`) for per-tenant OAuth credentials (AES-256-GCM
  at rest, keys via secrets manager); `users.global_subject_id` (immutable
  provider `sub` claim — never key identity on email alone; nullable for
  existing password users, backfilled on first link); `tenant_users`
  (`tenant_id`, `user_id`, unique pair) membership join; per-instance roles
  (string-backed role on the membership for V2, with `tenant_roles` /
  `tenant_user_roles` tables as the later custom-RBAC extension point).
  Tenant context is resolved **before** the auth flow (instance picker on the
  central login portal; `state` + PKCE carry the tenant through the redirect).
  Linking requires verified-email match **plus explicit user confirmation** —
  never silent merge, never privilege elevation on first social login. JIT
  onboarding defaults to the least-privileged role; elevation needs
  Instance Admin action. After success the server mints the standard
  short-lived JWT + rotating DB refresh pair — provider tokens never reach the
  client. Password accounts keep working; remember-me (30 d vs 7 d) and refresh
  rotation unchanged. Auth events are logged server-side tagged with
  `tenant_id`; never log tokens, codes, or PII. Migrating from V1: add
  `global_subject_id` nullable, introduce tenants/memberships without altering
  existing password-login behaviour or JWT mechanics.
- **Guardrail impact:** new OAuth endpoints get the login rate limit
  (5/min/IP), generic errors, bcrypt untouched, no PII in logs; provider
  client secrets join the secrets table (env-sourced, never committed).

---

## 5. Lifecycle (V2 status pipeline)

### 5.1 States

| State | Meaning |
|-------|---------|
| **Spark** | Ideation: raw ideas, feedback, market research. Entry point for all new ideas. |
| **Scope** | Product refinement: requirements/PRD work happens here. |
| **Map** | Design: blueprints, layouts, system logic. |
| **Ship** | Build & deploy: code, test, launch. |
| **Scale** | Live iteration: bugs + features loop until retired. |
| **Drop** | Discarded: explored, decided not to proceed. Read-only except admin restore. |
| **Freeze** | On hold: good idea, wrong time. Votes/comments stay open. |
| **Archive** | Closed/retired. **Terminal** — no exits. Read-only. |

The old status diagram image was missing from the draft; the table above plus
§5.2 is normative until a new diagram is attached.

### 5.2 Allowed transitions (admin-only, UI confirms every change, no gates)

| From | To |
|------|----|
| Spark | Scope, Map, Drop, Freeze |
| Scope | Map, Ship, Drop, Freeze |
| Map | Scope, Ship, Drop, Freeze, Archive |
| Ship | Scope, Map, **Scale** (normal live path), Drop, Freeze, Archive |
| Scale | Scope, Map, Ship, Drop, Freeze, Archive |
| Drop | Scope, Map, Ship, Scale, Freeze, Archive |
| Freeze | Scope, Map, Ship, Scale, Drop, Archive |
| Archive | — (terminal) |

Notes:

- Skip-level moves (e.g. Spark→Map, Scope→Ship) are intentional — no gates.
- Only Admin users (Instance Admin, Site Admin acting within the instance) can
  change state. The UI **always prompts for confirmation** on change and writes
  an `IdeaStatusHistory` row.
- Votes/comments/secondary-action history survive every transition (Drop and
  Archive are soft states, never hard deletes).

### 5.3 V1 → V2 migration map (locked)

| V1 | V2 | Rule |
|----|----|------|
| NEW | Spark | All new ideas are created as Spark. |
| CONSIDERATION | Scope | Consideration is dropped as a concept; stragglers map to Scope. |
| HOLD | Freeze | Direct rename. |
| DESIGN without a PRD | Scope | |
| DESIGN with a current PRD | Map | "If Idea has a PRD, set State to Map." |
| BUILD | Ship | |
| COMPLETE | Archive | Terminal. |
| DISCARDED | Drop | |

`IdeaStatusHistory` is backfilled with a migration row per idea. Unknown or
ambiguous values default to Scope (per prior agreement), never to Archive.

### 5.4 Capability matrix (locked deltas from draft)

| Stage | Normal users | Instance Admins (plus user caps) |
|-------|--------------|----------------------------------|
| Spark | See/add/edit-own/vote/comment, Chat-to-AI | All secondary actions **except PRD**, configure AI actions, change state, Ignore-flag comments |
| Scope | See/comment, Chat-to-AI | All secondary actions **including PRD** (create/edit), change state, Ignore-flag |
| Map | See/comment, Chat-to-AI | Secondary actions, **Design docs** create/edit, configure AI actions, change state, Ignore-flag |
| Ship | (none beyond viewing own history) | Initiate Build, change state |
| Scale | See/comment/vote, add Bugs + Features, Chat-to-AI | Change state |
| Drop / Freeze / Archive | See (Drop/Archive read-only; Freeze vote/comment) | Restore via state change |

---

## 6. Comments: per-phase threads + Ignore flag

- **One `Idea` row flows through all phases** (no separate Scope/Map objects).
- **Comments gain an indexed `phase` column** (the V2 state the comment was
  made in). Existing `parent_id` threading, `scope` (idea vs doc), soft-delete
  and doc threads are unchanged. `phase` is an index for filtering, not a
  replacement key — the earlier "instanceID + IdeaNumber + Phase as key"
  sketch is implemented as `(instance_id, idea_id, phase)` composite index.
  The composite (not single-column) form is deliberate: the phase filter is
  always evaluated within one idea of one instance, so the leftmost-column
  query plan applies — the required-by-filter exception to the
  no-speculative-indexes rule (`Guides/Guide_Database.md` §4); all other new
  indexes stay single-column on FKs/unique columns.
- **Migration:** all existing comments backfill `phase = Scope`.
- **UI:** phase filter on the idea thread; default shows all phases with phase
  chips.
- **Ignore flag (locked):** nullable boolean `is_ignored` (default false) on
  comments, set via admin tickbox. Visible to admins only; hidden from normal
  users. `build_idea_context()` **excludes ignored comments** from every
  secondary action and from Chat-to-AI context. Toggling is audit-logged.

---

## 7. AI providers and secondary actions

- **Providers (locked):** OpenAI, Anthropic, Gemini, **local** (Ollama stays
  supported). Each instance stores its own keys/endpoints, managed by its
  Instance Admins in a per-instance settings screen. Keys are Fernet-encrypted
  at rest (same pattern as prompt bodies), never logged, never returned to
  non-admins, never copied from Instance 1.
- **Abstraction (per `Guides/Guide_MultiTenantAIConnectivity.md`,
  Adopted-for-V2):** a central LLM proxy interface fronts all providers, with
  the existing `OllamaClient` kept as one first-class provider implementation
  behind it (local Ollama remains a route, not a special case) — LiteLLM or
  equivalent is the default proxy choice, decided finally in Phase 3. The proxy
  standardises request/response shapes so JSON-mode + Pydantic
  schema-validation guarantees hold on every route, including proxy-routed
  ones.
- **Tenant isolation:** per-instance **virtual keys** issued at the proxy —
  the app holds only the virtual key; downstream provider credentials are
  mapped inside the proxy and never sit in application memory. Per-prompt
  config selects provider + model; allowlist is per-instance.
- **Request tagging:** every outbound call carries `instance_id`, `user_id`,
  project and environment tags, persisted by the proxy for per-tenant querying
  and billing. Local-model calls skip spend maths but keep tagging so
  telemetry stays uniform.
- **DLP:** a governance layer at the proxy masks PII before prompts reach
  hosted providers (enterprise compliance; cross-tenant privacy).
- **Cost logging and budgets:** the proxy records exact per-request token
  usage × real-time model pricing. Each tenant virtual key gets a token/dollar
  budget with alerts at 70% and a hard cutoff at 100% — cutoff behaviour is
  explicit per instance (refuse with a clear error, queue for admin release,
  or degrade to a local model; never fail silently or partially bill).
  Instance-level cost dashboards (prompt/completion tokens, daily spend, own
  instance only) ship with budgets.
- **Streaming and caching:** streaming responses (Chat-to-AI, `test-stream`
  SSE) pass `stream_options: {include_usage: true}` (or use proxy async
  callbacks) so usage is captured from the final chunk. Prompt caching is
  tenant-scoped (keyed on sanitised prompt + params); never serve one
  tenant's cache to another; exclude PII-bearing prompts from shared caches.
- **Secrets rule (non-negotiable):** provider and OAuth secrets are
  env/secrets-manager sourced and encrypted at rest (Fernet/AES-256-GCM),
  and are **never interpolated into prompts, never logged, and never appear
  in error bodies**. This extends the existing "log hash only" rule to all
  V2 key types.
- **Embeddings:** default stays `nomic-embed-text` for local; hosted embedding
  model per provider is configurable.
- **Privacy update:** the V1 Guardrail "no external calls / local-only" rule
  is relaxed **per instance**: instances with no hosted keys behave exactly as
  today (local-only); entering a hosted key explicitly opts that instance into
  egress to that provider only. No cross-instance key reuse.
- **Secondary-action matrix:** Spark (all except PRD), Scope (all incl. PRD),
  Map (Design docs). Temperature caps, token floors, confirmation flow (409
  `CONFIRMATION_REQUIRED`), versioned results, feasibility→idea score, and
  fuzzy question-drop behaviour carry over unchanged, with ignored comments
  excluded.
- **Per-stage AI config:** Spark, Scope, Map, Ship, Scale each get their own
  prompt settings, skills and guidelines (already stage-aware in V1 via the
  Design gate; generalised to all five stages).

---

## 8. Chat-to-AI (new)

- **Availability:** all phases (Spark, Scope, Map, Ship, Scale), on instances
  where the feature is enabled.
- **Behaviour:** signed-in users iterate the idea conversationally
  (clarifications, rewrites, counter-arguments). Each turn uses the idea
  context builder (respects Ignore flags and phase filter) plus recent chat
  history within a token budget.
- **Persistence:** every turn is logged (who/when/model/phase, prompt hash —
  never secrets); "iterate" actions that change the idea write a versioned
  update (IdeaEdit audit) with **rollback** to any prior version.
- **Controls:** per-instance enable/disable, per-user and per-instance rate
  limits (default: reuse the actions limit 3/min/user until tuned), model
  follows the instance's stage config unless overridden by an admin.

---

## 9. Flutter replatform (complete replacement)

- Flutter **replaces** all Jinja/Alpine pages (dashboard, prompts, admin,
  auth). No dual-maintenance: the Flask backend becomes API-only; the
  `index.html` orphan is deleted, not ported.
- **Contract:** keep the `{success, data|message}` envelope, JWT
  access+rotating-refresh auth (secure storage, not localStorage), 401 →
  refresh-or-login flow, admin probe pattern, and all deep links
  (`/ideas?status&prompt&model&idea`, activity `?run_status&model`,
  prompts `?edit=`).
- **Footer build number** (§2) ships in Flutter from day one.
- **Web + mobile** from one codebase; push notifications and offline cache are
  post-V2 stretch goals, not acceptance criteria.

---

## 10. Billing / premium (TBD)

- `Free` flag and Start/End dates are stored placeholders; **no enforcement in
  V2**.
- Premium candidates (unconfirmed): extra Guides (e.g. Security packs),
  hosted (3rd-party) AI access, deployment options. Each must become an
  entitlement with an explicit gate before build.

---

## 11. Backup, export and restore

- **Full detail, no retention policy required** (locked): backups contain
  everything needed to restore (rows, docs, versions, history, settings;
  secrets included in encrypted form with key-portability notes).
- **Site Admin:** full backup of **all instances** (site-wide bundle).
- **Instance Admin:** per-instance export **in JSON form**, restorable to the
  same or a fresh instance.
- **Pre-upgrade rule:** every upgrade takes a backup first and proves restore
  (rollback drill) before migrating production.
- Formats/CLI: site bundle (`.tar.gz` with per-instance JSON + manifest +
  checksum) and single-instance JSON; exact tooling chosen in Phase 6 but the
  JSON schema is versioned from the start.

---

## 12. Privacy release gate (per `Guides/Policy_Privacy.md`)

The privacy policy is a **template placeholder** — it must be tailored to the
actual deployment and legally reviewed before any release relies on it, and in
particular **before any hosted-AI-provider or social-login rollout**:

- **AI-processing disclosure (mandatory):** which provider is configured per
  instance (local Ollama vs hosted), what content is sent (prompts, ideas,
  comments, supporting material), provider-side retention, and any human
  review. The default local-Ollama posture (no external transmission) must be
  stated explicitly — it is a differentiator.
- **Third parties:** Slack workspaces and social login providers added per
  instance must be listed as service providers receiving data on the
  deployment's behalf.
- **Cross-border (NZ Privacy Act IPP 12):** local-only deployments state that
  no cross-border disclosure occurs; enabling hosted providers re-activates
  this section (comparable safeguards or model clauses).
- **Retention vs history:** the design retains history by default
  (soft-discarded ideas/comments, status-history and edit-audit trails). The
  adopted policy must define retention per category, explain what in-app
  "deletion" means (discard/soft-delete vs hard erase), and provide a genuine
  erasure path for access/privacy requests (20-working-day response).
- Privacy-officer contact details must be filled in; breach-notification
  duties (notify affected users + Privacy Commissioner where serious harm is
  likely) apply from day one.

---

## 13. Similarity, Slack, embeddings, observability

- **Similarity/dedup stays within-instance only** (thresholds .85 similar /
  .95 near-dup / .97 auto-discard unchanged, per-instance embed store).
- **Slack:** channel config, Block Kit posts, reaction votes and thread sync
  become per-instance (token per instance, `SlackPost` scoped by instance).
- **Health/ops:** `/api/health` + `/api/ready` gain per-instance and
  provider checks; Celery keeps the `ollama`-serial vs `default`-parallel
  split (renamed to `llm`-serial only if trivially safe — otherwise keep
  names). Structured logs stay content-free; per-provider latency/queue
  counters complete the partially-implemented Prometheus requirement.

---

## 14. Open items (explicitly deferred, not blockers)

1. Enforcement semantics for Start/End/Free (block vs read-only vs scheduler
   pause) and the Site Admin "which site to use" picker workflow.
2. Payment provider, pricing and entitlement gates.
3. Developer/Deployment/BA role permissions matrix.
4. Push/offline for Flutter; Slack multi-workspace UX polish.

---

## 15. Phased development plan

> Each phase ends with: backup taken, migrations reversible-tested, tests
> green (`pytest`, coverage gate ≥ 35%, aim 80%), docs + CHANGELOG updated,
> version bumped. Guardrail checklist (§13 of `Guardrail.md`) applies to every
> phase; the local-only egress exception (§7) is the only rule change, and it
> is per-instance opt-in.
>
> Migration discipline (per `Guides/Guide_Database.md` §3 and
> `Guides/Guide_Upgrades.md` §4–§5): **expand-and-contract** for any
> destructive or reshaping change on populated tables (additive nullable
> columns, new tables and single-column FK/unique indexes ship as one
> migration); destructive steps are isolated and need human sign-off; new
> `NOT NULL` columns carry a `DEFAULT`; every up migration ships a down
> script verified in CI (`upgrade` then `downgrade`) as the development
> safety net, while **production recovery rolls forward** (revert containers,
> old code ignores new columns) with snapshot restore reserved for declared
> disasters. Never run `db.create_all()` in production; never use the
> `:latest` container tag — deploy versioned hashes with automatic reversion
> on failed health checks. CI proves migrations against ephemeral
> prod-schema database copies before live deploy. Backend work follows the
> `Guide_Python.md` BS deltas throughout: GUID PKs, `ensure_aware()`,
> whole-document JSON writes, content-free structlog, JSON-mode + Pydantic
> validation, scoped session with function-scoped fixtures, ORM-only queries.

### Phase 0 — Safety net (0.27.x)

- Versioned JSON export schema (v1) + site-bundle manifest + checksum.
- `flask backup-site` / `flask backup-instance` / `flask restore` CLI with
  pre-upgrade runbook; restore drill on a scratch DB in CI.
- **Exit:** backup → wipe → restore round-trips Site 5 data with zero diff.

### Phase 1 — Multi-tenancy foundation (0.28.x)

- `Instance` model + `instance_id` on all tenant tables; membership join
  (`user_id`, `instance_id`, role); JWT gains `instance_id` claim.
- Site 5 migration (all rows incl. users), Instance 1 template seed, Site
  Admin creation; reserve 2–19 (no rows).
- Instance scoping on all queries, scheduler, health, activity, Slack,
  embeddings; 403/404 cross-instance behaviour + tests.
- Copy-on-create service (config-only inventory, empty keys).
- **Exit:** single-tenant test suite passes scoped to Site 5; new instance
  boots empty-configured from Instance 1.

### Phase 2 — V2 lifecycle + comments (0.29.x)

- New status enum (Spark/Scope/Map/Ship/Scale/Drop/Freeze/Archive),
  transition matrix enforcement (API + tests), confirm-before-change contract,
  `IdeaStatusHistory` continuity.
- V1→V2 data migration per §5.3 (PRD-presence rule, Consideration→Scope,
  existing comments→Scope phase).
- `phase` + `is_ignored` columns, phase filter API/UI contract, context
  builder exclusion, audit logging.
- Secondary-action gating rewritten per stage (§5.4/§7).
- **Exit:** migrated prod data verified (counts per state, history intact);
  illegal transitions rejected with tests.

### Phase 3 — Provider abstraction (0.30.x)

- Provider interface + Ollama backend parity; per-instance provider/key
  management (encrypted, admin-only); per-prompt provider+model routing;
  per-instance allowlists; hosted embeddings config.
- Guardrail update (per-instance egress opt-in), rate-limit and cost logging.
- **Exit:** Ollama-only instance behaves exactly as V1; hosted provider
  works on a test instance with keys never leaking to non-admins/logs.

### Phase 4 — Chat-to-AI (0.31.x)

- Chat API (all phases), logging + versioned iteration + rollback, rate
  limits, Flutter-ready contract.
- **Exit:** scripted chat → iterate → rollback round-trip tested; ignored
  comments proven excluded.

### Phase 5 — Auth: social + memberships (0.32.x)

- Google/Apple/Microsoft login, link-by-verified-email, per-instance roles,
  Site Admin management screens (API first).
- **Exit:** password + social logins coexist; cross-instance membership
  switching tested; rate limits + audit pass.

### Phase 6 — Backup/restore GA (0.33.x)

- Productionise Phase 0 tooling: scheduled site backups, per-instance JSON
  self-service, checksum verification, documented RTO (restore drill timed).
- **Exit:** Site Admin full restore + Instance Admin JSON restore both proven.

### Phase 7 — Flutter replatform (0.34.x–0.35.x)

- API-only backend; Flutter app (auth, ideas, prompts, admin, chat, footer
  build number, deep links); Jinja removal; `index.html` deletion.
- Flutter standards (per `Guides/Guide_Flutter.md` and
  `Guides/Guide_UITesting.md`, Aspirational → applicable here): feature-first
  `lib/features/` structure — the Flask app is **not** restructured to match;
  dumb widgets with logic in controllers (Riverpod/Bloc/Signals),
  ≤ 150-line widget files, `const` constructors, design tokens (no hardcoded
  strings/colours/padding), `dispose()` of all controllers/subscriptions,
  single networking client with token-refresh (never raw `http` in widgets),
  strict Dart domain models (`freezed`/`json_serializable`) validated before
  UI work. Testing pyramid: unit (many) / widget + golden (medium) /
  integration-E2E (few); `Key`-based finders, `pump` vs `pumpAndSettle`
  discipline, goldens generated on locked-OS Linux CI (git-lfs if large),
  multi-device sizes, no hardcoded sleeps, `mocktail` mocking; CI runs
  `dart format`, `flutter analyze`, `flutter test --coverage` with an explicit
  coverage gate. pytest keeps API/business behaviour; Flutter tests own
  widget and visual consistency (existing `tests/ui/` pytest stays until the
  client lands, then responsibilities split).
- **Exit:** feature parity checklist signed off (every §9 contract item),
  Flutter quality gates green, old UI routes return 410 with pointer to
  Flutter.

### Phase 8 — Billing/premium + hardening (0.36.x)

- Entitlement framework + Free flag wiring once §10 candidates are confirmed;
  Start/End enforcement per deferred decision.
- Full Guardrail re-audit (bandit, safety, SAST/SCA), coverage push toward
  80%, load/scheduler soak, docs (`README`, `docs/*`, ERD, install-config,
  user-guide) finalised.

### Phase ordering rationale

Tenancy first (everything else keys off `instance_id`), lifecycle second
(unblocks all UX), providers third (needs per-instance config), chat fourth
(needs providers + phases), auth fifth (needs memberships live), backups
hardened sixth (tooling exists from Phase 0), Flutter seventh (stable API to
build against), billing last (most TBDs).
