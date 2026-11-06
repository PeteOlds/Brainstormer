"""Store the repo a release's builds write into.

A release used to resolve its repo only at build time, and only by
matching the release name. That left a release with no repo after PRD
and Design had already run. The chosen repo is now part of the release:
the parent's repo by default, or null to resolve/create one at run time.

Revision ID: kk2d3e4f5a6b
Revises: jj2d3e4f5a6b
"""

from alembic import op
import sqlalchemy as sa

from app.models.types import GUID

# revision identifiers, used by Alembic.
revision = "kk2d3e4f5a6b"
down_revision = "jj2d3e4f5a6b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "releases",
        sa.Column("build_target_id", GUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_releases_build_target_id",
        "releases",
        "instance_build_targets",
        ["build_target_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_releases_build_target_id",
        "releases",
        ["build_target_id"],
    )


def downgrade():
    op.drop_index("ix_releases_build_target_id", table_name="releases")
    op.drop_constraint(
        "fk_releases_build_target_id", "releases", type_="foreignkey"
    )
    op.drop_column("releases", "build_target_id")
