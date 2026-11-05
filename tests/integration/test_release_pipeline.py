"""One-action release run: PRD → Design → Build → Test.

The pipeline is a persisted state machine, so tests drive it with
``advance_release()`` until it stops asking for another tick. Ollama is
faked at the client boundary: the real task, manifest validation, file
writes, status moves and test seeding all run.
"""

import json
import uuid

from app.extensions import db
from app.models import (
    Idea,
    IdeaStatusHistory,
    IdeaTest,
    Instance,
    InstanceBuildTarget,
    PromptRunStatus,
    Release,
    SecondaryActionResult,
    User,
    UserRole,
)
from app.services.build_service import existing_repo_snapshot
from app.services.release_pipeline import (
    advance_release,
    start_release_pipeline,
    stop_release_pipeline,
)

PRD = {
    "executive_summary": "A small app that fixes the reported problem for its users.",
    "user_personas": "People who use the app every day and need the fix to work.",
    "product_scope": "Only the reported problem; no unrelated redesign.",
    "functional_requirements": "The failing action completes and the screen updates.",
    "non_functional_requirements": "The app stays responsive and keeps existing pages working.",
    "ux_guidelines": "Keep the existing layout; make the fixed control obvious.",
    "assumptions_risks": "The existing app keeps its current routes and data.",
    "open_questions": [],
}

DESIGN = {
    "architecture": "Extend the existing single-process web app; no new services.",
    "screens": "The existing main screen, with the fixed control in place.",
    "data_model": "No schema change; reuse the current in-memory data.",
    "api_contracts": "GET / returns the page; POST /action returns JSON.",
    "build_notes": "Preserve every existing route and template.",
    "open_questions": [],
}

BUILD = {
    "summary": "Runnable slice that keeps the existing screen and fixes the action.",
    "files": [
        {"path": "src/app.py", "content": "print('hello')\n"},
        {
            "path": "tests/test_app.py",
            "content": "def test_x():\n    assert True\n",
        },
    ],
    "tests": [
        {
            "name": "UI: main screen loads in a browser",
            "description": "Open the app URL; the page renders without an error.",
            "test_type": "e2e",
        }
    ],
}


class FakeOllama:
    """Returns valid PRD/Design/Build JSON based on the prompt.

    Build prompts are recorded so a test can prove the second child's
    preview saw the first child's written files.
    """

    base_url = "fake://ollama"
    build_prompts = []

    def __init__(self, *args, **kwargs):
        pass

    def is_model_available(self, model):
        return True

    def close(self):
        pass

    def generate_sync(
        self, model, prompt, system=None, format=None, options=None, keep_alive=None
    ):
        if "Product Requirements Document (PRD)" in prompt:
            payload = PRD
        elif "Design Document a developer can implement" in prompt:
            payload = DESIGN
        else:
            FakeOllama.build_prompts.append(prompt)
            content = "print('hello')\n"
            if len(FakeOllama.build_prompts) == 1:
                # Only the first manifest carries this marker; the second
                # preview can only know it from the repo snapshot.
                content += "# sentinel-first-build\n"
            payload = {
                **BUILD,
                "files": [
                    {"path": "src/app.py", "content": content},
                    {
                        "path": "tests/test_app.py",
                        "content": "def test_x():\n    assert True\n",
                    },
                ],
            }
        return {"response": json.dumps(payload)}


def _make_idea(instance, code, title, status, parent=None, kind=None, release=None):
    idea = Idea(
        reference_code=code,
        prompt_title=title,
        raw_content=f"{title}: the export button fails on files over 10 MB.",
        status=status,
        instance_id=instance.id,
        parent_id=parent.id if parent is not None else None,
        child_kind=kind,
        release_id=release.id if release is not None else None,
    )
    db.session.add(idea)
    db.session.flush()
    return idea


def _seed(app, tmp_path, statuses=("SPARK", "SPARK"), name="Release 1.1"):
    suffix = uuid.uuid4().hex[:6].upper()
    with app.app_context():
        inst = Instance(number=int(suffix[:4], 16) % 9000 + 1000, name=f"Rel {suffix}")
        db.session.add(inst)
        db.session.flush()
        owner = User(
            email=f"owner-{suffix.lower()}@example.com", role=UserRole.ADMIN
        )
        owner.set_password("secret123")
        db.session.add(owner)
        db.session.flush()
        parent = _make_idea(inst, f"IDEA-P{suffix}", "Notes app", "SCALE")
        release = Release(
            parent_idea_id=parent.id,
            instance_id=inst.id,
            name=name,
            created_by_id=owner.id,
        )
        db.session.add(release)
        db.session.flush()
        kids = [
            _make_idea(
                inst,
                f"IDEA-C{i}{suffix}",
                f"Problem {i}",
                status,
                parent=parent,
                kind="bugfix",
                release=release,
            )
            for i, status in enumerate(statuses)
        ]
        db.session.add(
            InstanceBuildTarget(
                instance_id=inst.id, name=name, path=str(tmp_path)
            )
        )
        db.session.commit()
        return str(inst.id), str(parent.id), str(release.id), [str(k.id) for k in kids]


