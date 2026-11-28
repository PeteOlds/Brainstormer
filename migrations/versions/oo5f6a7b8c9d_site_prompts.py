"""Add site_prompts for central internal AI prompt overrides.

Revision ID: oo5f6a7b8c9d
Revises: nn4e5f6a7b8c
"""

from alembic import op
import sqlalchemy as sa

from app.models.types import GUID

revision = "oo5f6a7b8c9d"
down_revision = "nn4e5f6a7b8c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "site_prompts",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by_id", GUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_site_prompts_key", "site_prompts", ["key"], unique=True)


def downgrade():
    op.drop_index("ix_site_prompts_key", table_name="site_prompts")
    op.drop_table("site_prompts")
