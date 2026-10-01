"""idea author tracking for edit-own permissions (Phase 9)

Revision ID: f9a0b1c2d3e4
Revises: f8a9b0c1d2e3
Create Date: 2026-10-01

`ideas.created_by_id` (nullable): set on manual creation going
forward; NULL means system-generated (admins only). No backfill —
existing rows predate authorship and stay admin-edited.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9a0b1c2d3e4'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ideas", sa.Column("created_by_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_ideas_created_by_id", "ideas", "users", ["created_by_id"], ["id"])
    op.create_index("ix_ideas_created_by_id", "ideas", ["created_by_id"], unique=False)


def downgrade():
    op.drop_index("ix_ideas_created_by_id", table_name="ideas")
    op.drop_constraint("fk_ideas_created_by_id", "ideas", type_="foreignkey")
    op.drop_column("ideas", "created_by_id")
