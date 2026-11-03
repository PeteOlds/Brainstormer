"""Build manifests seed the Test tab.

A written build used to leave the Tests tab empty. These tests pin the
derived checklist (including a mandatory browser-level UI check), the
idempotent upsert behaviour, and the confirm-build hook that writes the
rows.
"""

import json
from unittest.mock import patch

from app.extensions import db
from app.models import IdeaTest, SecondaryActionResult
from app.models.idea_test import TestStatus as RunStatus
from app.models.idea_test import TestType as CaseType
from app.services.build_tests import derive_build_tests, seed_idea_tests
from tests.integration.test_build import (
    MANIFEST,
    make_instance,
    seed_design,
    seed_idea,
    seed_target,
)

FLASK_IDEA = [
    {
        "path": "app.py",
        "content": (
            "from flask import Flask, jsonify, render_template\n"
            "\n"
            "app = Flask(__name__)\n"
            "\n"
            "@app.route(\"/\")\n"
            "def index():\n"
            "    return render_template(\"index.html\")\n"
            "\n"
            "@app.route(\"/describe\", methods=[\"POST\"])\n"
            "def describe():\n"
            "    return jsonify({\"description\": \"x\"})\n"
        ),
    },
    {"path": "templates/index.html", "content": "<html><body>hi</body></html>"},
    {"path": "requirements.txt", "content": "flask\n"},
]


def _names(tests):
    return [t["name"].lower() for t in tests]


class TestDeriveBuildTests:
    def test_flask_app_gets_ui_and_endpoint_checks(self):
        runtime = {
            "app_url": "http://192.168.1.130:5000",
            "start_command": "python3 app.py",
        }
        tests = derive_build_tests(FLASK_IDEA, runtime, runbook={"run": "python3 app.py"})

        # The UI check comes first and is an e2e check naming the URL.
        assert tests[0]["test_type"] == "e2e"
        assert tests[0]["name"].startswith("UI:")
        assert "http://192.168.1.130:5000" in tests[0]["description"]

        names = _names(tests)
        assert any("get / returns the page" in n for n in names)
        assert any("post /describe" in n for n in names)
        assert any("dependencies install" in n for n in names)

    def test_model_tests_are_kept_and_deduped(self):
        runtime = {"app_url": "http://127.0.0.1:8000", "start_command": "flask run"}
        model_tests = [
            {
                "name": "UI: paste an image and see tags",
                "description": "Upload a PNG, expect a description and tags.",
                "test_type": "e2e",
            },
            {
                "name": "UI: paste an image and see tags",
                "description": "duplicate",
                "test_type": "e2e",
            },
            {"name": "Unknown type falls back", "test_type": "nonsense"},
        ]
        tests = derive_build_tests(
            FLASK_IDEA, runtime, model_tests=model_tests, runbook={"run": "flask run"}
        )
        names = _names(tests)
        assert names.count("ui: paste an image and see tags") == 1
        assert "unknown type falls back" in names
        assert tests[0]["name"].startswith("UI:")

    def test_api_only_build_still_has_a_browser_check(self):
        files = [
            {
                "path": "main.py",
                "content": (
                    "from fastapi import FastAPI\n"
                    "app = FastAPI()\n"
                    "@app.get(\"/health\")\n"
                    "def health():\n"
                    "    return {\"ok\": True}\n"
                ),
            }
        ]
        tests = derive_build_tests(files, {"app_url": "http://127.0.0.1:9000"})
        assert any(t["test_type"] == "e2e" for t in tests)
        assert any("get /health" in t["name"].lower() for t in tests)

    def test_no_entry_point_still_returns_a_manual_check(self):
        tests = derive_build_tests(
            [{"path": "README.md", "content": "hi"}], runtime={}
        )
        assert len(tests) == 1
        assert tests[0]["test_type"] == "manual"


