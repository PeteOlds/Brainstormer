"""Add test_runs table for background test execution progress.

Revision ID: ll2d3e4f5a6c
Revises: kk2d3e4f5a6b
"""

from alembic import op
import sqlalchemy as sa

from app.models.types import GUID

revision = "ll2d3e4f5a6c"
down_revision = "kk2d3e4f5a6b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_runs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("idea_id", GUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", name="testrunstatus"),
            nullable=False,
        ),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("selected_ids", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_runs_idea_id", "test_runs", ["idea_id"])


def downgrade():
    op.drop_index("ix_test_runs_idea_id", table_name="test_runs")
    op.drop_table("test_runs")
    op.execute("DROP TYPE IF EXISTS testrunstatus")
