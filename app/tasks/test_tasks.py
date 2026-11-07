"""Run a build's generated test suite and record the result on the Test tab."""

import os
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone

import structlog
import urllib.request

from app.extensions import db
from app.models import Idea, IdeaTest, TestStatus
from app.tasks import BaseTask, celery

logger = structlog.get_logger()


def _now():
    return datetime.now(timezone.utc)


def _is_runnable(row) -> bool:
    name = (row.name or "").lower()
    return "test suite passes" in name or "generated test suite" in name


def _build_env(venv_python):
    env = dict(os.environ)
    env["PATH"] = (
        (os.path.dirname(venv_python) if venv_python else "")
        + os.pathsep
        + env.get("PATH", "")
    )
    env.setdefault("CI", "1")
    return env


def _find_row(idea, predicate):
    for row in IdeaTest.query.filter_by(idea_id=idea.id, source="build").all():
        if predicate((row.name or "").lower()):
            return row
    return None


def _friendly_error(text):
    low = (text or "").lower()
    if "no module named pytest" in low or "no module named 'pytest'" in low:
        return "The test tool isn't installed. Brainstormer tried to install it; if this persists, check the app's internet/dependency setup."
    if "modulenotfounderror" in low:
        import re

        m = re.search(r"no module named ['\"]?([a-zA-Z0-9_.-]+)", text or "", re.I)
        dep = m.group(1) if m else "a dependency"
        return f"Missing dependency '{dep}'. Add it to requirements.txt and rebuild the app."
    if "address already in use" in low:
        return "The app's port is already in use. Stop the other app and rerun."
    if "syntaxerror" in low:
        return "There's a syntax error in the generated code. Open the build files and fix it, then rerun."
    if "timed out" in low:
        return "The tests took too long. Try running a smaller subset."
    if "command not found" in low or "not found" in low and "docker" in low:
        return "Docker isn't available in this environment, so the container check was skipped."
    return None


def _update_row(row, status, output):
    if row is None:
        return
    row.status = status
    row.last_run_at = _now()
    if output is not None:
        text = str(output).strip()
        hint = _friendly_error(text)
        if hint and status == TestStatus.FAILED:
            text = hint + "\n\n--- details ---\n" + text
        if len(text) > 4000:
            text = text[-4000:]
        row.last_run_output = text or None
    db.session.commit()


def _record_test_failure(idea, message: str):
    try:
        row = _get_or_create_suite_row(idea)
        row.status = TestStatus.FAILED
        row.last_run_at = _now()
        row.last_run_output = message
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()
        logger.exception("run_tests_record_failed", idea_id=str(idea.id))


def _get_or_create_suite_row(idea):
    from app.models.idea_test import TestType

    name = "Generated test suite passes"
    row = IdeaTest.query.filter_by(idea_id=idea.id, source="build").filter(
        IdeaTest.name.ilike(name)
    ).first()
    if row is None:
        for candidate in IdeaTest.query.filter_by(idea_id=idea.id, source="build").all():
            if "test suite" in (candidate.name or "").lower():
                row = candidate
                break
    if row is None:
        row = IdeaTest(
            idea_id=idea.id,
            instance_id=getattr(idea, "instance_id", None),
            name=name,
            description=(
                "Run the project's test command (e.g. `pytest` or `npm test`) "
                "in the build folder. Expect all generated tests to pass."
            ),
            test_type=TestType.UNIT,
            status=TestStatus.NOT_RUN,
            source="build",
        )
        db.session.add(row)
        db.session.flush()
    return row


def _free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _http_ok(url, timeout=5):
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return 200 <= res.status < 400
    except Exception:
        return False


