"""System settings builds section (build defaults).

Revision ID: ff0b1c2d3e4f
Revises: fe0b1c2d3e4f
Create Date: 2026-10-11

`system_settings.builds` JSON: instance build defaults, currently
`default_root` — where new build repos go unless given another path.
Plain JSON column, no backfill needed.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ff0b1c2d3e4f'
down_revision = 'fe0b1c2d3e4f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "system_settings",
        sa.Column("builds", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("system_settings", "builds")
