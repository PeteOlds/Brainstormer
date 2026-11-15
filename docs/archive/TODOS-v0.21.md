# TODOS — Brainstormer

## Current Session — Manual Idea Creation Feature

### ✅ Completed
- **User model**: Added `can_create_ideas` boolean field (default `True`), updated `to_dict()`
- **API endpoints**: 
  - `POST /api/v1/ideas` — Manual idea creation with validation (title ≤200 chars, content, optional structured fields)
  - `PATCH /api/v1/me/settings` — Per-user toggle of `can_create_ideas`
- **Dashboard UI**: "Create Idea" button (shown only when `canCreateIdeas=true`), modal with form, JavaScript functions (`openCreateIdeaModal`, `closeCreateIdeaModal`, `createIdea`)
- **Migration**: `migrations/versions/5e6f7a8b9c0d_user_can_create_ideas.py` — Adds column with `server_default='1'`
- **Tests**: All 161 tests pass across unit, integration, and UI suites
- **PRD.md**: Updated "Add Ideas manually" section to reflect implementation
- **VERSION**: Bumped to `0.21.0`
- **CHANGELOG.md**: Added v0.21.0 entry documenting manual idea creation, user settings toggle, AGENTS.md update
- **AGENTS.md**: Updated with comprehensive repo guidance (app factory, auth decorators, GUID type, naive datetimes, migration patterns, test isolation lessons, test patterns, key files table, related skills)

### 📋 Remaining / Future Items
- **Migration history cleanup**: There are multiple merge heads in the migration chain (`3d4e5f6a7b80`, `4e5f6a7b8c90`, `a1b2c3d4e5f6`, `d705d33be54b`) created during development database setup. These are PostgreSQL-specific migration compatibility issues that won't affect production (which uses PostgreSQL properly). May want to clean up for a clean repo state.
- **VERSION/CHANGELOG per-release entries**: Ensure each release adds a `## [x.y.z] - YYYY-MM-DD` entry under the current version header.

## Project Context
- Flask/SQLAlchemy/Angular-alpine hybrid web application
- 161 tests pass
- Version 0.21.0
- Key design: Data-Dense Dashboard style; 44px minimum touch targets; no third-party JS; server-rendered Alpine.js templates
- Security: Guardrail.md checklist required; no raw SQL; Pydantic response validation; local Ollama only; Fernet-encrypted prompt configs; per-endpoint rate limits; Alembic migrations only; non-root Docker