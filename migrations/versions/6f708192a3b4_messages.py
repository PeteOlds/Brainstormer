"""In-app messages table (Phase 4: Talk).

Revision ID: 6f708192a3b4
Revises: 5e6f708192a3
"""
from alembic import op
import sqlalchemy as sa
from app.models.types import GUID


# revision identifiers, used by Alembic.
revision = '6f708192a3b4'
down_revision = '5e6f708192a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "messages",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("instance_id", GUID(), nullable=True),
        sa.Column("sender_id", GUID(), nullable=False),
        sa.Column("recipient_id", GUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("idea_id", GUID(), nullable=True),
        sa.Column("comment_id", GUID(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["instances.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["comment_id"], ["comments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    op.create_index("ix_messages_recipient_id", "messages", ["recipient_id"])
    op.create_index("ix_messages_instance_id", "messages", ["instance_id"])


def downgrade():
    op.drop_index("ix_messages_instance_id", table_name="messages")
    op.drop_index("ix_messages_recipient_id", table_name="messages")
    op.drop_index("ix_messages_sender_id", table_name="messages")
    op.drop_table("messages")
