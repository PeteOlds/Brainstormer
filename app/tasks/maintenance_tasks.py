from app.tasks import celery, BaseTask
from app.extensions import db
from app.models import Idea, Vote
from datetime import datetime, timezone, timedelta
import structlog

logger = structlog.get_logger()


@celery.task(bind=True, base=BaseTask, name="app.tasks.maintenance_tasks.cleanup_old_discarded")
def cleanup_old_discarded(self, days: int = 90):
    """Soft delete old discarded ideas (keep for audit but mark)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # Note: We use soft delete (status = DISCARDED), so this could be
    # an archival task to move to cold storage
    logger.info("cleanup_old_discarded_not_implemented", days=days)
    return {"status": "not_implemented"}


@celery.task(bind=True, base=BaseTask, name="app.tasks.maintenance_tasks.recalculate_vote_counts")
def recalculate_vote_counts(self):
    """Recalculate all cached vote counts from votes table."""
    from sqlalchemy import func
    ideas = Idea.query.all()
    updated = 0
    for idea in ideas:
        counts = db.session.query(
            func.count(Vote.id).filter(Vote.value == 1),
            func.count(Vote.id).filter(Vote.value == -1),
            func.coalesce(func.sum(Vote.value), 0)
        ).filter(Vote.idea_id == idea.id).first()
        
        new_upvotes = counts[0] or 0
        new_downvotes = counts[1] or 0
        new_net = counts[2] or 0
        
        if (idea.upvotes_count != new_upvotes or 
            idea.downvotes_count != new_downvotes or 
            idea.net_score != new_net):
            idea.upvotes_count = new_upvotes
            idea.downvotes_count = new_downvotes
            idea.net_score = new_net
            updated += 1
    
    db.session.commit()
    logger.info("recalculated_vote_counts", updated=updated)
    return {"updated": updated}


@celery.task(bind=True, base=BaseTask, name="app.tasks.maintenance_tasks.update_next_run_times")
def update_next_run_times(self):
    """Update next_run_at for all active prompts based on interval."""
    from datetime import datetime, timezone, timedelta
    from app.models import PromptConfig
    
    now = datetime.now(timezone.utc)
    prompts = PromptConfig.query.filter(PromptConfig.is_active == True).all()
    updated = 0
    
    for prompt in prompts:
        if prompt.next_run_at and prompt.next_run_at <= now:
            # Prompt is overdue, schedule for next interval
            prompt.next_run_at = now + timedelta(minutes=prompt.interval_minutes)
            updated += 1
        elif not prompt.next_run_at:
            prompt.next_run_at = now + timedelta(minutes=prompt.interval_minutes)
            updated += 1
    
    db.session.commit()
    logger.info("updated_next_run_times", updated=updated)
    return {"updated": updated}

HEARTBEAT_KEY = "brainstormer:beat_heartbeat"
HEARTBEAT_MAX_AGE = 180  # seconds; beat ticks every 60s


def write_beat_heartbeat(redis_client) -> str:
    """Stamp scheduler liveness. Returns the stored ISO timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    redis_client.set(HEARTBEAT_KEY, now)
    return now


def check_beat_heartbeat(redis_client) -> bool:
    """True when beat ticked recently. Missing key = grace (fresh boot)."""
    try:
        raw = redis_client.get(HEARTBEAT_KEY)
    except Exception:
        return False
    if not raw:
        return True
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        stamped = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return False
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamped).total_seconds() < HEARTBEAT_MAX_AGE


@celery.task(bind=True, base=BaseTask, name="app.tasks.maintenance_tasks.beat_heartbeat")
def beat_heartbeat(self):
    """Scheduler liveness stamp (runs on beat, executes on default queue)."""
    from flask import current_app
    redis_client = current_app.extensions.get("redis_client")
    if redis_client is None:
        logger.warning("heartbeat_no_redis")
        return {"status": "no_redis"}
    stamped = write_beat_heartbeat(redis_client)
    logger.info("beat_heartbeat", at=stamped)
    return {"status": "ok", "at": stamped}
