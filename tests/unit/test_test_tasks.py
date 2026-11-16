"""Unit tests for the build test runner (helpers + early exits).

``app/tasks/test_tasks.py`` grew a lot with the release-gate work but had
no direct coverage, which dragged the project gate below 75%. These tests
pin the small, pure helpers and the task's guard paths (bad id, missing
idea, no confirmed build, unusable workdir) without running subprocesses
or binding ports.
"""

from unittest.mock import patch

import pytest

from app.extensions import db
from app.models import Idea, IdeaTest, SecondaryActionResult
from app.models.idea_test import TestRun as RunModel
from app.models.idea_test import TestStatus as RunStatus
from app.models.idea_test import TestType as CaseType
from app.tasks import test_tasks


def _idea(ref="IDEA-TT1", status="SHIP", **kw):
    idea = Idea(
        reference_code=ref,
        prompt_title="T",
        raw_content="c",
        status=status,
        **kw,
    )
    db.session.add(idea)
    db.session.commit()
    return idea


def _row(idea, name, **kw):
    row = IdeaTest(
        idea_id=idea.id,
        instance_id=getattr(idea, "instance_id", None),
        name=name,
        test_type=CaseType.UNIT,
        status=RunStatus.NOT_RUN,
        source="build",
        **kw,
    )
    db.session.add(row)
    db.session.commit()
    return row


class TestHelpers:
    def test_now_is_utc_aware(self):
        now = test_tasks._now()
        assert now.tzinfo is not None
        assert now.utcoffset().total_seconds() == 0

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Generated test suite passes", True),
            ("test suite passes", True),
            ("App installs without errors", False),
            ("", False),
        ],
    )
    def test_is_runnable(self, name, expected):
        row = type("R", (), {"name": name})()
        assert test_tasks._is_runnable(row) is expected

    def test_build_env_prepends_venv_bin(self):
        env = test_tasks._build_env("/opt/app/.venv/bin/python")
        assert env["PATH"].startswith("/opt/app/.venv/bin")
        assert env["CI"] == "1"

    def test_build_env_without_venv(self):
        env = test_tasks._build_env(None)
        assert env["CI"] == "1"

    def test_find_row(self, app):
        with app.app_context():
            idea = _idea()
            _row(idea, "Generated test suite passes")
            assert test_tasks._find_row(idea, lambda n: "suite" in n) is not None
            assert test_tasks._find_row(idea, lambda n: "missing" in n) is None

    @pytest.mark.parametrize(
        "text,hint",
        [
            ("No tests ran", "No automated tests were found"),
            ("unrecognized arguments: --foo", "Test configuration conflict"),
            ("No module named pytest", "test tool isn't installed"),
            (
                "ModuleNotFoundError: No module named 'requests'",
                "Missing dependency 'requests'",
            ),
            ("Address already in use", "port is already in use"),
            ("SyntaxError: bad", "syntax error"),
            ("timed out", "took too long"),
            ("docker: command not found", "Docker isn't available"),
            ("all good", None),
        ],
    )
    def test_friendly_error(self, text, hint):
        result = test_tasks._friendly_error(text)
        if hint is None:
            assert result is None
        else:
            assert hint.lower() in (result or "").lower()

    def test_update_row_sets_status(self, app):
        with app.app_context():
            idea = _idea()
            row = _row(idea, "Check")
            test_tasks._update_row(row, RunStatus.PASSED, "ok")
            db.session.refresh(row)
            assert row.status == RunStatus.PASSED
            assert row.last_run_output == "ok"
            assert row.last_run_at is not None

    def test_update_row_none_is_noop(self):
        test_tasks._update_row(None, RunStatus.PASSED, "x")

    def test_update_row_truncates(self, app):
        with app.app_context():
            idea = _idea()
            row = _row(idea, "Check")
            test_tasks._update_row(row, RunStatus.PASSED, "x" * 5000)
            db.session.refresh(row)
            assert len(row.last_run_output) <= 4000

    def test_update_row_adds_hint_on_failure(self, app):
        with app.app_context():
            idea = _idea()
            row = _row(idea, "Check")
            test_tasks._update_row(row, RunStatus.FAILED, "No tests ran")
            db.session.refresh(row)
            assert row.last_run_output.startswith("No automated tests were found")

    def test_get_or_create_suite_row_prefers_existing(self, app):
        with app.app_context():
            idea = _idea()
            existing = _row(idea, "Generated test suite passes")
            assert test_tasks._get_or_create_suite_row(idea).id == existing.id

    def test_get_or_create_suite_row_creates(self, app):
        with app.app_context():
            idea = _idea()
            row = test_tasks._get_or_create_suite_row(idea)
            assert row.name == "Generated test suite passes"
            assert row.source == "build"

    def test_record_test_failure(self, app):
        with app.app_context():
            idea = _idea()
            test_tasks._record_test_failure(idea, "boom")
            row = IdeaTest.query.filter_by(idea_id=idea.id, source="build").one()
            assert row.status == RunStatus.FAILED
            assert row.last_run_output == "boom"

    def test_free_port(self):
        port = test_tasks._free_port()
        assert 1024 <= port <= 65535

    def test_http_ok_false(self):
        assert test_tasks._http_ok("http://127.0.0.1:1/nope", timeout=0.2) is False


class TestRunIdeaTestsEarlyExits:
    def test_bad_id(self, app):
        with app.app_context():
            test_tasks.run_idea_tests.run("not-a-uuid")
            assert RunModel.query.count() == 0

    def test_missing_idea(self, app):
        with app.app_context():
            test_tasks.run_idea_tests.run("00000000-0000-0000-0000-000000000000")
            assert RunModel.query.count() == 0

    def test_no_confirmed_build(self, app):
        with app.app_context():
            idea = _idea()
            test_tasks.run_idea_tests.run(str(idea.id))
            run = RunModel.query.filter_by(idea_id=idea.id).one()
            assert run.status.value == "failed"
            assert "No confirmed build" in run.message

    def test_missing_spec(self, app):
        with app.app_context():
            idea = _idea()
            db.session.add(
                SecondaryActionResult(
                    idea_id=idea.id,
                    action_type="BUILD_CODE",
                    model_used="m",
                    result_data={"written": True},
                    version=1,
                    is_current=True,
                )
            )
            db.session.commit()
            with patch(
                "app.routes.instances._spec_from_build_version",
                return_value=(None, None, "no spec"),
            ):
                test_tasks.run_idea_tests.run(str(idea.id))
            run = RunModel.query.filter_by(idea_id=idea.id).one()
            assert run.status.value == "failed"
            assert "no spec" in run.message

    def test_build_folder_gone(self, app):
        with app.app_context():
            idea = _idea()
            db.session.add(
                SecondaryActionResult(
                    idea_id=idea.id,
                    action_type="BUILD_CODE",
                    model_used="m",
                    result_data={"written": True},
                    version=1,
                    is_current=True,
                )
            )
            db.session.commit()
            spec = {"workdir": "/nonexistent/brainstormer-test-dir"}
            with patch(
                "app.routes.instances._spec_from_build_version",
                return_value=(spec, "cmd", None),
            ):
                test_tasks.run_idea_tests.run(str(idea.id))
            run = RunModel.query.filter_by(idea_id=idea.id).one()
            assert run.status.value == "failed"
            assert "Build folder is gone" in run.message
