"""multi-tenancy foundation: instances, memberships, instance_id columns

Revision ID: d9e0f1a2b3c4
Revises: b4c5d6e7f8a9
Create Date: 2026-09-29

Phase 1: single database + instance_id. New tables `instances` and
`memberships` (string roles, no Postgres enum); nullable `instance_id`
FK on all tenant-scoped tables. Data backfill (Site 5, Instance 1,
memberships) runs via `flask init-tenancy`, not here, so this migration
stays purely structural and safe to apply any time after a backup.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9e0f1a2b3c4'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


TENANT_TABLES = [
    "prompt_configs",
    "prompt_runs",
    "ideas",
    "votes",
    "comments",
    "idea_edits",
    "secondary_action_results",
    "idea_status_history",
    "slack_posts",
    "system_settings",
]


def upgrade():
    op.create_table(
        "instances",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_free", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number", name="uq_instance_number"),
    )
    op.create_index("ix_instances_number", "instances", ["number"], unique=True)

    op.create_table(
        "memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="USER"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "instance_id", name="uq_membership_user_instance"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"], unique=False)
    op.create_index("ix_memberships_instance_id", "memberships", ["instance_id"], unique=False)

    for table in TENANT_TABLES:
        op.add_column(table, sa.Column("instance_id", sa.UUID(), nullable=True))
        op.create_foreign_key(f"fk_{table}_instance_id", table, "instances", ["instance_id"], ["id"])
        op.create_index(f"ix_{table}_instance_id", table, ["instance_id"], unique=False)


def downgrade():
    for table in reversed(TENANT_TABLES):
        op.drop_index(f"ix_{table}_instance_id", table_name=table)
        op.drop_constraint(f"fk_{table}_instance_id", table, type_="foreignkey")
        op.drop_column(table, "instance_id")

    op.drop_index("ix_memberships_instance_id", table_name="memberships")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_table("memberships")

    op.drop_index("ix_instances_number", table_name="instances")
    op.drop_table("instances")
