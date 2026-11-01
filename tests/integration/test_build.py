"""BUILD_CODE: gates, targets CRUD, preview/write task flow."""

import json
import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models import (
    Idea,
    Instance,
    InstanceBuildTarget,
    Membership,
    PromptConfig,
    PromptRun,
    SecondaryActionResult,
    User,
    UserRole,
)


def make_instance(number, name=None):
    instance = Instance(number=number, name=name or f"Inst {number}")
    db.session.add(instance)
    db.session.flush()
    return instance


def make_user(email, role=UserRole.USER):
    user = User(email=email, role=role)
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    return user


def grant(user, instance, role):
    db.session.add(Membership(user_id=user.id, instance_id=instance.id, role=role))
    db.session.flush()


def login(client, email, instance_id=None):
    body = {"email": email, "password": "password123"}
    if instance_id:
        body["instance_id"] = str(instance_id)
    res = client.post("/api/v1/login", json=body)
    assert res.status_code == 200, res.get_json()
    return {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}


_seed_counter = [0]


def seed_idea(db, instance_id, email="build@t.test", status="SHIP"):
    from app.models import ROLE_INSTANCE_ADMIN

    _seed_counter[0] += 1
    admin = make_user(email)
    inst = db.session.get(Instance, instance_id)
    grant(admin, inst, ROLE_INSTANCE_ADMIN)
    prompt = PromptConfig(
        title="B",
        prompt_body="b",
        interval_minutes=60,
        model_name="llama3:8b",
        provider="ollama",
        is_active=True,
        created_by_id=admin.id,
        instance_id=inst.id,
    )
    db.session.add(prompt)
    db.session.flush()
    idea = Idea(
        reference_code=f"IDEA-B{_seed_counter[0]:04d}",
        prompt_title="B",
        raw_content="content",
        status=status,
        prompt_config_id=prompt.id,
        instance_id=inst.id,
    )
    db.session.add(idea)
    db.session.commit()
    return idea


def seed_design(idea, version=1, current=True):
    row = SecondaryActionResult(
        idea_id=idea.id,
        action_type="DESIGN_DOC",
        model_used="llama3:8b",
        provider_used="ollama",
        result_data={
            "architecture": "x" * 30,
            "screens": "y" * 30,
            "data_model": "z" * 30,
            "api_contracts": "w" * 30,
            "build_notes": "v" * 30,
            "open_questions": [],
        },
        version=version,
        is_current=current,
        instance_id=idea.instance_id,
    )
    db.session.add(row)
    db.session.commit()
    return row


def seed_target(instance_id, name="repo", path=None, admin_id=None):
    target = InstanceBuildTarget(
        instance_id=instance_id,
        name=name,
        path=path or "/tmp",
        created_by_id=admin_id,
    )
    db.session.add(target)
    db.session.commit()
    return target


MANIFEST = {
    "summary": "Minimal notes app slice with tests, all runnable locally.",
    "files": [
        {"path": "src/app.py", "content": "print('hello')\n"},
        {"path": "tests/test_app.py", "content": "def test_x():\n    assert True\n"},
    ],
}


class TestBuildGates:
    def test_build_requires_ship(self, app, client):
        with app.app_context():
            inst = make_instance(80, "BG")
            idea = seed_idea(db, inst.id, status="SCOPE")
            iid = inst.id
            idea_id = idea.id
        headers = login(client, "build@t.test", str(iid))
        res = client.post(
            f"/api/v1/ideas/{idea_id}/actions",
            json={"action_type": "BUILD_CODE", "confirm": True},
            headers=headers,
        )
        assert res.status_code == 400
        assert "Ship" in res.get_json()["message"]

    def test_build_requires_design_doc(self, app, client):
        with app.app_context():
            inst = make_instance(81, "BG2")
            idea = seed_idea(db, inst.id, email="build2@t.test")
            iid = inst.id
            idea_id = idea.id
        headers = login(client, "build2@t.test", str(iid))
        res = client.post(
            f"/api/v1/ideas/{idea_id}/actions",
            json={"action_type": "BUILD_CODE", "confirm": True},
            headers=headers,
        )
        assert res.status_code == 400
        assert "Design" in res.get_json()["message"]

    def test_build_requires_target(self, app, client):
        with app.app_context():
            inst = make_instance(82, "BG3")
            idea = seed_idea(db, inst.id, email="build3@t.test")
            seed_design(idea)
            iid = inst.id
            idea_id = idea.id
        headers = login(client, "build3@t.test", str(iid))
        res = client.post(
            f"/api/v1/ideas/{idea_id}/actions",
            json={"action_type": "BUILD_CODE", "confirm": True},
            headers=headers,
        )
        assert res.status_code == 400
        assert "No build repo selected" in res.get_json()["message"]


class TestBuildTargets:
    def test_crud_validation(self, app, client, tmp_path):
        from app.models import ROLE_INSTANCE_ADMIN

        with app.app_context():
            inst = make_instance(83, "BT")
            admin = make_user("bt@t.test")
            grant(admin, inst, ROLE_INSTANCE_ADMIN)
            db.session.commit()
            iid = inst.id
        headers = login(client, "bt@t.test", str(iid))

        # Missing name rejected.
        res = client.post(
            f"/api/v1/instances/{iid}/build-targets",
            json={"name": "", "path": str(tmp_path)},
            headers=headers,
        )
        assert res.status_code == 400

        # Outside roots / missing dir rejected (fail closed).
        res = client.post(
            f"/api/v1/instances/{iid}/build-targets",
            json={"name": "r", "path": "/definitely/not/here-xyz"},
            headers=headers,
        )
        assert res.status_code == 400

        # Valid root (tmp is outside default empty roots -> still 400
        # unless configured; here we only assert the shape, not success).
        res = client.get(f"/api/v1/instances/{iid}/build-targets", headers=headers)
        assert res.status_code == 200
        assert res.get_json()["data"]["targets"] == []

    def test_create_and_delete_with_roots(self, app, client, tmp_path):
        with app.app_context():
            from flask import current_app

            # Route reads flask config (base default is fail-closed "").
            current_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
            inst = make_instance(84, "BT2")
            admin = make_user("bt2@t.test")
            grant(admin, inst, "INSTANCE_ADMIN")
            db.session.commit()
            iid = inst.id
        headers = login(client, "bt2@t.test", str(iid))
        sub = tmp_path / "repo"
        sub.mkdir()
        res = client.post(
            f"/api/v1/instances/{iid}/build-targets",
            json={"name": "repo", "path": str(sub)},
            headers=headers,
        )
        assert res.status_code == 201, res.get_json()
        tid = res.get_json()["data"]["target"]["id"]
        # Duplicate name.
        res = client.post(
            f"/api/v1/instances/{iid}/build-targets",
            json={"name": "repo", "path": str(sub)},
            headers=headers,
        )
        assert res.status_code == 409
        # Delete.
        res = client.delete(
            f"/api/v1/instances/{iid}/build-targets/{tid}", headers=headers
        )
        assert res.status_code == 200