class TestSeedIdeaTests:
    def test_seed_is_idempotent_and_keeps_recorded_status(self, app):
        with app.app_context():
            inst = make_instance(91, "BT")
            idea = seed_idea(db, inst.id, email="bt@t.test")
            idea_id = idea.id

            checks = [
                {"name": "UI: home loads", "test_type": "e2e"},
                {"name": "GET / responds", "test_type": "integration"},
            ]
            first = seed_idea_tests(idea, checks)
            db.session.commit()
            assert first == {"created": 2, "updated": 0, "removed": 0}

            ui = IdeaTest.query.filter_by(idea_id=idea_id, name="UI: home loads").one()
            assert ui.source == "build"
            ui.status = RunStatus.PASSED
            ui.coverage_pct = 42.0
            db.session.commit()

            # Rebuild drops the GET check, adds POST, keeps the UI one.
            second = seed_idea_tests(
                idea,
                [
                    {"name": "UI: home loads", "test_type": "e2e"},
                    {"name": "POST /describe responds", "test_type": "integration"},
                ],
            )
            db.session.commit()
            assert second == {"created": 1, "updated": 0, "removed": 1}
            ui = IdeaTest.query.filter_by(idea_id=idea_id, name="UI: home loads").one()
            assert ui.status == RunStatus.PASSED
            assert ui.coverage_pct == 42.0
            assert (
                IdeaTest.query.filter_by(idea_id=idea_id, name="GET / responds").first()
                is None
            )

    def test_manual_tests_survive_reseeding(self, app):
        with app.app_context():
            inst = make_instance(92, "BM")
            idea = seed_idea(db, inst.id, email="bm@t.test")
            manual = IdeaTest(
                idea_id=idea.id,
                name="Manually verified login",
                test_type=CaseType.MANUAL,
                status=RunStatus.PASSED,
                source="manual",
            )
            db.session.add(manual)
            db.session.commit()

            seed_idea_tests(idea, [{"name": "UI: home loads", "test_type": "e2e"}])
            db.session.commit()

            assert IdeaTest.query.filter_by(idea_id=idea.id, name="Manually verified login").count() == 1
            assert IdeaTest.query.filter_by(idea_id=idea.id, source="manual").count() == 1


class TestConfirmBuildSeedsTests:
    def test_confirm_writes_creates_test_rows(self, celery_app, tmp_path):
        celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
        with celery_app.app_context():
            inst = make_instance(93, "BTS")
            idea = seed_idea(db, inst.id, email="bts@t.test")
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
                run_secondary_action(
                    str(idea_id),
                    "BUILD_CODE",
                    extra_context={"target_id": str(tid), "confirm_build": True},
                )

            rows = IdeaTest.query.filter_by(idea_id=idea_id).all()
            assert rows, "confirm build should seed Test-tab entries"
            assert all(r.source == "build" for r in rows)
            assert any(r.test_type == CaseType.E2E for r in rows), "UI check required"

            current = SecondaryActionResult.query.filter_by(
                idea_id=idea_id, action_type="BUILD_CODE", is_current=True
            ).one()
            assert any(
                line.startswith("tests:")
                for line in current.result_data.get("write_report", [])
            )

    def test_reconfirm_does_not_duplicate(self, celery_app, tmp_path):
        celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
        with celery_app.app_context():
            inst = make_instance(94, "BTR")
            idea = seed_idea(db, inst.id, email="btr@t.test")
            seed_design(idea)
            target = seed_target(inst.id, path=str(tmp_path))
            tid, idea_id = target.id, idea.id

            from app.tasks.ollama_tasks import run_secondary_action

            with patch("app.tasks.ollama_tasks.OllamaClient") as mock_cls:
                mock_cls.return_value.generate_sync.return_value = {
                    "response": json.dumps(MANIFEST)
                }
                run_secondary_action(
                    str(idea_id), "BUILD_CODE", extra_context={"target_id": str(tid)}
                )
                run_secondary_action(
                    str(idea_id),
                    "BUILD_CODE",
                    extra_context={"target_id": str(tid), "confirm_build": True},
                )
            first = IdeaTest.query.filter_by(idea_id=idea_id).count()
            assert first > 0

            # A newer preview + confirm (rebuild) must update, not duplicate.
            with patch("app.tasks.ollama_tasks.OllamaClient") as mock_cls:
                mock_cls.return_value.generate_sync.return_value = {
                    "response": json.dumps(MANIFEST)
                }
                run_secondary_action(
                    str(idea_id), "BUILD_CODE", extra_context={"target_id": str(tid)}
                )
                run_secondary_action(
                    str(idea_id),
                    "BUILD_CODE",
                    extra_context={"target_id": str(tid), "confirm_build": True},
                )
            assert IdeaTest.query.filter_by(idea_id=idea_id).count() == first
