"""secondary actions: Porter's Five Forces

Revision ID: e5f7a9b1c303
Revises: d4e6f8a0b202
Create Date: 2026-09-14

Add FIVE_FORCES to the actiontype enum.
NOTE: Postgres forbids ADD VALUE inside a transaction block — apply
with psql directly (autocommit), not via transactional migrate.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e5f7a9b1c303'
down_revision = 'd4e6f8a0b202'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE actiontype ADD VALUE 'FIVE_FORCES'")


def downgrade():
    # Postgres cannot drop enum values; requires recreate. No-op by design.
    pass
