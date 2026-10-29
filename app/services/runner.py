"""Supervised app processes: start/stop/status/logs behind one interface.

LocalRunner spawns apps on this host as subprocesses; a RemoteRunner can
implement the same ABC later without touching callers. Deliberate rules:

- No shell, ever: specs carry argv lists, executed directly. Model-made
  command strings are display-only and never reach a shell here.
- Minimal environment: PATH (+ venv), HOME, LANG. Nothing is inherited,
  so app frameworks with strict settings (pydantic extra=forbid) cannot
  choke on Brainstormer's own variables — seen live on IDEA-9603.
- One process group per app (start_new_session): stop kills the whole
  tree, not just the parent (uvicorn reloader/workers otherwise survive).
- The runner is stateless: pids live in the ManagedApp row, logs in files.
  A dead pid simply reports stopped (lazy reconcile, no boot hooks).
"""

import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import urllib.request
from abc import ABC, abstractmethod


class RunnerError(Exception):
    """Refused or failed supervision operation. Message is user-facing."""


class Runner(ABC):
    """Supervision backend. All methods take/return plain JSON-safe data."""

    @abstractmethod
    def start(self, spec: dict) -> dict:
        """Launch per spec. Returns {"pid": int}. Raises RunnerError."""

    @abstractmethod
    def stop(self, pid: int) -> dict:
        """Stop pid's process group. Returns {"stopped": True}. Never raises
        for an already-dead pid."""

    @abstractmethod
    def status(self, pid: int | None, health_url: str | None = None) -> dict:
        """Returns {"state": "running"|"stopped", "healthy": True|False|None,
        "pid": pid}."""

    @abstractmethod
    def tail(self, log_path: str, lines: int = 200) -> list:
        """Last N lines of a log file. Returns [] when unreadable."""


# Controlled PATH for resolution and children: venv first when known,
# then the container python dir, then the system dirs. Deliberately
# NOT inherited: builders must not see the supervisor's environment.
_RUNNER_PATH = "/usr/local/bin:/usr/bin:/bin"


def poll_health(url: str | None, timeout: float = 3) -> bool | None:
    """Health check that works from any container on the host network.

    Pids are container-local, so a pid check from the web container
    cannot see worker-spawned processes — the HTTP health endpoint is
    the cross-container source of truth. Returns True (2xx), False
    (reachable but failing, or unreachable), None when no URL recorded.
    """
    if not (url or "").strip():
        return None
    try:
        with urllib.request.urlopen(url.strip(), timeout=timeout) as res:
            return 200 <= res.status < 300
    except Exception:
        return False


def _resolve_exe(argv: list, env_path: str = _RUNNER_PATH) -> list:
    """Resolve a bare executable against a controlled PATH. Absolute
    entries pass through; anything with a slash that is not absolute is
    refused (never search the caller's PATH for relative commands)."""
    if not argv:
        return argv
    exe = argv[0]
    if "/" in exe:
        return argv
    found = shutil.which(exe, path=env_path)
    if not found:
        raise RunnerError(
            f"Cannot run {exe}: not found where apps execute. "
            "Press Start again after a rebuild."
        )
    return [found] + argv[1:]


def _check_spec(spec: dict) -> dict:
    """Validate a start spec. Returns normalized copy or raises RunnerError
    with a plain-language message."""
    if not isinstance(spec, dict):
        raise RunnerError("The app has no runnable setup yet — confirm a build first.")
    workdir = str(spec.get("workdir") or "").strip()
    if not workdir or not os.path.isabs(workdir):
        raise RunnerError(
            "The app has no working folder recorded — confirm a build first."
        )
    if not os.path.isdir(workdir):
        raise RunnerError(
            f"The app folder is gone ({workdir}) — confirm the build again."
        )
    argv = spec.get("run_argv") or []
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(a, str) and a for a in argv)
    ):
        raise RunnerError(
            "The recorded start command cannot be run safely — confirm the build again."
        )
    exe = argv[0]
    if "/" in exe:
        missing = not (
            os.path.isabs(exe) and os.path.isfile(exe) and os.access(exe, os.X_OK)
        )
        if missing and "venv" not in exe:
            raise RunnerError(f"Cannot run {exe}: not found or not executable.")
        # A missing venv interpreter is fine: the setup step creates it.
        # Anything else missing fails here with a plain message instead
        # of an OSError at spawn time.
    elif not _re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", exe):
        raise RunnerError(
            "The recorded start command cannot be run safely — confirm the build again."
        )
    frontend_argv = spec.get("frontend_run_argv") or []
    if frontend_argv and (
        not isinstance(frontend_argv, list)
        or not frontend_argv
        or not all(isinstance(a, str) and a for a in frontend_argv)
    ):
        raise RunnerError(
            "The recorded front-end command cannot be run safely — "
            "confirm the build again."
        )
    frontend_workdir = str(spec.get("frontend_workdir") or "").strip() or workdir
    if frontend_argv and (
        not frontend_workdir or not os.path.isabs(frontend_workdir)
    ):
        raise RunnerError(
            "The app has no front-end folder recorded — confirm the build again."
        )
    # Bare names (e.g. python3 for venv creation) resolve at start time
    # against the runner-controlled PATH below.
    return {
        "workdir": workdir,
        "run_argv": list(argv),
        "setup_argv": list(spec.get("setup_argv") or []),
        "pip_argv": list(spec.get("pip_argv") or []),
        "log_path": str(spec.get("log_path") or "").strip(),
        "health_url": str(spec.get("health_url") or "").strip() or None,
        "frontend_run_argv": list(frontend_argv),
        "frontend_workdir": frontend_workdir,
    }


