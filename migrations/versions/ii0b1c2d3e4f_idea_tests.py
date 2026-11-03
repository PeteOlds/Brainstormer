"""Create the idea_tests table (Test tab).

The Test tab shipped in v0.74.0 with a model but no migration; SQLite's
``create_all()`` hid that, and Postgres answered every /tests request with
``relation "idea_tests" does not exist``. This creates the table the model
expects, including the ``source`` column that distinguishes build-seeded
checks from tests a person added.

Revision ID: ii0b1c2d3e4f
Revises: 59c92efae8dc
"""

from alembic import op
import sqlalchemy as sa

from app.models.types import GUID

# revision identifiers, used by Alembic.
revision = "ii0b1c2d3e4f"
down_revision = "59c92efae8dc"
branch_labels = None
depends_on = None

# SQLAlchemy persists Python enum *names* (UNIT, NOT_RUN, …), not their
# lowercase values, so the PG types must use the names to match the model.
TEST_TYPE = sa.Enum(
    "UNIT",
    "INTEGRATION",
    "E2E",
    "MANUAL",
    "PERFORMANCE",
    name="testtype",
)
TEST_STATUS = sa.Enum("NOT_RUN", "PASSED", "FAILED", "SKIPPED", name="teststatus")


def upgrade():
    op.create_table(
        "idea_tests",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("idea_id", GUID(), nullable=False),
        sa.Column("instance_id", GUID(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("test_type", TEST_TYPE, nullable=False, server_default="UNIT"),
        sa.Column(
            "status", TEST_STATUS, nullable=False, server_default="NOT_RUN"
        ),
        sa.Column(
            "source", sa.String(length=20), nullable=False, server_default="manual"
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_output", sa.Text(), nullable=True),
        sa.Column("coverage_pct", sa.Float(), nullable=True),
        sa.Column("created_by_id", GUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_idea_tests_idea_id", "idea_tests", ["idea_id"])
    op.create_index("ix_idea_tests_instance_id", "idea_tests", ["instance_id"])


def downgrade():
    op.drop_index("ix_idea_tests_instance_id", table_name="idea_tests")
    op.drop_index("ix_idea_tests_idea_id", table_name="idea_tests")
    op.drop_table("idea_tests")
    bind = op.get_bind()
    TEST_STATUS.drop(bind, checkfirst=True)
    TEST_TYPE.drop(bind, checkfirst=True)
