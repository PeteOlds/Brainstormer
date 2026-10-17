"""Link instances to accounts and ideas to repositories.

Adds `system_settings.account` (the account an instance belongs to) and
`ideas.repository` (the GitHub repo an idea's build was pushed to).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'gg0b1c2d3e4f'
down_revision = 'ff0b1c2d3e4f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "system_settings",
        sa.Column("account", sa.String(200), nullable=True),
    )
    op.add_column(
        "ideas",
        sa.Column("repository", sa.String(200), nullable=True),
    )


def downgrade():
    op.drop_column("system_settings", "account")
    op.drop_column("ideas", "repository")
