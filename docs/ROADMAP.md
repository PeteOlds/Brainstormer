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
| RM-052 | planned | **Typed design contract for codegen** | `DesignDocOutput` is currently all plain strings, so the BUILD_CODE turn must hold unstructured prose in an ~8k-char context. Add typed `screens`, `entities`, `endpoints` (and keep the existing string fields for stored manifests), update `design_doc.txt` and `build_code.txt` to consume them. Acceptance: existing manifests still validate; schema tests cover both shapes. |
| RM-053 | planned | **Deterministic build manifest lint** | Before confirm, reject manifests with unsafe/absolute paths, per-file line count over ~300, TODO/placeholder stubs, or missing runbook. Follow the `scripts/check_no_external_calls.py` pattern; give actionable errors. Model-described checks (`BuildTest`) are not a gate. |
| RM-054 | planned | **Server-authored `AGENTS.md` in generated builds** | Emit a concise AGENTS.md (stack, layout, naming, test/run commands) into the manifest from server-side code, never model prose. Include it in incremental "EXISTING PROJECT FILES" builds so later agentic fixes stay within contract. |
| RM-055 | planned | **Vertical BUILD_CODE checkpoints** | Replace the single 25-file/60k-char turn with staged slices — schema + data + happy-path test, then UI/routes, then polish — reusing the parent/child idea flow. Keep a single-shot path for small builds. Acceptance: each checkpoint verifies before the next starts. |
| RM-056 | planned | **Local context / VRAM tuning** | `_generation_options` sets temperature/top_p/repeat_penalty/num_predict only. Make `num_ctx` configurable per provider/stage, forward it through Ollama options and OpenCode, and document context-versus-VRAM trade-offs. No silent huge-context runs on small models. |
| RM-057 | planned | **Documented OpenCode + GitHub workflow for brainstormer** | Record: read-only planning → fresh session per task → short-lived branch or worktree → thin end-to-end slice → fast checks → atomic semantic commit at each verified checkpoint → PR → squash merge. Project `AGENTS.md` "no pushes to `main`" overrides the global default; say so explicitly. Keep root `AGENTS.md` concise; put detail in a dedicated doc rather than inflating agent context. |
| RM-058 | planned | **Decompose oversized brainstormer modules** | `ideas.py` (2,311), `instances.py` (1,698), `ollama_tasks.py` (1,546), `build_runtime.py` (1,396). Extract cohesive helpers incrementally, target ~150–300 lines per module, URLs and behaviour unchanged. Keep the layer-based layout; do not restructure to feature-first (see `Guide_ProjectOverview.md`). |
| RM-059 | planned | **API boundary schemas** | Add Pydantic request/response schemas for key endpoints and extend `scripts/check_api_contract.py`. Preserve the `{success, data}` envelope; never mutate JSON columns in place. |
| RM-060 | planned | **Guide deduplication** | Follow up on RM-005: `Guides/` and `guidelines/` overlap. Keep one source of truth so agents and humans do not read conflicting instructions. |
| RM-061 | planned | **Fast lint/typecheck feedback in CI** | `guardrails.yml` runs pytest, guardrail scripts and UI gates, but not black/isort/mypy. Add quick format/type checks so agentic edits fail fast before the slow suite. Complements RM-002. |
| RM-062 | planned | **Protect `main`** | Enable branch protection on GitHub: require a PR before merge and require the `guardrails` status checks to pass; no direct pushes. Both workflows already trigger on `pull_request` and all branch pushes, so enforcement is the only missing piece. Needs repo admin access. |
| RM-063 | planned | **Worktree isolation for agent sessions** | Document `git worktree add ../brainstormer-<RM-id> -b feat/RM-052 main`, moving the OpenCode session into that directory with `session_move`, testing there, and removing the worktree after merge. Keeps the primary checkout, dev servers, DB and venv untouched; avoids the broken `git stash`. |
| RM-064 | planned | **Issue-driven slices and small PRs** | One GitHub issue per RM item with acceptance criteria; reference the issue in the Stage 1 plan prompt and close it with `Closes #N` in the PR. Keep diffs under ~400–500 lines, squash-merge, delete the branch, and tag `vX.Y.Z-stable` before risky refactors or dependency upgrades. |

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

Guidance applied to both generated apps and brainstormer itself. These are standing principles, not work items; the work is tracked as RM-052–RM-064.

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
