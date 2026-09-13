"""prompt generation params

Revision ID: d4e6f8a0b202
Revises: c3d5e7a9b101
Create Date: 2026-09-12

Per-prompt Ollama sampling params (PRD §8.5): top_p, repeat_penalty,
num_predict, seed (nullable = random), keep_alive.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e6f8a0b202'
down_revision = 'c3d5e7a9b101'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('prompt_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('top_p', sa.Float(), nullable=True, server_default='0.9'))
        batch_op.add_column(sa.Column('repeat_penalty', sa.Float(), nullable=True, server_default='1.1'))
        batch_op.add_column(sa.Column('num_predict', sa.Integer(), nullable=True, server_default='1000'))
        batch_op.add_column(sa.Column('seed', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('keep_alive', sa.String(length=20), nullable=True, server_default='2h'))


def downgrade():
    with op.batch_alter_table('prompt_configs', schema=None) as batch_op:
        batch_op.drop_column('keep_alive')
        batch_op.drop_column('seed')
        batch_op.drop_column('num_predict')
        batch_op.drop_column('repeat_penalty')
        batch_op.drop_column('top_p')
