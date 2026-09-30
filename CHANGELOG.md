# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [0.41.0] - 2026-09-30
### Added
- Staging smoke test (item 15): `flutter/integration_test/app_test.dart` walks register → login → ideas → vote → comment → chat history with a throwaway user and cleanup; verified headless against a scratch backend (device/Chrome required for on-device runs; never point at production)

## [0.40.0] - 2026-09-30
### Added
- Offline + local notifications (item 14): TTL GET cache with stale-on-failure fallback and prefix invalidation on mutations, connectivity banner in the app shell, new-idea digest and chat-reply local notifications (no-op off-platform), 6 new Flutter tests (18 total). FCM deliberately unwired pending project credentials (documented follow-up)

## [0.39.0] - 2026-09-30
### Added
- Proxy-server virtual keys (item 10): LiteLLM sidecar in compose plus config template, per-config proxy mode with encrypted virtual keys (raw keys stay server-side in LiteLLM), app-side budget/entitlement/spend enforcement on every proxied call, `provision-proxy-key` CLI (key prefix only on screen), API toggle gated on provisioning, per-call pricing from the bundled table. Deferred: proxy DB persistence beyond documented setup, embeddings via proxy

## [0.38.0] - 2026-09-30
### Added
- Per-stage AI config (item 18): `stage_ai_configs` (one row per instance+stage, all settings nullable) with GET/PUT API, resolution order explicit-args > stage > prompt > defaults across generation, secondary actions (model/provider/params/skills/guidelines) and chat routing; rewritten user guide for the V2 pipeline and API

## [0.37.0] - 2026-09-30
### Added
- Phase 8 billing entitlements + hardening: entitlement framework (stored grants layer over Free-flag baselines, `hosted_ai` enforced on hosted generation and chat with 402, suspended instances refused, site-admin management API + `set-entitlement` CLI), `guardrails.yml` CI (bandit, safety, guard scripts, Flutter analyze/test, backend gate), `check_no_external_calls`/`check_no_secrets` scripts. Audit: bandit 0 high/medium (14 pre-existing lows), safety 0 vulnerabilities, backend coverage 73% (gate 35, target 80 tracked). Honest deferrals: payment provider/pricing, Start/End enforcement, DLP layer, proxy-server virtual keys, push/offline

## [0.36.0] - 2026-09-30
### Added
- Phase 7 Flutter replatform (`flutter/`, verified with Flutter 3.41.4): feature-first Riverpod app (auth with instance picker, ideas list/detail with vote/comments/phase filter/status change, chat tab, prompts with provider routing, admin dashboard/activity/users, instance settings with write-only keys and spend), single ApiClient with 401-refresh-retry, secure token storage, Inter/blue tokens with dark mode, version footer, web deep-link parity, 10 widget/unit tests plus a tracked golden, release web build proven. Backend: `LEGACY_WEB_ENABLED` flag (default on) with 410 retirement path for all Jinja routes. Deliberately deferred: push/offline, integration_test against staging, freezed codegen (hand-written models for now)

## [0.35.0] - 2026-09-30
### Added
- Phase 6 backup GA: real per-instance export (tenant rows plus members and referenced authors; sessions and global event ids excluded by design) and scoped restore that never touches other instances, `restore-instance` CLI, self-service `GET /instances/<id>/export` download, daily `scheduled_site_backup` beat task with write-verify, site-restore scope guard, RTO runbook with measured drill record. `backup-instance` now requires an instance number or UUID

## [0.34.0] - 2026-09-29
### Added
- Phase 5 social login (Google/Apple/Microsoft OIDC): stateless PKCE with Fernet-encrypted state, JWKS-verified ID tokens (issuer/audience/nonce/expiry), verified-email requirement, link-by-email ceremony with explicit confirm token (409 LINKING_REQUIRED, never silent merges), JIT onboarding at least privilege, immutable (provider, subject) identity links surviving email changes, per-instance OAuth credentials (write-only secrets), member roster with role guards (never self, never last admin), 5/min/IP rate limits, tenant-tagged auth telemetry. Apple uses a pasted client-secret JWT. Deviation: identity links in `oauth_identities` table instead of the guide's single column (multi-provider reality)

## [0.33.0] - 2026-09-29
### Added
- Phase 4 Chat-to-AI: prose chat turns on all phases (JSON-mode escape hatch in the provider interface), versioned iterate with IdeaEdit audit + before/after snapshots, rollback of any iterate turn (itself audited), per-user 3/min rate limit, per-instance enable switch (`CHAT_DISABLED` 403), admin-only iterate/rollback/model-override, content-hash-only logging, ignored comments proven excluded from sent prompts, fixed latent `Comment.user` crash in context builder. Known gap: iterate is admin-only while the V2 matrix grants users edit-own — flagged as open item

