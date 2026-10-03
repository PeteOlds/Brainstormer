import os

from celery import Celery, Task
import structlog

logger = structlog.get_logger()


# Create Celery instance at module level
celery = Celery("brainstormer")


class BaseTask(Task):
    """Base task with Flask app context + structured logging."""
    abstract = True

    def __call__(self, *args, **kwargs):
        # Worker processes have no request/app context; push the Flask app
        # context so db.session and current_app work inside task bodies.
        # Falls back to a plain run when init_celery() never ran (unit tests).
        app = getattr(celery, "flask_app", None)
        if app is None:
            return self.run(*args, **kwargs)
        with app.app_context():
            return self.run(*args, **kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("task_failed", task_id=task_id, task_name=self.name, args=args, kwargs=kwargs, exc_info=exc)
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning("task_retry", task_id=task_id, task_name=self.name, attempt=self.request.retries, exc_info=exc)


def enqueue_generation(task, args, kwargs, provider):
    """Enqueue a generation task on the right queue.

    Ollama prompts keep the legacy ``.delay()`` path (static task route
    -> ``ollama`` queue), so existing mocks stay valid. OpenCode runs go
    to a dedicated serial ``opencode`` queue with longer time limits.
    """
    if (provider or "").lower() != "opencode":
        return task.delay(*args, **kwargs)
    from flask import current_app

    options = {"queue": "opencode", "args": args, "kwargs": kwargs}
    try:
        options["soft_time_limit"] = current_app.config.get(
            "OPENCODE_SOFT_TIME_LIMIT", 1560
        )
        options["time_limit"] = current_app.config.get("OPENCODE_TIME_LIMIT", 1620)
    except RuntimeError:
        pass
    return task.apply_async(**options)


def init_celery(app):
    """Initialize Celery with the Flask app."""
    # Stashed for BaseTask.__call__ so workers run tasks inside app context.
    celery.flask_app = app
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        # Ollama generation on CPU can take several minutes per idea.
        task_soft_time_limit=600,
        task_time_limit=660,
        task_routes={
            "app.tasks.ollama_tasks.*": {"queue": "ollama"},
            "app.tasks.maintenance_tasks.*": {"queue": "default"},
        },
        beat_schedule={
            "check-due-prompts": {
                "task": "app.tasks.ollama_tasks.check_due_prompts",
                "schedule": 60.0,
            },
            "beat-heartbeat": {
                "task": "app.tasks.maintenance_tasks.beat_heartbeat",
                "schedule": 60.0,
            },
        },
    )

    # Import tasks to register them
    from . import ollama_tasks  # noqa: F401
    from . import maintenance_tasks  # noqa: F401

    return celery


# Auto-initialize if Flask app is already created (for worker processes).
# NOTE: never silence this again with a bare pass — a hidden failure here
# leaves workers running with zero registered tasks (see: missing `import os`).
try:
    from app import create_app
    _app = create_app(os.getenv("FLASK_ENV", "development"), init_celery_app=True)
except Exception as exc:
    logger.warning("celery_auto_init_skipped", error=str(exc))