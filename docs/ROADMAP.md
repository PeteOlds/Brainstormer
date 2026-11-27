# Brainstormer — Roadmap

**Single source of truth for outstanding work.** Update on every build: add new items, refine scope, and remove items only when released (record them in `ReleaseNotes.md`).
**Version:** 0.101.0 · **Date:** 2026-11-25 · **Branch:** `main`

Spec baselines: `PRD_V2.md`, `docs/Design.md`, `Guardrail.md`. Standing decisions: see **Decisions** below.

## How to use this roadmap

- **No completed items** live here. Shipped work is documented in [`ReleaseNotes.md`](../ReleaseNotes.md) (and per-release notes in `docs/release-notes/` where applicable).
- Every item has a **unique ID** (`RM-xxx`) that must not be reused. When scope changes, update the item; when shipped, remove it and add a release note.
- Items are grouped into **phased releases** (`R1`, `R2`, …). Phases are delivery targets, not deadlines: items may move between phases, but the ID stays the same.
- Status: `planned` (default), `in-progress`, or `blocked` (with blocker noted).

---

## R1 — Stabilisation and quality

| ID | Status | Item | Notes / acceptance |
| --- | --- | --- | --- |
| RM-001 | blocked | **Device CI maiden run (Chrome)** | Workflow now builds with `./scripts/build_web.sh`; a confirmed green GitHub Actions run is still required. |
| RM-002 | in-progress | **Coverage ratchet to 85%** | Gate restored to 75% with tests for release and supervision wrappers; the ratchet to 85% remains. |
| RM-003 | blocked | **GitHub flow CI coverage** | Mocked push-flow tests always run; the optional Actions secret `CI_TEST_PAT` (exposed to tests as `GITHUB_TEST_PAT`) enables the CI-secret leg. The secret is now configured; live GitHub-flow coverage still needs test work. |
| RM-005 | planned | **Housekeeping: untracked/stale artefacts** | Partly done in v0.99.2 (v0.26.9 doc archived); duplicate `Guides/` and `guidelines/` guide files still remain. |

## R2 — User-visible bug sweep