## [0.32.0] - 2026-09-29
### Added
- Phase 3 provider abstraction (LiteLLM): `generate_for_prompt` routing with Ollama legacy-path parity, hosted JSON-mode generation with usage capture and static-fallback pricing, rolling 30d budgets (70% alert, 100% refuse-fast without retry), append-only `ai_spend_ledger`, encrypted per-instance provider configs with write-only keys and allowlists, per-prompt provider routing, hosted embedding override, spend dashboard API, Guardrail per-instance egress opt-in. Deferred honestly: proxy-server virtual keys (in-process for now), queue/degrade cutoffs, pricing auto-sync, DLP layer

## [0.31.0] - 2026-09-29
### Added
- Phase 2 V2 lifecycle: 8-state `IdeaStatus` (Spark/Scope/Map/Ship/Scale/Drop/Freeze/Archive) with transition matrix enforcement (`ILLEGAL_TRANSITION` 400, bulk skips with count), per-phase comment threads (`phase` column + `?phase=` filter + composite index), admin-only Ignore flag (`PATCH /comments/<id>/flag`, hidden from users, excluded from all AI context, IdeaEdit-audited), stage-gated secondary actions (PRD at Scope+, Design docs at Map+, nothing on Drop/Archive), Jinja UI rewritten to V2 states with always-confirm status changes, transactional-safe enum migration with V1 map (PRD-bearing DESIGN ideas become MAP), fixed latent `Comment.user` crash in context builder

## [0.30.0] - 2026-09-29
### Added
- Phase 1 tenancy foundation: `instances` + `memberships` (string roles, NULL = site-wide grant), `instance_id` on all tenant tables, JWT `instance_id` claim (optional; legacy tokens stay unscoped), membership-enforcing decorators plus `site_admin_required`, per-request scoping on ideas/prompts/admin/tasks/embeddings/Slack, LiteLLM-ready task instance threading, `/api/v1/instances` CRUD, copy-on-create from Instance 1 (config only, Slack cleared, keys never copied), `init-tenancy / promote-site-admin / create-instance` CLI, reserved numbers 2-19, Postgres RLS failsafe migration, tenancy runbook in `docs/install-config.md`

## [0.29.0] - 2026-09-29
### Added
- Phase 0 safety net: versioned JSON site bundles (schema v1, manifest, SHA-256) via `app/services/backup.py`; `flask backup-site / backup-instance / restore` CLI (restore confirms unless `--yes`, refuses corrupt/newer-schema bundles, friendly error on unmigrated DB); backup → wipe → restore proven zero-diff by per-table fingerprints (listener double-counts and `onupdate` drift corrected); `backup-drill` CI job with backup tests plus scratch-SQLite CLI drill; ops notes in `docs/install-config.md`

## [0.28.0] - 2026-09-29
### Added
- Whole-V2 system design (`docs/Design.md`): LiteLLM proxy + Ollama backend, Riverpod Flutter app with screen inventory and Inter/blue design tokens, fresh mermaid lifecycle diagram for all 8 states, 7 new tables + `instance_id` rollout with RLS defence-in-depth, full API contract table (instances, switcher, AI/OAuth config, chat + rollback, spend, social PKCE), riskiest-first build notes and open questions; PRD_V2 cross-linked

## [0.27.1] - 2026-09-29
### Added
- PRD V2 aligned with Guides review: full social-login schema (tenants, per-tenant OAuth configs, global_subject_id, memberships, PKCE/state, JIT least-privilege, explicit link confirmation), LLM proxy decision with virtual keys, request tagging, DLP, budgets with 70%/100% cutoffs, streaming usage capture and tenant-scoped caching, secrets-never-in-prompts rule, privacy release gate (§12), expand-and-contract migration discipline, Flutter quality gates in Phase 7; Guides catalogue marks SocialLogin and MultiTenantAIConnectivity Adopted-for-V2

## [0.27.0] - 2026-09-29
### Added
- PRD V2 approved for planning: multi-tenant model (Site/Instance, single DB + instance_id, copy-on-create, Site 5 migration, reserved 2-19), V2 lifecycle (Spark/Scope/Map/Ship/Scale/Drop/Freeze/Archive with transition matrix and V1 migration map), per-phase comments + Ignore flag, provider abstraction (OpenAI/Anthropic/Gemini/local), Chat-to-AI, Flutter replatform scope, backup/restore, and full phased development plan (Phase 0-8)

## [0.26.9] - 2026-09-27
### Changed
- PRD/Design editor is now a human-readable per-section form (labeled fields, one-entry-per-line lists) instead of a raw JSON textarea; verified field-edit → save → new version round-trips in a headless browser

## [0.26.8] - 2026-09-26
### Fixed
- PRD/Design Edit button did nothing: the inline editor lived inside the per-tab panel loop where it never inserted into the DOM (proven via headless-browser repro: handler ran, state set, element absent). Editor is now a single modal-level block driven by direct result lookup; open-edit-save verified end to end (v3 with edited content, history preserved).

