"""idea edit audit trail

Revision ID: 1b2c3d4e5f60
Revises: 0a4b6c8d2e10
Create Date: 2026-09-15

Admin content edits on ideas with who/when/what (PRD §10.2).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b2c3d4e5f60'
down_revision = '0a4b6c8d2e10'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('idea_edits',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('idea_id', sa.UUID(), nullable=False),
    sa.Column('editor_id', sa.UUID(), nullable=False),
    sa.Column('field', sa.String(length=50), nullable=False),
    sa.Column('old_value', sa.Text(), nullable=True),
    sa.Column('new_value', sa.Text(), nullable=True),
    sa.Column('edited_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['editor_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['idea_id'], ['ideas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('idea_edits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_idea_edits_edited_at'), ['edited_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_idea_edits_editor_id'), ['editor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_idea_edits_idea_id'), ['idea_id'], unique=False)


def downgrade():
    with op.batch_alter_table('idea_edits', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_idea_edits_idea_id'))
        batch_op.drop_index(batch_op.f('ix_idea_edits_editor_id'))
        batch_op.drop_index(batch_op.f('ix_idea_edits_edited_at'))
    op.drop_table('idea_edits')
