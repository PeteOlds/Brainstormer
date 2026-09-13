"""prompt runs: follow-up actions

Revision ID: a91f3c7b2e44
Revises: f2a84c1d9e77
Create Date: 2026-09-11

Follow-up AI actions (Refine, Competitors, ...) belong to ideas, not
prompts: allow null prompt and record the action type.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a91f3c7b2e44'
down_revision = 'f2a84c1d9e77'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('prompt_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('action_type', sa.String(length=30), nullable=True))
        batch_op.alter_column('prompt_config_id', existing_type=sa.UUID(), nullable=True)


def downgrade():
    with op.batch_alter_table('prompt_runs', schema=None) as batch_op:
        batch_op.alter_column('prompt_config_id', existing_type=sa.UUID(), nullable=False)
        batch_op.drop_column('action_type')
