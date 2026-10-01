"""row-level security failsafe for instance isolation (Postgres only)

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-09-29

Defence in depth: policies mirror the server-side scoping in
`app/utils/tenancy.py`, which remains the enforcement layer. The app
sets `app.instance_id` per request/transaction (best effort, never
fatal); connections without it (CLI, migrations, workers between tasks)
see everything, so operations tooling keeps working. SQLite has no RLS
and skips this migration entirely.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e0f1a2b3c4d5'
down_revision = 'd9e0f1a2b3c4'
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

POLICY_SQL = (
    "CREATE POLICY {table}_tenant_isolation ON {table} "
    "USING (current_setting('app.instance_id', true) = '' "
    "OR instance_id = current_setting('app.instance_id', true)::uuid)"
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade():
    if not _is_postgres():
        return
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(POLICY_SQL.format(table=table))


def downgrade():
    if not _is_postgres():
        return
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
