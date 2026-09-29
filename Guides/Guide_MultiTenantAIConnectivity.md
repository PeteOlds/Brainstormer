> **Status: Template.** Brainstormer today calls local Ollama directly (`app/services/ollama_client.py`) with no proxy, no virtual keys, and no per-tenant billing. Apply this guide only if multi-tenant hosted-model routing is adopted. "BS baseline" means root `AGENTS.md`, `Guardrail.md`, and `PRD.md`.

## Best Practice Guide: Multi-Tenant AI Connectivity & Cost Management

To successfully manage a multi-tenanted application where each instance connects to a distinct AI provider and code access is restricted, the architecture must completely decouple AI routing from the application codebase. This requires dynamic configuration, rigorous isolation protocols, and real-time observability.

### 1. Architecture & Dynamic Provider Routing

* **Database-Driven Configuration:** Expose an administrative UI panel for each tenant instance to select their preferred AI provider (e.g., OpenAI, Anthropic, local Ollama) and input their specific credentials. Store these configurations and API keys securely using a dedicated secrets manager or encrypted database fields.
* **Centralized LLM Proxy:** Deploy an abstraction proxy (such as LiteLLM) backed by a relational database like PostgreSQL. Instead of writing custom formatting logic for every provider, your backend routes all requests to this internal proxy, which standardizes the API calls and handles the complex downstream routing based on the tenant's stored configuration. (BS bridge: keep the existing `OllamaClient` as one provider implementation behind the proxy interface, so local Ollama remains a first-class route rather than a special case.)
* **Local vs Hosted Paths:** Local models (Ollama) incur no token costs — skip spend logging for them but keep request tagging, so telemetry stays uniform. Token/cost math below applies to hosted providers only. Preserve the existing JSON-mode + schema-validation guarantees on every route, including proxy-routed ones.
* **Structured Request Tagging:** Tag every outgoing API request with custom metadata identifying the instance ID, user ID, project, and environment. The proxy intercepts these tags and writes them to the database, forming the foundation for granular, per-tenant querying and billing.

### 2. Security & Tenant Isolation

* **Virtual Key Provisioning:** Instead of relying on raw provider keys in application memory, issue unique Virtual Keys for each tenant instance via the proxy. The proxy maps this Virtual Key to the instance's preferred downstream provider while completely abstracting the underlying credentials. Record tenant-specific routing parameters in the project's configuration store (per the BS baseline secret-management rules — encrypted at rest, never in prompts or logs).
* **Data Loss Prevention (DLP):** Integrate a governance layer at the proxy level (using tools like AWS Bedrock Guardrails, Google Cloud DLP, or Nightfall). This automatically detects and masks sensitive Personally Identifiable Information (PII) before the prompt ever reaches the external AI providers, ensuring cross-tenant data privacy and enterprise compliance.

### 3. Cost Logging & Visibility for Administrators

* **Real-Time Spend Logging:** Utilize the proxy’s database integration to capture the precise cost of every request. The system must calculate this by extracting the exact token usage returned by the provider and multiplying it by real-time model pricing tables.
* **Budgets and Automated Guardrails:** Assign specific token or dollar-value budgets directly to each tenant's Virtual Key. Configure automated guardrails to trigger administrative alerts (via email or webhook) at 70% budget utilization, and enforce a hard network cutoff at 100% to prevent runaway billing cycles. Define the cutoff behaviour explicitly per tenant: refuse new requests with a clear error, queue them for admin release, or degrade to a local model — never fail silently or partially bill a request.
* **Instance-Level Dashboards:** Expose a dedicated cost dashboard within each tenant's admin UI. By querying the proxy's backend using the specific instance ID tag, the application displays isolated, real-time metrics showing prompt tokens, completion tokens, and total daily spend without exposing other tenants' usage data.

### 4. Advanced Cost Optimization & Telemetry

* **Handling Streaming Telemetry:** If your application streams responses to the user to improve perceived latency, standard cost headers are often missed. To ensure accurate billing, pass `stream_options: {include_usage: true}` in the initial payload. Extract the token usage from the final streamed chunk, or utilize the proxy's asynchronous backend callbacks to accurately log the cost after the connection closes.
* **Prompt Caching:** Implement semantic or exact-match caching within the proxy layer. By caching frequent or identical queries (keyed by the sanitized prompt and model parameters), repeated requests from the same instance can be served locally from the cache. This significantly reduces latency and bypasses provider token costs entirely. Cache keys and entries are tenant-scoped: never serve one tenant's cached output to another, and exclude PII-containing prompts from shared caches.