def _run_until_done(release_id, limit=40):
    for _ in range(limit):
        if not advance_release(release_id):
            return True
    return False


def test_full_release_runs_every_phase(celery_app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.tasks.ollama_tasks.OllamaClient", FakeOllama
    )
    celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
    _, _, rid, kid_ids = _seed(celery_app, tmp_path)
    FakeOllama.build_prompts = []

    with celery_app.app_context():
        release = db.session.get(Release, uuid.UUID(rid))
        ok, message = start_release_pipeline(release, None)
        assert ok, message
        assert _run_until_done(rid), "pipeline did not settle"

        release = db.session.get(Release, uuid.UUID(rid))
        assert release.pipeline_status == "done"
        assert release.status == "done"
        assert release.pipeline_phase == "done"
        assert release.pipeline_error is None
        assert "2 shipped, 0 rejected" in (release.notes or "")

        for kid_id in kid_ids:
            kid = db.session.get(Idea, uuid.UUID(kid_id))
            assert kid.status.value == "SHIP"
            for action in ("PRD_DOC", "DESIGN_DOC", "BUILD_CODE"):
                row = SecondaryActionResult.query.filter_by(
                    idea_id=kid.id, action_type=action, is_current=True
                ).first()
                assert row is not None, f"{kid.reference_code} missing {action}"
            build = SecondaryActionResult.query.filter_by(
                idea_id=kid.id, action_type="BUILD_CODE", is_current=True
            ).one()
            assert build.result_data["written"] is True
            tests = IdeaTest.query.filter_by(idea_id=kid.id).all()
            assert tests, "build must seed the Test tab"
            assert any(t.test_type.value == "e2e" for t in tests)
            history = IdeaStatusHistory.query.filter_by(idea_id=kid.id).all()
            assert len(history) >= 3  # SPARK → SCOPE → MAP → SHIP

        assert (tmp_path / "src" / "app.py").exists()
        # 1A: sequential builds with the repo as context. The second
        # preview must read the first child's written file.
        assert len(FakeOllama.build_prompts) >= 2
        assert "# sentinel-first-build" not in FakeOllama.build_prompts[0]
        assert "# sentinel-first-build" in FakeOllama.build_prompts[1]


def test_existing_build_is_not_rebuilt(celery_app, tmp_path, monkeypatch):
    monkeypatch.setattr("app.tasks.ollama_tasks.OllamaClient", FakeOllama)
    celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
    _, _, rid, kid_ids = _seed(celery_app, tmp_path, statuses=("SHIP",))

    with celery_app.app_context():
        kid = db.session.get(Idea, uuid.UUID(kid_ids[0]))
        target = InstanceBuildTarget.query.filter_by(instance_id=kid.instance_id).one()
        db.session.add(
            SecondaryActionResult(
                idea_id=kid.id,
                action_type="BUILD_CODE",
                model_used="m",
                provider_used="ollama",
                result_data={
                    "summary": "already built",
                    "files": [],
                    "tests": [],
                    "written": True,
                    "runbook": {"run": "python3 app.py"},
                },
                version=1,
                is_current=True,
                target_id=str(target.id),
                target_name=target.name,
                instance_id=kid.instance_id,
            )
        )
        db.session.commit()

        release = db.session.get(Release, uuid.UUID(rid))
        ok, _ = start_release_pipeline(release, None)
        assert ok
        assert _run_until_done(rid)

        builds = SecondaryActionResult.query.filter_by(
            idea_id=kid.id, action_type="BUILD_CODE"
        ).all()
        assert len(builds) == 1, "a current written build must be left alone"
        assert builds[0].result_data["written"] is True


