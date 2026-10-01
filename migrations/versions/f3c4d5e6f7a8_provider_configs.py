"""provider configs, spend ledger, per-prompt provider (Phase 3)

Revision ID: f3c4d5e6f7a8
Revises: f2b3c4d5e6f7
Create Date: 2026-09-29

`instance_ai_configs` (one row per instance+provider, keys encrypted by
the app layer) and append-only `ai_spend_ledger`, plus
`prompt_configs.provider` (default 'ollama': existing prompts keep the
legacy path). RLS policies extend to the new tenant tables on Postgres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3c4d5e6f7a8'
down_revision = 'f2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instance_ai_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("model_allowlist", sa.JSON(), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("budget_cents", sa.Integer(), nullable=True),
        sa.Column("cutoff_behaviour", sa.String(length=20), nullable=False, server_default="refuse"),
        sa.Column("chat_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id", "provider", name="uq_instance_provider"),
    )
    op.create_index("ix_instance_ai_configs_instance_id", "instance_ai_configs", ["instance_id"], unique=False)

    op.create_table(
        "ai_spend_ledger",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_spend_ledger_instance_id", "ai_spend_ledger", ["instance_id"], unique=False)
    op.create_index("ix_ai_spend_ledger_created_at", "ai_spend_ledger", ["created_at"], unique=False)

    op.add_column("prompt_configs", sa.Column("provider", sa.String(length=20), nullable=False, server_default="ollama"))

    if op.get_bind().dialect.name == "postgresql":
        for table in ("instance_ai_configs", "ai_spend_ledger"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (current_setting('app.instance_id', true) = '' "
                "OR instance_id = current_setting('app.instance_id', true)::uuid)"
            )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table in reversed(("instance_ai_configs", "ai_spend_ledger")):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_column("prompt_configs", "provider")
    op.drop_index("ix_ai_spend_ledger_created_at", table_name="ai_spend_ledger")
    op.drop_index("ix_ai_spend_ledger_instance_id", table_name="ai_spend_ledger")
    op.drop_table("ai_spend_ledger")
    op.drop_index("ix_instance_ai_configs_instance_id", table_name="instance_ai_configs")
    op.drop_table("instance_ai_configs")
