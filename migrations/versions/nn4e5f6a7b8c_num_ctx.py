"""Add configurable context size to stage and release AI settings.

Revision ID: nn4e5f6a7b8c
Revises: mm3e4f5a6b7c
"""

from alembic import op
import sqlalchemy as sa

revision = "nn4e5f6a7b8c"
down_revision = "mm3e4f5a6b7c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("stage_ai_configs", sa.Column("num_ctx", sa.Integer(), nullable=True))
    op.add_column("release_ai_configs", sa.Column("num_ctx", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("release_ai_configs", "num_ctx")
    op.drop_column("stage_ai_configs", "num_ctx")
