"""ideas: DESIGN status for the PRD/Design stage

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-24

Add DESIGN to the ideastatus enum. Pipeline: CONSIDERATION -> DESIGN
(PRD + Design document built here) -> DEVELOPMENT -> (Build, undefined).
NOTE: Postgres forbids ADD VALUE inside a transaction block — apply
with psql directly (autocommit), not via transactional migrate.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE ideastatus ADD VALUE 'DESIGN'")


def downgrade():
    # Postgres cannot drop enum values; requires recreate. No-op by design.
    pass
