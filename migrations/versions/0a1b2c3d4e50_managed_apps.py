"""Supervised apps table (one-click start/stop for generated builds).

Revision ID: 0a1b2c3d4e50
Revises: ff0b1c2d3e4f
Create Date: 2026-10-13

`managed_apps`: one row per (idea, build target). Start reconfigures it
from the current BUILD_CODE version and launches the app as a supervised
subprocess; pids live here, logs live in files. State is a plain string
column (no enum), so no out-of-band enum surgery is ever needed.
"""
from alembic import op
import sqlalchemy as sa
from app.models.types import GUID


# revision identifiers, used by Alembic.
revision = '0a1b2c3d4e50'
down_revision = 'ff0b1c2d3e4f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "managed_apps",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("instance_id", GUID(), nullable=False),
        sa.Column("idea_id", GUID(), nullable=False),
        sa.Column("target_id", GUID(), nullable=True),
        sa.Column("target_name", sa.String(length=200), nullable=True),
        sa.Column("build_version", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("workdir", sa.Text(), nullable=True),
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column("spec", sa.JSON(), nullable=True),
        sa.Column("health_url", sa.String(length=500), nullable=True),
        sa.Column("open_url", sa.String(length=500), nullable=True),
        sa.Column("log_path", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idea_id", "target_id", name="uq_managedapp_idea_target"),
    )
    op.create_index(
        "ix_managed_apps_instance_id",
        "managed_apps",
        ["instance_id"],
    )
    op.create_index(
        "ix_managed_apps_idea_id",
        "managed_apps",
        ["idea_id"],
    )


def downgrade():
    op.drop_index("ix_managed_apps_idea_id", table_name="managed_apps")
    op.drop_index("ix_managed_apps_instance_id", table_name="managed_apps")
    op.drop_table("managed_apps")
