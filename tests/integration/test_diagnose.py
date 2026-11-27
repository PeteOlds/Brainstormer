"""Diagnose endpoints must never surface a 500 to the UI."""

from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import ManagedApp
from tests.integration.test_build import login, make_instance, seed_idea


def _idea(app, client, inst_number, email):
    with app.app_context():
        inst = make_instance(inst_number, "DG")
        idea = seed_idea(db, inst.id, email=email)
        iid, idea_id = inst.id, idea.id
    return iid, idea_id, login(client, email, str(iid))


def test_tests_diagnose_handles_bad_log_path(app, client):
    """A malformed log_path in the managed-app spec must not cause a 500."""
    iid, idea_id, headers = _idea(app, client, 120, "diag-bad@t.test")
    with app.app_context():
        db.session.add(
            ManagedApp(
                instance_id=iid,
                idea_id=idea_id,
                state="stopped",
                spec='{"log_path": "/tmp/not-a-real-log"}',
            )
        )
        db.session.commit()
    with patch("app.services.ollama_client.OllamaClient") as mock:
        mock.return_value = MagicMock()
        mock.return_value.generate_sync.return_value = {
            "response": "Likely a missing dependency."
        }
        res = client.post(f"/api/v1/ideas/{idea_id}/tests/diagnose", headers=headers)
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["data"]["diagnosis"]


def test_tests_diagnose_handles_llm_failure(app, client):
    iid, idea_id, headers = _idea(app, client, 121, "diag-llm@t.test")
    with patch("app.services.ollama_client.OllamaClient") as mock:
        mock.return_value = MagicMock()
        mock.return_value.generate_sync.side_effect = RuntimeError("engine down")
        res = client.post(f"/api/v1/ideas/{idea_id}/tests/diagnose", headers=headers)
    assert res.status_code == 200
    assert "Diagnosis failed" in res.get_json()["data"]["diagnosis"]