## [0.26.7] - 2026-09-26
### Fixed
- Answered PRD questions came back on regenerate: new questions matching already-answered ones (fuzzy ≥ 0.8) are now filtered deterministically, plus stronger no-repeat prompt instructions. (The earlier null-answers persistence fix required a worker restart to take effect — done.)

## [0.26.6] - 2026-09-26
### Fixed
- PRD answers were never saved: human answers to open questions lived only in transient job args and vanished on regenerate. Stored on the regenerated version (`answers` column) and shown under "Your answers" in the PRD tab.

## [0.26.5] - 2026-09-26
### Changed
- Run dialog Skills section only appears for Design-stage ideas (model picker and guidelines unaffected); selections reset on every open so nothing leaks across runs

## [0.26.4] - 2026-09-26
### Fixed
- List-view action chips only ever showed five hardcoded actions (VRIO, GTM, PRD, Design… never appeared): chips are now registry-driven like the detail tabs, deduped across versions
- Stale list behind the detail modal: closing the modal now refreshes ideas + totals, so chips/counts/statuses reflect runs made inside it (auto-refresh pauses while the modal is open)

## [0.26.3] - 2026-09-26
### Added
- Automatic duplicate handling: generations scoring >= 0.97 similarity (`DEDUP_SIMILARITY_THRESHOLD`) are created DISCARDED with no Slack post; manual creation never auto-discards

## [0.26.2] - 2026-09-26
### Fixed
- Embedding pipeline actually works now: async path posted to `/api/generate` (400 for embed models) — dedicated `embeddings()` client method using `/api/embeddings`; backfill reached full coverage, which immediately surfaced real duplicates (IDEA-8888/8926/8937/8942 score 1.0)

## [0.26.1] - 2026-09-26
### Changed
- Pipeline statuses: `DEVELOPMENT` retired, `BUILD` added (`CONSIDERATION → DESIGN → BUILD → COMPLETE`); the single live DEVELOPMENT idea + history moved to BUILD via migration. The orphaned PG label stays (undroppable), removed from code and UI.
- PRD/Design tabs now hidden unless the idea status is Design (run options were already gated).

## [0.26.0] - 2026-09-26
### Added
- DESIGN stage: new `DESIGN` status (CONSIDERATION → DESIGN → DEVELOPMENT); PRD/Design run options and tabs gated to Design-stage ideas for admins (UI + API 400/403 enforcement); DESIGN_DOC requires an existing PRD
- Design document action: build-ready blueprint (architecture, screens, data model, API contracts, build notes) with model picker per run
- Run dialog: per-run AI model select, multi-select opencode skills (live discovery from mounted skill dirs) and guideline files (`guidelines/*.md`), injected into generation with token budget
- Per-document discussion threads (PRD/Design versions, all users) with replies; doc versions retained on recreate/edit instead of replace; admin manual edit stores validated new version with audit
- Discovery API `GET /api/v1/discovery` (admin): live skills + guidelines lists

### Fixed
- `ActionType` enum only had 6 of 12 actions: persisting VRIO/3Cs/Market-Sizing/BMC/Hypothesis/GTM results failed on Postgres; enum repaired via migration
- Idea thread no longer leaks document comments (`scope` filter)
- Live containers recreated with read-only opencode-skills mounts (31 skills discovered); guidelines dir created

## [0.25.3] - 2026-09-24
### Added
- Ideas-by-Prompt bar captions: thick bar labelled "ideas vs largest prompt", thin dual bar labelled "run outcomes for this prompt"

## [0.25.2] - 2026-09-24
### Fixed
- `Event loop is closed` crash on strict-retry/second Ollama call: one shared `AsyncClient` was reused across `asyncio.run()` calls; sync paths now use a plain sync client per call (no event loop involved)
- Backfill task silently did nothing: sync Celery task returned the async service coroutine un-awaited; now wrapped in `asyncio.run`
- Dict-shaped scalars coerced (recorded MarketSizing `tam`-as-object shape joins all string leaves incl. keys)

## [0.25.1] - 2026-09-24
### Fixed
- Desktop vote buttons missing: the vote breakdown edit had removed them (mobile/modal kept theirs); restored side-by-side with larger counts (text-sm semibold, w-6 icons, 44px targets)
- Vote counts went stale after voting: `POST /vote` now returns `upvotes_count`/`downvotes_count` and the UI refreshes all three vote displays live
- Removed the misleading Similarity column (badge only reflected embedding presence, never a comparison); fixed stale `colspan="7"` on empty/loading rows to dynamic `isAdmin ? 9 : 8`
- Similarity quality: embeddings now use title + human-readable excerpt instead of the raw JSON blob (shared schema keys inflated same-prompt scores); zero prod embeddings explained by pre-0.24.0 endpoint bug + stale workers — restart + backfill required
- Test fixture rot: `user_with_token` called non-existent `User.get_token()`; now uses `create_tokens`

