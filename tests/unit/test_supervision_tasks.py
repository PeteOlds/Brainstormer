"""Unit coverage for the managed-app supervision tasks.

No real processes are started. The runner, port checks and session are faked
so the worker's failure reporting and state transitions can be exercised in
isolation.
"""

from unittest.mock import MagicMock

import pytest

from app.tasks import supervision_tasks


def _row(**overrides):
    row = MagicMock()
    row.id = "123e4567-e89b-12d3-a456-426614174000"
    row.state = "stopped"
    row.last_error = None
    row.pid = None
    row.port = None
    row.workdir = "/tmp/build"
    row.health_url = "http://127.0.0.1:8123/health"
    row.spec = {}
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _patch_db(monkeypatch, row, run=None, run_id_supplied=False):
    db = MagicMock()
    if run_id_supplied:
        db.session.get.side_effect = [row, run]
    else:
        db.session.get.return_value = row
    monkeypatch.setattr(supervision_tasks, "db", db)
    return db


def _patch_runner(monkeypatch, runner=None):
    runner = runner or MagicMock()
    monkeypatch.setattr("app.services.runner.get_runner", lambda: runner)
    return runner


def _patch_ports(monkeypatch, busy=False, new_port=None):
    from app.services import build_service

    monkeypatch.setattr(build_service, "port_in_use", lambda port: busy)
    monkeypatch.setattr(
        build_service, "allocate_port", lambda port: (new_port or port + 1, None)
    )


def test_start_rejects_a_bad_id(app, monkeypatch):
    db = _patch_db(monkeypatch, _row())
    _patch_runner(monkeypatch)

    with app.app_context():
        supervision_tasks.start_managed_app.run("not-a-uuid")

    db.session.get.assert_not_called()


def test_start_ignores_a_missing_row(app, monkeypatch):
    db = _patch_db(monkeypatch, None)
    _patch_runner(monkeypatch)

    with app.app_context():
        supervision_tasks.start_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    db.session.get.assert_called_once()


def test_start_refuses_a_spec_without_a_run_command(app, monkeypatch):
    from app.models import PromptRunStatus

    row = _row()
    run = MagicMock()
    run.status = PromptRunStatus.PENDING
    db = _patch_db(monkeypatch, row, run, run_id_supplied=True)
    _patch_runner(monkeypatch)

    with app.app_context():
        supervision_tasks.start_managed_app.run(
            "123e4567-e89b-12d3-a456-426614174000",
            "223e4567-e89b-12d3-a456-426614174000",
        )

    run.mark_running.assert_called_once()
    run.mark_failed.assert_called_once()
    assert row.state == "failed"
    assert "confirm the build" in row.last_error
    db.session.commit.assert_called()


def test_start_refuses_a_spec_without_a_log_path(app, monkeypatch):
    row = _row(spec={"run_argv": ["python", "app.py"]})
    _patch_db(monkeypatch, row)
    _patch_runner(monkeypatch)

    with app.app_context():
        supervision_tasks.start_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    assert row.state == "failed"
    assert "No log file" in row.last_error


def test_start_refuses_a_port_held_by_another_program(app, monkeypatch):
    row = _row(
        port=9000,
        spec={"run_argv": ["python", "app.py"], "log_path": "/tmp/app.log"},
    )
    runner = MagicMock()
    runner.status.return_value = {"state": "stopped", "pid": None}
    _patch_db(monkeypatch, row)
    _patch_runner(monkeypatch, runner)
    _patch_ports(monkeypatch, busy=True)

    with app.app_context():
        supervision_tasks.start_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    assert row.state == "failed"
    assert "already in use" in row.last_error


def test_start_reuses_the_live_process_on_a_busy_port(app, monkeypatch):
    row = _row(
        port=9000,
        pid=4242,
        spec={"run_argv": ["python", "app.py"], "log_path": "/tmp/app.log"},
    )
    runner = MagicMock()
    runner.status.return_value = {"state": "running", "pid": 4242}
    _patch_db(monkeypatch, row)
    _patch_runner(monkeypatch, runner)
    _patch_ports(monkeypatch, busy=True)

    with app.app_context():
        supervision_tasks.start_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    assert row.state == "running"
    runner.start.assert_not_called()


def test_start_reuses_a_live_process_without_a_port(app, monkeypatch):
    row = _row(
        pid=4242,
        spec={"run_argv": ["python", "app.py"], "log_path": "/tmp/app.log"},
    )
    runner = MagicMock()
    runner.status.return_value = {"state": "running", "pid": 4242}
    _patch_db(monkeypatch, row)
    _patch_runner(monkeypatch, runner)
    _patch_ports(monkeypatch)

    with app.app_context():
        supervision_tasks.start_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    assert row.state == "running"
    runner.start.assert_not_called()


