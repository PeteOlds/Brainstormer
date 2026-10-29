"""Add job-run diagnostics for the admin Jobs view.

Adds job type, provider/model/queue/worker, and normalized error category to
PromptRun so AI and app-supervision jobs can be filtered and diagnosed.
"""
from alembic import op
import sqlalchemy as sa


revision = "hh0b1c2d3e4f"
down_revision = "gg0b1c2d3e4f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "prompt_runs",
        sa.Column("job_type", sa.String(20), nullable=False, server_default="ai"),
    )
    op.add_column("prompt_runs", sa.Column("provider", sa.String(50), nullable=True))
    op.add_column("prompt_runs", sa.Column("model", sa.String(100), nullable=True))
    op.add_column("prompt_runs", sa.Column("queue", sa.String(50), nullable=True))
    op.add_column("prompt_runs", sa.Column("worker", sa.String(100), nullable=True))
    op.add_column(
        "prompt_runs", sa.Column("error_category", sa.String(50), nullable=True)
    )


def downgrade():
    op.drop_column("prompt_runs", "error_category")
    op.drop_column("prompt_runs", "worker")
    op.drop_column("prompt_runs", "queue")
    op.drop_column("prompt_runs", "model")
    op.drop_column("prompt_runs", "provider")
    op.drop_column("prompt_runs", "job_type")
