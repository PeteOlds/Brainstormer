### Overall Project Guide

> **Status: Adopted (with BS deltas).** This guide applies to Brainstormer today. "BS baseline" means the Brainstormer project baseline: root `AGENTS.md`, `Guardrail.md`, and `PRD.md`. When reusing this guide as a template, substitute the target project's own baseline documents. On any conflict, `AGENTS.md`/`Guardrail.md` win.
>
> **Applicability:** Sections referencing Flutter/Dart are **Aspirational** (current frontend is Jinja2 + Alpine.js) and apply only if/when a Flutter client is built. The backend-contract principles apply regardless of client.

This guide defines the foundational architecture, repository management, and AI interaction rules for the project.

**1. System Architecture & AI Guardrails**

* **Establish an AI Rulebook (`AGENTS.md`):** LLMs drift without constraints. Maintain an `AGENTS.md` file in your repository root to define strict coding standards (e.g., "Always use `const` constructors," "No new packages without approval"). This acts as the AI's memory and enforces brevity by preventing hallucinated boilerplate.
* **Agentic Execution:** Utilize Model Context Protocol (MCP) to manage multi-file code generation and repository-wide refactoring smoothly.
* **Limit Context Windows:** Provide the AI with hyper-focused context. Do not prompt the AI to build an entire app in one go. Use an incremental loop: Domain Model ➔ Logic ➔ UI ➔ Review.

**2. Project Structure**

> **BS delta:** Brainstormer as-built uses **layer-based** modules (`app/models`, `app/routes`, `app/services`, `app/utils` — see root `AGENTS.md`), not feature folders. The feature-first pattern below is the **template default for new (especially Flutter) projects** and for replatforming targets. Do not restructure the existing Flask app to match it.

Organize new codebases by feature rather than by layer (e.g., `models`, `views`, `controllers`). This isolates context for AI tools, preventing them from hallucinating dependencies across unrelated domains and keeping file modifications brief.

* **Structure Pattern:**
```text
lib/
  features/
    authentication/
      auth_page.dart
      auth_controller.dart
      auth_service.dart
      auth_model.dart
  core/
    network/
    theme/

```


* **Configuration:** For baseline environment variables and foundational setup, see the BS baseline (`AGENTS.md`, `Guardrail.md`, and `.env.example` in the repository root).

**3. API Integration (Python Backend)**

> **Aspirational for Flutter clients; principle applies to all clients:** keep a single networking layer with token-refresh and error parsing, and validate strict domain models before building UI on them.

* **Domain Models First:** When interfacing with your Python backend, always have the AI generate and validate strict domain models and JSON serialization (Dart: `freezed` or `json_serializable`) before generating any UI. This ensures the client–server contract remains rigid and strongly typed. For the current web frontend, the equivalent is the `{success, data}` response envelope (see `docs/APPLICATION_DOCUMENTATION.md` §4).
* **Centralized Networking:** Create a single networking client in your `core/network` directory to handle interceptors, token refresh logic, and error parsing. Instruct the AI to route all requests through this client rather than instantiating raw `http` calls across various services. (Current web equivalent: the `authFetch` wrapper in `app/templates/base.html`.)

