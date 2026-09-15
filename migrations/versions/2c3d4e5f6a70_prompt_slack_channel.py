"""prompt slack channel

Revision ID: 2c3d4e5f6a70
Revises: 1b2c3d4e5f60
Create Date: 2026-09-15

Per-prompt Slack channel for auto-posting new ideas (PRD §10.3).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2c3d4e5f6a70'
down_revision = '1b2c3d4e5f60'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('prompt_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('slack_channel', sa.String(length=80), nullable=True))


def downgrade():
    with op.batch_alter_table('prompt_configs', schema=None) as batch_op:
        batch_op.drop_column('slack_channel')