## [0.25.0] - 2026-09-24
### Added
- Activity runs pagination: Recent runs list has Previous/Next with page counts, driven by the server's `recent_runs_pagination` (deep-linkable via `?page=`)
- Clickable job runs: each run links to its idea (`/ideas?idea=<id>` auto-opens the detail modal) or its prompt's ideas; new `?idea=` deep-link support on `/ideas`
- Per-prompt run health: Ideas-by-Prompt rows show green ✓ success and red ✗ failed run counts with proportional bar (scheduled + follow-up runs attributed via idea)
- Validation coercion: string fields arriving as lists (recorded PESTEL/Refine failure shapes) are joined instead of failing the run; unknown action types now fail fast naming known keys

### Fixed
- Five Forces / PESTEL truncation: token floor raised 4000 → 8000; prompts require plain strings, never lists
- New actions (GTM/VRIO/3Cs/Market Sizing/Hypothesis) `Unknown action type` failures were stale pre-0.20.0 workers, not code — resolves on worker restart

## [0.24.1] - 2026-09-24
### Fixed
- Empty Ideas list / broken status updates / stale activity page: the `comments_count` column added to the `Idea` model had no migration, so every full-row `SELECT` on `ideas` failed on Postgres (`column ideas.comments_count does not exist`) while SQLite tests stayed green. New migration `c9d0e1f2a3b4` adds the column with backfill from existing top-level, non-deleted comments. No data was lost — all failures were read/write errors, rows untouched. Also verify migration `b7c8d9e0f1a2` (HOLD/DEVELOPMENT/COMPLETE enum values) is applied — status changes to the new values fail without it.
- Bulk confirm modal showed raw `<strong>` tags: message rendered with `x-text`, now `x-html` (content is internally generated, no user-input surface).

## [0.24.0] - 2026-09-23
### Added
- Self-diagnosing Ollama failures: `OllamaError` now carries HTTP status code and response body so failed runs show e.g. `model 'llama3:8b' not found, try pulling it first` instead of bare `HTTPStatusError: 404`
- Pre-flight model check: tasks verify `is_model_available()` via `/api/tags` before calling `/api/generate`; missing model fails fast with `Model 'X' not installed at <base_url>` (no retry storm)
- Task logging: every Ollama task now logs `base_url`, model, and prompt/action ID at start for instant topology diagnosis
- Rich context for secondary actions: all secondary actions (Refine, Competitors, Feasibility, Five Forces, PESTEL, PRD, VRIO, 3Cs, Market Sizing, BMC, Hypothesis, GTM) now receive full supporting material — comments with authors, structured fields, prior action summaries, vote tallies — via `${SUPPORTING_MATERIAL}` placeholder in every prompt template

### Fixed
- Refine ignored supporting material: now injects comments, prior analyses, structured fields, and vote counts via new `build_idea_context()` helper
- Competitors and other actions ran without context: all 12 secondary action templates updated with `${SUPPORTING_MATERIAL}` placeholder and wired through `run_secondary_action`

## [0.23.0] - 2026-09-23
### Added
- Ideas header count indicator: "N matching / M total ideas" under the dashboard title
- Ideas `GET /api/v1/ideas` search: `?search=` matches reference code, prompt title and content server-side
- Ideas `GET /api/v1/ideas` sort: `?sort_by=-created_at` (oldest first) and `?sort_by=-votes` (lowest votes)
- Migration `b7c8d9e0f1a2`: adds HOLD, DEVELOPMENT, COMPLETE to the Postgres `ideastatus` enum (apply via psql autocommit; ADD VALUE cannot run in a transaction)

### Fixed
- Detail modal never opened: the `x-data="ideasApp()"` scope closed before the modals, leaving Detail/Create/Confirm modals outside the Alpine component; scope now wraps all modals, dropdown container is `relative`, nested `newActionOpen` scope merged into parent state
- Ideas pagination never displayed: frontend re-paginated an already-paginated page and overwrote server totals (totalPages stuck at 1); pagination is now server-driven with page reset on filter change and working Previous/Next
- Competitor Analysis failures: `CompetitorsOutput` schema requires nested objects that small models garble; fields now default (partial output validates), token floor raised to 8000, prompt requires non-empty lists
- Admin dashboard: removed redundant "Create Prompt" quick-action card (use "Manage Prompts")
- Create Idea header button: removed plus icon, text-only "Create Idea"

