"""Seed Test-tab entries for builds written before build-seeding existed.

Reads every current, written BUILD_CODE version, derives the same checklist
a new write would produce (UI check first, then endpoint/dependency checks),
and upserts it as ``source="build"`` IdeaTest rows. Idempotent: re-running
updates in place instead of duplicating, and never touches manual rows.

Usage (inside the web container, where DATABASE_URL points at Postgres):

    python scripts/backfill_build_tests.py --dry-run
    python scripts/backfill_build_tests.py
    python scripts/backfill_build_tests.py --idea IDEA-1519
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Idea, SecondaryActionResult  # noqa: E402
from app.services.build_tests import derive_build_tests, seed_idea_tests  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idea", help="Only this reference code (e.g. IDEA-1519)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report without committing"
    )
    args = parser.parse_args()

    app = create_app(init_celery_app=False)
    totals = {"builds": 0, "created": 0, "updated": 0, "removed": 0, "skipped": 0}
    with app.app_context():
        rows = (
            SecondaryActionResult.query.filter_by(
                action_type="BUILD_CODE", is_current=True
            )
            .order_by(SecondaryActionResult.executed_at.asc())
            .all()
        )
        for row in rows:
            data = row.result_data or {}
            if not data.get("written"):
                totals["skipped"] += 1
                continue
            idea = db.session.get(Idea, row.idea_id)
            if idea is None:
                continue
            if args.idea and idea.reference_code != args.idea:
                continue
            tests = derive_build_tests(
                data.get("files") or [],
                data,
                data.get("tests"),
                data.get("runbook"),
            )
            stats = seed_idea_tests(idea, tests)
            totals["builds"] += 1
            for key in ("created", "updated", "removed"):
                totals[key] += stats[key]
            print(
                f"{idea.reference_code}: {len(tests)} checks "
                f"(+{stats['created']} ~{stats['updated']} -{stats['removed']})",
                flush=True,
            )
        if args.dry_run:
            db.session.rollback()
            print("dry run: rolled back", flush=True)
        else:
            db.session.commit()
    print(
        "done: "
        f"{totals['builds']} builds, {totals['created']} added, "
        f"{totals['updated']} updated, {totals['removed']} removed, "
        f"{totals['skipped']} skipped (preview only)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
