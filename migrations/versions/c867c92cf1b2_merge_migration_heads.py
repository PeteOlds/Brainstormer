"""merge migration heads

Revision ID: c867c92cf1b2
Revises: 4e5f6a7b8c90, 5e6f7a8b9c0d, a1b2c3d4e5f6
Create Date: 2026-09-22 19:20:04.555371

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c867c92cf1b2'
down_revision = ('4e5f6a7b8c90', '5e6f7a8b9c0d', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
