"""Unit coverage for the release pipeline tick wrapper."""

from unittest.mock import MagicMock, patch

import pytest


class _Row:
    def __init__(self, pipeline_status="running"):
        self.pipeline_status = pipeline_status
        self.pipeline_error = None


@pytest.fixture
def fake_db():
    db = MagicMock()
    with patch("app.extensions.db", db):
        yield db


def test_tick_delegates_to_advance_release(app, fake_db):
    from app.tasks.release_tasks import release_pipeline_tick

    with patch(
        "app.services.release_pipeline.advance_release", return_value=False
    ) as advance:
        with app.app_context():
            release_pipeline_tick.run("123e4567-e89b-12d3-a456-426614174000")

    advance.assert_called_once_with("123e4567-e89b-12d3-a456-426614174000")
    fake_db.session.rollback.assert_not_called()


def test_tick_marks_a_running_release_failed_after_error(app, fake_db):
    from app.tasks.release_tasks import release_pipeline_tick

    row = _Row()
    fake_db.session.get.return_value = row
    with patch(
        "app.services.release_pipeline.advance_release",
        side_effect=RuntimeError("pipeline exploded"),
    ):
        with app.app_context():
            release_pipeline_tick.run("123e4567-e89b-12d3-a456-426614174000")

    assert row.pipeline_status == "failed"
    assert "stopped unexpectedly" in row.pipeline_error
    fake_db.session.commit.assert_called_once()


def test_tick_does_not_overwrite_a_settled_release(app, fake_db):
    from app.tasks.release_tasks import release_pipeline_tick

    row = _Row(pipeline_status="done")
    fake_db.session.get.return_value = row
    with patch(
        "app.services.release_pipeline.advance_release",
        side_effect=RuntimeError("late failure"),
    ):
        with app.app_context():
            release_pipeline_tick.run("123e4567-e89b-12d3-a456-426614174000")

    assert row.pipeline_status == "done"
    assert row.pipeline_error is None
    fake_db.session.commit.assert_not_called()


def test_tick_swallows_secondary_failure_for_a_bad_id(app, fake_db):
    from app.tasks.release_tasks import release_pipeline_tick

    fake_db.session.get.side_effect = ValueError("bad id")
    with patch(
        "app.services.release_pipeline.advance_release",
        side_effect=RuntimeError("primary failure"),
    ):
        with app.app_context():
            release_pipeline_tick.run("not-a-uuid")

    assert fake_db.session.rollback.call_count == 2
