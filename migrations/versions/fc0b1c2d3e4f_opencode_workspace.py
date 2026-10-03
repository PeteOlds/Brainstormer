"""opencode workspace mode on AI configs

Revision ID: fc0b1c2d3e4f
Revises: fb0b1c2d3e4f
Create Date: 2026-10-03

`opencode_workspace`: OpenCode-only run isolation. `sandbox` (default)
runs in a throwaway empty dir with a read-only agent; `repo` grants
workspace access and is Site-Admin only. Non-nullable with a server
default so existing rows migrate without a data backfill.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fc0b1c2d3e4f'
down_revision = 'fb0b1c2d3e4f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "instance_ai_configs",
        sa.Column(
            "opencode_workspace",
            sa.String(length=20),
            nullable=False,
            server_default="sandbox",
        ),
    )


def downgrade():
    op.drop_column("instance_ai_configs", "opencode_workspace")
