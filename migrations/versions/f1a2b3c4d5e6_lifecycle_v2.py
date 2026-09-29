"""V2 lifecycle: SPARK/SCOPE/MAP/SHIP/SCALE/DROP/FREEZE/ARCHIVE + data map

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-09-29

PRD_V2 §5.3: NEW->SPARK, CONSIDERATION->SCOPE, HOLD->FREEZE,
DESIGN->SCOPE (or MAP with a current PRD), BUILD->SHIP,
COMPLETE->ARCHIVE, DISCARDED->DROP. History rows map the same way
(DESIGN->SCOPE; audit has no PRD context).

Postgres cannot ADD/DROP enum values transactionally and cannot rename
labels, so the type is rebuilt (create new -> convert with CASE ->
drop old -> rename). This runs fine inside one migration transaction,
unlike the old ADD VALUE approach. SQLite just remaps values and
recreates the CHECK via batch mode.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e0f1a2b3c4d5'
branch_labels = None
depends_on = None


V2_VALUES = ["SPARK", "SCOPE", "MAP", "SHIP", "SCALE", "DROP", "FREEZE", "ARCHIVE"]

CASE_MAP = (
    "CASE status::text "
    "WHEN 'NEW' THEN 'SPARK' WHEN 'CONSIDERATION' THEN 'SCOPE' "
    "WHEN 'HOLD' THEN 'FREEZE' WHEN 'DESIGN' THEN 'SCOPE' "
    "WHEN 'DEVELOPMENT' THEN 'SHIP' WHEN 'BUILD' THEN 'SHIP' "
    "WHEN 'COMPLETE' THEN 'ARCHIVE' WHEN 'DISCARDED' THEN 'DROP' "
    "ELSE 'SPARK' END::ideastatus_v2"
)
CASE_OLD = CASE_MAP.replace("CASE status::text", "CASE old_status::text")
CASE_NEW = CASE_MAP.replace("CASE status::text", "CASE new_status::text")

PRD_PROMOTE = (
    "UPDATE ideas SET status = 'MAP' WHERE status = 'SCOPE' AND id IN "
    "(SELECT idea_id FROM secondary_action_results "
    "WHERE action_type = 'PRD_DOC' AND is_current)"
)

SQLITE_MAP = [
    ("NEW", "SPARK"),
    ("CONSIDERATION", "SCOPE"),
    ("HOLD", "FREEZE"),
    ("DESIGN", "SCOPE"),
    ("DEVELOPMENT", "SHIP"),
    ("BUILD", "SHIP"),
    ("COMPLETE", "ARCHIVE"),
    ("DISCARDED", "DROP"),
]


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE TYPE ideastatus_v2 AS ENUM (%s)" % ", ".join(f"'{v}'" for v in V2_VALUES))
        op.execute(f"ALTER TABLE ideas ALTER COLUMN status TYPE ideastatus_v2 USING ({CASE_MAP})")
        op.execute(f"ALTER TABLE idea_status_history ALTER COLUMN old_status TYPE ideastatus_v2 USING ({CASE_OLD})")
        op.execute(f"ALTER TABLE idea_status_history ALTER COLUMN new_status TYPE ideastatus_v2 USING ({CASE_NEW})")
        op.execute(PRD_PROMOTE)
        op.execute("DROP TYPE ideastatus")
        op.execute("ALTER TYPE ideastatus_v2 RENAME TO ideastatus")
    else:
        new_enum = sa.Enum(*V2_VALUES, name="ideastatus")
        with op.batch_alter_table("ideas") as batch:
            batch.alter_column("status", existing_type=sa.String(), type_=new_enum)
        with op.batch_alter_table("idea_status_history") as batch:
            batch.alter_column("old_status", existing_type=sa.String(), type_=new_enum)
            batch.alter_column("new_status", existing_type=sa.String(), type_=new_enum)
        for column in ("status", "old_status", "new_status"):
            table = "ideas" if column == "status" else "idea_status_history"
            for old, new in SQLITE_MAP:
                op.execute(f"UPDATE {table} SET {column} = '{new}' WHERE {column} = '{old}'")
        op.execute(PRD_PROMOTE)


def downgrade():
    """Lossy reverse map (dev/CI safety net only; production rolls forward).

    SCOPE collapses to CONSIDERATION (original DESIGN vs CONSIDERATION is
    unrecoverable) and SHIP/SCALE both return to BUILD/COMPLETE.
    """
    reverse = [
        ("SPARK", "NEW"),
        ("SCOPE", "CONSIDERATION"),
        ("MAP", "DESIGN"),
        ("SHIP", "BUILD"),
        ("SCALE", "COMPLETE"),
        ("DROP", "DISCARDED"),
        ("FREEZE", "HOLD"),
        ("ARCHIVE", "COMPLETE"),
    ]
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE TYPE ideastatus_v1 AS ENUM ('NEW', 'CONSIDERATION', 'HOLD', 'DESIGN', 'BUILD', 'COMPLETE', 'DISCARDED')")
        conv = "CASE status::text " + " ".join(f"WHEN '{n}' THEN '{o}'" for n, o in reverse) + " END::ideastatus_v1"
        op.execute(f"ALTER TABLE ideas ALTER COLUMN status TYPE ideastatus_v1 USING ({conv})")
        op.execute("ALTER TABLE idea_status_history ALTER COLUMN old_status TYPE ideastatus_v1 "
                   "USING (" + conv.replace("CASE status::text", "CASE old_status::text") + ")")
        op.execute("ALTER TABLE idea_status_history ALTER COLUMN new_status TYPE ideastatus_v1 "
                   "USING (" + conv.replace("CASE status::text", "CASE new_status::text") + ")")
        op.execute("DROP TYPE ideastatus")
        op.execute("ALTER TYPE ideastatus_v1 RENAME TO ideastatus")
    else:
        old_enum = sa.Enum("NEW", "CONSIDERATION", "HOLD", "DESIGN", "BUILD", "COMPLETE", "DISCARDED",
                           name="ideastatus")
        with op.batch_alter_table("ideas") as batch:
            batch.alter_column("status", existing_type=sa.String(), type_=old_enum)
        with op.batch_alter_table("idea_status_history") as batch:
            batch.alter_column("old_status", existing_type=sa.String(), type_=old_enum)
            batch.alter_column("new_status", existing_type=sa.String(), type_=old_enum)
        for column in ("status", "old_status", "new_status"):
            table = "ideas" if column == "status" else "idea_status_history"
            for new, old in reverse:
                op.execute(f"UPDATE {table} SET {column} = '{old}' WHERE {column} = '{new}'")