@celery.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.test_tasks.run_idea_tests",
    max_retries=0,
    time_limit=900,
    soft_time_limit=840,
)
def run_idea_tests(self, idea_id: str, selected_test_ids: list | None = None, run_id: str | None = None):
    """Execute the build's verification pipeline and record results.

    Runs dependency install, generated test suite, npm install, container build,
    and an HTTP smoke (starting the app if needed). Updates each seeded test
    row. Never raises to the caller.
    """
    from app.models import SecondaryActionResult, InstanceBuildTarget
    from app.models.idea_test import TestRun, TestRunStatus
    from app.routes.instances import _spec_from_build_version

    idea_uuid = None
    try:
        idea_uuid = uuid.UUID(str(idea_id))
    except (ValueError, TypeError):
        logger.warning("run_tests_bad_id", idea_id=str(idea_id)[:40])
        return
    idea = db.session.get(Idea, idea_uuid)
    if idea is None:
        logger.warning("run_tests_missing_idea", idea_id=str(idea_id)[:40])
        return

    run = TestRun(
        idea_id=idea.id,
        status=TestRunStatus.RUNNING,
        progress=2,
        message="Preparing build…",
        selected_ids=selected_test_ids or [],
        started_at=_now(),
    )
    db.session.add(run)
    db.session.commit()

    def _finish(status, progress, message, output=None):
        run.status = status
        run.progress = progress
        run.message = message
        run.output = output
        run.finished_at = _now()
        db.session.commit()

    build = None
    candidates = (
        SecondaryActionResult.query.filter_by(idea_id=idea.id, action_type="BUILD_CODE")
        .order_by(SecondaryActionResult.version.desc())
        .all()
    )
    for c in candidates:
        if (c.result_data or {}).get("written"):
            build = c
            break
    if build is None or not (build.result_data or {}).get("written"):
        _finish(TestRunStatus.FAILED, 100, "No confirmed build to test yet.")
        _record_test_failure(idea, "No confirmed build to test yet.")
        return

    target = None
    if build.target_id:
        try:
            target = db.session.get(InstanceBuildTarget, uuid.UUID(str(build.target_id)))
        except (ValueError, TypeError):
            target = None
    spec, _display, err = _spec_from_build_version(build, target, idea.reference_code)
    if err or not spec or not spec.get("workdir"):
        _finish(TestRunStatus.FAILED, 100, err or "No runnable build workdir recorded.")
        _record_test_failure(idea, err or "No runnable build workdir recorded.")
        return
    workdir = spec["workdir"]
    if not os.path.isdir(workdir):
        _finish(TestRunStatus.FAILED, 100, f"Build folder is gone: {workdir}")
        _record_test_failure(idea, f"Build folder is gone: {workdir}")
        return

    venv_python = None
    venv_dir = spec.get("venv_dir") or ""
    if venv_dir:
        cand = os.path.join(venv_dir, "bin", "python")
        if os.path.isfile(cand):
            venv_python = cand
    has_node = os.path.exists(os.path.join(workdir, "package.json"))
    env = _build_env(venv_python)

    run.progress = 5
    run.message = "Starting verification pipeline…"
    db.session.commit()

    # Selected rows (if any); otherwise run all automatable checks.
    rows = IdeaTest.query.filter_by(idea_id=idea.id, source="build").all()
    by_id = {str(r.id): r for r in rows}
    selected = [by_id[i] for i in (selected_test_ids or []) if i in by_id]
    if not selected:
        selected = list(rows)

    # Helper to decide if a row should be automated.
    def _name(r):
        return (r.name or "").lower()

    # --- 1. Dependencies install cleanly ---
    dep_row = _find_row(idea, lambda n: "dependencies install" in n or "dependencies install cleanly" in n)
    if dep_row is not None and (not selected or dep_row in selected):
        run.progress = 10
        run.message = "Installing dependencies…"
        db.session.commit()
        setup_cmd = (spec.get("setup_argv") or [])
        if not setup_cmd:
            # Fall back to pip install -r requirements.txt
            req = os.path.join(workdir, "requirements.txt")
            if os.path.exists(req):
                setup_cmd = [venv_python or "python3", "-m", "pip", "install", "-r", "requirements.txt"]
        output = ""
        ok = True
        if setup_cmd:
            try:
                proc = subprocess.run(
                    setup_cmd, cwd=workdir, capture_output=True, text=True, timeout=300, env=env
                )
                output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
                ok = proc.returncode == 0
            except Exception as exc:  # noqa: BLE001
                output = str(exc)
                ok = False
        else:
            output = "No setup command recorded."
            ok = True
        _update_row(dep_row, TestStatus.PASSED if ok else TestStatus.FAILED, output)

    # --- 2. npm install completes ---
    npm_row = _find_row(idea, lambda n: "npm install" in n)
    if npm_row is not None and has_node and (not selected or npm_row in selected):
        run.progress = 20
        run.message = "Running npm install…"
        db.session.commit()
        try:
            proc = subprocess.run(
                ["npm", "install"], cwd=workdir, capture_output=True, text=True, timeout=300, env=env
            )
            output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            ok = proc.returncode == 0
        except Exception as exc:  # noqa: BLE001
            output = str(exc)
            ok = False
        _update_row(npm_row, TestStatus.PASSED if ok else TestStatus.FAILED, output)

    # --- 3. Generated test suite passes ---
    suite_row = _get_or_create_suite_row(idea)
    if (not selected) or (suite_row in selected):
        run.progress = 35
        run.message = "Running test suite…"
        db.session.commit()
        if has_node:
            cmd = ["npm", "test"]
        else:
            interpreter = venv_python or "python3"
            # Make sure the test runner is available in the app's
            # environment; otherwise a non-technical user sees a cryptic
            # "No module named pytest" failure.
            try:
                check = subprocess.run(
                    [interpreter, "-m", "pytest", "--version"],
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=env,
                )
                if check.returncode != 0:
                    subprocess.run(
                        [interpreter, "-m", "pip", "install", "pytest"],
                        cwd=workdir,
                        capture_output=True,
                        text=True,
                        timeout=120,
                        env=env,
                    )
            except Exception:  # noqa: BLE001
                pass
            cmd = [interpreter, "-m", "pytest", "-q"]
        output = ""
        ok = False
        attempts = []
        for attempt in range(2):
            try:
                proc = subprocess.run(
                    cmd, cwd=workdir, capture_output=True, text=True, timeout=300, env=env
                )
                out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
                ok = proc.returncode == 0
            except FileNotFoundError as exc:
                out = f"Test runner not found: {exc}"
                ok = False
            except subprocess.TimeoutExpired:
                out = "Test run timed out after 5 minutes."
                ok = False
            except Exception as exc:  # noqa: BLE001
                out = f"Could not run tests: {exc}"
                ok = False
            attempts.append((ok, out))
            if ok:
                break
            # Auto-retry once for fixable environment issues.
            if attempt == 0 and not has_node:
                hint = _friendly_error(out) or ""
                if "test tool isn't installed" in hint or "Missing dependency" in hint:
                    # Try to install pytest or the missing dependency.
                    if "test tool isn't installed" in hint:
                        subprocess.run(
                            [interpreter, "-m", "pip", "install", "pytest"],
                            cwd=workdir,
                            capture_output=True,
                            text=True,
                            timeout=120,
                            env=env,
                        )
                    else:
                        import re as _re

                        m = _re.search(r"Missing dependency '([^']+)'", hint)
                        if m:
                            subprocess.run(
                                [interpreter, "-m", "pip", "install", m.group(1)],
                                cwd=workdir,
                                capture_output=True,
                                text=True,
                                timeout=120,
                                env=env,
                            )
                    continue
            break
        # Combine outputs.
        output = "\n\n=== retry ===\n".join(a[1] for a in attempts) if len(attempts) > 1 else attempts[0][1]
        ok = attempts[-1][0]
        _update_row(suite_row, TestStatus.PASSED if ok else TestStatus.FAILED, output)

    # --- 4. Container image builds ---
    container_row = _find_row(idea, lambda n: "container image builds" in n)
    if container_row is not None and (not selected or container_row in selected):
        run.progress = 55
        run.message = "Building container image…"
        db.session.commit()
        output = ""
        ok = False
        if os.path.exists(os.path.join(workdir, "docker-compose.yml")) or os.path.exists(
            os.path.join(workdir, "docker-compose.yaml")
        ):
            try:
                proc = subprocess.run(
                    ["docker", "compose", "build"],
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    env=env,
                )
                output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
                ok = proc.returncode == 0
            except FileNotFoundError:
                output = "Docker is not available in this environment."
                ok = False
            except subprocess.TimeoutExpired:
                output = "Container build timed out."
                ok = False
            except Exception as exc:  # noqa: BLE001
                output = str(exc)
                ok = False
        elif os.path.exists(os.path.join(workdir, "Dockerfile")):
            try:
                proc = subprocess.run(
                    ["docker", "build", "-t", "brainstormer-build-check", "."],
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    env=env,
                )
                output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
                ok = proc.returncode == 0
            except FileNotFoundError:
                output = "Docker is not available in this environment."
                ok = False
            except subprocess.TimeoutExpired:
                output = "Container build timed out."
                ok = False
            except Exception as exc:  # noqa: BLE001
                output = str(exc)
                ok = False
        else:
            output = "No Dockerfile or compose file found."
            ok = False
        _update_row(container_row, TestStatus.PASSED if ok else TestStatus.FAILED, output)

    # --- 5 & 6. Start app + HTTP smoke for routes and UI ---
    app_proc = None
    app_url = None
    try:
        run.progress = 70
        run.message = "Starting app for smoke checks…"
        db.session.commit()
        port = _free_port()
        cmd = spec.get("run_argv") or []
        # Resolve interpreter if needed.
        if cmd and isinstance(cmd[0], str) and "/" not in cmd[0]:
            found = None
            import shutil

            found = shutil.which(cmd[0], path=env.get("PATH", ""))
            if found:
                cmd = [found] + cmd[1:]
        if cmd:
            log_path = os.path.join(workdir, ".brainstormer-smoke.log")
            try:
                with open(log_path, "w") as fh:
                    app_proc = subprocess.Popen(
                        cmd,
                        cwd=workdir,
                        stdout=fh,
                        stderr=subprocess.STDOUT,
                        env=env,
                        start_new_session=True,
                    )
            except Exception as exc:  # noqa: BLE001
                app_proc = None
                logger.warning("smoke_start_failed", error=str(exc))

        # Wait for health (up to 30s).
        health_url = spec.get("health_url")
        if not health_url:
            health_url = f"http://127.0.0.1:{port}"
        ready = False
        for _ in range(30):
            if app_proc is not None and app_proc.poll() is not None:
                break
            if _http_ok(health_url):
                ready = True
                break
            time.sleep(1)
        app_url = health_url

        run.progress = 80
        run.message = "Running HTTP smoke checks…"
        db.session.commit()

        # UI: app responds at its URL
        ui_row = _find_row(idea, lambda n: n.startswith("ui:") and "responds at its url" in n)
        if ui_row is not None and (not selected or ui_row in selected):
            ok = ready and _http_ok(app_url)
            _update_row(ui_row, TestStatus.PASSED if ok else TestStatus.FAILED, f"GET {app_url} -> {'ok' if ok else 'failed'}")

        # Route checks
        routes = []
        # Re-derive routes from files in the build.
        try:
            from app.services.build_tests import _routes as _extract_routes

            build_files = (build.result_data or {}).get("files") or []
            routes = _extract_routes(build_files)
        except Exception:  # noqa: BLE001
            routes = []
        for method, path in routes[:6]:
            row_name = f"{method} {path or '/'} responds" if method == "GET" else f"{method} {path} returns a valid response"
            # Match by prefix since generated names vary slightly.
            row = None
            for r in IdeaTest.query.filter_by(idea_id=idea.id, source="build").all():
                if (r.name or "").upper().startswith(f"{method} {path or '/'}"):
                    row = r
                    break
            if row is None:
                continue
            if selected and row not in selected:
                continue
            url = app_url.rstrip("/") + (path or "/")
            if method.upper() == "GET":
                ok = ready and _http_ok(url)
            else:
                # For POST, just check the endpoint is reachable (not 5xx).
                ok = ready
                try:
                    req = urllib.request.Request(url, method="POST", data=b"{}")
                    req.add_header("Content-Type", "application/json")
                    with urllib.request.urlopen(req, timeout=5) as res:
                        ok = res.status < 500
                except urllib.error.HTTPError as e:
                    ok = e.code < 500
                except Exception:
                    ok = False
            _update_row(row, TestStatus.PASSED if ok else TestStatus.FAILED, f"{method} {path or '/'} -> {'ok' if ok else 'failed'}")

        # Main screen UI check (best-effort: pass if app responds).
        ui_main = _find_row(idea, lambda n: n.startswith("ui:") and "main screen" in n)
        if ui_main is not None and (not selected or ui_main in selected):
            ok = ready and _http_ok(app_url)
            _update_row(ui_main, TestStatus.PASSED if ok else TestStatus.FAILED, f"GET {app_url} -> {'ok' if ok else 'failed'}")

    finally:
        if app_proc is not None:
            try:
                import signal

                os.killpg(app_proc.pid, signal.SIGTERM)
            except Exception:  # noqa: BLE001
                try:
                    app_proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
            try:
                app_proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                try:
                    app_proc.kill()
                except Exception:  # noqa: BLE001
                    pass

    # Mark any remaining selected manual rows as skipped (no automation).
    for r in selected:
        if r.status == TestStatus.NOT_RUN:
            r.status = TestStatus.SKIPPED
            r.last_run_at = _now()
            r.last_run_output = "No automated command; verify manually."
            db.session.commit()

    run.progress = 100
    run.message = "Completed"
    run.status = TestRunStatus.COMPLETED
    run.finished_at = _now()
    db.session.commit()
    logger.info("idea_tests_run", idea_id=str(idea.id))