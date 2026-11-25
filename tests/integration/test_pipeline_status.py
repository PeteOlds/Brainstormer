"""Persistent pipeline status for the Flutter shell.

The shell's bottom status bar is only useful if a full pipeline has a
server-side row before its child actions run. These tests cover the tracking
row created by the API and the compact aggregate polled by the shell.
"""

import uuid
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import (
    Idea,
    IdeaStatus,
    PromptRun,
    PromptRunStatus,
    Release,
)


def _idea(code=None):
    idea = Idea(
        reference_code=code or f"IDEA-{uuid.uuid4().hex[:8].upper()}",
        prompt_title="Pipeline status idea",
        raw_content="A small idea used by status tests.",
        status=IdeaStatus.SPARK,
    )
    db.session.add(idea)
    db.session.commit()
    return idea


def test_run_full_creates_tracking_run(app, admin_client):
    with app.app_context():
        idea_id = str(_idea().id)

    job = MagicMock()
    job.id = "task-123"
    with patch(
        "app.tasks.ollama_tasks.run_full_pipeline.delay", return_value=job
    ) as delay:
        response = admin_client.post(f"/api/v1/ideas/{idea_id}/run-full")

    assert response.status_code == 202
    data = response.get_json()["data"]
    assert data["task_id"] == "task-123"

    with app.app_context():
        run = PromptRun.query.filter_by(
            action_type="FULL_PIPELINE", idea_id=uuid.UUID(idea_id)
        ).one()
        assert data["run_id"] == str(run.id)
        assert run.status == PromptRunStatus.PENDING
        assert run.job_id == "task-123"
        delay.assert_called_once_with(idea_id, run_id=str(run.id))


def test_pipeline_status_returns_only_active_runs(app, admin_client):
    with app.app_context():
        idea = _idea()
        active = PromptRun(
            idea_id=idea.id,
            action_type="FULL_PIPELINE",
            status=PromptRunStatus.RUNNING,
        )
        finished = PromptRun(
            idea_id=idea.id,
            action_type="FULL_PIPELINE",
            status=PromptRunStatus.SUCCESS,
        )
        parent = _idea("IDEA-PARENT")
        release = Release(
            parent_idea_id=parent.id,
            name="Release 1.1",
            pipeline_status="running",
            pipeline_phase="design",
            pipeline_state={
                "children": {
                    str(uuid.uuid4()): {"prd": "done", "design": "running"},
                    str(uuid.uuid4()): {"prd": "done", "design": "pending"},
                }
            },
        )
        done_release = Release(
            parent_idea_id=parent.id,
            name="Release 1.0",
            pipeline_status="done",
            pipeline_phase="done",
        )
        db.session.add_all([active, finished, release, done_release])
        db.session.commit()
        release_id = str(release.id)
        reference_code = idea.reference_code

    response = admin_client.get("/api/v1/pipeline/status")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data["idea_runs"]) == 1
    idea_run = data["idea_runs"][0]
    assert idea_run["status"] == "RUNNING"
    assert idea_run["reference_code"] == reference_code

    assert [r["release_id"] for r in data["release_runs"]] == [release_id]
    release_run = data["release_runs"][0]
    assert release_run["name"] == "Release 1.1"
    assert release_run["phase"] == "design"
    assert release_run["total"] == 2
    assert release_run["counts"]["prd"] == 2


def test_full_pipeline_task_marks_its_tracking_run_complete(celery_app):
    from app.tasks.ollama_tasks import run_full_pipeline

    with celery_app.app_context():
        idea = _idea()
        run = PromptRun(
            idea_id=idea.id,
            action_type="FULL_PIPELINE",
            status=PromptRunStatus.PENDING,
        )
        db.session.add(run)
        db.session.commit()
        idea_id = str(idea.id)
        run_id = str(run.id)

    with celery_app.app_context():
        with patch("app.tasks.ollama_tasks.run_secondary_action") as secondary:
            run_full_pipeline.run(idea_id, run_id=run_id)
        assert secondary.called
    with celery_app.app_context():
        tracked = db.session.get(PromptRun, uuid.UUID(run_id))
        assert tracked.status == PromptRunStatus.SUCCESS
        assert tracked.finished_at is not None
