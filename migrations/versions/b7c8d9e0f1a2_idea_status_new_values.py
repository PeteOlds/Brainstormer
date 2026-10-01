"""ideas: HOLD, DEVELOPMENT, COMPLETE statuses

Revision ID: b7c8d9e0f1a2
Revises: c867c92cf1b2
Create Date: 2026-09-23

Add HOLD, DEVELOPMENT and COMPLETE to the ideastatus enum (used by
ideas.status and idea_status_history.old/new_status).
NOTE: Postgres forbids ADD VALUE inside a transaction block — apply
with psql directly (autocommit), not via transactional migrate.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'c867c92cf1b2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE ideastatus ADD VALUE 'HOLD'")
    op.execute("ALTER TYPE ideastatus ADD VALUE 'DEVELOPMENT'")
    op.execute("ALTER TYPE ideastatus ADD VALUE 'COMPLETE'")


def downgrade():
    # Postgres cannot drop enum values; requires recreate. No-op by design.
    pass
