"""slack phase 3b: user linking, post mapping, event dedup

Revision ID: 3d4e5f6a7b80
Revises: 2c3d4e5f6a70
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3d4e5f6a7b80'
down_revision = '2c3d4e5f6a70'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('slack_user_id', sa.String(length=20), nullable=True))
        batch_op.create_unique_constraint('uq_users_slack_user_id', ['slack_user_id'])
        batch_op.create_index(batch_op.f('ix_users_slack_user_id'), ['slack_user_id'], unique=False)
    op.create_table('slack_posts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('idea_id', sa.UUID(), nullable=False),
    sa.Column('channel_id', sa.String(length=20), nullable=False),
    sa.Column('message_ts', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['idea_id'], ['ideas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('channel_id', 'message_ts', name='uq_slack_post')
    )
    with op.batch_alter_table('slack_posts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_slack_posts_idea_id'), ['idea_id'], unique=False)
    op.create_table('slack_events',
    sa.Column('event_id', sa.String(length=60), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('event_id')
    )


def downgrade():
    op.drop_table('slack_events')
    with op.batch_alter_table('slack_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_slack_posts_idea_id'))
    op.drop_table('slack_posts')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_slack_user_id'))
        batch_op.drop_constraint('uq_users_slack_user_id', type_='unique')
        batch_op.drop_column('slack_user_id')
