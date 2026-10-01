"""ideas: comments_count column with backfill

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-09-24

Adds ideas.comments_count (non-null, default 0) and backfills it from
existing top-level, non-deleted comments — matching the ORM event
listener semantics in app/models/comment.py. Without this column every
full-row SELECT on ideas fails on Postgres (SQLite create_all masks it),
which emptied the Ideas list and broke status updates and activity stats.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ideas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('comments_count', sa.Integer(), nullable=False, server_default='0'))
    # Backfill: top-level, non-deleted comments only (matches listeners).
    op.execute(
        "UPDATE ideas SET comments_count = COALESCE(sub.cnt, 0) "
        "FROM (SELECT idea_id, COUNT(*) AS cnt FROM comments "
        "WHERE parent_id IS NULL AND is_deleted = false "
        "GROUP BY idea_id) AS sub "
        "WHERE ideas.id = sub.idea_id"
    )


def downgrade():
    with op.batch_alter_table('ideas', schema=None) as batch_op:
        batch_op.drop_column('comments_count')
