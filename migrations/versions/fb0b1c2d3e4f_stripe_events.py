"""stripe webhook idempotency log (Phase 12)

Revision ID: fb0b1c2d3e4f
Revises: fa0b1c2d3e4f
Create Date: 2026-10-01

`stripe_events` records processed provider event IDs so retried
webhooks replay safely. Global table (like slack_events): no RLS, no
instance column — the event ID itself is the dedupe key.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fb0b1c2d3e4f'
down_revision = 'fa0b1c2d3e4f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stripe_events",
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade():
    op.drop_table("stripe_events")