def _mock_manifest(monkeypatch=None):
    from app.services.llm_backends import GenerationResult

    return GenerationResult(text=json.dumps(MANIFEST), model="llama3:8b")


class TestBuildTargetResolution:
    """Which repo a BUILD_CODE run writes into."""

    def test_prefers_repo_named_after_idea(self, app, tmp_path):
        from app.routes.ideas import _resolve_build_target

        with app.app_context():
            inst = make_instance(74, "BR")
            idea = seed_idea(db, inst.id, email="br@t.test")
            other = seed_target(inst.id, name="IDEA-9603", path=str(tmp_path / "a"))
            own = seed_target(
                inst.id, name=idea.reference_code, path=str(tmp_path / "b")
            )
            db.session.commit()
            # The per-idea repo wins over the instance's other repo.
            assert _resolve_build_target(idea, None).id == own.id
            # An explicit choice is still honoured.
            assert _resolve_build_target(idea, str(other.id)).id == other.id

    def test_falls_back_to_only_repo(self, app, tmp_path):
        from app.routes.ideas import _resolve_build_target

        with app.app_context():
            inst = make_instance(75, "BR2")
            idea = seed_idea(db, inst.id, email="br2@t.test")
            only = seed_target(inst.id, name="shared", path=str(tmp_path / "c"))
            db.session.commit()
            assert _resolve_build_target(idea, None).id == only.id


class TestBuildTask:
    def test_preview_saves_manifest_unwritten(self, celery_app, tmp_path):
        celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
        with celery_app.app_context():
            inst = make_instance(85, "BP")
            idea = seed_idea(db, inst.id, email="bp@t.test")
            seed_design(idea)
            target = seed_target(inst.id, path=str(tmp_path))
            tid, idea_id = target.id, idea.id
            run = PromptRun(
                prompt_config_id=None,
                action_type="BUILD_CODE",
                idea_id=idea.id,
                triggered_by="manual",
            )
            db.session.add(run)
            db.session.commit()
            rid = run.id

            from app.tasks.ollama_tasks import run_secondary_action

            with patch("app.tasks.ollama_tasks.OllamaClient") as mock_cls:
                mock_cls.return_value.generate_sync.return_value = {
                    "response": json.dumps(MANIFEST)
                }
                run_secondary_action(
                    str(idea_id),
                    "BUILD_CODE",
                    extra_context={"target_id": str(tid)},
                    run_id=str(rid),
                )
            row = SecondaryActionResult.query.filter_by(
                idea_id=idea_id, action_type="BUILD_CODE"
            ).one()
            assert row.version == 1 and row.is_current is True
            assert row.result_data["written"] is False
            assert [f["path"] for f in row.result_data["files"]] == [
                "src/app.py",
                "tests/test_app.py",
            ]
            assert row.target_id is not None and row.target_name == "repo"
            assert row.result_data.get("target_path") == str(tmp_path)
            db.session.expire_all()
            assert db.session.get(PromptRun, rid).status.value == "SUCCESS"
            # Nothing written yet.
            assert not (tmp_path / "src" / "app.py").exists()

    def test_confirm_writes_files_new_version(self, celery_app, tmp_path):
        celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
        with celery_app.app_context():
            inst = make_instance(86, "BC")
            idea = seed_idea(db, inst.id, email="bc@t.test")
            seed_design(idea)
            target = seed_target(inst.id, path=str(tmp_path))
            tid, idea_id = target.id, idea.id

            from app.tasks.ollama_tasks import run_secondary_action

            with patch("app.tasks.ollama_tasks.OllamaClient") as mock_cls:
                mock_cls.return_value.generate_sync.return_value = {
                    "response": json.dumps(MANIFEST)
                }
                run_secondary_action(
                    str(idea_id),
                    "BUILD_CODE",
                    extra_context={"target_id": str(tid)},
                )
                # Confirm path must not call the LLM again.
                mock_cls.return_value.generate_sync.reset_mock()
                run_secondary_action(
                    str(idea_id),
                    "BUILD_CODE",
                    extra_context={"target_id": str(tid), "confirm_build": True},
                )
                mock_cls.return_value.generate_sync.assert_not_called()
            assert (tmp_path / "src" / "app.py").read_text() == "print('hello')\n"
            rows = (
                SecondaryActionResult.query.filter_by(
                    idea_id=idea_id, action_type="BUILD_CODE"
                )
                .order_by(SecondaryActionResult.version)
                .all()
            )
            assert [r.version for r in rows] == [1, 2]
            assert rows[1].result_data["written"] is True
            assert rows[1].result_data["write_report"]
            assert rows[1].result_data.get("target_path") == str(tmp_path)

    def test_confirm_refuses_unrunnable_manifest(self, celery_app, tmp_path):
        """No entry point -> fail before writing, so Built means runnable."""
        celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
        manifest = {
            "summary": "Notes about the build with no runnable entry point.",
            "files": [{"path": "README.md", "content": "hi\n"}],
        }
        with celery_app.app_context():
            inst = make_instance(73, "BU")
            idea = seed_idea(db, inst.id, email="bu@t.test")
            seed_design(idea)
            target = seed_target(inst.id, path=str(tmp_path))
            tid, idea_id = target.id, idea.id
            run = PromptRun(
                prompt_config_id=None,
                action_type="BUILD_CODE",
                idea_id=idea.id,
                triggered_by="manual",
            )
            db.session.add(run)
            db.session.commit()
            rid = run.id

            from app.tasks.ollama_tasks import run_secondary_action

            with patch("app.tasks.ollama_tasks.OllamaClient") as mock_cls:
                mock_cls.return_value.generate_sync.return_value = {
                    "response": json.dumps(manifest)
                }
                run_secondary_action(
                    str(idea_id),
                    "BUILD_CODE",
                    extra_context={"target_id": str(tid)},
                )
                run_secondary_action(
                    str(idea_id),
                    "BUILD_CODE",
                    extra_context={"target_id": str(tid), "confirm_build": True},
                    run_id=str(rid),
                )
            db.session.expire_all()
            failed = db.session.get(PromptRun, rid)
            assert failed.status.value == "FAILED"
            assert "runnable entry point" in (failed.error or "")
            # Nothing was written, and no version claims to be Built.
            assert not (tmp_path / "README.md").exists()
            rows = SecondaryActionResult.query.filter_by(
                idea_id=idea_id, action_type="BUILD_CODE"
            ).all()
            assert len(rows) == 1
            assert rows[0].result_data["written"] is False

    def test_confirm_without_preview_fails(self, celery_app, tmp_path):
        celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
        with celery_app.app_context():
            inst = make_instance(87, "BN")
            idea = seed_idea(db, inst.id, email="bn@t.test")
            seed_design(idea)
            target = seed_target(inst.id, path=str(tmp_path))
            tid, idea_id = target.id, idea.id
            run = PromptRun(
                prompt_config_id=None,
                action_type="BUILD_CODE",
                idea_id=idea.id,
                triggered_by="manual",
            )
            db.session.add(run)
            db.session.commit()
            rid = run.id

            from app.tasks.ollama_tasks import run_secondary_action

            run_secondary_action(
                str(idea_id),
                "BUILD_CODE",
                extra_context={"target_id": str(tid), "confirm_build": True},
                run_id=str(rid),
            )
            db.session.expire_all()
            assert db.session.get(PromptRun, rid).status.value == "FAILED"


