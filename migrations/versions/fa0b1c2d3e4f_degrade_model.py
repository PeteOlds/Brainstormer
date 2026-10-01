"""degrade fallback model on AI configs (Phase 10)

Revision ID: fa0b1c2d3e4f
Revises: f9a0b1c2d3e4
Create Date: 2026-10-01

`degrade_model`: local Ollama model used when a hosted call hits an
exhausted budget on an instance whose cutoff is `degrade`. Nullable:
unset means degrade is unavailable (falls back to refuse behaviour).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fa0b1c2d3e4f'
down_revision = 'f9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "instance_ai_configs",
        sa.Column("degrade_model", sa.String(length=100), nullable=True),
    )


def downgrade():
    op.drop_column("instance_ai_configs", "degrade_model")
