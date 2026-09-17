"""idea embeddings for similarity search

Revision ID: 4e5f6a7b8c90
Revises: 1b2c3d4e5f60
Create Date: 2026-09-16

Add embedding column to ideas table for similarity search.
Using float[] array type with Python pgvector for similarity computation.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4e5f6a7b8c90'
down_revision = '1b2c3d4e5f60'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ideas', schema=None) as batch_op:
        # Store embeddings as float array (JSONB or array type)
        # Using JSONB for flexibility and GIN index support
        batch_op.add_column(sa.Column('embedding', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('ideas', schema=None) as batch_op:
        batch_op.drop_column('embedding')