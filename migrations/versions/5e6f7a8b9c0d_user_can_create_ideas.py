"""Add can_create_ideas field to User model

Revision ID: 5e6f7a8b9c0d
Revises: 3d4e5f6a7b80
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5e6f7a8b9c0d'
down_revision = '3d4e5f6a7b80'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('can_create_ideas', sa.Boolean(), nullable=False, server_default='1'))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('can_create_ideas')