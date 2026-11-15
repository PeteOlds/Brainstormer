> **Status: Adopted.** Applies to Brainstormer today. This guide complements root `Guardrail.md`, which remains authoritative on security and privacy. On any conflict, `Guardrail.md` wins. "BS baseline" means root `AGENTS.md`, `Guardrail.md`, and `PRD.md`.

## 1. Requirements and Threat Modeling

* **Define Intent:** Always begin with a clear outline or Product Requirements Document (PRD) to define user roles and data structures before prompting AI agents.
* **Assume Broad Access:** AI models may grant admin-level permissions by default; proactively scope agent access to specific repositories using the principle of least privilege.
* **Establish Guardrails:** Never share credentials, API keys, or sensitive customer data in prompts, as they can become part of the model’s training data or get leaked.

## 2. Secure Code Generation

* **Manage Secrets:** Explicitly instruct the AI to use environment variables for all sensitive configuration instead of hardcoding keys in the frontend.
* **Validate Inputs:** Require the AI to generate strict server-side validation and sanitization for all user inputs to prevent injection attacks (like SQLi or XSS).
* **Enforce Access Control:** Do not trust AI-generated authentication logic blindly; manually verify that server-side checks exist for privileged actions. Where the database supports Row Level Security (Postgres/Supabase), enable RLS as a failsafe — but note SQLite has no RLS, so server-side checks (per `Guardrail.md`) are the enforcement layer on the local path, not an optional extra.

## 3. Testing and Verification

* **Maintain AGENTS.md:** Keep the root `AGENTS.md` file current to enforce baseline security standards and rules for AI coding tools to follow.
* **Beware of Hallucinations:** AI agents can invent non-existent, "hallucinated" dependencies. Manually verify all imported packages on official registries to prevent supply chain compromise.
* **Automate Scanning:** Run basic Static Application Security Testing (SAST) tools or extensions (e.g., Snyk, Semgrep) to catch vulnerable patterns in the generated output before committing.

## 4. Deployment and Infrastructure

* **Separate Setup Context:** Keep setup and configuration instructions in `AGENTS.md` ("Commands") and `docs/install-config.md` to limit the operational context exposed to the AI agent.
* **Secure Defaults:** Review generated configurations to ensure HTTPS is enforced and appropriate security headers (like Content-Security-Policy) are included.
* **Continuous Patching:** Regularly update dependencies and use automated tools to monitor for newly discovered vulnerabilities in the packages your AI agent selected.

For additional foundational SDLC principles that complement these practices, see the BS baseline: root `AGENTS.md` and `Guardrail.md`.

## 5. Project Controls Checklist (Brainstormer)

Every change touching auth, input, or infrastructure must preserve these controls (details in `Guardrail.md`):

* JWT on all API routes except health and login/register; role checks on privileged actions.
* Pydantic (or equivalent) validation at input boundaries; ORM-only queries, no raw SQL.
* Fernet-encrypted prompt bodies; secrets from `.env` only.
* Rate limits (login, run-now, actions, votes, default) via Flask-Limiter + Redis.
* No external network calls from the app path (local Ollama only); no PII in logs.
* `bandit` + `safety` + pytest coverage gate in CI.