"""Regression: beat-driven maintenance must not depend on the ollama worker.

On 2026-10-26 the ollama worker was down. check_due_prompts (which also
reconciles orphaned runs) was routed to the ollama queue, so it never ran,
and a run stayed RUNNING for 13 hours. It must route to default.
"""

from app.tasks import celery


def _queue_for(name):
    return celery.amqp.router.route({}, name)["queue"].name


def test_due_prompt_scheduler_routes_to_default_queue(app):
    assert _queue_for("app.tasks.ollama_tasks.check_due_prompts") == "default"


def test_other_ollama_tasks_stay_on_ollama_queue(app):
    assert _queue_for("app.tasks.ollama_tasks.generate_idea") == "ollama"
    assert _queue_for("app.tasks.ollama_tasks.run_secondary_action") == "ollama"


def test_due_prompt_schedule_advances_on_enqueue(app):
    """A run that never completes must not leave its prompt due (re-run storm)."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock, patch

    from app.extensions import db
    from app.models import PromptConfig, User, UserRole
    from app.tasks import ollama_tasks

    with app.app_context():
        admin = User(email="sched@t.test", role=UserRole.ADMIN)
        admin.set_password("password123")
        db.session.add(admin)
        db.session.flush()
        prompt = PromptConfig(
            title="Sched",
            prompt_body="b",
            interval_minutes=60,
            model_name="llama3:8b",
            provider="ollama",
            is_active=True,
            created_by_id=admin.id,
            next_run_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.session.add(prompt)
        db.session.commit()
        prompt_id = prompt.id

    fake_job = MagicMock()
    fake_job.id = "job-sched"
    with app.app_context(), patch.object(
        ollama_tasks, "enqueue_generation", return_value=fake_job
    ) as enq:
        ollama_tasks.check_due_prompts.run()
    assert enq.called

    with app.app_context():
        refreshed = db.session.get(PromptConfig, prompt_id)
        next_run = refreshed.next_run_at
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        assert next_run > datetime.now(timezone.utc)
