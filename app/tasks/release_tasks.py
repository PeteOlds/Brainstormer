"""Celery entry point for the one-action release pipeline.

The tick is deliberately short: it inspects the persisted state, queues
whatever is next, and schedules itself again. That keeps progress durable
across worker restarts and stops long releases from sitting inside a
single task that a deploy could kill.
"""

import uuid

import structlog

from app.tasks import BaseTask, celery

logger = structlog.get_logger()


@celery.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.release_tasks.release_pipeline_tick",
    max_retries=0,
)
def release_pipeline_tick(self, release_id):
    from app.services.release_pipeline import advance_release

    try:
        advance_release(release_id)
    except Exception as exc:
        logger.exception(
            "release_pipeline_tick_failed", release_id=str(release_id), error=str(exc)
        )
        # Never leave a release stuck "running" with no tick scheduled.
        from app.extensions import db
        from app.models import Release

        try:
            db.session.rollback()
            key = uuid.UUID(str(release_id))
            release = db.session.get(Release, key)
            if release is not None and release.pipeline_status in (
                "running",
                "stopping",
            ):
                release.pipeline_status = "failed"
                release.pipeline_error = (
                    "The release run stopped unexpectedly. Run the release "
                    "again to resume from the last finished step."
                )
                db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception(
                "release_pipeline_mark_failed_failed", release_id=str(release_id)
            )
