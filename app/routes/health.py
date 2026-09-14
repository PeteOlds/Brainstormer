import httpx
from flask import Blueprint, current_app
from sqlalchemy import text

from app.extensions import db
from app.utils.responses import api_ok, api_error

bp = Blueprint("health", __name__)


async def check_ollama() -> bool:
    """Check if Ollama is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{current_app.config['OLLAMA_BASE_URL']}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


def check_redis() -> bool:
    """Check if Redis is reachable."""
    try:
        redis_client = current_app.extensions.get("redis_client")
        if redis_client:
            return redis_client.ping()
        return False
    except Exception:
        return False


def check_scheduler() -> bool:
    """Check beat liveness via its heartbeat key (see maintenance_tasks)."""
    try:
        from app.tasks.maintenance_tasks import check_beat_heartbeat
        redis_client = current_app.extensions.get("redis_client")
        if redis_client is None:
            return False
        return check_beat_heartbeat(redis_client)
    except Exception:
        return False


def check_database() -> bool:
    """Check if database is reachable."""
    try:
        db.session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@bp.route("/api/health", methods=["GET"])
def health():
    """Liveness check - basic app health."""
    checks = {
        "database": check_database(),
        "redis": check_redis(),
        "scheduler": check_scheduler(),
    }
    # Ollama check is async, do it separately for ready endpoint
    status = "healthy" if all(checks.values()) else "degraded"
    code = 200 if status == "healthy" else 503
    return api_ok({"status": status, "checks": checks}, status_code=code)


@bp.route("/api/ready", methods=["GET"])
def ready():
    """Readiness check - includes Ollama and queue depths."""
    import httpx
    
    def check_ollama_sync() -> bool:
        """Check if Ollama is reachable."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{current_app.config['OLLAMA_BASE_URL']}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
    
    checks = {
        "database": check_database(),
        "redis": check_redis(),
        "ollama": check_ollama_sync(),
    }
    
    # Get queue depths from Celery
    queue_depth_ollama = 0
    queue_depth_default = 0
    workers_ollama = 0
    workers_default = 0
    
    try:
        from app.tasks import celery
        inspect = celery.control.inspect()
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        
        for worker, tasks in active.items():
            if "ollama" in worker:
                workers_ollama += 1
                queue_depth_ollama += len(tasks)
            else:
                workers_default += 1
                queue_depth_default += len(tasks)
        
        for worker, tasks in reserved.items():
            if "ollama" in worker:
                queue_depth_ollama += len(tasks)
            else:
                workers_default += 1
                queue_depth_default += len(tasks)
    except Exception:
        pass
    
    status = "ready" if all(checks.values()) else "not ready"
    code = 200 if status == "ready" else 503
    
    return api_ok({
        "status": status,
        "checks": checks,
        "queue_depth_ollama": queue_depth_ollama,
        "queue_depth_default": queue_depth_default,
        "workers_ollama": workers_ollama,
        "workers_default": workers_default,
    }, status_code=code)