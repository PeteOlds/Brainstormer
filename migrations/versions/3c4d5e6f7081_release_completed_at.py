"""Release completion date (shown beside the name, in notes).

Revision ID: 3c4d5e6f7081
Revises: 2b3c4d5e6f70
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3c4d5e6f7081'
down_revision = '2b3c4d5e6f70'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "releases",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("releases", "completed_at")
