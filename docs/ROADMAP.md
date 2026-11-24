# Brainstormer — Roadmap

**Single source of truth for outstanding work.** Update on every build: add new items, refine scope, and remove items only when released (record them in `ReleaseNotes.md`).
**Version:** 0.98.0 · **Date:** 2026-11-24 · **Branch:** `main`

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
| RM-001 | blocked | **Device CI maiden run (Chrome)** | `flutter-integration-chrome` job exists in `guardrails.yml` but has not had a confirmed green run. Unblock by running/watching the job and fixing any environment or test issues until green. |
| RM-002 | planned | **Coverage ratchet to 85%** | Raise and hold backend coverage from the current baseline toward ≥85% without reducing the existing gate; add targeted tests on touched/under-covered paths. |
| RM-003 | planned | **GitHub flow CI coverage** | Add or enable tests for the GitHub push flow in CI using a configured PAT/secret; currently skipped without secrets. Document required CI secrets. |
| RM-004 | planned | **OpenCode attach-mode auth** | Investigate and fix LAN attach-mode auth: `OPENCODE_PASSWORD`/server password from `~/.config/opencode/service.json` is rejected by the v2 CLI client. Replace the current Ollama workaround for SHIP/SCALE once verified. |
| RM-005 | planned | **Housekeeping: untracked/stale artefacts** | Decide and act on stale/untracked items (e.g. `TODOS.md`, `docs/APPLICATION_DOCUMENTATION.md`, stray images, duplicate/pasted guide files): archive, refresh, or remove so the working tree is intentional. |

## R2 — Product and UX

| ID     | Status  | Item                              | Notes / acceptance                                                                                                                                        |
| ------ | ------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RM-013 | planned | **Remove legacy Jinja templates** | After the Flutter cutover has been monitored with no P1 regressions, delete the retired Jinja templates/routes and related assets to end dual maintenance. |

## R3 — Accounts and tenancy

_No outstanding items._

## R4 — Operations (external / manual)

| ID     | Status  | Item                         | Notes / acceptance                                                                                                                                                                                                                |
| ------ | ------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RM-030 | planned | **Live Stripe billing loop** | Operational setup: configure real Stripe plans mapped to entitlement keys and verify the test/staging grant → gate → revoke loop. Primarily admin/configuration work; track any small code fixes discovered as separate RM items. |


## Release Unassigned — 

| ID       | Item               | Notes / acceptance                                                                                                                                                                                                                                                                                         |
| -------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RM-040.1 | **Default Guides** | HOLD<br>Site Administrator should be able to configure default Guides for each phase, and this will apply across all instances.  On first configuration, this should be copied to all instances.  Instance administrator should be able to Guides should be                                                |
| RM050    | Updated README     | HOLD                                                                                                                                                                                                                                                                                                       |
| BUG.010  |                    | HOLD<br>If AI Provider Spend tab is different from AI Providers / Configure / Monthly budgets, then remove the duplication                                                                                                                                                                                 |
| REQ.022  |                    | HOLD<br>Allow voting on comments                                                                                                                                                                                                                                                                           |
| REQ.023  |                    | HOLD<br>Include voting on comments on the Dashboard shown for all roles                                                                                                                                                                                                                                    |




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
