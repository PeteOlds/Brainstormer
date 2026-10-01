"""proxy virtual keys on AI configs (item 10)

Revision ID: f8a9b0c1d2e3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-30

`virtual_key` holds the LiteLLM proxy key (encrypted, write-only);
`use_proxy` routes the instance+provider through the proxy so raw
provider keys live only server-side in LiteLLM.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8a9b0c1d2e3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("instance_ai_configs", sa.Column("virtual_key", sa.Text(), nullable=True))
    op.add_column("instance_ai_configs", sa.Column("use_proxy", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("instance_ai_configs", "use_proxy")
    op.drop_column("instance_ai_configs", "virtual_key")
