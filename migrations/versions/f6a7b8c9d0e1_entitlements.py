"""billing entitlement grants (Phase 8)

Revision ID: f6a7b8c9d0e1
Revises: f5e6f7a8b9c0
Create Date: 2026-09-30

`instance_entitlements` stores per-instance grants. Empty table means
Free-flag baselines apply (see app/models/entitlement.py). RLS on
Postgres like the other tenant tables.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'f5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instance_entitlements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("limits", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id", "key", name="uq_instance_entitlement"),
    )
    op.create_index("ix_instance_entitlements_instance_id", "instance_entitlements", ["instance_id"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE instance_entitlements ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY instance_entitlements_tenant_isolation ON instance_entitlements "
            "USING (current_setting('app.instance_id', true) = '' "
            "OR instance_id = current_setting('app.instance_id', true)::uuid)"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS instance_entitlements_tenant_isolation ON instance_entitlements")
        op.execute("ALTER TABLE instance_entitlements DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_instance_entitlements_instance_id", table_name="instance_entitlements")
    op.drop_table("instance_entitlements")