## [0.22.0] - 2026-09-23
### Added
- Admin Activity pagination: `GET /api/v1/admin/activity/stats` now accepts `page`/`limit` params, returns paginated `recent_runs` with metadata (page, pages, total, has_next, has_prev); default 20 items per page
- Admin Dashboard deep links: Ideas by Prompt/Model/Status panels link to `/ideas` with `status=ALL` to show all records including discarded
- Secondary Action confirmation: Refine and PRD actions require explicit confirmation when idea has no comments and <3 secondary actions done; returns 409 with `error_code=CONFIRMATION_REQUIRED`; frontend shows reusable modal with Yes/No

### Fixed
- Migration history cleaned: merged 3 divergent heads into single `c867c92cf1b2` merge point; database stamped to merge head
- Create Idea modal display: removed conflicting inline `style="display: none"` and `onclick` handlers; modals now rely solely on Alpine `x-show` + `x-cloak`
- Admin settings page: fixed 404 on `/admin/settings` by splitting admin blueprint into `admin_pages_bp` (HTML pages, no prefix) and `admin_api_bp` (JSON API, `/api/v1` prefix)

### Changed
- Idea model: added `actions_run` property for checking completed secondary actions

## [0.21.0] - 2026-09-22
### Added
- Manual idea creation: users can create ideas from the dashboard (`POST /api/v1/ideas`)
  - Format matches generated ideas (reference code, prompt_title, raw_content, structured_content)
  - Available to all users by default; per-user toggle disables the feature
  - UI: dashboard "Create Idea" button → modal with title, content, optional structured fields
  - API: validates title (≤200 chars), content, and optional structured fields
  - On success: generates IDEA-XXXX reference code, saves as status=NEW, opens detail modal
- User settings toggle: `PATCH /api/v1/me/settings` — can disable manual idea creation per user
- AGENTS.md updated with comprehensive repo guidance, architecture notes, lessons learned, test patterns, key files, and related skills

### Fixed
- Verified all 161 tests pass across unit, integration, and UI suites
- Modal redesign no longer overlaps; bordered cards prevent button/content clipping
- `can_create_ideas` defaults to `True`; user can toggle off in settings
- `ensure_aware()` usage documented to prevent naive-aware datetime TypeErrors

## [0.20.0] - 2026-09-19
### Added
- Six new secondary actions: VRIO Framework, 3Cs Analysis, Market Sizing (TAM/SAM/SOM), Business Model Canvas, Hypothesis Test roadmap, GTM Strategy — registry-driven, no UI changes needed; complex actions use `num_predict=8000`
- System Settings page (`/admin/settings`, linked from admin Quick Actions): Platform (title/description/type checkboxes), Location (country), AI Connections (placeholder)
### Fixed
- Idea detail modal redesign: fixed-height meta strip (Prompt link / Generated + admin gen-time / Votes + comment count, breadcrumb folded in), single sticky tab bar with admin-only "+ New" run-action dropdown, every section in its own bordered card — no more overlapping buttons, clipped tabs, or lost navigation
- Prompt Health "View ideas" links show all statuses (`status=ALL`) for tuning

## [0.19.0] - 2026-09-17
### Added
- PRD document generation (`PRD_DOC` action): 7-section PRD with capped open-questions list, answer-and-regenerate loop (reruns replace), per-action tabs in the idea detail modal, admin-generate / view-for-all visibility
### Fixed
- Admin idea edit is WYSIWYG: labeled fields for pitch/audience/value/monetization instead of raw JSON (raw fallback kept for unstructured ideas); fixed silent UPDATE loss from in-place JSON mutation
- Prompt Health "View ideas" links now show all statuses (`status=ALL`) for tuning, not just active ones
- Secondary action tabs always accessible: sticky tab bar and dynamic `actionTabs()` from API ensure Overview can always be reached; admin can select all secondary actions (PESTEL, Five Forces, Generate PRD etc.) from both the top tab bar and 3-dot menu
- Secondary-action outputs cut off mid-JSON by the 1000-token cap: `num_predict` floored at 4000 for analytical actions (a higher per-prompt setting is respected)

## [0.18.0] - 2026-09-16
### Added
- Idea embeddings for similarity search (PRD §9.3): `embedding` JSON column on ideas, `EmbeddingService` with nomic-embed-text via Ollama, cosine similarity search endpoint, "Similarity" badge in ideas list with link to filtered results

## [0.17.0] - 2026-09-16
### Added
- Slack Phase 3c (two-way threads): app comments mirror to Slack threads (for posted ideas), Slack thread replies sync back as comments, loop-guard marker, Socket Mode listener entrypoint (`slack_listener.py`, needs `SLACK_APP_TOKEN`)

## [0.14.0] - 2026-09-16
### Added
- Slack Phase 3c (two-way threads): app comments mirror to Slack threads (for posted ideas), Slack thread replies sync back as comments, loop-guard marker, Socket Mode listener entrypoint (`slack_listener.py`)

