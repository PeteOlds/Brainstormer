"""run context on action results (Recreate defaults)

Revision ID: fd0b1c2d3e4f
Revises: fc0b1c2d3e4f
Create Date: 2026-10-10

`skills_used` / `guidelines_used`: which skills and guideline docs were
injected into the prompt that produced each version. Powers Recreate
defaults (model/skills/guides pre-filled from the latest run) and audit.
`provider_used`: the serving provider, so Recreate pre-selects the engine.
Nullable: older rows simply predate the tracking.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fd0b1c2d3e4f'
down_revision = 'fc0b1c2d3e4f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "secondary_action_results",
        sa.Column("skills_used", sa.JSON(), nullable=True),
    )
    op.add_column(
        "secondary_action_results",
        sa.Column("guidelines_used", sa.JSON(), nullable=True),
    )
    op.add_column(
        "secondary_action_results",
        sa.Column("provider_used", sa.String(length=20), nullable=True),
    )


def downgrade():
    op.drop_column("secondary_action_results", "provider_used")
    op.drop_column("secondary_action_results", "guidelines_used")
    op.drop_column("secondary_action_results", "skills_used")
