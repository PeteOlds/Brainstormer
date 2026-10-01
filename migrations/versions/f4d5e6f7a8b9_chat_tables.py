"""chat sessions and turns (Phase 4)

Revision ID: f4d5e6f7a8b9
Revises: f3c4d5e6f7a8
Create Date: 2026-09-29

Turns persist who/when/model/phase plus content hashes; RLS extends to
both tables on Postgres (same permissive-when-unset failsafe pattern).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4d5e6f7a8b9'
down_revision = 'f3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=True),
        sa.Column("idea_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("phase", sa.String(length=20), nullable=True),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"]),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_instance_id", "chat_sessions", ["instance_id"], unique=False)
    op.create_index("ix_chat_sessions_idea_id", "chat_sessions", ["idea_id"], unique=False)
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"], unique=False)

    op.create_table(
        "chat_turns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="chat"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_before", sa.JSON(), nullable=True),
        sa.Column("snapshot_after", sa.JSON(), nullable=True),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_turns_instance_id", "chat_turns", ["instance_id"], unique=False)
    op.create_index("ix_chat_turns_session_id", "chat_turns", ["session_id"], unique=False)
    op.create_index("ix_chat_turns_created_at", "chat_turns", ["created_at"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        for table in ("chat_sessions", "chat_turns"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (current_setting('app.instance_id', true) = '' "
                "OR instance_id = current_setting('app.instance_id', true)::uuid)"
            )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table in reversed(("chat_sessions", "chat_turns")):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_chat_turns_created_at", table_name="chat_turns")
    op.drop_index("ix_chat_turns_session_id", table_name="chat_turns")
    op.drop_index("ix_chat_turns_instance_id", table_name="chat_turns")
    op.drop_table("chat_turns")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_idea_id", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_instance_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