def test_start_rewrites_a_conflicting_hard_coded_port(app, monkeypatch, tmp_path):
    entry = tmp_path / "app.py"
    entry.write_text("app.run(port=8123)\n")
    row = _row(
        workdir=str(tmp_path),
        spec={"run_argv": ["python", str(entry)], "log_path": "/tmp/app.log"},
    )
    runner = MagicMock()
    runner.status.return_value = {"state": "stopped", "pid": None}
    runner.start.return_value = {"pid": 5150, "pids": [5150], "frontend_pid": 5151}
    _patch_db(monkeypatch, row)
    _patch_runner(monkeypatch, runner)
    _patch_ports(monkeypatch, busy=True, new_port=8124)

    with app.app_context():
        supervision_tasks.start_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    assert row.port == 8124
    assert ":8124/" in row.health_url
    assert "moved your app to port 8124" in row.spec["port_note"]
    assert "port=8124" in entry.read_text()
    assert row.state == "running"
    assert row.spec["pids"] == [5150]
    assert row.spec["frontend_pid"] == 5151


def test_start_reports_runner_error_on_the_row(app, monkeypatch):
    from app.services.runner import RunnerError

    row = _row(spec={"run_argv": ["python", "app.py"], "log_path": "/tmp/app.log"})
    runner = MagicMock()
    runner.status.return_value = {"state": "stopped", "pid": None}
    runner.start.side_effect = RunnerError("bad command")
    _patch_db(monkeypatch, row)
    _patch_runner(monkeypatch, runner)
    _patch_ports(monkeypatch)

    with app.app_context():
        supervision_tasks.start_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    assert row.state == "failed"
    assert row.last_error == "bad command"


def test_start_reports_an_unexpected_launch_error(app, monkeypatch):
    row = _row(spec={"run_argv": ["python", "app.py"], "log_path": "/tmp/app.log"})
    runner = MagicMock()
    runner.status.return_value = {"state": "stopped", "pid": None}
    runner.start.side_effect = RuntimeError("boom")
    _patch_db(monkeypatch, row)
    _patch_runner(monkeypatch, runner)
    _patch_ports(monkeypatch)

    with app.app_context():
        supervision_tasks.start_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    assert row.state == "failed"
    assert row.last_error == "Could not start the app: boom"


def test_start_success_records_pid_and_run_state(app, monkeypatch):
    from app.models import PromptRunStatus

    row = _row(spec={"run_argv": ["python", "app.py"], "log_path": "/tmp/app.log"})
    run = MagicMock()
    run.status = PromptRunStatus.PENDING
    db = _patch_db(monkeypatch, row, run, run_id_supplied=True)
    runner = MagicMock()
    runner.status.return_value = {"state": "stopped", "pid": None}
    runner.start.return_value = {"pid": 5150}
    _patch_runner(monkeypatch, runner)
    _patch_ports(monkeypatch)

    with app.app_context():
        supervision_tasks.start_managed_app.run(
            "123e4567-e89b-12d3-a456-426614174000",
            "223e4567-e89b-12d3-a456-426614174000",
        )

    assert row.state == "running"
    assert row.pid == 5150
    assert row.spec["pids"] == [5150]
    assert row.started_at is not None
    assert row.stopped_at is None
    run.mark_running.assert_called_once()
    run.mark_success.assert_called_once()
    db.session.commit.assert_called()


def test_stop_rejects_a_bad_id(app, monkeypatch):
    db = _patch_db(monkeypatch, _row())
    _patch_runner(monkeypatch)

    with app.app_context():
        supervision_tasks.stop_managed_app.run("not-a-uuid")

    db.session.get.assert_not_called()


def test_stop_ignores_a_missing_row(app, monkeypatch):
    db = _patch_db(monkeypatch, None)
    _patch_runner(monkeypatch)

    with app.app_context():
        supervision_tasks.stop_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    db.session.get.assert_called_once()


def test_stop_marks_a_still_live_app_failed(app, monkeypatch):
    from app.models import PromptRunStatus

    row = _row(pid=100, spec={"pids": [101], "frontend_pid": 102})
    run = MagicMock()
    run.status = PromptRunStatus.PENDING
    db = _patch_db(monkeypatch, row, run, run_id_supplied=True)
    runner = MagicMock()
    runner.stop.side_effect = [None, RuntimeError("already gone"), None]
    _patch_runner(monkeypatch, runner)
    monkeypatch.setattr("app.services.runner.poll_health", lambda url: True)

    with app.app_context():
        supervision_tasks.stop_managed_app.run(
            "123e4567-e89b-12d3-a456-426614174000",
            "223e4567-e89b-12d3-a456-426614174000",
        )

    assert runner.stop.call_count == 3
    assert row.state == "failed"
    assert "did not shut down" in row.last_error
    assert row.pid is None
    run.mark_running.assert_called_once()
    run.mark_failed.assert_called_once()
    db.session.commit.assert_called()


def test_stop_success_when_the_port_is_quiet(app, monkeypatch):
    row = _row(pid=100, spec={})
    db = _patch_db(monkeypatch, row)
    runner = MagicMock()
    _patch_runner(monkeypatch, runner)
    monkeypatch.setattr("app.services.runner.poll_health", lambda url: False)

    with app.app_context():
        supervision_tasks.stop_managed_app.run("123e4567-e89b-12d3-a456-426614174000")

    runner.stop.assert_called_once_with(100)
    assert row.state == "stopped"
    assert row.stopped_at is not None
    db.session.commit.assert_called_once()
