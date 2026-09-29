"""comments: phase column, ignore flag, backfill, composite index

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-29

Phase 2: every comment records the V2 phase it was made in (existing
rows backfill to SCOPE per PRD_V2) and gains the admin-only is_ignored
flag. The (instance_id, idea_id, phase) composite index serves the
per-phase thread filter — the deliberate required-by-filter exception
to the no-speculative-indexes rule.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2b3c4d5e6f7'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("comments", sa.Column("phase", sa.String(length=20), nullable=True))
    op.add_column("comments", sa.Column("is_ignored", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE comments SET phase = 'SCOPE' WHERE phase IS NULL")
    op.create_index("ix_comments_phase", "comments", ["phase"], unique=False)
    op.create_index("ix_comments_instance_idea_phase", "comments",
                    ["instance_id", "idea_id", "phase"], unique=False)


def downgrade():
    op.drop_index("ix_comments_instance_idea_phase", table_name="comments")
    op.drop_index("ix_comments_phase", table_name="comments")
    op.drop_column("comments", "is_ignored")
    op.drop_column("comments", "phase")
