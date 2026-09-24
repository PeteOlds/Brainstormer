"""system_settings singleton table

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-24

Creates the system_settings table backing app/models/system_settings.py.
The model was added without a migration, so /admin/settings (page and
API) failed on Postgres with 'relation "system_settings" does not exist'
while SQLite dev/test (create_all) stayed green.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'system_settings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('platform', sa.JSON(), nullable=True),
        sa.Column('location', sa.JSON(), nullable=True),
        sa.Column('ai_connections', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('system_settings')
