"""per-stage AI configs (Phase 8 item 18)

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-30

`stage_ai_configs`: one row per (instance, stage). All settings
nullable — resolution merges explicit run args > stage row > prompt
values > hardcoded defaults, so empty/missing rows change nothing.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stage_ai_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("top_p", sa.Float(), nullable=True),
        sa.Column("num_predict", sa.Integer(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("guidelines", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id", "stage", name="uq_instance_stage"),
    )
    op.create_index("ix_stage_ai_configs_instance_id", "stage_ai_configs", ["instance_id"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE stage_ai_configs ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY stage_ai_configs_tenant_isolation ON stage_ai_configs "
            "USING (current_setting('app.instance_id', true) = '' "
            "OR instance_id = current_setting('app.instance_id', true)::uuid)"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS stage_ai_configs_tenant_isolation ON stage_ai_configs")
        op.execute("ALTER TABLE stage_ai_configs DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_stage_ai_configs_instance_id", table_name="stage_ai_configs")
    op.drop_table("stage_ai_configs")
