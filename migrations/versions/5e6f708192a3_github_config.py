"""Per-instance GitHub config + release push state.

Revision ID: 5e6f708192a3
Revises: 4d5e6f708192
"""

from alembic import op
import sqlalchemy as sa
from app.models.types import GUID

# revision identifiers, used by Alembic.
revision = "5e6f708192a3"
down_revision = "4d5e6f708192"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instance_github_configs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("instance_id", GUID(), nullable=False),
        sa.Column("repo", sa.String(length=200), nullable=False),
        sa.Column("branch", sa.String(length=100), nullable=False),
        sa.Column("pat", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id"),
    )
    op.create_index(
        "ix_instance_github_configs_instance_id",
        "instance_github_configs",
        ["instance_id"],
    )
    op.add_column(
        "releases",
        sa.Column("github_sha", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "releases",
        sa.Column("github_pushed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("releases", "github_pushed_at")
    op.drop_column("releases", "github_sha")
    op.drop_index(
        "ix_instance_github_configs_instance_id",
        table_name="instance_github_configs",
    )
    op.drop_table("instance_github_configs")
