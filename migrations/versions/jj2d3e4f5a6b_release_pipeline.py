"""Persist the one-action release pipeline state.

A release can now run PRD → Design → Build → Test in the background. The
progress lives on the release row so a worker restart resumes instead of
forgetting where it was, and the Scale tab can poll a small summary.

Revision ID: jj2d3e4f5a6b
Revises: ii0b1c2d3e4f
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "jj2d3e4f5a6b"
down_revision = "ii0b1c2d3e4f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "releases",
        sa.Column(
            "pipeline_status",
            sa.String(length=20),
            nullable=False,
            server_default="idle",
        ),
    )
    op.add_column(
        "releases", sa.Column("pipeline_phase", sa.String(length=20), nullable=True)
    )
    op.add_column("releases", sa.Column("pipeline_state", sa.JSON(), nullable=True))
    op.add_column(
        "releases",
        sa.Column("pipeline_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "releases",
        sa.Column("pipeline_finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("releases", sa.Column("pipeline_error", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("releases", "pipeline_error")
    op.drop_column("releases", "pipeline_finished_at")
    op.drop_column("releases", "pipeline_started_at")
    op.drop_column("releases", "pipeline_state")
    op.drop_column("releases", "pipeline_phase")
    op.drop_column("releases", "pipeline_status")