| ID | Status | Item | Notes / acceptance |
| --- | --- | --- | --- |
| BUG.062 | planned | **Human-readable Brief** | On "Run full pipeline" for IDEA-10802, the Brief is not properly human readable <br><br>{<br>  "assumptions_risks": "Technical Dependencies: The success of CodeSynth relies on the accuracy and efficiency of the AI model for musical analysis and code generation. Risk Mitigation: Invest heavily in training data, explore different AI architectures, and conduct thorough testing. Third-Party Integrations: Potential integration with game engines (Unity, Unreal Engine) could introduce compatibility issues. Risk Mitigation: Prioritize integrations based on user demand and maintain close communication with engine developers. Assumptions: Users possess a basic understanding of programming concepts. Risk Mitigation: Provide clear tutorials and documentation to guide users through the code generation process.", |
| BUG.064 | planned | **Human-readable Design** | On "Run full pipeline" for IDEA-10802, the Design is not properly human readable<br><br>{<br>  "api_contracts": "1. **POST /compositions:** Method: POST, Path: /api/v1/compositions, Request: JSON { ‘audio_file’: ‘url’ }, Response: JSON { ‘composition_id’: UUID }, Auth: API Key 2. **GET /compositions/{composition_id}:** Method: GET, Path: /api/v1/compositions/{composition_id}, Response: JSON { ‘composition’: {}, ‘analysis’: {} } , Auth: API Key 3. **POST /snippets:** Method: POST, Path: /api/v1/snippets, Request: JSON { ‘code’: ‘string’, ‘language’: ‘string’ }, Response: JSON { ‘snippet_id’: UUID }, Auth: API Key 4. **GET /users/{user_id}/subscriptions:** Method: GET, Path: /api/v1/users/{user_id}/subscriptions, Response: JSON { ‘tier’: {}, ‘usage_count’: integer } , Auth: API Key",<br>  "architecture": "The system will employ a microservices architecture. A frontend built with React will communicate with a backend API built using Python (Flask/FastAPI) for core logic and AI processing. An LSTM-based neural network, trained on musical data, will reside in a separate Docker container accessible via gRPC.  A PostgreSQL database will store user data, generated code snippets, musical compositions, and analysis results.  Third-party services like OpenAI's API (for potential future expansion) and a cloud storage service (AWS S3 or Google Cloud Storage) for storing large audio files will be integrated.",<br>  "build_notes": "1. |
| BUG.068 | planned | **Analysis count matches tabs** | On "Run full pipeline" for IDEA-10802,the Ideas list view shows "Analysis (2)" but there is no Analysis tab (but there is a Brief and a Design) |
| BUG.063 | planned | **Full pipeline continues past Design** | On "Run full pipeline" for IDEA-10802,the pipeline stopped at Design |
| BUG.065 | planned | **Create Idea upload button works on web** | The Create Idea / Upload .md/.txt button doesn't open an upload box |
| BUG.066 | planned | **Copy Open App URL or command** | On Build tab, Open App should allow copy to clipboard.  Note that Open App may be either a URL or a command line |
| BUG.067 | planned | **Build logs display** | On the Build tab, check that logs are working properly - they keep showing as blank |

## R3 — Features

| ID      | Status  | Item                                         | Notes / acceptance                                                                                                                                                                                                                        |
| ------- | ------- | -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| REQ.022 | planned | **Vote on comments**                         | Allow voting on comments                                                                                                                                                                                                                  |
| REQ.023 | planned | **Comment votes on Dashboard for all roles** | Include voting on comments on the Dashboard shown for all roles                                                                                                                                                                           |

## R4 — Platform follow-through

| ID     | Status  | Item                              | Notes / acceptance                                                                                                                                                                                                                |
| ------ | ------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RM-004 | planned | **OpenCode attach-mode auth**     | Investigate and fix LAN attach-mode auth: `OPENCODE_PASSWORD`/server password from `~/.config/opencode/service.json` is rejected by the v2 CLI client. Replace the current Ollama workaround for SHIP/SCALE once verified.        |
| RM-013 | planned | **Remove legacy Jinja templates** | After the Flutter cutover has been monitored with no P1 regressions, delete the retired Jinja templates/routes and related assets to end dual maintenance.                                                                        |
| RM-051 | planned | **Live Stripe billing loop**      | Operational setup: configure real Stripe plans mapped to entitlement keys and verify the test/staging grant → gate → revoke loop. Primarily admin/configuration work; track any small code fixes discovered as separate RM items. |

## R5 — Agentic-ready code (OpenCode + Ollama)

Applies to two targets: apps **generated** by brainstormer, and the brainstormer repo itself. See *Agentic-readiness design notes* below for the principles these items implement.

| ID | Status | Item | Notes / acceptance |
| --- | --- | --- | --- |
| RM-058 | planned | **Decompose oversized brainstormer modules** | `ideas.py` (2,311), `instances.py` (1,698), `ollama_tasks.py` (1,546), `build_runtime.py` (1,396). Extract cohesive helpers incrementally, target ~150–300 lines per module, URLs and behaviour unchanged. Keep the layer-based layout; do not restructure to feature-first (see `Guide_ProjectOverview.md`). Issue: #10 |
| RM-059 | planned | **API boundary schemas** | Add Pydantic request/response schemas for key endpoints and extend `scripts/check_api_contract.py`. Preserve the `{success, data}` envelope; never mutate JSON columns in place. Issue: #11 |
| RM-060 | planned | **Guide deduplication** | Follow up on RM-005: `Guides/` and `guidelines/` overlap. Keep one source of truth so agents and humans do not read conflicting instructions. Issue: #12 |
| RM-069 | planned | **Make fast checks required** | `fast-checks.yml` is advisory until the existing baseline is clean: black would reformat 85 files, isort reports many files, and mypy reports ~280 errors. Fix the baseline in small slices, then remove `continue-on-error` and add `fast-checks` to branch protection. |
| RM-068 | planned | **Restore a working dependency audit** | `safety check` is deprecated, crashes on a clean runner (`httpx.Timeout` TypeError with httpx 0.28.1) and reports 46 known vulnerabilities locally. Triage and upgrade affected dependencies, choose a maintained audit tool, then restore it as a required CI check. Removed from the gate in v0.101.1 so bandit and the guardrail scripts can block merges. Issue: #14 |

## Release Unassigned — no phase

| ID       | Item               | Notes / acceptance                                                                                                                                                                                                                                          |
| -------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RM-040.1 | **Default Guides** | HOLD<br>Site Administrator should be able to configure default Guides for each phase, and this will apply across all instances.  On first configuration, this should be copied to all instances.  Instance administrator should be able to Guides should be |
| RM050    | Updated README     | HOLD                                                                                                                                                                                                                                                        |
| BUG.010  |                    | HOLD<br>If AI Provider Spend tab is different from AI Providers / Configure / Monthly budgets, then remove the duplication                                                                                                                                  |
| BUG.069  |                    | Debugging a failed job (Design Doc on IDEA-9263) gave the following error message<br><br>Failed to load: ApiException(0): Network error: ClientException: Failed to fetch, uri=/api/v1/ideas/f588be63-71bf-442f-8ba1-6a75e335a9ba                           |
| BUG.070  |                    | HOLD<br>On the Admin Panel, update the System settings tile to read "System Settings Platform, location, build location" (old BUG.001 was reused for a different fix)                                                                                       |

---

## Agentic-readiness design notes

Guidance applied to both generated apps and brainstormer itself. These are standing principles, not work items; the outstanding work is tracked as RM-058–RM-069.

- **Small, single-purpose files** — roughly 150–300 lines where practical, with clear entry and exit points.
- **Organise by feature/domain slice** for generated apps; keep brainstormer's existing layer layout (see RM-058).
- **Typed contracts at boundaries** — schemas for LLM output, API payloads, DB records and UI props; derived run instructions, never model prose.
- **Pure logic separate from side effects** — network, file I/O, DB and global state stay at the edges.
- **Fast automated checks** — lint, typecheck, unit tests, manifest lint; quick feedback lets the model self-correct.
- **Concise `AGENTS.md`** in both targets; no repetition of conventions in every prompt.
- **Plan separately from implementation** — read-only planning first, fresh sessions per task, small commits on a branch.
- **Right-size context** — match context window and model to hardware; scope prompts to one slice, name target files, state inputs/outputs/invariants, anchor on an existing pattern, and require a plan before multi-file edits.
- **`main` is an always-working sanctuary** — no direct commits or pushes; every change arrives through a PR with passing checks.
- **One slice = one branch** — short-lived `feat/`, `fix/` or `agent/` branches, atomic commits at verified checkpoints, squash merge on green CI.
- **Isolate agent work with worktrees** — one directory per task, primary checkout stays stable for dev servers, DB and venv.
- **Drive sessions from GitHub Issues** — acceptance criteria in the issue, `Closes #N` in the PR, small diffs, stable tags before risky work.

## ID index — full descriptions

Cross-reference of every ID used in `ReleaseNotes.md` or this roadmap. Shipped IDs show the release they landed in; outstanding IDs show the roadmap status. This is an index only — it adds no work items.

- **BUG.001** — BUG.001: clicking an analysis now opens a dialog showing its full content. *(v0.96.1)*
- **BUG.002** — BUG.002: ideas list now shows a spinner and "analyzing…" while a secondary analysis is running. *(v0.96.1)*
- **BUG.003** — BUG.003: vote counts refresh after voting. *(v0.96.3)*
- **BUG.004** — BUG.001/BUG.004: completed secondary analyses now display in the idea Analysis tab (auto-refreshing cached detail view). *(v0.96.0)*
- **BUG.005** — BUG.005: clicking a prompt row opens the editor. *(v0.96.0)*
- **BUG.006** — BUG.006: prompt parameters editable via Advanced section. *(v0.96.0)*
- **BUG.007** — BUG.007: removed `{{topic}} for theme` helper text. *(v0.96.0)*
- **BUG.008** — BUG.008: model allowlists are multi-select. *(v0.96.0)*
- **BUG.009** — BUG.009: provider Test endpoint now returns and displays success/failure. *(v0.96.1)*
- **BUG.010** — BUG.010: spend/budget duplication removed (budget line dropped from Spend tab). *(v0.96.0)*
- **BUG.011** — BUG.011: admin tiles navigate to their sections. *(v0.96.0)*
- **BUG.012** — BUG.012: admin tile counts are instance-scoped. *(v0.96.0)*
- **BUG.013** — BUG.013: System Health traffic lights restored under Admin. *(v0.96.0)*
- **BUG.014** — BUG.014: admin titles consistent. *(v0.96.0)*
- **BUG.015** — BUG.015: analysis results render as readable markdown. *(v0.96.3)*
- **BUG.016** — BUG.016: chat send is now a prominent button with wait hint. *(v0.96.3)*
- **BUG.017** — BUG.017: chat timeout handling improved (gunicorn 600s + friendly message). *(v0.96.3)*
- **BUG.018** — BUG.018: Actions section now loads (fixed missing import). *(v0.96.3)*
- **BUG.019** — BUG.019: vote button colors and counts update after voting. *(v0.96.6)*
- **BUG.020** — BUG.020: dashboard Ideas-by-stage chips are clickable (filter Ideas). *(v0.96.6)*
- **BUG.021** — BUG.021: most-voted and recent-runs rows are clickable. *(v0.96.6)*
- **BUG.022** — BUG.022: dashboard now shows most-commented ideas. *(v0.96.6)*
- **BUG.023** — BUG.023: prompt detail trend chart no longer shows redundant Ideas series. *(v0.96.6)*
- **BUG.024** — BUG.024: dashboard 500 fixed (comment_count -> comments_count). *(v0.96.8)*
- **BUG.025** — BUG.025: editing a paused prompt no longer resets to active (is_active now returned for instance admins). *(v0.96.8)*
- **BUG.026** — BUG.026: recent runs show full job details and link to idea. *(v0.96.13)*
- **BUG.027** — BUG.027: Secondary Analysis list shows human-readable labels instead of raw JSON keys. *(v0.96.17)*
- **BUG.028** — BUG.028: Chat error messages are user-friendly (strips ApiException prefix, retry button). *(v0.96.17)*
- **BUG.029** — BUG.029: Idea List shows "Analysis (N)" indicator for ideas with secondary actions. *(v0.96.17)*
- **BUG.030** — BUG.030: Dashboard comments prefixed with date; Most Commented shows "<IDEA-Number>: <Idea Title>"; ideas linked to detail. *(v0.96.17)*
- **BUG.031** — BUG.031: Dashboard Recent Runs shows "<IDEA Number>: <Title> <Prompt name> <Status> <timestamp> <duration>". *(v0.96.17)*
- **BUG.032** — BUG.032: Dashboard Recent Runs title no longer repeats idea title. *(v0.96.17)*
- **BUG.033** — BUG.033: Search field has Clear button. *(v0.96.17)*
- **BUG.034** — TEST.019/BUG.034: Voting rewritten — server-is-truth with loading spinner, no optimistic local state. *(v0.96.17)*
- **BUG.035** — BUG.034/BUG.035: Create new idea manually or by file upload (.md/.txt). *(v0.96.17)*
- **BUG.036** — BUG.036: Run full pipeline endpoint fixed (wrong import of _membership_allows_admin). *(v0.96.16)*
- **BUG.037** — BUG.037: VRIO validation schema fixed (min_length reduced). *(v0.96.17)*
- **BUG.038** — BUG.038: AI diagnosis of failures added (Diagnose button on failed runs). *(v0.96.17)*
- **BUG.039** — BUG.039: Change Status dropdown added to idea detail overview. *(v0.96.21)*
- **BUG.040** — BUG.040: Refresh button added to dashboard. *(v0.96.21)*
- **BUG.041** — BUG.041: Build and Scale tabs now show content for built ideas. *(v0.96.21)*
- **BUG.042** — BUG.042: BUILD_CODE results moved to Build tab (not Analysis). *(v0.96.21)*
- **BUG.043** — BUG.043: Brief/Design/Build tabs appear only once a result exists or is running; show "Running…" while in flight. *(v0.97.0)*
- **BUG.044** — BUG.044: idea detail auto-polls every 5s while a run is active and stops on completion. *(v0.97.0)*
- **BUG.045** — BUG.045: Activity refresh control is now a labelled button. *(v0.97.0)*
- **BUG.046** — BUG.046: "Run full pipeline" resumes from the current stage, skips existing Brief/Design, works on any non-terminal idea. *(v0.97.0)*
- **BUG.047** — BUG.047: Build tab gains confirm-write, runbook, one-click run (start/stop/open/logs), and a Tests tab. *(v0.97.0)*
- **BUG.048** — BUG.048: Scale tab gains "Suggest an improvement" / "Report a problem" child ideas. *(v0.97.0)*
- **BUG.049** — BUG.049: Scale tab gains release management (create/rename/target/delete, assign/move, bulk actions, pipeline run/stop, mark done, GitHub push). *(v0.97.0)*
- **BUG.050** — BUG.050: vote count now updates (was reading `net_score` instead of `net_votes`). *(v0.97.0)*
- **BUG.051** — BUG.051: Voting now works on both list and detail views (upvote and downvote). *(v0.98.0)*
- **BUG.052** — BUG.052/053/060/061 (reopened): instance scope is restored before the first `/me` request on session reload, and token refresh falls back to the persisted instance id. Expired Test admin sessions on Site 90 keep admin navigation, secondary actions and bulk status changes. *(v0.99.0)*
- **BUG.053** — BUG.053: Run full pipeline no longer shows "Admin access required" (instance context preserved in token refresh). *(v0.98.0)*
- **BUG.054** — BUG.054: Change status no longer returns 403 (instance context preserved in token refresh). *(v0.98.0)*
- **BUG.055** — BUG.055: Version selector added to Brief/Design/Build tabs (Jinja parity). *(v0.98.0)*
- **BUG.056** — BUG.056: Managed app Start button now reflects live state, logs display, Open app shows URL. *(v0.98.0)*
- **BUG.057** — BUG.057: Tests tab now has full Jinja parity (summary, run/diagnose/filter/add/per-test actions). *(v0.98.0)*
- **BUG.058** — BUG.058: Scale tab now has full Jinja parity (children, releases, pipeline, notes, AI settings, bulk actions). *(v0.98.0)*
- **BUG.059** — BUG.059: Page header no longer shown twice on idea detail. *(v0.98.0)*
- **BUG.062** — Human-readable Brief. On "Run full pipeline" for IDEA-10802, the Brief is not properly human readable <br><br>{<br>  "assumptions_risks": "Technical Dependencies: The success of CodeSynth relies on the accuracy and efficiency of the AI model for musical analysis and code generation. Risk Mitigation: Invest heavily in training data, explore different AI architectures, and conduct thorough testing. Third-Party Integrations: Potential integration with game engines (Unity, Unreal Engine) could introduce compatibility issues. Risk Mitigation: Prioritize integrations based on user demand and maintain close communication with engine developers. Assumptions: Users possess a basic understanding of programming concepts. Risk Mitigation: Provide clear tutorials and documentation to guide users through the code generation process.", *(outstanding)*
- **BUG.063** — Full pipeline continues past Design. On "Run full pipeline" for IDEA-10802,the pipeline stopped at Design *(outstanding)*
- **BUG.064** — Human-readable Design. On "Run full pipeline" for IDEA-10802, the Design is not properly human readable<br><br>{<br>  "api_contracts": "1. **POST /compositions:** Method: POST, Path: /api/v1/compositions, Request: JSON { ‘audio_file’: ‘url’ }, Response: JSON { ‘composition_id’: UUID }, Auth: API Key 2. **GET /compositions/{composition_id}:** Method: GET, Path: /api/v1/compositions/{composition_id}, Response: JSON { ‘composition’: {}, ‘analysis’: {} } , Auth: API Key 3. **POST /snippets:** Method: POST, Path: /api/v1/snippets, Request: JSON { ‘code’: ‘string’, ‘language’: ‘string’ }, Response: JSON { ‘snippet_id’: UUID }, Auth: API Key 4. **GET /users/{user_id}/subscriptions:** Method: GET, Path: /api/v1/users/{user_id}/subscriptions, Response: JSON { ‘tier’: {}, ‘usage_count’: integer } , Auth: API Key",<br>  "architecture": "The system will employ a microservices architecture. A frontend built with React will communicate with a backend API built using Python (Flask/FastAPI) for core logic and AI processing. An LSTM-based neural network, trained on musical data, will reside in a separate Docker container accessible via gRPC.  A PostgreSQL database will store user data, generated code snippets, musical compositions, and analysis results.  Third-party services like OpenAI's API (for potential future expansion) and a cloud storage service (AWS S3 or Google Cloud Storage) for storing large audio files will be integrated.",<br>  "build_notes": "1. *(outstanding)*
- **BUG.065** — Create Idea upload button works on web. The Create Idea / Upload .md/.txt button doesn't open an upload box *(outstanding)*
- **BUG.066** — Copy Open App URL or command. On Build tab, Open App should allow copy to clipboard.  Note that Open App may be either a URL or a command line *(outstanding)*
- **BUG.067** — Build logs display. On the Build tab, check that logs are working properly - they keep showing as blank *(outstanding)*
- **BUG.068** — Analysis count matches tabs. On "Run full pipeline" for IDEA-10802,the Ideas list view shows "Analysis (2)" but there is no Analysis tab (but there is a Brief and a Design) *(outstanding)*
- **BUG.069** — Debugging a failed job (Design Doc on IDEA-9263) gave the following error message<br><br>Failed to load: ApiException(0): Network error: ClientException: Failed to fetch, uri=/api/v1/ideas/f588be63-71bf-442f-8ba1-6a75e335a9ba. *(outstanding)*
- **BUG.070** — Bookkeeping: the live Stripe roadmap item is now RM-051, avoiding a clash with the shipped Guides request, and the old System settings tile wording request is recorded as BUG.070. *(v0.101.0)*
- **REQ.001** — REQ.001/REQ.002: user avatars (URL-based) with upload and display on admin/users. *(v0.96.7)*
- **REQ.002** — REQ.001/REQ.002: user avatars (URL-based) with upload and display on admin/users. *(v0.96.7)*
- **REQ.003** — REQ.003-REQ.008: Product Manager role, password reset, Prompts visibility gating, test user. *(v0.96.3)*
- **REQ.008** — REQ.003-REQ.008: Product Manager role, password reset, Prompts visibility gating, test user. *(v0.96.3)*
- **REQ.009** — REQ.009: more visible upvote/downvote controls (filled tonal buttons + larger count). *(v0.96.4)*
- **REQ.010** — REQ.010-REQ.014: user/admin/PM dashboard page with ideas-by-stage, most-voted, recent runs; rerun button on activity runs. *(v0.96.5)*
- **REQ.014** — REQ.010-REQ.014: user/admin/PM dashboard page with ideas-by-stage, most-voted, recent runs; rerun button on activity runs. *(v0.96.5)*
- **REQ.015** — REQ.015: admin can edit member name/email. *(v0.96.4)*
- **REQ.016** — REQ.016: user avatar upload (file upload to /static/avatars). *(v0.96.9)*
- **REQ.017** — REQ.017: paid instance guide upload (markdown, max 10 MB) via Settings > Guides. *(v0.96.11)*
- **REQ.018** — REQ.018: dashboard ideas-by-stage now a pie chart. *(v0.96.9)*
- **REQ.019** — REQ.019: most-voted shows voting details. *(v0.96.9)*
- **REQ.020** — REQ.020: most-commented shows latest comment. *(v0.96.9)*
- **REQ.021** — REQ.021: recent runs show job/provider/model/duration. *(v0.96.9)*
- **REQ.022** — Vote on comments. Allow voting on comments *(outstanding)*
- **REQ.023** — Comment votes on Dashboard for all roles. Include voting on comments on the Dashboard shown for all roles *(outstanding)*
- **REQ.024** — REQ.024: Analysis list shows first 3 lines of Exec Summary. *(v0.96.17)*
- **REQ.025** — REQ.025: Chat no longer starts with generic comment. *(v0.96.17)*
- **REQ.026** — REQ.026: Rerun creates V2 not V1. *(v0.96.17)*
- **REQ.027** — REQ.027: Shows COMPETITOR_ANALYSIS not COMPETITOR. *(v0.96.17)*
- **REQ.028** — REQ.028: Copy analysis output to clipboard. *(v0.96.17)*
- **REQ.029** — REQ.029: Refresh button on Activity/Recent Runs. *(v0.96.17)*
- **REQ.030** — REQ.030: Dashboard comments show user who posted. *(v0.96.21)*
- **REQ.031** — REQ.031: Idea title format updated (IDEA-number: Prompt title - first 2 lines). *(v0.96.21)*
- **REQ.032** — REQ.032: Pipeline running indicator on idea detail. *(v0.96.21)*
- **REQ.033** — REQ.033: Lifecycle actions (Brief/Design/Build) separated from secondary analysis. *(v0.96.21)*
- **REQ.034** — REQ.034: Run full pipeline available for all phases after spark. *(v0.96.21)*
- **REQ.035** — REQ.035: Idea numbers continue to lead Ideas list titles, and idea detail now uses the same format. *(v0.101.0)*
- **REQ.036** — REQ.036: Admin Activity → Recent Runs has an Idea number filter. Partial matches such as `9401` work alongside the existing outcome, job and model filters. *(v0.101.0)*
- **REQ.037** — REQ.037: Idea detail titles now show the idea number before the title, for example `IDEA-9401: Title check idea`. *(v0.101.0)*
- **REQ.038** — Bookkeeping: the v0.100.0 status-bar items were renumbered to REQ.038/REQ.039, the duplicated v0.96.21 release block was merged, and the roadmap regained RM-005. *(v0.101.0)*
- **REQ.039** — Bookkeeping: the v0.100.0 status-bar items were renumbered to REQ.038/REQ.039, the duplicated v0.96.21 release block was merged, and the roadmap regained RM-005. *(v0.101.0)*
- **RM-001** — Device CI maiden run (Chrome). Workflow now builds with `./scripts/build_web.sh`; a confirmed green GitHub Actions run is still required. *(outstanding)*
- **RM-002** — Coverage ratchet to 85%. Gate restored to 75% with tests for release and supervision wrappers; the ratchet to 85% remains. *(outstanding)*
- **RM-003** — GitHub flow CI coverage. Mocked push-flow tests always run; the optional Actions secret `CI_TEST_PAT` (exposed to tests as `GITHUB_TEST_PAT`) enables the CI-secret leg. The secret is now configured; live GitHub-flow coverage still needs test work. *(outstanding)*
- **RM-004** — OpenCode attach-mode auth. Investigate and fix LAN attach-mode auth: `OPENCODE_PASSWORD`/server password from `~/.config/opencode/service.json` is rejected by the v2 CLI client. Replace the current Ollama workaround for SHIP/SCALE once verified. *(outstanding)*
- **RM-005** — Bookkeeping: the v0.100.0 status-bar items were renumbered to REQ.038/REQ.039, the duplicated v0.96.21 release block was merged, and the roadmap regained RM-005. *(v0.101.0)*
- **RM-010** — Roadmap updated: RM-010 completed (cutover flip) and replaced by RM-013 for template removal after monitoring. *(v0.89.0)*
- **RM-011** — Roadmap reset to outstanding-only work with unique IDs and phased releases; added `ReleaseNotes.md`. Removed RM-011 (Tests tab) as already shipped in earlier releases (e.g. v0.77.0). *(v0.88.2)*
- **RM-012** — Roadmap cleanup: removed RM-012 (forgotten password flow) and RM-020 (multi-instance membership/switching) as already shipped in earlier releases. *(v0.89.0)*
- **RM-013** — **Flutter/legacy web cutover:** legacy Jinja web routes are now retired by default (`LEGACY_WEB_ENABLED=False`, returning 410). Set `LEGACY_WEB_ENABLED=True` to temporarily re-enable them while completing migration; Jinja template removal is tracked as follow-up work (RM-013). *(v0.89.0)*
- **RM-020** — Roadmap cleanup: removed RM-012 (forgotten password flow) and RM-020 (multi-instance membership/switching) as already shipped in earlier releases. *(v0.89.0)*
- **RM-040.1** — HOLD<br>Site Administrator should be able to configure default Guides for each phase, and this will apply across all instances.  On first configuration, this should be copied to all instances.  Instance administrator should be able to Guides should be. *(outstanding)*
- **RM-051** — Bookkeeping: the live Stripe roadmap item is now RM-051, avoiding a clash with the shipped Guides request, and the old System settings tile wording request is recorded as BUG.070. *(v0.101.0)*
- **RM-052** — Design documents now carry typed screen/entity/endpoint specs; legacy summaries are filled from them, and BUILD_CODE receives a capped "Design contract" section instead of a key-only analysis summary. *(v0.102.0)*
- **RM-053** — Build manifests are rejected by deterministic checks for unsafe paths, source files over 300 lines and TODO/FIXME/placeholder stubs, both at preview and before writing. *(v0.103.0)*
- **RM-054** — Generated builds ship a server-authored `AGENTS.md` with stack, layout, commands and editing rules, replacing any model-generated copy. *(v0.103.0)*
- **RM-055** — BUILD_CODE offers three selectable checkpoints (data/happy path, screens/routes, hardening); each narrows the prompt, records its stage, and extends the existing repo snapshot. *(v0.104.0)*
- **RM-056** — `num_ctx` is configurable on stage and release AI settings, forwarded to Ollama and local OpenCode sandbox runs, with documented VRAM trade-offs and a schema migration. *(v0.103.1)*
- **RM-057** — Added `docs/opencode-workflow.md` covering read-only planning, worktree isolation, checkpoint commits, fast checks, PR review, squash merge and cleanup; linked from `AGENTS.md`. *(v0.101.2)*
- **RM-058** — Decompose oversized brainstormer modules. `ideas.py` (2,311), `instances.py` (1,698), `ollama_tasks.py` (1,546), `build_runtime.py` (1,396). Extract cohesive helpers incrementally, target ~150–300 lines per module, URLs and behaviour unchanged. Keep the layer-based layout; do not restructure to feature-first (see `Guide_ProjectOverview.md`). Issue: #10 *(outstanding)*
- **RM-059** — API boundary schemas. Add Pydantic request/response schemas for key endpoints and extend `scripts/check_api_contract.py`. Preserve the `{success, data}` envelope; never mutate JSON columns in place. Issue: #11 *(outstanding)*
- **RM-060** — Guide deduplication. Follow up on RM-005: `Guides/` and `guidelines/` overlap. Keep one source of truth so agents and humans do not read conflicting instructions. Issue: #12 *(outstanding)*
- **RM-061** — Added black/isort/mypy pre-commit hooks and an advisory `fast-checks` CI job; required enforcement is tracked as RM-069 until the existing baseline is clean. *(v0.104.1)*
- **RM-062** — `main` is protected: PRs required, with `guardrails` and `drill` as required status checks. *(v0.101.2)*
- **RM-063** — Documented worktree isolation and `session_move` for agent sessions; the primary checkout, dev servers, DB and venv stay untouched. *(v0.101.2)*
- **RM-064** — One GitHub issue per outstanding R5 item, linked from its roadmap row, plus a PR template requiring `Closes #N`, scope checks, verification commands and release bookkeeping. *(v0.101.2)*
- **RM-065** — RM-065: removed the GitHub PAT embedded in the `origin` remote URL; git now authenticates through the `gh` credential helper. Added `scripts/check_no_credentials_in_config.py` to pre-commit and CI so credential-bearing remote URLs are rejected before they leak. *(v0.101.1)*
- **RM-066** — RM-066: untracked `certs/server.key` and `certs/server.crt` and added `certs/` to `.gitignore`; local TLS material is generated by `scripts/gen_certs.sh` and is never committed. *(v0.101.1)*
- **RM-067** — RM-067: the backup drill now runs with `--no-cov` so the narrow test suite is not failed by the global coverage gate. Both workflows now trigger on PRs and pushes to `main` only, removing duplicate CI runs. *(v0.101.1)*
- **RM-068** — CI: bandit fails on medium-severity findings only; nine reviewed intentional binds, local URL probes and `/tmp` paths carry explanatory `# nosec` annotations. Actions secret `CI_TEST_PAT` supplies the test token (exposed to tests as `GITHUB_TEST_PAT`), since GitHub reserves the `GITHUB_` prefix for secret names. The broken `safety check` gate was removed and is tracked as RM-068. Build-gate tests now isolate build roots explicitly, and the test runner forces `CI=1` regardless of the host environment. Added `playwright` to development requirements so the browser-test step can install Chromium in CI. *(v0.101.1)*
- **RM042** — RM042: full run from Spark to Build preview (instance admin only). *(v0.96.7)*
- **RM050** — HOLD. *(outstanding)*

## Additional comments

Decisions made in the agentic-readiness planning session (2026-11-27):

- **Bandit policy:** fail on medium and above; nine reviewed intentional findings carry `# nosec` annotations, low-severity cleanup remains outstanding.
- **TLS material:** `certs/` is generated locally by `scripts/gen_certs.sh` and is never committed.
- **Branch protection:** initially requires `guardrails` and `drill` only; Flutter checks are not yet required.
- **RM-052 compatibility:** typed design fields keep the legacy string fields populated so current document views and comments stay working.
- **Traceability:** each outstanding R5 item has a GitHub issue linked in its roadmap row; PRs close it with `Closes #N` and squash-merge.
- **Merge order:** CI repairs landed before the RM-065 release PR; stable tags mark known-good points before risky work.

## Decisions

Standing decisions that constrain delivery (do not relitigate without cause). Historical context lives in git history and prior release notes.

- **D-01 Tenancy:** single database with `instance_id`; server-side scoping enforces access, Postgres RLS is a defence-in-depth failsafe.
- **D-02 Provisioning:** copy-on-create from the template instance for config only; never copy keys or content.
- **D-03 Tokens:** JWT `instance_id` remains optional for legacy compatibility until the Flutter client is the only client; treat unscoped traffic as legacy.
- **D-04 Lifecycle:** skip-level moves allowed, no gates; Archive is reversible (restore to prior stage) and read-only for secondary actions.
- **D-05 Providers:** LiteLLM-based routing; budgets refuse-fast by default with explicit queue/degrade options where configured.
- **D-06 Backups:** backup before upgrades and prove by restore; no silent auto-pruning without an explicit, tested retention policy.
- **D-07 UI strategy:** retire legacy Jinja once Flutter parity is proven; avoid long-lived dual maintenance.
- **D-08 Integrations:** GitHub uses a per-instance PAT with direct push; Slack messaging is two-way.
- **D-09 Agentic builds:** generated apps ship a server-authored `AGENTS.md`, pass manifest lint, and derive run instructions in code; model prose never defines how to run a build.
- **D-10 Refactor strategy:** keep brainstormer's layer-based Flask layout; decompose oversized modules incrementally, never reorganise into feature folders.
- **D-11 GitHub flow:** `main` is protected and PR-only; work happens on short-lived issue-scoped branches in worktrees and lands via squash merge. The project Git rules override the global agent defaults.
