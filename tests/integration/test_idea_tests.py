"""Idea test cases (manual + imported) CRUD."""

import pytest

from app.extensions import db
from app.models import Idea, IdeaTest, TestStatus, TestType, User, UserRole


def _seed_idea(app):
    with app.app_context():
        user = User.query.filter_by(email="test-admin@example.com").first()
        if user is None:
            user = User(email="test-admin@example.com", role=UserRole.ADMIN)
            user.set_password("password123")
            db.session.add(user)
            db.session.commit()
        idea = Idea(
            reference_code="IDEA-T1",
            prompt_title="Test idea",
            raw_content="content",
            created_by_id=user.id,
        )
        db.session.add(idea)
        db.session.commit()
        return str(idea.id), str(user.id)


def _login(client, email="test-admin@example.com"):
    res = client.post("/api/v1/login", json={"email": email, "password": "password123"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}


def test_create_and_list_idea_test(app, client):
    idea_id, _ = _seed_idea(app)
    headers = _login(client)

    res = client.post(
        f"/api/v1/ideas/{idea_id}/tests",
        json={"name": "Login works", "test_type": "e2e", "status": "passed", "coverage_pct": 80},
        headers=headers,
    )
    assert res.status_code == 201, res.get_json()
    test = res.get_json()["data"]["test"]
    assert test["name"] == "Login works"
    assert test["status"] == "passed"
    assert test["coverage_pct"] == 80
    assert test["source"] == "manual"

    res = client.get(f"/api/v1/ideas/{idea_id}/tests", headers=headers)
    assert res.status_code == 200
    assert len(res.get_json()["data"]["tests"]) == 1


def test_update_idea_test_status(app, client):
    idea_id, _ = _seed_idea(app)
    headers = _login(client)
    tid = client.post(
        f"/api/v1/ideas/{idea_id}/tests",
        json={"name": "Unit", "test_type": "unit"},
        headers=headers,
    ).get_json()["data"]["test"]["id"]

    res = client.put(
        f"/api/v1/ideas/{idea_id}/tests/{tid}",
        json={"status": "failed", "last_run_output": "AssertionError: boom"},
        headers=headers,
    )
    assert res.status_code == 200
    t = res.get_json()["data"]["test"]
    assert t["status"] == "failed"
    assert t["last_run_output"] == "AssertionError: boom"
    assert t["last_run_at"] is not None


def test_delete_idea_test(app, client):
    idea_id, _ = _seed_idea(app)
    headers = _login(client)
    tid = client.post(
        f"/api/v1/ideas/{idea_id}/tests",
        json={"name": "x", "test_type": "unit"},
        headers=headers,
    ).get_json()["data"]["test"]["id"]

    res = client.delete(f"/api/v1/ideas/{idea_id}/tests/{tid}", headers=headers)
    assert res.status_code == 200
    res = client.get(f"/api/v1/ideas/{idea_id}/tests", headers=headers)
    assert res.get_json()["data"]["tests"] == []


def test_summary(app, client):
    idea_id, _ = _seed_idea(app)
    headers = _login(client)
    for name, status, cov in [("a", "passed", 90), ("b", "failed", 60), ("c", "not_run", None)]:
        client.post(
            f"/api/v1/ideas/{idea_id}/tests",
            json={"name": name, "test_type": "unit", "status": status, "coverage_pct": cov},
            headers=headers,
        )
    res = client.get(f"/api/v1/ideas/{idea_id}/tests/summary", headers=headers)
    assert res.status_code == 200
    d = res.get_json()["data"]
    assert d["total"] == 3
    assert d["counts"]["passed"] == 1
    assert d["counts"]["failed"] == 1
    assert d["counts"]["not_run"] == 1
    assert d["coverage_pct"] == 75.0


def test_filter_by_status(app, client):
    idea_id, _ = _seed_idea(app)
    headers = _login(client)
    client.post(f"/api/v1/ideas/{idea_id}/tests", json={"name": "p", "test_type": "unit", "status": "passed"}, headers=headers)
    client.post(f"/api/v1/ideas/{idea_id}/tests", json={"name": "f", "test_type": "unit", "status": "failed"}, headers=headers)
    res = client.get(f"/api/v1/ideas/{idea_id}/tests?status=failed", headers=headers)
    tests = res.get_json()["data"]["tests"]
    assert len(tests) == 1
    assert tests[0]["name"] == "f"