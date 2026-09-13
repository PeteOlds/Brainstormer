"""users: last login tracking

Revision ID: c3d5e7a9b101
Revises: a91f3c7b2e44
Create Date: 2026-09-12

Admin users table shows Last Login + Number of Logins (PRD §8.4).
Existing rows keep NULL / 0 (displayed as "Never").
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d5e7a9b101'
down_revision = 'a91f3c7b2e44'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('login_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('login_count')
        batch_op.drop_column('last_login_at')
