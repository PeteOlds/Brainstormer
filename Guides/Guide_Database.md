
> **Status: Adopted (with BS deltas).** Applies to Brainstormer today: SQLAlchemy + Flask-Migrate (Alembic), SQLite locally, PostgreSQL in production. "BS baseline" means root `AGENTS.md`, `Guardrail.md`, and `PRD.md`. On conflict, `AGENTS.md`/`Guardrail.md` win.

This document defines the constraints and best practices for all database-related code, schema design, and migration generation in this repository. All automated agents and developers must strictly adhere to these rules before modifying database states or writing query logic.

## 1. Core Architectural Principles

* **ORM / Abstraction First:** Never write raw, engine-specific SQL strings for standard CRUD operations. All database interactions must be routed through the project's established ORM or query builder (e.g., Prisma, Drizzle, SQLAlchemy) to ensure dialect abstraction.
* **Parameterized Queries Only:** If raw SQL is completely unavoidable for a complex query, it must use strict parameterization. String concatenation or template literals for SQL variables are strictly forbidden to prevent SQL injection.
* **Single Source of Truth:** The database schema is the ultimate source of truth. All application-level types, models, and API payloads must be generated from or strictly mirror the database schema definitions.
* **Separation of Concerns:** Business logic must not reside in the database layer. Avoid using database triggers, stored procedures, or complex engine-specific functions unless explicitly authorised for a highly specific performance optimisation. Prefer ORM-level event listeners / hooks (e.g. SQLAlchemy event listeners, as used for vote and comment counters) when derived state must stay in sync — they remain portable across SQLite and PostgreSQL.
* **JSON Columns:** Where the ORM maps a JSON column type (`db.JSON`), treat documents as immutable values: build a fresh document and assign it rather than mutating nested keys in place, or the ORM's change tracking will skip the UPDATE. Querying inside JSON documents is engine-specific by nature — isolate such queries in repository/service functions and never inline engine operators in business logic.

## 2. Cross-Platform Compatibility (SQLite & PostgreSQL)

Code must be designed to run locally on SQLite for rapid development and on PostgreSQL (or Supabase) in production.

* **Strict ANSI SQL:** Adhere entirely to ANSI standard SQL. Do not use MySQL-specific string formatting, SQLite-specific pragmas, or Postgres-specific operators (like `->>`) directly in business logic.
* **Timestamp Standardisation:** All dates and times must be stored as UTC. When interacting with SQLite, ensure timestamps are serialised as ISO-8601 strings to prevent time-zone offset bugs when migrating to PostgreSQL's native `TIMESTAMPTZ`. (BS: SQLite returns naive datetimes — always compare via `ensure_aware()`; see `app/models/types.py`.)
* **Primary Keys:** Use standardised UUIDs (v4 or v7) for primary keys whenever possible to ensure uniform behavior across distributed systems and offline-first mobile synchronisation, avoiding auto-increment discrepancies between engines. (BS: use the `GUID` TypeDecorator, `app/models/types.py`.)
* **Boolean Normalisation:** Ensure the ORM layer explicitly handles boolean coercion, as SQLite stores these as integers (0/1) while PostgreSQL utilises a strict `BOOLEAN` type.

## 3. Zero-Downtime Migrations & Data Safety

* **The Expand-and-Contract Pattern:** Schema changes on populated tables in production must be backward compatible. To modify an existing column, you must:
1. **Expand:** Create the new column/table.
2. **Migrate Code:** Update the application to write to both, but read from the new.
3. **Backfill Data:** Copy historical data to the new structure.
4. **Contract:** Remove the old column in a subsequent, completely separate release.

> Small additive changes (new nullable columns, new tables, new indexes) do not require the full pattern — one migration is fine. The pattern is mandatory for destructive or reshaping changes on tables with production data. See `Guide_Upgrades.md` §5 for the complementary rule: in production, prefer rolling forward over rolling back the database.


* **No Destructive Operations:** Never combine a `DROP` or `ALTER` constraint with structural additions in the same migration file. Destructive actions must be isolated and require explicit human sign-off.
* **Mandatory Rollbacks:** Every "up" migration script must be accompanied by a "down" script that reverses the schema change without corrupting data. Verify both directions in CI (`upgrade` then `downgrade`) before merging. (Note the production preference for roll-forward over rollback in `Guide_Upgrades.md` §5 — down scripts are a development/CI safety net, not the production recovery strategy.)
* **Default Values for Constraints:** If adding a `NOT NULL` constraint to an existing table, you must provide a `DEFAULT` value to prevent immediate migration failures on tables containing existing rows.

## 4. AI Guardrails

When generating code, analyzing schemas, or proposing data structural changes, AI agents must observe the following constraints:

* **Stop and Ask:** Before generating any migration file or executing CLI commands that alter the database state, you must explicitly detail the proposed schema changes and wait for human approval.
* **Review BS Baseline:** Always check the BS baseline (`AGENTS.md` "Architecture Notes" and "Lessons Learned", `docs/erd.md`) for domain-specific requirements regarding data limits, acceptable null states, or relational mapping before designing a new table.
* **Enforce Typing:** When generating models or APIs, strictly map database types to the corresponding TypeScript/Python/Dart types, ensuring nullability in the database matches optionality in the code.
* **No Speculative Indexing:** Do not generate complex composite indexes unless directly instructed or required to resolve an identified performance bottleneck. Stick to indexing foreign keys and uniquely constrained columns.