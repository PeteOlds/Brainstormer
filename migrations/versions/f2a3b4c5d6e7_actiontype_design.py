"""actiontype: backfill missing values + DESIGN_DOC

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-26

Add VRIO, THREE_CS, MARKET_SIZING, BUSINESS_MODEL_CANVAS,
HYPOTHESIS_TEST, GTM_STRATEGY (present in code/registry but never added
to the Postgres enum — persisting those results failed) and DESIGN_DOC
for the new Design document action.
NOTE: Postgres forbids ADD VALUE inside a transaction block — apply
with psql directly (autocommit), not via transactional migrate.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    for value in ("VRIO", "THREE_CS", "MARKET_SIZING",
                  "BUSINESS_MODEL_CANVAS", "HYPOTHESIS_TEST",
                  "GTM_STRATEGY", "DESIGN_DOC"):
        op.execute(f"ALTER TYPE actiontype ADD VALUE '{value}'")


def downgrade():
    # Postgres cannot drop enum values; requires recreate. No-op by design.
    pass
