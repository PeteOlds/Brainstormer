"""social login tables: tenant oauth configs + identity links (Phase 5)

Revision ID: f5e6f7a8b9c0
Revises: f4d5e6f7a8b9
Create Date: 2026-09-29

`tenant_oauth_configs` holds per-instance client credentials (secrets
encrypted by the app layer); `oauth_identities` maps immutable
(provider, subject) pairs to the shared user identity. RLS extends to
both tables on Postgres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f5e6f7a8b9c0'
down_revision = 'f4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenant_oauth_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("provider_name", sa.String(length=20), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id", "provider_name", name="uq_tenant_oauth_provider"),
    )
    op.create_index("ix_tenant_oauth_configs_instance_id", "tenant_oauth_configs", ["instance_id"], unique=False)

    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),
    )
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        # oauth_identities is the global identity layer (looked up by
        # unguessable provider+subject pairs), so only the tenant
        # credentials table is isolated here.
        op.execute("ALTER TABLE tenant_oauth_configs ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_oauth_configs_tenant_isolation ON tenant_oauth_configs "
            "USING (current_setting('app.instance_id', true) = '' "
            "OR instance_id = current_setting('app.instance_id', true)::uuid)"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_oauth_configs_tenant_isolation ON tenant_oauth_configs")
        op.execute("ALTER TABLE tenant_oauth_configs DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_oauth_identities_user_id", table_name="oauth_identities")
    op.drop_table("oauth_identities")
    op.drop_index("ix_tenant_oauth_configs_instance_id", table_name="tenant_oauth_configs")
    op.drop_table("tenant_oauth_configs")
