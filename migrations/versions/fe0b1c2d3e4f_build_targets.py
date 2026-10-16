"""Instance build targets table.

Revision ID: fe0b1c2d3e4f
Revises: fd0b1c2d3e4f
Create Date: 2026-10-10

`instance_build_targets`: named server-side repos that BUILD_CODE runs
may write into (one instance admin's registry per instance). Action
results gain `target_id` / `target_name` so a confirm run finds its
preview and the UI shows where each version was written. The `actiontype`
enum value for BUILD_CODE is added out of band via psql autocommit (see
AGENTS.md), not in this revision.
"""
from alembic import op
import sqlalchemy as sa
from app.models.types import GUID


# revision identifiers, used by Alembic.
revision = 'fe0b1c2d3e4f'
down_revision = 'fd0b1c2d3e4f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instance_build_targets",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("instance_id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_by_id", GUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id", "name", name="uq_target_instance_name"),
    )
    op.create_index(
        "ix_instance_build_targets_instance_id",
        "instance_build_targets",
        ["instance_id"],
    )
    op.add_column(
        "secondary_action_results",
        sa.Column("target_id", GUID(), nullable=True),
    )
    op.add_column(
        "secondary_action_results",
        sa.Column("target_name", sa.String(length=200), nullable=True),
    )


def downgrade():
    op.drop_column("secondary_action_results", "target_name")
    op.drop_column("secondary_action_results", "target_id")
    op.drop_index(
        "ix_instance_build_targets_instance_id",
        table_name="instance_build_targets",
    )
    op.drop_table("instance_build_targets")
