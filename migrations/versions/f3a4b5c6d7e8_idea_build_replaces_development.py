"""ideas: BUILD replaces DEVELOPMENT

Revision ID: f3a4b5c5d6e7
Revises: a3b4c5d6e7f8
Create Date: 2026-09-26

Pipeline is now CONSIDERATION -> DESIGN -> BUILD -> COMPLETE.
- The 'BUILD' enum value itself was added via psql directly (autocommit):
  Postgres forbids ADD VALUE inside a transaction block.
- This migration moves any remaining DEVELOPMENT rows (ideas + history)
  forward to BUILD so no row references the retired value. The orphaned
  'DEVELOPMENT' enum label is left in Postgres (cannot be dropped
  without a type recreate) and removed from the Python enum + UI.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f3a4b5c5d6e7'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE ideas SET status = 'BUILD' WHERE status = 'DEVELOPMENT'")
    op.execute("UPDATE idea_status_history SET old_status = 'BUILD' WHERE old_status = 'DEVELOPMENT'")
    op.execute("UPDATE idea_status_history SET new_status = 'BUILD' WHERE new_status = 'DEVELOPMENT'")


def downgrade():
    op.execute("UPDATE ideas SET status = 'DEVELOPMENT' WHERE status = 'BUILD'")
