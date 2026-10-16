"""LocalRunner: real subprocesses, short-lived, no network beyond loopback."""

import socket
import sys
import time

import pytest

from app.services.runner import LocalRunner, RunnerError, get_runner


def _free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _spec(tmp_path, argv, **over):
    spec = {
        "workdir": str(tmp_path),
        "run_argv": argv,
        "log_path": str(tmp_path / "app.log"),
    }
    spec.update(over)
    return spec


class TestLocalRunner:
    def test_get_runner_returns_local(self):
        assert isinstance(get_runner(), LocalRunner)

    def test_start_stop_status_cycle(self, tmp_path):
        runner = LocalRunner()
        spec = _spec(
            tmp_path,
            [sys.executable, "-c", "import time; time.sleep(30)"],
        )
        pid = runner.start(spec)["pid"]
        try:
            assert runner.status(pid)["state"] == "running"
            assert runner.status(pid)["healthy"] is None
        finally:
            assert runner.stop(pid) == {"stopped": True}
        assert runner.status(pid)["state"] == "stopped"

    def test_stop_dead_pid_is_quiet(self):
        assert LocalRunner().stop(999999999) == {"stopped": True}
        assert LocalRunner().stop(None) == {"stopped": True}
        assert LocalRunner().status(None)["state"] == "stopped"
        assert LocalRunner().status(999999999)["state"] == "stopped"

    def test_instant_exit_reports_log_lines(self, tmp_path):
        runner = LocalRunner()
        spec = _spec(tmp_path, [sys.executable, "-c", "print('bye-now')"])
        with pytest.raises(RunnerError) as exc:
            runner.start(spec)
        assert "exited immediately" in str(exc.value)
        assert "bye-now" in str(exc.value)

    def test_pip_failure_uses_fallback(self, tmp_path):
        runner = LocalRunner()
        log = str(tmp_path / "app.log")
        spec = _spec(
            tmp_path,
            [sys.executable, "-c", "import time; time.sleep(30)"],
            setup_argv=[sys.executable, "-c", "pass"],
            pip_argv=["/bin/false"],
            pip_fallback_argv=[sys.executable, "-c", "pass"],
        )
        spec["log_path"] = log
        pid = runner.start(spec)["pid"]
        try:
            assert runner.status(pid)["state"] == "running"
            assert "retrying unpinned" in open(log).read()
        finally:
            runner.stop(pid)

    def test_pip_failure_without_fallback_reports(self, tmp_path):
        runner = LocalRunner()
        spec = _spec(
            tmp_path,
            [sys.executable, "-c", "import time; time.sleep(30)"],
            pip_argv=["/bin/false"],
        )
        with pytest.raises(RunnerError) as exc:
            runner.start(spec)
        assert "Setup failed" in str(exc.value)

    def test_unlaunchable_setup_step_reports_plainly(self, tmp_path):
        runner = LocalRunner()
        launcher = tmp_path / "launcher"
        launcher.write_text("#!/nonexistent/interpreter\n")
        launcher.chmod(0o755)
        spec = _spec(
            tmp_path,
            [sys.executable, "-c", "import time; time.sleep(30)"],
            setup_argv=[str(launcher)],
        )
        with pytest.raises(RunnerError) as exc:
            runner.start(spec)
        assert "failed to launch" in str(exc.value)

    def test_broken_venv_recreated_cleanly(self, tmp_path):
        import shutil

        runner = LocalRunner()
        venv_dir = tmp_path / ".venv"
        broken_bin = venv_dir / "bin"
        broken_bin.mkdir(parents=True)
        (broken_bin / "activate").write_text("# fake\n")
        spec = _spec(
            tmp_path,
            [str(venv_dir / "bin" / "python"), "-c", "import time; time.sleep(30)"],
            setup_argv=[
                shutil.which("python3") or sys.executable,
                "-m",
                "venv",
                "--upgrade",
                str(venv_dir),
            ],
        )
        pid = runner.start(spec)["pid"]
        try:
            assert runner.status(pid)["state"] == "running"
            assert (venv_dir / "bin" / "python").exists() or list(
                venv_dir.glob("bin/python*")
            )
            log_text = open(spec["log_path"]).read()
            assert "Virtual environment is broken" in log_text
        finally:
            runner.stop(pid)

    def test_bare_executable_resolves_via_runner_path(self, tmp_path):
        import shutil

        from app.services.runner import _RUNNER_PATH

        runner = LocalRunner()
        assert shutil.which("python3", path=_RUNNER_PATH) is not None
        spec = _spec(
            tmp_path,
            [sys.executable, "-c", "import time; time.sleep(30)"],
            setup_argv=["python3", "-c", "pass"],
        )
        pid = runner.start(spec)["pid"]
        try:
            assert runner.status(pid)["state"] == "running"
        finally:
            runner.stop(pid)

    def test_missing_venv_python_allowed_until_setup(self, tmp_path):
        runner = LocalRunner()
        spec = _spec(
            tmp_path,
            [
                str(tmp_path / ".venv" / "bin" / "python"),
                "-c",
                "import time; time.sleep(30)",
            ],
            setup_argv=["python3", "-m", "venv", str(tmp_path / ".venv")],
        )
        pid = runner.start(spec)["pid"]
        try:
            assert runner.status(pid)["state"] == "running"
        finally:
            runner.stop(pid)

    def test_refusals_are_plain_language(self, tmp_path):
        runner = LocalRunner()
        with pytest.raises(RunnerError):
            runner.start({"workdir": "relative/path"})
        with pytest.raises(RunnerError):
            runner.start({"workdir": str(tmp_path), "run_argv": []})
        with pytest.raises(RunnerError):
            runner.start(
                {
                    "workdir": str(tmp_path),
                    "run_argv": ["/nonexistent/python", "-c", "pass"],
                }
            )
        with pytest.raises(RunnerError):
            runner.start("not-a-dict")

    def test_tail_reads_end_and_missing_is_empty(self, tmp_path):
        runner = LocalRunner()
        assert runner.tail(str(tmp_path / "missing.log")) == []
        log = tmp_path / "app.log"
        log.write_text("\n".join(f"line {i}" for i in range(10)) + "\n")
        assert runner.tail(str(log), 3) == ["line 7", "line 8", "line 9"]

    def test_healthy_http_app(self, tmp_path):
        runner = LocalRunner()
        port = _free_port()
        spec = _spec(
            tmp_path,
            [sys.executable, "-m", "http.server", str(port)],
            health_url=f"http://127.0.0.1:{port}/",
        )
        pid = runner.start(spec)["pid"]
        try:
            deadline = time.monotonic() + 15
            state = runner.status(pid, spec["health_url"])
            while state["healthy"] is not True and time.monotonic() < deadline:
                time.sleep(0.5)
                state = runner.status(pid, spec["health_url"])
            assert state == {"state": "running", "healthy": True, "pid": pid}
        finally:
            runner.stop(pid)
