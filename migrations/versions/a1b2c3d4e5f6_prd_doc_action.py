"""secondary actions: PRD document generation

Revision ID: a1b2c3d4e5f6
Revises: f6a8b0c2d404
Create Date: 2026-09-17

Add PRD_DOC to the actiontype enum.
NOTE: Postgres forbids ADD VALUE inside a transaction block — apply
with psql directly (autocommit), not via transactional migrate.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f6a8b0c2d404'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE actiontype ADD VALUE 'PRD_DOC'")


def downgrade():
    # Postgres cannot drop enum values; requires recreate. No-op by design.
    pass