class TestBuildSchema:
    def test_unsafe_paths_rejected(self):
        from pydantic import ValidationError

        from app.schemas.ollama_schemas import BuildCodeOutput

        summary = "A proper summary of what was built here ok."
        for bad in [
            "/abs/path.py",
            "../escape.py",
            "a/../../b.py",
            "",
            "x" * 201,
            "~/x.py",
            "C:/x.py",
        ]:
            with pytest.raises(ValidationError):
                BuildCodeOutput(summary=summary, files=[{"path": bad, "content": "x"}])

    def test_caps_enforced(self):
        from pydantic import ValidationError

        from app.schemas.ollama_schemas import BuildCodeOutput

        big = "x" * 15001
        try:
            BuildCodeOutput(
                summary="A proper summary of what was built here ok.",
                files=[{"path": "a.py", "content": big}],
            )
        except ValidationError:
            pass
        else:
            raise AssertionError("oversize file accepted")

    def test_traversal_write_refused(self, tmp_path):
        from app.services.build_service import BuildError, join_target_path

        try:
            join_target_path(str(tmp_path), "../escape.py")
        except BuildError:
            pass
        else:
            raise AssertionError("traversal accepted")
        assert join_target_path(str(tmp_path), "src/a.py") == str(
            tmp_path / "src" / "a.py"
        )


class TestTargetDefaults:
    def test_config_default_root_is_repo_projects(self, app):
        with app.app_context():
            from flask import current_app

            roots = current_app.config["OPENCODE_BUILD_ROOTS"]
            assert roots.endswith(os.path.join("", "projects")) or "projects" in roots

    def test_create_auto_creates_missing_dir(self, app, client, tmp_path):
        import os as _os

        with app.app_context():
            from flask import current_app

            current_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
            inst = make_instance(88, "BD")
            admin = make_user("bd@t.test")
            grant(admin, inst, "INSTANCE_ADMIN")
            db.session.commit()
            iid = inst.id
        headers = login(client, "bd@t.test", str(iid))
        new_dir = tmp_path / "auto" / "nested"
        assert not new_dir.exists()
        res = client.post(
            f"/api/v1/instances/{iid}/build-targets",
            json={"name": "auto", "path": str(new_dir)},
            headers=headers,
        )
        assert res.status_code == 201, res.get_json()
        assert new_dir.is_dir()

    def test_create_hands_new_dir_to_parent_owner(
        self, app, client, tmp_path, monkeypatch
    ):
        import os as _os

        with app.app_context():
            from flask import current_app

            current_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
            inst = make_instance(90, "BH")
            admin = make_user("bh@t.test")
            grant(admin, inst, "INSTANCE_ADMIN")
            db.session.commit()
            iid = inst.id
        headers = login(client, "bh@t.test", str(iid))
        calls = []
        real_chown = _os.chown

        def _spy(path, uid, gid, *a, **k):
            calls.append((str(path), uid, gid))
            return real_chown(path, uid, gid, *a, **k)

        monkeypatch.setattr(_os, "chown", _spy)
        new_dir = tmp_path / "owned" / "repo"
        res = client.post(
            f"/api/v1/instances/{iid}/build-targets",
            json={"name": "owned", "path": str(new_dir)},
            headers=headers,
        )
        assert res.status_code == 201, res.get_json()
        parent = _os.stat(tmp_path)
        # Both created levels (not just the leaf) inherit the owner.
        assert calls == [
            (str(new_dir), parent.st_uid, parent.st_gid),
            (str(tmp_path / "owned"), parent.st_uid, parent.st_gid),
        ]

    def test_create_outside_roots_still_refused(self, app, client, tmp_path):
        with app.app_context():
            from flask import current_app

            current_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
            inst = make_instance(89, "BE")
            admin = make_user("be@t.test")
            grant(admin, inst, "INSTANCE_ADMIN")
            db.session.commit()
            iid = inst.id
        headers = login(client, "be@t.test", str(iid))
        res = client.post(
            f"/api/v1/instances/{iid}/build-targets",
            json={"name": "evil", "path": "/tmp/evil-root-xyz"},
            headers=headers,
        )
        assert res.status_code == 400

    def test_list_includes_defaults(self, app, client):
        with app.app_context():
            inst = make_instance(90, "BF")
            admin = make_user("bf@t.test")
            grant(admin, inst, "INSTANCE_ADMIN")
            db.session.commit()
            iid = inst.id
        headers = login(client, "bf@t.test", str(iid))
        res = client.get(f"/api/v1/instances/{iid}/build-targets", headers=headers)
        assert res.status_code == 200
        assert "defaults" in res.get_json()["data"]

    def test_defaults_include_configured_root(self, app, client, tmp_path):
        from app.models import SystemSettings

        with app.app_context():
            from flask import current_app

            current_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
            inst = make_instance(91, "BG")
            admin = make_user("bg@t.test")
            grant(admin, inst, "INSTANCE_ADMIN")
            db.session.add(
                SystemSettings(
                    instance_id=inst.id, builds={"default_root": str(tmp_path)}
                )
            )
            db.session.commit()
            iid = inst.id
        headers = login(client, "bg@t.test", str(iid))
        res = client.get(f"/api/v1/instances/{iid}/build-targets", headers=headers)
        assert res.status_code == 200
        assert res.get_json()["data"]["defaults"]["configured_root"] == str(tmp_path)


