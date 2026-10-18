"""One-click supervision for generated builds (Slice 1: start/stop).

start_managed_app runs the recorded spec (venv setup first, then the app)
as a supervised subprocess on this host. stop_managed_app signals the
process group — it must run on a worker because pids are
container-local (a kill from the web container could hit an unrelated
process). Status/tail stay in the routes (health-first, file-based).
"""
import uuid
from datetime import datetime, timezone

import structlog

from app.extensions import db
from app.models import ManagedApp
from app.tasks import celery
from app.tasks import BaseTask

logger = structlog.get_logger()


def _now():
    return datetime.now(timezone.utc)


@celery.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.supervision_tasks.start_managed_app",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def start_managed_app(self, app_id: str):
    """Bring one managed app up. Slow path (venv+pip+boot): generous
    limits, generous logging. All failures land on the row in plain
    language — the UI never has to interpret tracebacks."""
    from app.services.build_service import port_in_use
    from app.services.runner import RunnerError, get_runner

    try:
        row_id = uuid.UUID(str(app_id))
    except (ValueError, TypeError, AttributeError):
        logger.warning("supervise_bad_id", app_id=str(app_id)[:40])
        return
    app_row = db.session.get(ManagedApp, row_id)
    if app_row is None:
        logger.warning("supervise_missing", app_id=str(app_id)[:40])
        return
    runner = get_runner()
    app_row.state = "starting"
    app_row.last_error = None
    db.session.commit()

    def _fail(message: str):
        app_row.state = "failed"
        app_row.last_error = message
        app_row.stopped_at = _now()
        db.session.commit()
        logger.warning("supervise_failed", app_id=str(app_row.id), error=message[:200])

    spec = dict(app_row.spec or {})
    if not spec.get("run_argv"):
        _fail(
            "The recorded start command cannot be run safely — confirm the build again."
        )
        return
    if not spec.get("workdir"):
        spec["workdir"] = app_row.workdir
    if not spec.get("health_url"):
        spec["health_url"] = app_row.health_url
    if not spec.get("log_path"):
        _fail("No log file recorded for this app — press Start again after reloading.")
        return
    port = app_row.port
    if port:
        try:
            busy = port_in_use(int(port))
        except (TypeError, ValueError):
            busy = False
        if busy:
            live = runner.status(app_row.pid, None)
            if live["state"] != "running" or live["pid"] != app_row.pid:
                _fail(
                    f"Port {port} is already in use by another program — "
                    "stop it and press Start again."
                )
                return
            app_row.state = "running"
            app_row.last_error = None
            db.session.commit()
            return
    live = runner.status(app_row.pid, None)
    if live["state"] == "running" and live["pid"] == app_row.pid:
        app_row.state = "running"
        app_row.last_error = None
        db.session.commit()
        return
    try:
        launched = runner.start(spec)
    except RunnerError as exc:
        _fail(str(exc))
        return
    except Exception as exc:  # never leak a traceback to the row
        _fail(f"Could not start the app: {exc}")
        return
    app_row.pid = launched["pid"]
    app_row.state = "running"
    app_row.last_error = None
    app_row.started_at = _now()
    app_row.stopped_at = None
    db.session.commit()
    logger.info("supervise_started", app_id=str(app_row.id), pid=launched["pid"])


@celery.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.supervision_tasks.stop_managed_app",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def stop_managed_app(self, app_id: str):
    """Stop one managed app. Runs on a worker so the pid resolves in the
    spawner's PID namespace. Verifies the port went quiet afterwards."""
    from app.services.runner import get_runner, poll_health

    try:
        row_id = uuid.UUID(str(app_id))
    except (ValueError, TypeError, AttributeError):
        logger.warning("supervise_bad_id", app_id=str(app_id)[:40])
        return
    app_row = db.session.get(ManagedApp, row_id)
    if app_row is None:
        logger.warning("supervise_missing", app_id=str(app_id)[:40])
        return
    runner = get_runner()
    try:
        runner.stop(app_row.pid)
    except Exception as exc:  # stop never raises, but never trust that here
        logger.warning(
            "supervise_stop_error", app_id=str(app_id)[:40], error=str(exc)[:200]
        )
    app_row.state = "stopped"
    app_row.pid = None
    app_row.stopped_at = _now()
    if poll_health(app_row.health_url) is True:
        app_row.state = "failed"
        app_row.last_error = (
            "The app did not shut down — its port is still answering. "
            "Press Stop again, or stop the program using that port."
        )
    db.session.commit()
    logger.info("supervise_stopped", app_id=str(app_row.id), state=app_row.state)
