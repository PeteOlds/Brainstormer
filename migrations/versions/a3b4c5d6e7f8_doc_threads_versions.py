"""per-document threads + doc versioning

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-26

- comments.scope ('idea' default) + comments.action_result_id (nullable
  FK): threads scoped to one PRD/Design document version.
- secondary_action_results.version / .is_current / .edited_by_id:
  PRD/DESIGN_DOC recreate+edit append versions instead of deleting, so
  threads stay pinned. Existing rows backfilled to v1/current.
All additive; no data deleted or altered.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scope', sa.String(length=20), nullable=False, server_default='idea'))
        batch_op.add_column(sa.Column('action_result_id', sa.UUID(), nullable=True))
        batch_op.create_index('ix_comments_action_result_id', ['action_result_id'])
        batch_op.create_foreign_key('fk_comments_action_result_id', 'secondary_action_results', ['action_result_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('secondary_action_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('is_current', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('edited_by_id', sa.UUID(), nullable=True))
        batch_op.create_index('ix_secondary_action_results_is_current', ['is_current'])
        batch_op.create_foreign_key('fk_secondary_action_results_edited_by', 'users', ['edited_by_id'], ['id'])


def downgrade():
    with op.batch_alter_table('secondary_action_results', schema=None) as batch_op:
        batch_op.drop_constraint('fk_secondary_action_results_edited_by', type_='foreignkey')
        batch_op.drop_index('ix_secondary_action_results_is_current')
        batch_op.drop_column('edited_by_id')
        batch_op.drop_column('is_current')
        batch_op.drop_column('version')
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_comments_action_result_id', type_='foreignkey')
        batch_op.drop_index('ix_comments_action_result_id')
        batch_op.drop_column('action_result_id')
        batch_op.drop_column('scope')
