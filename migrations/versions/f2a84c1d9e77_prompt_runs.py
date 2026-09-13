"""prompt runs history

Revision ID: f2a84c1d9e77
Revises: e9192f69bfdb
Create Date: 2026-09-11

Tracks each prompt execution (manual Run Now or scheduled) with status,
trigger source, linked idea, error and duration.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a84c1d9e77'
down_revision = 'e9192f69bfdb'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('prompt_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('prompt_config_id', sa.UUID(), nullable=False),
        sa.Column('triggered_by', sa.String(length=20), nullable=False),
        sa.Column('job_id', sa.String(length=100), nullable=True),
        sa.Column('idea_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', name='promptrunstatus'), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['idea_id'], ['ideas.id'], ),
        sa.ForeignKeyConstraint(['prompt_config_id'], ['prompt_configs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('prompt_runs', schema=None) as batch_op:
        batch_op.create_index('ix_prompt_runs_prompt_config_id', ['prompt_config_id'])
        batch_op.create_index('ix_prompt_runs_status', ['status'])


def downgrade():
    with op.batch_alter_table('prompt_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_prompt_runs_status')
        batch_op.drop_index('ix_prompt_runs_prompt_config_id')
    op.drop_table('prompt_runs')
    sa.Enum(name='promptrunstatus').drop(op.get_bind(), checkfirst=True)