class TestBuildRuntimeInfo:
    def test_extract_from_dockerfile_and_compose(self):
        from app.tasks.ollama_tasks import _extract_runtime_info

        info = _extract_runtime_info(
            [
                {
                    "path": "Dockerfile",
                    "content": 'FROM python:3.12\nEXPOSE 8000\nCMD ["python", "-m", "uvicorn", "src.main:app"]\n',
                },
                {
                    "path": "docker-compose.yml",
                    "content": 'services:\n  api:\n    ports: ["3000:8000"]\n',
                },
                {
                    "path": ".env.example",
                    "content": "#x\nADMIN_USER=admin\nADMIN_PASSWORD=secret\n",
                },
            ]
        )
        assert info["port"] == 3000
        assert "uvicorn" in (info["start_command"] or "")
        from app.tasks.ollama_tasks import _host_network_ip
        assert info["app_url"] == f"http://{_host_network_ip()}:3000"
        assert info["frontend_url"] is None
        assert info["credentials"] == {
            "ADMIN_USER": "<set via environment>",
            "ADMIN_PASSWORD": "<set via environment>",
        }
        assert info["run_notes"]
        # The How-to-run panel already shows the command as a copyable Run
        # row — the notes must not restate it.
        assert "Start command:" not in (info["run_notes"] or "")

    def test_extract_frontend_service_url(self):
        from app.tasks.ollama_tasks import _extract_runtime_info

        info = _extract_runtime_info(
            [
                {
                    "path": "docker-compose.yml",
                    "content": (
                        "services:\n"
                        "  backend:\n"
                        "    ports: ['8001:8000']\n"
                        "  frontend:\n"
                        "    image: nginx:alpine\n"
                        '    ports: ["3000:3000"]\n'
                    ),
                },
            ]
        )
        # Backend keeps the API port; the human UI gets its own URL.
        assert info["port"] == 8001
        from app.tasks.ollama_tasks import _host_network_ip
        assert info["app_url"] == f"http://{_host_network_ip()}:8001"
        assert info["frontend_port"] == 3000
        from app.tasks.ollama_tasks import _host_network_ip
        assert info["frontend_url"] == f"http://{_host_network_ip()}:3000"
        # The browser line names the UI, never the raw API.
        from app.tasks.ollama_tasks import _host_network_ip
        assert f"http://{_host_network_ip()}:3000" in (info["run_notes"] or "")
        assert "Open http://localhost:8001" not in (info["run_notes"] or "")

    def test_extract_empty_manifest(self):
        from app.tasks.ollama_tasks import _extract_runtime_info

        info = _extract_runtime_info([{"path": "README.md", "content": "hi"}])
        assert info["port"] is None
        assert info["start_command"] is None
        assert info["run_notes"] is None

    def test_infers_flask_entry_without_dockerfile(self):
        from app.tasks.ollama_tasks import _extract_runtime_info

        info = _extract_runtime_info(
            [
                {
                    "path": "app.py",
                    "content": "from flask import Flask\napp = Flask(__name__)\n",
                },
                {"path": "templates/index.html", "content": "<h1>hi</h1>"},
            ]
        )
        assert info["start_command"] == (
            "python3 -m flask --app app run --host 0.0.0.0 --port 5000"
        )
        assert info["port"] == 5000
        assert info["app_url"].endswith(":5000")
        assert "inferred from app.py" in (info["run_notes"] or "")
        # No requirements.txt shipped: say so instead of failing at start.
        assert "install flask" in (info["run_notes"] or "")

    def test_infers_fastapi_entry_under_src(self):
        from app.tasks.ollama_tasks import _extract_runtime_info

        info = _extract_runtime_info(
            [
                {
                    "path": "src/main.py",
                    "content": "from fastapi import FastAPI\napp = FastAPI()\n",
                },
                {"path": "requirements.txt", "content": "fastapi\nuvicorn\n"},
            ]
        )
        assert info["start_command"] == (
            "python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000"
        )
        assert info["port"] == 8000

    def test_infers_plain_script_entry(self):
        from app.tasks.ollama_tasks import _extract_runtime_info

        info = _extract_runtime_info(
            [{"path": "src/app.py", "content": "print('hello')\n"}]
        )
        assert info["start_command"] == "python3 src/app.py"
        assert info["port"] is None

    def test_dockerfile_cmd_wins_over_inference(self):
        from app.tasks.ollama_tasks import _extract_runtime_info

        info = _extract_runtime_info(
            [
                {"path": "Dockerfile", "content": 'FROM x\nCMD ["node", "server.js"]\n'},
                {
                    "path": "app.py",
                    "content": "from flask import Flask\napp = Flask(__name__)\n",
                },
            ]
        )
        assert info["start_command"] == '["node", "server.js"]'


