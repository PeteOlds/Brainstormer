"""Scale-phase collaboration: child ideas + releases.

Revision ID: 1a2b3c4d5e60
Revises: 0a1b2c3d4e50

`ideas`: additive nullable parent_id / child_kind / release_id (no
backfill, no enum change). `releases`: one planning batch per SCALE
parent; children complete together via the existing bulk-status path.
"""

from alembic import op
import sqlalchemy as sa
from app.models.types import GUID

# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e60"
down_revision = "0a1b2c3d4e50"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "releases",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("instance_id", GUID(), nullable=True),
        sa.Column("parent_idea_id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", GUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_releases_parent_idea_id", "releases", ["parent_idea_id"])
    op.create_index("ix_releases_instance_id", "releases", ["instance_id"])

    op.add_column("ideas", sa.Column("parent_id", GUID(), nullable=True))
    op.add_column("ideas", sa.Column("child_kind", sa.String(length=20), nullable=True))
    op.add_column("ideas", sa.Column("release_id", GUID(), nullable=True))
    op.create_index("ix_ideas_parent_id", "ideas", ["parent_id"])
    op.create_index("ix_ideas_release_id", "ideas", ["release_id"])
    op.create_foreign_key(
        "fk_ideas_parent_id",
        "ideas",
        "ideas",
        ["parent_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_ideas_release_id",
        "ideas",
        "releases",
        ["release_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_ideas_release_id", "ideas", type_="foreignkey")
    op.drop_constraint("fk_ideas_parent_id", "ideas", type_="foreignkey")
    op.drop_index("ix_ideas_release_id", table_name="ideas")
    op.drop_index("ix_ideas_parent_id", table_name="ideas")
    op.drop_column("ideas", "release_id")
    op.drop_column("ideas", "child_kind")
    op.drop_column("ideas", "parent_id")
    op.drop_index("ix_releases_instance_id", table_name="releases")
    op.drop_index("ix_releases_parent_idea_id", table_name="releases")
    op.drop_table("releases")
