"""secondary actions: PESTEL analysis

Revision ID: f6a8b0c2d404
Revises: e5f7a9b1c303
Create Date: 2026-09-14

Add PESTEL to the actiontype enum.
NOTE: Postgres forbids ADD VALUE inside a transaction block — apply
with psql directly (autocommit), not via transactional migrate.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f6a8b0c2d404'
down_revision = 'e5f7a9b1c303'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE actiontype ADD VALUE 'PESTEL'")


def downgrade():
    # Postgres cannot drop enum values; requires recreate. No-op by design.
    pass