def _supervision_env(workdir: str, argv: list) -> dict:
    """Minimal child environment. Venv bin dir first when the executable
    lives in one, so `python`/`pip` resolve inside it without activation."""
    exe_dir = os.path.dirname(argv[0])
    path = exe_dir + ":/usr/local/bin:/usr/bin:/bin" if exe_dir else _RUNNER_PATH
    return {
        "PATH": path,
        "HOME": workdir,
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


class LocalRunner(Runner):
    """Subprocess supervision on this host."""

    HEALTH_TIMEOUT = 3
    STOP_GRACE_SECONDS = 10
    MAX_TAIL_LINES = 500
    MAX_TAIL_BYTES = 200 * 1024

    def _pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except (TypeError, ValueError, OverflowError):
            return False
        # Unreaped children linger as zombies, which answer signals but
        # are already dead: read the kernel state (Linux) so stop/status
        # never report a zombie as running. Unreadable state keeps the
        # signal verdict (non-Linux, races).
        try:
            with open(f"/proc/{int(pid)}/stat") as fh:
                state = fh.read().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError, ValueError):
            return True
        return state not in ("Z", "X", "x")

    def _terminate_process_group(self, pid: int, sig: int, grace: float) -> None:
        """Best-effort full process-group teardown. Never raises."""
        try:
            pgid = os.getpgid(int(pid))
        except (ProcessLookupError, PermissionError, OSError, TypeError, ValueError):
            return
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if not self._pid_alive(pid):
                self._reap(pid)
                return
            time.sleep(0.25)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        self._reap(pid)

    def _reap(self, pid: int) -> None:
        """Collect our own dead children so they vanish instead of
        zombifying. Never raises (other processes' pids, races)."""
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass

    def _venv_python_ok(self, venv_dir: str) -> bool:
        """True when the venv's interpreter actually executes. Name checks
        and stat checks both lie about dangling symlink chains (a venv
        built by another machine's Python); only exec proves it."""
        for name in ("python", "python3"):
            try:
                proc = subprocess.run(
                    [os.path.join(venv_dir, "bin", name), "-c", "pass"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                )
                if proc.returncode == 0:
                    return True
            except OSError:
                continue
        return False

    def start(self, spec: dict) -> dict:
        norm = _check_spec(spec)
        norm["setup_argv"] = _resolve_exe(norm["setup_argv"])
        log_path = norm["log_path"]
        if not log_path:
            raise RunnerError("No log file recorded for this app.")
        log_dir = os.path.dirname(log_path)
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as exc:
            raise RunnerError(f"Cannot write the app log: {exc}") from exc
        # Idempotent setup is the caller's job (venv+pip argv run first).
        # Setup output goes to the same log the UI tails: a failed pip
        # install must be diagnosable without SSH.
        try:
            log_fh = open(log_path, "ab")
        except OSError as exc:
            raise RunnerError(f"Cannot write the app log: {exc}") from exc
        # Reconcile the venv before installing: a healthy one is reused
        # as-is (no reinstall churn on every Start); a missing or
        # python-less one is wiped and recreated with --clear (--upgrade
        # fails on such corpses). Only our own `.venv` convention dir is
        # ever touched (basename match, not substring: the project venv
        # itself contains "venv" too). Logged in all cases; the pip step
        # below always runs to converge dependencies.
        run_exe = norm["run_argv"][0]
        venv_parent = os.path.dirname(os.path.dirname(run_exe))
        venv_dir = venv_parent if os.path.basename(venv_parent) == ".venv" else ""
        setup = list(norm["setup_argv"])
        if venv_dir and setup and setup[1:3] == ["-m", "venv"]:
            if self._venv_python_ok(venv_dir):
                log_fh.write(
                    b"Virtual environment already healthy; skipping creation.\n"
                )
                log_fh.flush()
                setup = []
            else:
                setup = [setup[0], "-m", "venv", "--clear", venv_dir]
                log_fh.write(
                    b"Virtual environment is broken (python does not run); "
                    b"recreating it.\n"
                )
                log_fh.flush()
        norm["setup_argv"] = setup
        for index, step in enumerate((norm["setup_argv"], norm["pip_argv"])):
            if not step:
                continue
            # Checked here (not up front): the venv's own pip only exists
            # after the venv step has run.
            if not (os.path.isabs(step[0]) and os.path.isfile(step[0])):
                log_fh.close()
                raise RunnerError(
                    "The app's Python setup is missing a step — press Start again."
                )
            try:
                proc = subprocess.run(
                    step,
                    cwd=norm["workdir"],
                    env=_supervision_env(norm["workdir"], step),
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    timeout=1500,
                )
            except OSError as exc:
                # Includes bad-shebang executables (ENOENT at exec time):
                # fail plainly instead of leaking a traceback.
                log_fh.close()
                raise RunnerError(
                    f"Setup step {describe_argv(step[:2])} failed to launch ({exc}). "
                    "The full output is in the app log below."
                ) from exc
            if proc.returncode == 0:
                continue
            fallback = list(spec.get("pip_fallback_argv") or [])
            if (
                index == 1
                and fallback
                and fallback != step
                and os.path.isabs(fallback[0])
                and os.path.isfile(fallback[0])
            ):
                log_fh.write(
                    (
                        "\nPinned install failed "
                        f"(exit {proc.returncode}); retrying unpinned.\n"
                    ).encode("utf-8", errors="replace")
                )
                log_fh.flush()
                retry = subprocess.run(
                    fallback,
                    cwd=norm["workdir"],
                    env=_supervision_env(norm["workdir"], fallback),
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    timeout=1500,
                )
                if retry.returncode == 0:
                    continue
            log_fh.close()
            raise RunnerError(
                f"Setup failed (step {describe_argv(step[:3])} exited "
                f"{proc.returncode}). The full output is in the app log below."
            )
        try:
            proc = subprocess.Popen(
                norm["run_argv"],
                cwd=norm["workdir"],
                env=_supervision_env(norm["workdir"], norm["run_argv"]),
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            log_fh.close()
            raise RunnerError(f"Could not start the app: {exc}") from exc

        frontend_proc = None
        frontend_argv = norm.get("frontend_run_argv") or []
        if frontend_argv:
            try:
                frontend_proc = subprocess.Popen(
                    frontend_argv,
                    cwd=norm.get("frontend_workdir") or norm["workdir"],
                    env=_supervision_env(
                        norm.get("frontend_workdir") or norm["workdir"],
                        frontend_argv,
                    ),
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as exc:
                self._terminate_process_group(proc.pid, signal.SIGTERM, self.STOP_GRACE_SECONDS)
                log_fh.close()
                raise RunnerError(f"Could not start the app UI: {exc}") from exc
            time.sleep(1)
            if frontend_proc.poll() is not None:
                self._terminate_process_group(proc.pid, signal.SIGTERM, self.STOP_GRACE_SECONDS)
                log_fh.close()
                tail_lines = self.tail(log_path, 15)
                raise RunnerError(
                    "The app UI exited immediately. "
                    + (
                        "Last log lines: " + " / ".join(tail_lines)
                        if tail_lines
                        else "No output was logged."
                    )
                )
            # The children keep their own copies; closing ours is correct.
            try:
                log_fh.close()
            except OSError:
                pass
        # Reap instant exits: a command that dies in <2s is a failed start,
        # not a running app. Surface its last log lines, not silence.
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pids = [proc.pid]
            if frontend_proc is not None:
                pids.append(frontend_proc.pid)
            return {"pid": proc.pid, "frontend_pid": getattr(frontend_proc, "pid", None), "pids": pids}
        tail_lines = self.tail(log_path, 15)
        if frontend_proc is not None:
            try:
                os.killpg(os.getpgid(frontend_proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        raise RunnerError(
            "The app exited immediately. "
            + (
                "Last log lines: " + " / ".join(tail_lines)
                if tail_lines
                else "No output was logged."
            )
        )

    def stop(self, pid: int) -> dict:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return {"stopped": True}
        if not self._pid_alive(pid):
            return {"stopped": True}
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            return {"stopped": True}
        deadline = time.monotonic() + self.STOP_GRACE_SECONDS
        while time.monotonic() < deadline:
            if not self._pid_alive(pid):
                self._reap(pid)
                return {"stopped": True}
            time.sleep(0.5)
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        self._reap(pid)
        return {"stopped": True}

    def status(self, pid: int | None, health_url: str | None = None) -> dict:
        try:
            pid = int(pid) if pid is not None else None
        except (TypeError, ValueError):
            pid = None
        if pid is None or not self._pid_alive(pid):
            return {"state": "stopped", "healthy": None, "pid": pid}
        healthy = None
        if health_url:
            try:
                with urllib.request.urlopen(
                    health_url, timeout=self.HEALTH_TIMEOUT
                ) as res:
                    healthy = 200 <= res.status < 300
            except Exception:
                healthy = False
        return {"state": "running", "healthy": healthy, "pid": pid}

    def tail(self, log_path: str, lines: int = 200) -> list:
        try:
            count = max(1, min(int(lines), self.MAX_TAIL_LINES))
        except (TypeError, ValueError):
            count = 200
        try:
            with open(log_path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - self.MAX_TAIL_BYTES))
                text = fh.read().decode("utf-8", errors="replace")
        except OSError:
            return []
        return text.splitlines()[-count:]


def get_runner() -> Runner:
    """Backend selector. Only local exists today; a RemoteRunner plugs in
    here behind configuration without touching callers."""
    return LocalRunner()


def describe_argv(argv: list) -> str:
    """Human one-liner for logs. Never executed."""
    return " ".join(shlex.quote(str(a)) for a in (argv or []))