def test_stop_keeps_finished_work_and_halts(celery_app, tmp_path, monkeypatch):
    monkeypatch.setattr("app.tasks.ollama_tasks.OllamaClient", FakeOllama)
    celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
    _, _, rid, _ = _seed(celery_app, tmp_path)

    with celery_app.app_context():
        release = db.session.get(Release, uuid.UUID(rid))
        assert start_release_pipeline(release, None)[0]
        assert stop_release_pipeline(release)[0]
        assert advance_release(rid) is False
        release = db.session.get(Release, uuid.UUID(rid))
        assert release.pipeline_status == "idle"
        assert release.status == "in_progress"


def test_failure_does_not_stop_other_children(celery_app, tmp_path, monkeypatch):
    from app.services import release_pipeline as rp

    monkeypatch.setattr("app.tasks.ollama_tasks.OllamaClient", FakeOllama)
    celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
    _, _, rid, kid_ids = _seed(celery_app, tmp_path)
    failing_code = None
    with celery_app.app_context():
        failing_code = db.session.get(Idea, uuid.UUID(kid_ids[0])).reference_code

    real_enqueue = rp._enqueue_launch

    def flaky_enqueue(launch):
        if launch["args"][1] == "PRD_DOC":
            idea = db.session.get(Idea, uuid.UUID(launch["args"][0]))
            if idea is not None and idea.reference_code == failing_code:
                run = db.session.get(PromptRun, uuid.UUID(launch["run_id"]))
                run.status = PromptRunStatus.FAILED
                run.error = "model returned nonsense"
                db.session.commit()
                return
        real_enqueue(launch)

    monkeypatch.setattr(rp, "_enqueue_launch", flaky_enqueue)

    with celery_app.app_context():
        release = db.session.get(Release, uuid.UUID(rid))
        assert start_release_pipeline(release, None)[0]
        assert _run_until_done(rid)

        release = db.session.get(Release, uuid.UUID(rid))
        assert release.pipeline_status == "failed"
        assert release.status == "in_progress"
        assert "did not finish" in (release.pipeline_error or "")
        state = release.pipeline_state
        failed = next(
            c for c in state["children"].values() if c["reference_code"] == failing_code
        )
        assert failed["prd"] == "failed"
        assert failed["design"] == "skipped"
        other = next(
            c for c in state["children"].values() if c["reference_code"] != failing_code
        )
        assert other["test"] == "done"
        assert other["build"] == "done"


def test_repo_snapshot_includes_app_and_skips_noise(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (tmp_path / "notes.bin").write_bytes(b"\x00\x01")
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "ignored.py").write_text("x = 1\n", encoding="utf-8")
    modules = tmp_path / "node_modules" / "pkg"
    modules.mkdir(parents=True)
    (modules / "index.js").write_text("noop();\n", encoding="utf-8")

    snapshot = existing_repo_snapshot(str(tmp_path))
    assert "EXISTING PROJECT FILES" in snapshot
    assert "--- app.py ---" in snapshot
    assert "requirements.txt" in snapshot
    assert "ignored.py" not in snapshot
    assert "node_modules" not in snapshot
    assert "notes.bin" not in snapshot
    assert existing_repo_snapshot(str(tmp_path / "missing")) == ""


def test_pipeline_routes_start_and_stop(admin_client, app, tmp_path):
    inst_id, parent_id, rid, kid_ids = _seed(app, tmp_path)

    res = admin_client.post(f"/api/v1/releases/{rid}/pipeline")
    assert res.status_code == 202, res.get_json()
    body = res.get_json()["data"]
    assert body["release"]["pipeline"]["status"] == "running"
    assert body["release"]["pipeline"]["phase"] == "prd"

    res = admin_client.get(f"/api/v1/releases/{rid}/pipeline")
    assert res.status_code == 200
    assert res.get_json()["data"]["pipeline"]["total"] == 2

    res = admin_client.post(f"/api/v1/releases/{rid}/pipeline/stop")
    assert res.status_code == 200
    with app.app_context():
        release = db.session.get(Release, uuid.UUID(rid))
        assert release.pipeline_status == "stopping"


def test_pipeline_rejects_empty_release(admin_client, app, tmp_path):
    with app.app_context():
        inst = Instance(number=9901, name="Empty rel")
        db.session.add(inst)
        db.session.flush()
        parent = _make_idea(inst, "IDEA-EMPTY1", "Empty", "SCALE")
        release = Release(parent_idea_id=parent.id, instance_id=inst.id, name="R")
        db.session.add(release)
        db.session.commit()
        rid = str(release.id)

    res = admin_client.post(f"/api/v1/releases/{rid}/pipeline")
    assert res.status_code == 400
    assert "Nothing in this release" in res.get_json()["message"]
