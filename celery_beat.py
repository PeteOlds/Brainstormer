#!/usr/bin/env python
"""Celery beat scheduler entry point."""
import os
from app import create_app

app = create_app(os.getenv("FLASK_ENV", "development"), init_celery_app=True)

if __name__ == "__main__":
    import sys

    from app.tasks import celery
    from celery.apps.beat import Beat

    # Optional: --schedule <path> keeps the shelve DB out of the app tree
    # (the dev server auto-reloads on any file change under /app).
    schedule = None
    if "--schedule" in sys.argv:
        schedule = sys.argv[sys.argv.index("--schedule") + 1]

    # Run the beat scheduler (instantiated directly: `celery -A app.tasks`
    # would re-trigger the app/tasks circular import and lose the schedule).
    Beat(
        app=celery,
        loglevel="info",
        schedule=schedule,
        scheduler_cls="celery.beat.PersistentScheduler",
    ).run()