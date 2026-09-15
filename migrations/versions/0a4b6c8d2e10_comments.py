"""comments with threaded replies

Revision ID: 0a4b6c8d2e10
Revises: f6a8b0c2d404
Create Date: 2026-09-15

Threaded idea comments (PRD §10.1). Deletes are soft (is_deleted stub)
so child replies survive; reparenting handled in application code.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0a4b6c8d2e10'
down_revision = 'f6a8b0c2d404'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('comments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('idea_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('parent_id', sa.UUID(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['idea_id'], ['ideas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_id'], ['comments.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_comments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_comments_idea_id'), ['idea_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_comments_parent_id'), ['parent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_comments_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_comments_user_id'))
        batch_op.drop_index(batch_op.f('ix_comments_parent_id'))
        batch_op.drop_index(batch_op.f('ix_comments_idea_id'))
        batch_op.drop_index(batch_op.f('ix_comments_created_at'))
    op.drop_table('comments')
