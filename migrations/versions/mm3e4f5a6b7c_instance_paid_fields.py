"""Add paid/free usage fields to instances.

Revision ID: mm3e4f5a6b7c
Revises: ll2d3e4f5a6c
"""

from alembic import op
import sqlalchemy as sa

revision = "mm3e4f5a6b7c"
down_revision = "ll2d3e4f5a6c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("instances", sa.Column("renewal_date", sa.Date(), nullable=True))
    op.add_column("instances", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column("instances", sa.Column("payment_reference", sa.String(length=200), nullable=True))
    op.add_column("instances", sa.Column("amount_paid", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("instances", sa.Column("currency", sa.String(length=3), nullable=False, server_default="NZD"))
    op.add_column("instances", sa.Column("paid_by", sa.String(length=200), nullable=True))
    op.add_column("instances", sa.Column("promotional", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("instances", sa.Column("charitable", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade():
    op.drop_column("instances", "charitable")
    op.drop_column("instances", "promotional")
    op.drop_column("instances", "paid_by")
    op.drop_column("instances", "currency")
    op.drop_column("instances", "amount_paid")
    op.drop_column("instances", "payment_reference")
    op.drop_column("instances", "comment")
    op.drop_column("instances", "renewal_date")
