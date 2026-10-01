"""secondary_action_results.answers for PRD Q&A persistence

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-26

Stores the human answers given to the previous version's open questions
on the regenerated document version. Previously answers lived only in
the transient Celery job args and were lost after regeneration.
Purely additive nullable column; existing rows read back as [].
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c5d6e7f8a9'
down_revision = 'f3a4b5c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('secondary_action_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('answers', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('secondary_action_results', schema=None) as batch_op:
        batch_op.drop_column('answers')