def _hold_port():
    """Bind+listen an ephemeral port; returns (socket, port)."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


class TestBuildPortAllocation:
    def test_port_in_use(self):
        from app.services.build_service import port_in_use

        sock, busy = _hold_port()
        try:
            assert port_in_use(busy) is True
        finally:
            sock.close()
        assert port_in_use(0) is False
        assert port_in_use("not-a-port") is False

    def test_time_wait_after_clean_stop_reads_free(self):
        """A just-stopped server leaves TIME_WAIT sockets; a restart must
        not read those as busy (the failure seen live after stopping the
        8001 app). Server-side close puts our side in TIME_WAIT."""
        import socket as _socket
        import time as _time

        from app.services.build_service import port_in_use

        srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        srv.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        try:
            cli.connect(("127.0.0.1", port))
            conn, _ = srv.accept()
            conn.close()  # server closes first -> our TIME_WAIT
            _time.sleep(0.2)
            srv.close()  # listener gone: only TIME_WAIT remains
            assert port_in_use(port) is False
        finally:
            cli.close()
            srv.close()

    def test_allocate_port_skips_busy(self):
        from app.services.build_service import allocate_port, port_in_use

        sock, busy = _hold_port()
        try:
            port, changed = allocate_port(busy)
            assert changed is True
            assert port != busy
            assert port_in_use(port) is False
        finally:
            sock.close()

    def test_allocate_build_port_free_keeps_values(self):
        import socket

        from app.tasks.ollama_tasks import _allocate_build_port

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
        probe.close()
        runtime = {"port": free, "app_url": f"http://localhost:{free}"}
        out, files, report = _allocate_build_port(runtime, [])
        assert out["port"] == free
        assert out.get("port_changed") is not True
        assert report == []

    def test_allocate_build_port_rewrites_host_side(self):
        from app.tasks.ollama_tasks import _allocate_build_port

        from app.tasks.ollama_tasks import _host_network_ip

        sock, busy = _hold_port()
        try:
            runtime = {
                "port": busy,
                "app_url": f"http://{_host_network_ip()}:{busy}",
                "start_command": '["python", "-m", "uvicorn", "src.main:app", '
                f'"--host", "0.0.0.0", "--port", "{busy}"]',
                "run_notes": f"Open http://localhost:{busy} in your browser once it is running.",
            }
            files = [
                {
                    "path": "docker-compose.yml",
                    "content": (
                        "services:\n  web:\n    image: demo\n"
                        f'    ports: ["{busy}:8000"]\n'
                    ),
                }
            ]
            out, new_files, report = _allocate_build_port(runtime, files)
            new = out["port"]
            assert new != busy
            assert out["port_requested"] == busy
            assert out["port_changed"] is True
            assert out["app_url"] == f"http://{_host_network_ip()}:{new}"
            assert f'"{new}"]' in out["start_command"]
            assert f'"{busy}"]' not in out["start_command"]
            assert f"http://{_host_network_ip()}:{new}" in out["run_notes"]
            assert f"http://{_host_network_ip()}:{busy}" not in out["run_notes"]
            assert f"{new}:8000" in new_files[0]["content"]
            assert f"{busy}:8000" not in new_files[0]["content"]
            # Plain language for non-technical users, on the row and report.
            assert "already in use" in out["run_notes"]
            assert any("already in use" in line for line in report)
        finally:
            sock.close()

    def test_allocate_frontend_port_moves_dashboard(self):
        from app.tasks.ollama_tasks import _allocate_build_port

        import socket

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        free_api = probe.getsockname()[1]
        probe.close()
        from app.tasks.ollama_tasks import _host_network_ip

        sock, busy = _hold_port()
        try:
            runtime = {
                "port": free_api,
                "app_url": f"http://{_host_network_ip()}:{free_api}",
                "frontend_port": busy,
                "frontend_url": f"http://{_host_network_ip()}:{busy}",
                "run_notes": f"Open http://localhost:{busy} in your browser once it is running.",
            }
            files = [
                {
                    "path": "docker-compose.yml",
                    "content": (
                        "services:\n  backend:\n    ports: "
                        f'["{free_api}:8000"]\n  frontend:\n    ports: ["{busy}:3000"]\n'
                    ),
                }
            ]
            out, new_files, report = _allocate_build_port(runtime, files)
            new = out["frontend_port"]
            assert new != busy
            assert out["frontend_url"] == f"http://{_host_network_ip()}:{new}"
            # Backend untouched.
            assert out["port"] == free_api
            assert f"{new}:3000" in new_files[0]["content"]
            assert f"{busy}:3000" not in new_files[0]["content"]
            assert f"http://{_host_network_ip()}:{new}" in out["run_notes"]
            assert any("Dashboard port" in line for line in report)
        finally:
            sock.close()


class TestServerPath:
    def test_translates_container_root_to_host(self, tmp_path, monkeypatch):
        import os as _os

        from app.services import build_service as bs

        monkeypatch.setenv("OPENCODE_BUILD_ROOTS", f"/app/projects{_os.pathsep}/builds")
        monkeypatch.setenv(
            "OPENCODE_SERVER_BUILD_ROOTS",
            f"/mnt/host/projects{_os.pathsep}/mnt/host/builds",
        )
        assert bs.server_path("/app/projects/IDEA-1") == "/mnt/host/projects/IDEA-1"
        assert bs.server_path("/builds/x") == "/mnt/host/builds/x"

    def test_unmapped_paths_pass_through(self, tmp_path, monkeypatch):
        import os as _os

        from app.services import build_service as bs

        monkeypatch.setenv("OPENCODE_BUILD_ROOTS", "/app")
        monkeypatch.delenv("OPENCODE_SERVER_BUILD_ROOTS", raising=False)
        assert bs.server_path("/app/x") == "/app/x"
        assert bs.server_path("") == ""
        # Shorter server list: extras stay untranslated, never raise.
        monkeypatch.setenv("OPENCODE_SERVER_BUILD_ROOTS", "/mnt/host/a")
        monkeypatch.setenv("OPENCODE_BUILD_ROOTS", f"/app{_os.pathsep}/builds")
        assert bs.server_path("/builds/x") == "/builds/x"

    def test_container_path_inverts_server_path(self, tmp_path, monkeypatch):
        import os as _os

        from app.services import build_service as bs

        monkeypatch.setenv("OPENCODE_BUILD_ROOTS", f"/app/projects{_os.pathsep}/builds")
        monkeypatch.setenv(
            "OPENCODE_SERVER_BUILD_ROOTS",
            f"/mnt/host/projects{_os.pathsep}/mnt/host/builds",
        )
        assert (
            bs.container_path("/mnt/host/projects/IDEA-1/backend")
            == "/app/projects/IDEA-1/backend"
        )
        assert bs.container_path("/mnt/host/builds/x") == "/builds/x"
        assert bs.container_path("/elsewhere/x") == "/elsewhere/x"
        assert bs.container_path("") == ""


class TestDeriveRunbook:
    _FILES = [
        {"path": "backend/src/main.py", "content": "x"},
        {"path": "backend/src/config.py", "content": "x"},
        {"path": "backend/requirements.txt", "content": "fastapi\n"},
        {"path": "docker-compose.yml", "content": "x"},
    ]

    def test_uvicorn_module_resolves_app_dir(self):
        from app.tasks.ollama_tasks import _derive_runbook

        rb = _derive_runbook(
            self._FILES,
            '["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]',
            "/mnt/host/IDEA-1",
        )
        assert rb is not None
        assert rb["workdir"] == "/mnt/host/IDEA-1/backend"
        assert rb["setup"] == (
            'cd "/mnt/host/IDEA-1/backend" && rm -rf .venv && python3 -m venv .venv '
            "&& . .venv/bin/activate && .venv/bin/pip install fastapi"
        )
        assert rb["setup_fallback"] == (
            'cd "/mnt/host/IDEA-1/backend" && rm -rf .venv && python3 -m venv .venv '
            "&& . .venv/bin/activate && .venv/bin/pip install -r requirements.txt"
        )
        assert rb["workdir"] == "/mnt/host/IDEA-1/backend"
        assert rb["venv_dir"] == "/mnt/host/IDEA-1/backend/.venv"
        assert rb["setup_argv"] == [
            "python3",
            "-m",
            "venv",
            "--upgrade",
            "/mnt/host/IDEA-1/backend/.venv",
        ]
        assert rb["pip_argv"] == [
            "/mnt/host/IDEA-1/backend/.venv/bin/pip",
            "install",
            "-r",
            "requirements.txt",
        ]
        assert rb["pip_fallback_argv"] == [
            "/mnt/host/IDEA-1/backend/.venv/bin/pip",
            "install",
            "fastapi",
        ]
        assert rb["run_argv"] == [
            "/mnt/host/IDEA-1/backend/.venv/bin/python",
            "-m",
            "uvicorn",
            "src.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8001",
        ]
        assert rb["run"] == (
            'cd "/mnt/host/IDEA-1/backend" && . .venv/bin/activate '
            "&& python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8001"
        )

    def test_container_argv_uses_container_root(self):
        from app.tasks.ollama_tasks import _derive_runbook

        rb = _derive_runbook(
            self._FILES,
            '["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]',
            "/mnt/host/IDEA-1",
            "/app/projects/IDEA-1",
        )
        assert rb is not None
        # Display strings stay host-native for pasting...
        assert rb["workdir"] == "/mnt/host/IDEA-1/backend"
        assert rb["run"].startswith('cd "/mnt/host/IDEA-1/backend"')
        # ...while supervision argv is container-native for the runner.
        assert rb["workdir_container"] == "/app/projects/IDEA-1/backend"
        assert rb["run_argv"][0] == "/app/projects/IDEA-1/backend/.venv/bin/python"
        assert rb["setup_argv"][-1] == "/app/projects/IDEA-1/backend/.venv"

    def test_unresolvable_or_requirementless_returns_none(self):
        from app.tasks.ollama_tasks import _derive_runbook

        assert _derive_runbook(self._FILES, "run-the-thing --fast", "/h") is None
        assert _derive_runbook([], "python app.py", "/h") is None
        assert _derive_runbook(self._FILES, "", "/h") is None
        assert _derive_runbook(self._FILES, "python app.py", "") is None
        # Stdlib-only app (no requirements): setup-less runbook, system python.
        rb = _derive_runbook(
            [{"path": "src/app.py", "content": "x"}],
            '["python", "src/app.py"]',
            "/h",
        )
        assert rb is not None
        assert rb["setup"] is None
        assert rb["run"] == 'cd "/h" && python3 src/app.py'
        # Bare interpreter: the runner resolves it against its own PATH.
        assert rb["run_argv"] == ["python3", "src/app.py"]
        assert rb["setup_argv"] == []

    def test_bare_runner_and_flask_argv(self):
        from app.tasks.ollama_tasks import _derive_runbook

        files = [
            {
                "path": "app.py",
                "content": "from flask import Flask\napp = Flask(__name__)\n",
            },
            {"path": "requirements.txt", "content": "flask\n"},
        ]
        # `python -m flask --app app run` resolves the app module.
        rb = _derive_runbook(
            files,
            "python3 -m flask --app app run --host 0.0.0.0 --port 5000",
            "/h",
            "/c",
        )
        assert rb is not None
        assert rb["workdir_container"] == "/c"
        assert rb["run_argv"] == [
            "/c/.venv/bin/python",
            "-m",
            "flask",
            "--app",
            "app",
            "run",
            "--host",
            "0.0.0.0",
            "--port",
            "5000",
        ]
        # Bare `uvicorn` (no python prefix) still gets an argv.
        rb = _derive_runbook(files, "uvicorn app:app --port 8000", "/h")
        assert rb is not None
        assert rb["run_argv"] == [
            "/h/.venv/bin/python",
            "-m",
            "uvicorn",
            "app:app",
            "--port",
            "8000",
        ]

    def test_npm_start_gets_argv_and_install(self):
        from app.tasks.ollama_tasks import _derive_runbook

        rb = _derive_runbook(
            [
                {
                    "path": "package.json",
                    "content": '{"scripts": {"start": "node server.js"}}',
                },
                {"path": "server.js", "content": "x"},
            ],
            "npm start",
            "/h",
        )
        assert rb is not None
        assert rb["run_argv"] == ["npm", "start"]
        assert rb["setup"] == 'cd "/h" && npm install'
        assert rb["setup_argv"] == ["npm", "install"]
        assert rb["pip_argv"] == []

    def test_pretty_cmd(self):
        from app.tasks.ollama_tasks import _pretty_cmd

        assert _pretty_cmd(["python", "app.py"]) == "python3 app.py"
        assert _pretty_cmd('["python", "-m", "uvicorn"]') == "python3 -m uvicorn"
        assert _pretty_cmd("python3 -m uvicorn x") == "python3 -m uvicorn x"
        assert _pretty_cmd("cd /d && python app.py") == "cd /d && python3 app.py"
        assert _pretty_cmd("/usr/bin/python app.py") == "/usr/bin/python app.py"


class TestManagedApps:
    def _written_version(self, idea, target, tmp_path, port=None):
        import socket as _socket
        import sys as _sys

        if port is None:
            sock = _socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()
        row = SecondaryActionResult(
            idea_id=idea.id,
            action_type="BUILD_CODE",
            model_used="llama3:8b",
            provider_used="ollama",
            result_data={
                "summary": "Sleep demo app for supervision tests.",
                "files": [{"path": "app.py", "content": "x"}],
                "written": True,
                "target_name": "repo",
                "target_path": str(tmp_path),
                "target_host_path": str(tmp_path),
                "start_command": "python app.py",
                "port": port,
                "runbook": {
                    "setup": None,
                    "run": "sleep demo",
                    "workdir": str(tmp_path),
                    "workdir_container": str(tmp_path),
                    "run_argv": [
                        _sys.executable,
                        "-c",
                        "import time; time.sleep(60)",
                    ],
                },
            },
            version=1,
            is_current=True,
            target_id=target.id,
            target_name="repo",
            instance_id=idea.instance_id,
        )
        db.session.add(row)
        db.session.commit()
        return row

    def _setup(self, app, email, tmp_path):
        from app.models import ManagedApp

        with app.app_context():
            inst = make_instance(95, "MA")
            idea = seed_idea(db, inst.id, email=email)
            seed_design(idea)
            target = seed_target(inst.id, path=str(tmp_path))
            self._written_version(idea, target, tmp_path)
            iid, idea_id, tid = inst.id, idea.id, target.id
        return iid, idea_id, tid

    def test_upsert_creates_from_written(self, app, client, tmp_path):
        iid, idea_id, tid = self._setup(app, "ma@t.test", tmp_path)
        headers = login(client, "ma@t.test", str(iid))
        res = client.post(
            f"/api/v1/instances/{iid}/managed-apps",
            json={"idea_id": str(idea_id), "target_id": str(tid)},
            headers=headers,
        )
        assert res.status_code == 201, res.get_json()
        body = res.get_json()["data"]["app"]
        assert body["state"] == "stopped"
        assert "python" in body["spec"]["run_argv"][0].split("/")[-1]
        assert body["live"]["state"] == "stopped"

    def test_spec_open_url_prefers_frontend(self, tmp_path):
        from types import SimpleNamespace

        from app.routes.instances import _spec_from_build_version

        version_row = SimpleNamespace(
            result_data={
                "written": True,
                "target_path": str(tmp_path),
                "target_host_path": str(tmp_path),
                "start_command": "python app.py",
                "app_url": "http://localhost:8001",
                "port": 8001,
                "frontend_url": "http://localhost:3000",
                "frontend_port": 3000,
                "files": [
                    {"path": "app.py", "content": "x"},
                    {"path": "frontend/src/index.html", "content": "<h1>hi</h1>"},
                ],
                "frontend_port": 3000,
            }
        )
        target = SimpleNamespace(path=str(tmp_path))
        spec, display, err = _spec_from_build_version(version_row, target, "IDEA-1")
        assert err is None
        # Health still polls the API; Open goes to the human UI.
        from app.tasks.ollama_tasks import _host_network_ip

        assert spec["health_url"] == f"http://{_host_network_ip()}:8001"
        assert spec["open_url"] == f"http://{_host_network_ip()}:3000"
        assert spec["frontend_run_argv"]

    def test_spec_open_url_falls_back_to_api(self, tmp_path):
        from types import SimpleNamespace

        from app.routes.instances import _spec_from_build_version

        version_row = SimpleNamespace(
            result_data={
                "written": True,
                "target_path": str(tmp_path),
                "target_host_path": str(tmp_path),
                "start_command": "python app.py",
                "app_url": "http://localhost:8001",
                "port": 8001,
                "files": [{"path": "app.py", "content": "x"}],
            }
        )
        target = SimpleNamespace(path=str(tmp_path))
        spec, display, err = _spec_from_build_version(version_row, target, "IDEA-1")
        assert err is None
        from app.tasks.ollama_tasks import _host_network_ip
        assert spec["open_url"] == f"http://{_host_network_ip()}:8001"

    def test_spec_rederives_command_for_legacy_row(self, tmp_path):
        """Rows written before entry-point inference still become runnable."""
        from types import SimpleNamespace

        from app.routes.instances import _spec_from_build_version

        version_row = SimpleNamespace(
            result_data={
                "written": True,
                "target_path": str(tmp_path),
                "target_host_path": str(tmp_path),
                "start_command": None,
                "port": None,
                "runbook": None,
                "files": [
                    {
                        "path": "app.py",
                        "content": "from flask import Flask\napp = Flask(__name__)\n",
                    },
                    {"path": "templates/index.html", "content": "<h1>hi</h1>"},
                ],
            }
        )
        target = SimpleNamespace(path=str(tmp_path))
        spec, display, err = _spec_from_build_version(version_row, target, "IDEA-1")
        assert err is None
        assert spec["run_argv"][:3] == ["python3", "-m", "flask"]
        assert "--port" in spec["run_argv"]
        # The inferred port keeps the open URL honest.
        assert spec["open_url"].endswith(":5000")

    def test_upsert_requires_written_version(self, app, client, tmp_path):
        with app.app_context():
            inst = make_instance(96, "MB")
            idea = seed_idea(db, inst.id, email="mb@t.test")
            seed_design(idea)
            target = seed_target(inst.id, path=str(tmp_path))
            iid, idea_id, tid = inst.id, idea.id, target.id
        headers = login(client, "mb@t.test", str(iid))
        res = client.post(
            f"/api/v1/instances/{iid}/managed-apps",
            json={"idea_id": str(idea_id), "target_id": str(tid)},
            headers=headers,
        )
        assert res.status_code == 400
        assert "confirm" in res.get_json()["message"].lower()

    def test_managed_apps_admin_only(self, app, client, tmp_path):
        with app.app_context():
            inst = make_instance(96, "MC")
            idea = seed_idea(db, inst.id, email="mc@t.test")
            seed_design(idea)
            target = seed_target(inst.id, path=str(tmp_path))
            self._written_version(idea, target, tmp_path)
            viewer = make_user("viewer@t.test")
            grant(viewer, inst, "USER")
            db.session.commit()
            iid, idea_id, tid = inst.id, idea.id, target.id
        headers = login(client, "viewer@t.test", str(iid))
        res = client.post(
            f"/api/v1/instances/{iid}/managed-apps",
            json={"idea_id": str(idea_id), "target_id": str(tid)},
            headers=headers,
        )
        assert res.status_code in (403, 404)

    def test_start_stop_cycle(self, app, client, tmp_path):
        iid, idea_id, tid = self._setup(app, "md@t.test", tmp_path)
        headers = login(client, "md@t.test", str(iid))
        res = client.post(
            f"/api/v1/instances/{iid}/managed-apps",
            json={"idea_id": str(idea_id), "target_id": str(tid)},
            headers=headers,
        )
        app_id = res.get_json()["data"]["app"]["id"]
        res = client.post(
            f"/api/v1/instances/{iid}/managed-apps/{app_id}/start",
            headers=headers,
        )
        assert res.status_code == 202, res.get_json()
        res = client.get(f"/api/v1/instances/{iid}/managed-apps", headers=headers)
        apps = res.get_json()["data"]["apps"]
        assert apps[0]["live"]["state"] == "running"
        assert apps[0]["live"]["pid"]
        res = client.post(
            f"/api/v1/instances/{iid}/managed-apps/{app_id}/stop",
            headers=headers,
        )
        # Stop runs on a worker (pids are container-local); eager tests
        # run it inline, prod polls the list like the UI does.
        assert res.status_code == 202, res.get_json()
        res = client.get(f"/api/v1/instances/{iid}/managed-apps", headers=headers)
        assert res.get_json()["data"]["apps"][0]["live"]["state"] == "stopped"
        res = client.get(
            f"/api/v1/instances/{iid}/managed-apps/{app_id}/logs?lines=50",
            headers=headers,
        )
        assert res.status_code == 200
        assert isinstance(res.get_json()["data"]["lines"], list)

    def test_start_twice_does_not_launch_twins(self, app, client, tmp_path):
        iid, idea_id, tid = self._setup(app, "me@t.test", tmp_path)
        headers = login(client, "me@t.test", str(iid))
        res = client.post(
            f"/api/v1/instances/{iid}/managed-apps",
            json={"idea_id": str(idea_id), "target_id": str(tid)},
            headers=headers,
        )
        app_id = res.get_json()["data"]["app"]["id"]
        try:
            res = client.post(
                f"/api/v1/instances/{iid}/managed-apps/{app_id}/start",
                headers=headers,
            )
            assert res.status_code == 202
            # The start response predates the worker: poll the list for
            # the live state (same as the UI does).
            res = client.get(f"/api/v1/instances/{iid}/managed-apps", headers=headers)
            first_pid = res.get_json()["data"]["apps"][0]["live"]["pid"]
            assert first_pid
            res = client.post(
                f"/api/v1/instances/{iid}/managed-apps/{app_id}/start",
                headers=headers,
            )
            assert res.status_code == 200
            body = res.get_json()["data"]
            assert body.get("already") is True
            assert body["app"]["live"]["pid"] == first_pid
        finally:
            client.post(
                f"/api/v1/instances/{iid}/managed-apps/{app_id}/stop",
                headers=headers,
            )

    def test_task_refuses_without_argv(self, celery_app):
        from app.models import ManagedApp
        from app.tasks.supervision_tasks import start_managed_app

        with celery_app.app_context():
            inst = make_instance(97, "ME")
            idea = seed_idea(db, inst.id, email="me@t.test")
            row = ManagedApp(
                instance_id=inst.id,
                idea_id=idea.id,
                state="stopped",
                spec={},
            )
            db.session.add(row)
            db.session.commit()
            rid = row.id
            start_managed_app(str(rid))
            db.session.expire_all()
            got = db.session.get(ManagedApp, rid)
            assert got.state == "failed"
            assert "confirm the build" in (got.last_error or "")
