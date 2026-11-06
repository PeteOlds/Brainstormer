"""Run a build's generated test suite and record the result on the Test tab."""

import os
import subprocess
import uuid
from datetime import datetime, timezone

import structlog

from app.extensions import db
from app.models import Idea, IdeaTest, TestStatus
from app.tasks import BaseTask, celery

logger = structlog.get_logger()


def _now():
    return datetime.now(timezone.utc)


@celery.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.test_tasks.run_idea_tests",
    max_retries=0,
    time_limit=600,
    soft_time_limit=540,
)
def run_idea_tests(self, idea_id: str, run_id: str | None = None):
    """Execute the generated test suite for an idea's latest build.

    Runs pytest (Python) or `npm test` (Node) inside the confirmed build
    workdir, captures output, and updates the seeded
    "Generated test suite passes" check. Never raises to the caller: every
    failure is recorded on the row.
    """
    from app.models import SecondaryActionResult, InstanceBuildTarget
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

    build = (
        SecondaryActionResult.query.filter_by(
            idea_id=idea.id, action_type="BUILD_CODE", is_current=True
        )
        .order_by(SecondaryActionResult.version.desc())
        .first()
    )
    if build is None or not (build.result_data or {}).get("written"):
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
        _record_test_failure(idea, err or "No runnable build workdir recorded.")
        return
    workdir = spec["workdir"]
    if not os.path.isdir(workdir):
        _record_test_failure(idea, f"Build folder is gone: {workdir}")
        return

    # Pick the test command from what actually ships in the build.
    venv_python = None
    venv_dir = spec.get("venv_dir") or ""
    if venv_dir:
        cand = os.path.join(venv_dir, "bin", "python")
        if os.path.isfile(cand):
            venv_python = cand
    if os.path.exists(os.path.join(workdir, "package.json")):
        cmd = ["npm", "test"]
    else:
        interpreter = venv_python or "python3"
        cmd = [interpreter, "-m", "pytest", "-q"]

    env = dict(os.environ)
    env["PATH"] = (
        (os.path.dirname(venv_python) if venv_python else "")
        + os.pathsep
        + env.get("PATH", "")
    )
    env.setdefault("CI", "1")

    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
    except FileNotFoundError as exc:
        _record_test_failure(idea, f"Test runner not found: {exc}")
        return
    except subprocess.TimeoutExpired:
        _record_test_failure(idea, "Test run timed out after 5 minutes.")
        return
    except Exception as exc:  # noqa: BLE001
        _record_test_failure(idea, f"Could not run tests: {exc}")
        return

    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if len(output) > 8000:
        output = output[-8000:]
    passed = proc.returncode == 0

    row = _get_or_create_suite_row(idea)
    row.status = TestStatus.PASSED if passed else TestStatus.FAILED
    row.last_run_at = _now()
    row.last_run_output = output or ("Exit code %d" % proc.returncode)
    db.session.commit()
    logger.info(
        "idea_tests_run",
        idea_id=str(idea.id),
        passed=passed,
        returncode=proc.returncode,
    )


def _get_or_create_suite_row(idea):
    from app.models.idea_test import TestType

    name = "Generated test suite passes"
    row = IdeaTest.query.filter_by(idea_id=idea.id, source="build").filter(
        IdeaTest.name.ilike(name)
    ).first()
    if row is None:
        # Fall back to any build row with a similar name.
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
