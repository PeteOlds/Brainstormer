"""Release notes column (auto-written on completion, admin-editable).

Revision ID: 2b3c4d5e6f70
Revises: 1a2b3c4d5e60
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2b3c4d5e6f70"
down_revision = "1a2b3c4d5e60"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("releases", sa.Column("notes", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("releases", "notes")
