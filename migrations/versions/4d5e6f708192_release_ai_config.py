"""Per-release AI config (overrides stage config for ideas in a release).

Revision ID: 4d5e6f708192
Revises: 3c4d5e6f7081
"""

from alembic import op
import sqlalchemy as sa
from app.models.types import GUID

# revision identifiers, used by Alembic.
revision = "4d5e6f708192"
down_revision = "3c4d5e6f7081"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "release_ai_configs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("release_id", GUID(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("top_p", sa.Float(), nullable=True),
        sa.Column("num_predict", sa.Integer(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("guidelines", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_id", name="uq_release_ai_config"),
    )
    op.create_index(
        "ix_release_ai_configs_release_id",
        "release_ai_configs",
        ["release_id"],
    )


def downgrade():
    op.drop_index("ix_release_ai_configs_release_id", table_name="release_ai_configs")
    op.drop_table("release_ai_configs")