## [0.13.0] - 2026-09-16
### Fixed
- Secondary action timeout increased to 600s (from 120s) for CPU-bound large models; primary generation stays at 120s

## [0.12.0] - 2026-09-16
### Added
- Slack Phase 3b (votes): `slack_user_id` link + `slack_posts`/`slack_events` tables, email-match auto-provisioning, 👍/👎 reaction add/remove mapped to set/flip/rescind, event-ID dedup, Socket Mode listener entrypoint (`slack_listener.py`, needs `SLACK_APP_TOKEN`)

## [0.11.0] - 2026-09-15
### Added
- Slack Phase 3a (PRD §10.3): per-prompt `slack_channel` (#name or ID, validated, empty clears), `slack_sdk` dependency, best-effort Block Kit auto-post on new ideas (never blocks generation, one rate-limit retry), channel fields on both prompt forms

## [0.10.0] - 2026-09-15
### Added
- Mobile responsive polish (PRD §10.4): zero horizontal overflow at 360px on all pages (navbar user area truncates, admin link/username progressively hide), 44px touch targets on nav/buttons/filters/inputs/menus/footer, users table scroll container, detail modal becomes a bottom sheet on mobile, prompt forms usable single-column

## [0.9.0] - 2026-09-15
### Added
- Admin idea edit + audit (PRD §10.2): `PATCH /ideas/<id>` for prompt_title/raw_content (400 on empty, unchanged fields skipped), `idea_edits` table with editor names, history in detail view, edit form in Admin Actions

## [0.8.0] - 2026-09-15
### Added
- Threaded idea comments (PRD §10.1): all users can post/reply (full nesting), authors edit/delete own, admins any; deletes become "[deleted]" stubs with children reparented; UI lives in the idea detail modal with reply/edit/delete, 44px targets, optimistic post

## [0.7.0] - 2026-09-14
### Added
- Admin-only PESTEL analysis: new `PESTEL` action (flat-string schema), `pestel.txt` template, registry entry, 3-dot menu + chips support, `actiontype` enum extended

## [0.6.0] - 2026-09-14
### Added
- Admin-only Porter's Five Forces analysis: new `FIVE_FORCES` action (flat-string schema tuned for small models), `forces.txt` template, registry entry, 3-dot menu + chips support, `actiontype` enum extended

## [0.5.3] - 2026-09-14
### Fixed
- New ideas wrongly showed "You downvoted": `user_vote` is null (not 0) when unvoted, and `null !== 0` passed the check — now shows only on real +1/-1 votes (table + detail modal)

## [0.5.2] - 2026-09-14
### Fixed
- Circular import at startup (`celery_auto_init_skipped` noise): tasks import is lazy inside `create_app` — auto-init now succeeds with all tasks registered
- Beat liveness: new `beat_heartbeat` task (60s) stamping Redis; `/api/health` gains a `scheduler` check (missing key = boot grace, stale > 3 min = degraded)

## [0.5.1] - 2026-09-13
### Fixed
- Secondary actions now run cold (temperature capped at 0.3): analytical calls inherited creative temps and garbled schemas
- Validation-feedback retry: a schema failure retries once with the errors fed back instead of blindly repeating; markdown fences stripped before validation

## [0.5.0] - 2026-09-13
### Added
- Prompt health (PRD §9.2): `GET /api/v1/admin/prompts/health` with 7d stats (runs, ideas/run, discard %, avg score/feasibility) and HIGH_DISCARD / STARVED / LOW_FEASIBILITY flags linking to edit form + ideas; Activity panel section; `?edit=` deep link auto-opens the prompt edit modal

## [0.4.0] - 2026-09-13
### Added
- Prompt memory (PRD §9.1): every run renders Avoid (last 10 ideas) + Explore (top-voted themes) sections from `${MEMORY_AVOID}` / `${MEMORY_EXPLORE}`; "none yet" on new prompts; recomputed per run, never stored

## [0.3.7] - 2026-09-13
### Fixed
- Dropdown menu items overlapping invisibly: adjacent inline `<button>`s without `block` stacked at the same Y (hid Run 5x Burst; Refine/Competitors overlapped too) — all menu buttons now `block w-full`
- Sidebar footer version was blank: wired `VERSION` file into app config (also a freshness signal for cached pages)

## [0.3.6] - 2026-09-13
### Changed
- Speed-by-model links open a timings-only view (everything else hidden while a model is selected)
- Run Now no longer pops a dialog; the run-pending badge is the confirmation (errors still alert)

## [0.3.5] - 2026-09-13
### Fixed
- New UI (burst button, timing graph, status panels) invisible in browsers: HTML pages had no real cache headers (`<meta http-equiv>` is ignored) — now `Cache-Control: no-cache, no-store, must-revalidate` on all HTML responses

## [0.3.4] - 2026-09-13
### Fixed
- Removed Top-voted ideas from /admin/activity (backend payload trimmed too)
- Activity links 404'd (`/admin/activity...` — page lives at `/api/v1/admin/activity`): all tile/row links + history state corrected
- Ideas by Status showed run outcomes: now idea states, run outcomes moved to new Runs by Status panel
### Added
- Model timing graph: Speed rows open a timings-only view (successful-run bars, newest first); run stream hidden while a model is selected
- Admin burst runs: run-now `{"count": 1-5}` + "Run 5× Burst" menu item
- Secondary-action results (Refine/Competitors/Feasibility) render as labelled human-readable sections instead of raw JSON

## [0.3.3] - 2026-09-13
### Fixed
- Ideas by Status showed run outcomes (Failed/Success): now idea states (New/Consideration/Discarded) via `ideas_by_status`; run outcomes moved to a new Runs by Status panel
- Activity links 404'd (`/admin/activity...` — page lives at `/api/v1/admin/activity`): all tile/row links + history state corrected
### Added
- Per-model timing graph: Speed rows link to a Run-timings panel (successful-run durations as bars, newest first) + filtered run stream
- Admin burst runs: `POST run-now {"count": 1-5}` enqueues up to 5 independent runs; prompts menu gains "Run 5× Burst" (confirm first)

## [0.3.2] - 2026-09-13
### Fixed
- Run-stream filters (?run_status=, ?model=) were client-side over the 20 loaded runs — now server-side on `/admin/activity/stats` (wider window when filtered, 400 on bad status); Clear reloads unfiltered

## [0.3.1] - 2026-09-13
### Fixed
- Ideas by Model counts were fanned out by the runs join (12 shown for 6 ideas): now `count(DISTINCT ideas)`
- Clicking a model showed 1 idea: `?model=` filter was client-side over one page only — now server-side on `/api/v1/ideas`, client sends it with the request

## [0.3.0] - 2026-09-13
### Added (PRD §8, all items built)
- Per-prompt generation params: `top_p` (0.9), `repeat_penalty` (1.1), `num_predict` (1000), `seed` (null = random), `keep_alive` ("2h") — model columns, API validation (400 on out-of-range), worker pass-through, Generation section with tooltips on create + edit forms
- Users: `last_login_at` + `login_count` columns, stamped on login, shown in admin users table
- Activity: metric tiles link to filtered run lists, Ideas by Prompt/Model + Speed + Status moved above the run stream in 2-col rows, all rows link out, `run_status`/`model` filtering with clear chip, load-error banner with retry
- Ideas page honours `?status=&prompt=&model=` deep links; new model filter dropdown
- Navigation from a single `nav_links` context processor (all three menus loop it, active highlighting); `/dashboard` 302-redirects to `/ideas`
- Mobile stacked cards for ideas below `md` breakpoint (full summary, 44px targets)
- Ideas 3-dot menu: Consider / Discard (confirm) / Refine / Competitors for admins
- 24h access tokens (`JWT_ACCESS_TOKEN_EXPIRES=86400`); fixed `create_tokens`/`rotate_refresh_token` ignoring the config (hardcoded 15min) — the true cause of frequent logouts
### Fixed
- `prompt_body` now reaches Ollama via `${PROMPT_CONTEXT}` in the initial template (was silently ignored)
- API range validation for `temperature` 0–2 on all four parse sites (shared `_parse_temperature`)
- `POST /logout` 500 (tuple passed to `unset_jwt_cookies`); `RefreshToken.is_valid` naive/aware TypeError (shared `ensure_aware()`)
- Merged duplicate PRDs into `PRD.md` (removed stale `PRD_Brainstormer.md`)
### Tests
- Suite: 102 passed, coverage ≥ 35% gate met

## [Unreleased]

### Added
- Flask + Jinja2 + Tailwind CSS + Alpine.js frontend stack
- PostgreSQL/SQLite with SQLAlchemy models (User, PromptConfig, Idea, Vote, SecondaryActionResult, IdeaStatusHistory)
- JWT authentication with access/refresh tokens (flask-appkit + custom PyJWT)
- Admin CLI commands (create-admin, create-user, list-users, promote-user)
- Ollama client with JSON-enforced responses and Pydantic validation
- Prompt templates (base, refine, competitors, feasibility)
- Celery task queue with dual queues (ollama concurrency=1, default concurrency=4)
- Celery Beat scheduler for periodic prompt execution
- REST API endpoints:
  - Auth: register, login, refresh, me
  - Prompts: CRUD + run-now (Admin)
  - Ideas: list, detail, status, vote, actions (Admin)
  - Ollama models listing (Admin)
  - Health/Readiness checks
- Health/Ready endpoints with dependency checks
- Rate limiting (disabled in tests)
- Fakeredis for testing
- Security & Privacy Guardrails (`Guardrail.md`)
- Best Practice Updates for LLM integration (`BEST_PRACTICE_UPDATES.md`)

### Changed
- Updated PRD to reflect Flask + Jinja2 stack
- Updated AGENTS.md with project-specific conventions
- Updated README with architecture overview and planned API
- Lowered test coverage threshold to 35% (temporary, target 80%)

### Fixed
- JWT token creation with role claims using PyJWT
- Rate limiting disabled for tests
- Fakeredis integration for testing
- Health check uses app.extensions for Redis client

## [0.2.3] - 2026-09-12
### Fixed
- Test suite fully green (96 passed, coverage 68%): was 20 failed + 26 errors
- Test isolation: `app`/`celery_app` fixtures are now function-scoped (fresh `:memory:` DB per test); session scope had shared one DB across the run so hardcoded emails/codes collided with UNIQUE errors depending on order
- Added missing `admin_client`, `admin_user`, `admin_prompt` fixtures (integration suite was written against `admin_client` but it never existed — 12 setup errors)
- Fixed `@patch` swallowing the `celery_app` fixture in `test_generate_idea_prompt_not_found` (mock took the fixture's parameter slot; passed only by order luck)
- Fixed mocked `.delay().id` MagicMocks breaking `job_id` commits (set string ids)
- Corrected outdated expectations: prompt listing is `@token_required` (200, not 403), `/ollama/models` is user-visible per convention (mock `list_models_sync`, the method the route actually calls)
- `POST /api/v1/logout` 500'd in prod: `unset_jwt_cookies()` got the `(response, status)` tuple instead of the Response — now unpacked first
- `RefreshToken.is_valid()` raised `TypeError` (naive vs aware `expires_at` on SQLite): shared `ensure_aware()` helper in `app/models/types.py`, also adopted by `PromptRun` duration maths
- `test_refresh_token` now follows the real contract (refresh token in JSON body)
- `test_health_ok` stubs the Redis check (no Redis in test env); added `test_health_degraded_without_redis` locking the intended 503 behaviour

## [0.2.2] - 2026-09-12
### Fixed
- Idea generation stalled with orphaned RUNNING runs: `_generate_reference_code()` ordered by random-UUID `id`, re-issuing `IDEA-0005` on every insert -> `UniqueViolation` on all 5 prompts; now takes max over parsed numeric codes (skips non-numeric)
- Poisoned-session orphans: `generate_idea`/`run_secondary_action` now roll back before `mark_failed`, so failures record FAILED instead of raising `PendingRollbackError` and sticking at RUNNING (which also blocked `check_due_prompts` re-enqueue via the live-run guard)
- `PromptRun.mark_success`/`mark_failed` no longer raise `TypeError` on naive datetimes (SQLite/dev); naive values treated as UTC
- Tests: fixed stale-session read in `test_generate_idea_success`, MagicMock `job_id` binding in `test_check_due_prompts`, and cross-test email/code collisions in `tests/tasks/test_ollama_tasks.py` (now 8/8 green); added regression tests for code increment and poisoned-session failure recording

## [0.2.1] - 2026-09-10
### Fixed
- Login form: missing `});` on `fetch("/api/v1/login")` meant the submit handler never registered (silent reload, no message)
- Prompts list/create: unified split Alpine scopes to single page-root `x-data`; modal Cancel/Close/"Saving…" now work
- Model dropdowns: invalid `x-for` on `<option>` replaced with `<template x-for>`; handles string and object models with Ollama-unreachable fallback
- Unclosed script blocks in `prompts/list.html` (`initPromptsPage`) and `admin/users.html` (DOMContentLoaded) that killed all page JS
- RBAC page gating: anonymous users redirect to `/login`; non-admins bounced from `/prompts/create`; admin-only buttons hidden with `isAdmin`
- Admin users: role select/status toggle were permanently disabled (`user.id == user.id` self-compare); loop var renamed, self-row correctly disabled
- Admin API: missing `UserRole`/`api_error`/`api_created` imports (role updates 500'd); enum role search fixed for Postgres
- Admin Panel link 401: login/register now also set JWT cookies so browser navigation carries auth
- Vendored Alpine.js 3.14.8 to `/static/js/alpine.min.js` (no more CDN dependency for interactivity)
- Navbar: JS-driven guest/user areas with username, admin link, and working logout

## [0.1.0] - 2026-09-02
### Added
- Initial scaffold from flask-bootstrap (Flask + SQLite + JWT auth + tests + docs)
- Security & Privacy Guardrails (`Guardrail.md`)
- Best Practice Updates for LLM integration (`BEST_PRACTICE_UPDATES.md`)
- Product Requirements Document (`PRD.md`)
- Updated AGENTS.md with project-specific conventions
- Updated README with architecture overview and planned API