> **Status: Template.** Brainstormer has no social login or multi-tenancy today (auth is email/password with JWT + rotating refresh tokens). Apply this guide only if those capabilities are adopted, e.g. during replatforming. "BS baseline" means root `AGENTS.md`, `Guardrail.md`, and `PRD.md`.
>
> Implementing a secure multi-tenant social login system requires a decoupled architecture that bridges global identity with instance-scoped authorization. This guide details the unified standards for infrastructure, security, and database design to support seamless OAuth 2.0 integrations across multiple tenant environments.

## Core Architecture & Tenant Isolation

* **Context Resolution:** The system must definitively establish the tenant context before initiating the authentication flow via dynamic domain detection or explicit organizational identifiers at a centralized portal.
* **Identity Boundaries:** Utilize a shared global identity pool mapped strictly to isolated tenant profiles, ensuring the database engine enforces rigid data boundaries (RLS where supported — Postgres/Supabase; server-side tenant scoping otherwise, per the BS baseline `Guardrail.md`).
* **Architectural Baselines:** Align this infrastructure with the BS baseline (root `AGENTS.md`, `Guardrail.md`, `PRD.md`).

## Database Schema Design

To support dynamic credentials and delegated access, the schema must rigorously decouple the global authentication layer from tenant-specific authorization.

| Table | Primary Columns | Relationships & Constraints | Purpose |
| --- | --- | --- | --- |
| `tenants` | `id`, `domain_identifier`, `status` | **PK:** `id` | Core registry for each multi-tenant instance. |
| `tenant_oauth_configs` | `id`, `tenant_id`, `provider_name`, `encrypted_secret` | **FK:** `tenant_id`<br>

<br>**Unique:** `(tenant_id, provider_name)` | Stores dynamic social login credentials configured per tenant. |
| `users` | `id`, `email`, `global_subject_id` | **PK:** `id`<br>

<br>**Unique:** `email` | The single global social profile bridging across all allowed instances. |
| `tenant_users` | `id`, `tenant_id`, `user_id` | **FK:** `tenant_id`, `user_id`<br>

<br>**Unique:** `(tenant_id, user_id)` | Junction granting a global user access to a specific instance. |
| `tenant_roles` | `id`, `tenant_id`, `role_name`, `permissions` | **FK:** `tenant_id`<br>

<br>**Unique:** `(tenant_id, role_name)` | Custom RBAC roles managed by specific instance administrators. |
| `tenant_user_roles` | `tenant_user_id`, `role_id` | **FK:** `tenant_user_id`, `role_id` | Maps a user's specific instance profile to an instance-scoped role. |

## OAuth 2.0 & Dynamic Credentials

* **Dynamic Client Management:** Store social provider credentials dynamically within `tenant_oauth_configs`. Ensure application client secrets are encrypted at rest (e.g., AES-256-GCM) with decryption keys managed via a dedicated secrets manager.
* **State & PKCE Enforcement:** Mandate Proof Key for Code Exchange (PKCE) for public clients, and use it by default for confidential server-side clients too (current OAuth best practice). Utilize the OAuth `state` parameter to securely pass and verify the user's tenant context through the redirect lifecycle.
* **Global Identity Mapping:** Map the immutable `sub` claim returned by the social provider's OIDC token to the `global_subject_id` in the `users` table. This acts as the single source of truth, persisting the identity even if the user updates their provider-level email address.
* **Account Linking:** Define up-front what happens when an OAuth email matches an existing password account: require verified-email match plus explicit user confirmation before linking; never silently merge accounts or elevate privileges on first social login.
* **Token Strategy:** After successful social login, mint the project's standard session tokens (in Brainstormer terms: short-lived JWT access + rotating DB-backed refresh per `Guardrail.md`) rather than propagating provider tokens to clients.

## Instance-Level RBAC & Governance

* **Delegated Administration:** Scope the `tenant_roles` table exclusively by `tenant_id`. This empowers instance administrators to freely define, edit, and assign roles without bleeding into the global application schema or affecting other tenants.
* **Just-in-Time (JIT) Onboarding:** Map incoming OIDC claims to automate `tenant_users` account creation and schema assignment dynamically during a user's first successful social login into a specific instance. Default new JIT users to the least-privileged role; elevation requires instance-admin action.
* **Migrating from the Current Schema:** Brainstormer's existing `users` table (single-tenant `role`, unique `email`) maps to the global identity layer: add `global_subject_id` (nullable for existing password users, backfilled on first link), introduce `tenants` + `tenant_users` + `tenant_roles` without altering existing login behaviour, and keep current JWT/refresh mechanics unchanged for password users.
* **Granular Telemetry:** Implement real-time, server-side logging for all authentication events, strictly tagging each event with its corresponding `tenant_id`. Feed this structured data into operational dashboards to monitor tenant-specific performance and identify authentication anomalies. Never log tokens, codes, or PII.
* **Granular Telemetry:** Implement real-time, server-side logging for all authentication events, strictly tagging each event with its corresponding `tenant_id`. Feed this structured data into operational dashboards to monitor tenant-specific performance and identify authentication anomalies.