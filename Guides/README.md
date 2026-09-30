# Guides Index

This directory holds the shared guides and patterns used by **Brainstormer (BS)** and maintained as a **reusable template library** for future projects and the planned replatforming. The guides are deliberately generalised — **not every guide applies to every project**.

## Key terms

- **BS** = Brainstormer. Where a guide says "check the BS baseline", it means the Brainstormer project baseline: `AGENTS.md` (root), `Guardrail.md` (root), and `PRD.md` (root) for V1 work, or `PRD_V2.md` (root) for V2 (multi-tenant / multi-provider / Flutter) work. When reusing these guides as templates in another project, substitute that project's own baseline documents.
- **Canonical project standards** always win on conflict: root `AGENTS.md` (venv layout, black/isort/mypy, pytest) and `Guardrail.md` (security controls). If a guide disagrees with them, follow `AGENTS.md`/`Guardrail.md` and raise the discrepancy.

## Status labels

Each guide carries a status header:

| Status | Meaning |
|---|---|
| **Adopted** | Applies to Brainstormer today. Follow it now. |
| **Aspirational** | Not yet implemented in Brainstormer but planned (e.g. replatforming targets). Use for new work only where noted. |
| **Template** | Reusable pattern for future/greenfield projects. Does not describe Brainstormer as-built. |

## Guide catalogue

| Guide | Status | Applies to Brainstormer today? |
|---|---|---|
| `Guide_ProjectOverview.md` | Adopted (with BS deltas) | Yes — architecture rules, AI interaction, backend contract |
| `Guide_Python.md` | Adopted (with BS deltas) | Yes — with project tooling (`venv/`, black/isort/mypy) |
| `Guide_Database.md` | Adopted (with BS deltas) | Yes — ORM-first, SQLite/Postgres, safe migrations |
| `Guide_SecurityBasic.md` | Adopted | Yes — complements `Guardrail.md` (which remains authoritative) |
| `Guide_Upgrades.md` | Adopted (selectively) | Container, migration, and rollback practices — yes; Flutter/Supabase-specific tooling — no (see Aspirational) |
| `Policy_Privacy.md` | Template (placeholder) | No — placeholder text; tailor + legal review before any release relies on it (required gate before any hosted-AI or social-login rollout per `PRD_V2.md` §12) |
| `Guide_Flutter.md` | Adopted | Yes — the `flutter/` client (Riverpod, dumb widgets, tokens) |
| `Guide_UITesting.md` | Adopted | Yes — pytest owns API behaviour; widget/golden/integration in `flutter/test/` |
| `Guide_SocialLogin.md` | Adopted-for-V2 (Template otherwise) | V2 only — social login + multi-tenancy per `PRD_V2.md` §4; no social login in V1 |
| `Guide_MultiTenantAIConnectivity.md` | Adopted-for-V2 (Template otherwise) | V2 only — proxy, virtual keys, budgets per `PRD_V2.md` §7; V1 calls local Ollama directly |

## Conventions used across guides

- Python virtual environment: `venv/` (activate with `source venv/bin/activate`).
- Formatting/linting/typing: `black`, `isort`, `mypy`.
- Tests: `pytest` (see root `pyproject.toml` for coverage gates).
- Secrets: `.env` (gitignored) + `.env.example`. Never commit secrets; never store them under `docs/`.
- Spelling: New Zealand English.
