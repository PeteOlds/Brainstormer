# Brainstormer — Roadmap

**Single source of truth for outstanding work.** Update on every build: add new items, refine scope, and remove items only when released (record them in `ReleaseNotes.md`).
**Version:** 0.100.0 · **Date:** 2026-11-25 · **Branch:** `main`

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
| RM-003 | blocked | **GitHub flow CI coverage** | Mocked push-flow tests always run; the optional `GITHUB_TEST_PAT` secret enables the CI-secret leg. Configure the repository secret to unblock. |

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
| REQ.035 | planned | **Idea number before title** | On the Idea tab show the Idea Number before  the title |
| REQ.036 | planned | **Idea filter on Admin Activity** | On Admin Activity Recent Runs, add Idea to the existing options (Outcomes, Jobs, Models) |

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
| RM-030 | planned | **Live Stripe billing loop**      | Operational setup: configure real Stripe plans mapped to entitlement keys and verify the test/staging grant → gate → revoke loop. Primarily admin/configuration work; track any small code fixes discovered as separate RM items. |

## Release Unassigned — no phase

| ID       | Item               | Notes / acceptance                                                                                                                                                                                                                                          |
| -------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RM-040.1 | **Default Guides** | HOLD<br>Site Administrator should be able to configure default Guides for each phase, and this will apply across all instances.  On first configuration, this should be copied to all instances.  Instance administrator should be able to Guides should be |
| RM050    | Updated README     | HOLD                                                                                                                                                                                                                                                        |
| BUG.010  |                    | HOLD<br>If AI Provider Spend tab is different from AI Providers / Configure / Monthly budgets, then remove the duplication                                                                                                                                  |
| BUG.069  |                    | Debugging a failed job (Design Doc on IDEA-9263) gave the following error message<br><br>Failed to load: ApiException(0): Network error: ClientException: Failed to fetch, uri=/api/v1/ideas/f588be63-71bf-442f-8ba1-6a75e335a9ba                           |
| REQ.037  |                    |                                                                                                                                                                                                                                                             |

---

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
