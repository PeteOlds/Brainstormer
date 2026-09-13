import pytest


@pytest.fixture(scope="session")
def base_url():
    return "http://localhost:8000"


@pytest.fixture
def auth_info(client, app):
    """Login as admin and return access token."""
    with app.app_context():
        from app.extensions import db
        db.create_all()
        # Ensure admin user exists
        from app.models import User
        admin = User.query.filter_by(email="admin@example.com").first()
        if admin is None:
            admin = User(email="admin@example.com", role="ADMIN")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
        # Login
        login_res = client.post("/api/v1/login", json={
            "email": "admin@example.com",
            "password": "admin123"
        })
    assert login_res.status_code == 200
    return login_res.get_json()["data"]["access_token"]


@pytest.fixture
def logged_in_client(client, auth_info):
    """Return client with auth header for admin."""
    return client, {"Authorization": f"Bearer {auth_info}"}



    data = res.get_json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data


def test_prompts_list_admin(logged_in_client):
    """Test admin can list prompts."""
    client, headers = logged_in_client
    resp = client.get("/api/v1/prompts", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "prompts" in data


def test_prompts_create_admin(logged_in_client):
    """Test admin can create a prompt."""
    client, headers = logged_in_client
    resp = client.post("/api/v1/prompts", json={
        "title": "UITest Prompt",
        "prompt_body": "Generate an idea about {{topic}}",
        "interval_minutes": 1440,
        "model_name": "llama3:8b",
        "temperature": 0.7,
        "is_active": True
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["title"] == "UITest Prompt"


def test_prompts_rbac_user_forbidden(client, app):
    """Test regular user gets 403 on admin-only actions."""
    with app.app_context():
        # Register a regular user
        res = client.post("/api/v1/register", json={
            "email": "user@example.com",
            "password": "password123"
        })
        assert res.status_code == 201
        token = res.get_json()["data"]["access_token"]

    # User tries to create prompt - should be forbidden
    res = client.post("/api/v1/prompts", json={
        "title": "Test",
        "prompt_body": "Test",
        "interval_minutes": 60,
        "model_name": "llama3:8b",
        "is_active": True
    }, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_ollama_models_admin(logged_in_client):
    """Test admin can list Ollama models."""
    from unittest.mock import patch, MagicMock

    client, headers = logged_in_client
    # No live Ollama in the test env; stub the client at the route boundary.
    mock_client = MagicMock()
    mock_client.list_models_sync.return_value = [{"name": "llama3:8b"}]
    with patch("app.routes.ollama.OllamaClient", return_value=mock_client):
        resp = client.get("/api/v1/ollama/models", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "models" in data


def test_run_now_creates_pending_run(logged_in_client, app):
    """Test run-now records a PENDING run visible in prompt stats."""
    from unittest.mock import patch

    client, headers = logged_in_client
    # Create a prompt
    res = client.post("/api/v1/prompts", json={
        "title": "RunTrack Prompt",
        "prompt_body": "Generate an idea about {{topic}}",
        "interval_minutes": 1440,
        "model_name": "llama3:8b",
        "temperature": 0.7,
        "is_active": True
    }, headers=headers)
    assert res.status_code == 201
    prompt_id = res.get_json()["data"]["id"]

    # Trigger run with celery delayed (no worker in tests)
    with patch("app.tasks.ollama_tasks.generate_idea.delay") as mock_delay:
        mock_delay.return_value.id = "fake-job-id"
        res = client.post(f"/api/v1/prompts/{prompt_id}/run-now",
                          headers=headers)
    assert res.status_code == 202
    data = res.get_json()["data"]
    assert data["run"]["status"] == "PENDING"
    assert data["run"]["triggered_by"] == "manual"

    # Stats reflect the pending run
    res = client.get("/api/v1/prompts", headers=headers)
    assert res.status_code == 200
    prompts = res.get_json()["data"]["prompts"]
    stats = next(p for p in prompts if p["id"] == prompt_id)["run_stats"]
    assert stats["run_count"] >= 1
    assert stats["pending_run"] is True


def test_generation_seconds_admin_only(logged_in_client, app, client):
    """Test per-idea generation time is admin-only."""
    from datetime import datetime, timezone, timedelta

    admin_client, headers = logged_in_client
    with app.app_context():
        from app.extensions import db
        from app.models import Idea, PromptRun, PromptRunStatus, User

        admin = User.query.filter_by(email="admin@example.com").first()
        prompt = admin_client.post("/api/v1/prompts", json={
            "title": "GenTime Prompt",
            "prompt_body": "Test",
            "interval_minutes": 1440,
            "model_name": "llama3:8b",
            "is_active": True
        }, headers=headers).get_json()["data"]
        from app.models import PromptConfig
        pc = PromptConfig.query.get(prompt["id"])
        idea = Idea(reference_code="IDEA-T1", prompt_title="T",
                    raw_content="content", prompt_config_id=pc.id)
        db.session.add(idea)
        db.session.commit()
        now = datetime.now(timezone.utc)
        db.session.add(PromptRun(
            prompt_config_id=pc.id, triggered_by="manual",
            status=PromptRunStatus.SUCCESS, idea_id=idea.id,
            started_at=now - timedelta(seconds=42),
            finished_at=now, duration_seconds=42.0))
        db.session.commit()
        idea_id = str(idea.id)

    # Admin sees generation_seconds
    res = admin_client.get(f"/api/v1/ideas/{idea_id}", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["data"]["generation_seconds"] == 42.0

    # Regular user does not
    reg = client.post("/api/v1/register", json={
        "email": "genvis@example.com", "password": "password123"})
    token = reg.get_json()["data"]["access_token"]
    res = client.get(f"/api/v1/ideas/{idea_id}",
                     headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert "generation_seconds" not in res.get_json()["data"]


def test_secondary_action_creates_pending_run(logged_in_client, app):
    """Test REFINE enqueue records a PENDING action run for activity."""
    from unittest.mock import patch

    client, headers = logged_in_client
    with app.app_context():
        from app.extensions import db
        from app.models import Idea, PromptConfig, PromptRun, User

        admin = User.query.filter_by(email="admin@example.com").first()
        prompt = PromptConfig(
            title="Action Prompt", prompt_body="Test",
            interval_minutes=60, model_name="llama3:8b", is_active=True,
            created_by_id=admin.id)
        db.session.add(prompt)
        db.session.commit()
        idea = Idea(reference_code="IDEA-A1", prompt_title="T",
                    raw_content="content", prompt_config_id=prompt.id)
        db.session.add(idea)
        db.session.commit()
        idea_id = str(idea.id)

    with patch("app.tasks.ollama_tasks.run_secondary_action.delay") as mock_delay:
        mock_delay.return_value.id = "fake-action-job"
        res = client.post(f"/api/v1/ideas/{idea_id}/actions",
                          json={"action_type": "REFINE"}, headers=headers)
    assert res.status_code == 202
    assert res.get_json()["data"]["run"]["action_type"] == "REFINE"

    with app.app_context():
        from app.models import PromptRun
        run = PromptRun.query.filter_by(idea_id=idea.id).first()
        assert run is not None
        assert run.status.value == "PENDING"

    # Visible in activity stats pending list
    res = client.get("/api/v1/admin/activity/stats", headers=headers)
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["performance"]["pending_count"] >= 1
    assert any(r.get("action_type") == "REFINE"
               for r in data["pending_runs"])


def test_check_due_fails_stale_orphans(logged_in_client, app):
    """Scheduler fails PENDING/RUNNING runs older than 45 min (orphans)."""
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch

    client, headers = logged_in_client
    with app.app_context():
        from app.extensions import db
        from app.models import PromptConfig, PromptRun, PromptRunStatus, User

        admin = User.query.filter_by(email="admin@example.com").first()
        prompt = PromptConfig(
            title="Orphan Prompt", prompt_body="Test",
            interval_minutes=60, model_name="llama3:8b", is_active=True,
            next_run_at=datetime.now(timezone.utc) + timedelta(hours=6),
            created_by_id=admin.id)
        db.session.add(prompt)
        db.session.commit()
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        orphan = PromptRun(prompt_config_id=prompt.id,
                           triggered_by="manual",
                           status=PromptRunStatus.RUNNING,
                           created_at=old)
        db.session.add(orphan)
        db.session.commit()
        orphan_id = orphan.id

        from app.tasks import ollama_tasks
        with patch.object(ollama_tasks.generate_idea, "delay"):
            ollama_tasks.check_due_prompts()

        db.session.refresh(orphan)
        assert orphan.status == PromptRunStatus.FAILED
        assert "Orphaned" in (orphan.error or "")


def test_activity_stats_shape(logged_in_client):
    """Activity stats include queues, workers, pending and recent runs."""
    client, headers = logged_in_client
    res = client.get("/api/v1/admin/activity/stats", headers=headers)
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert "recent_runs" in data
    assert "pending_runs" in data
    assert "queues" in data
    assert "workers_alive" in data
    assert "pending_count" in data["performance"]
    # Tile/row links need these keys (§8.1).
    for p in data["popularity"]["prompts"]:
        assert "id" in p
    for p in data["ideas_by_prompt"]:
        assert "id" in p
    for r in data["recent_runs"]:
        assert "model" in r


def test_ideas_by_model_counts_distinct_ideas(logged_in_client, app):
    """Regression: the runs join fanned out (ideas x runs), e.g. 12 shown
    for 6 ideas. Count must be distinct ideas."""
    from datetime import datetime, timezone

    client, headers = logged_in_client
    with app.app_context():
        from app.extensions import db
        from app.models import Idea, PromptConfig, PromptRun, PromptRunStatus, User

        admin = User.query.filter_by(email="admin@example.com").first()
        prompt = PromptConfig(
            title="Fanout Prompt", prompt_body="Test", interval_minutes=60,
            model_name="fanout-model:1", is_active=True, created_by_id=admin.id)
        db.session.add(prompt)
        db.session.commit()
        db.session.add(Idea(reference_code="IDEA-F1", prompt_title="T",
                            raw_content="c", prompt_config_id=prompt.id))
        db.session.commit()
        for _ in range(3):
            db.session.add(PromptRun(
                prompt_config_id=prompt.id, triggered_by="manual",
                status=PromptRunStatus.SUCCESS,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc)))
        db.session.commit()

    res = client.get("/api/v1/admin/activity/stats", headers=headers)
    assert res.status_code == 200
    rows = [m for m in res.get_json()["data"]["ideas_by_model"]
            if m["model"] == "fanout-model:1"]
    assert len(rows) == 1
    assert rows[0]["count"] == 1


def test_activity_stats_run_filters(logged_in_client, app):
    """?run_status= / ?model= filter the stream server-side (client only
    ever sees one page of runs)."""
    from datetime import datetime, timezone

    client, headers = logged_in_client
    with app.app_context():
        from app.extensions import db
        from app.models import PromptConfig, PromptRun, PromptRunStatus, User

        admin = User.query.filter_by(email="admin@example.com").first()
        prompt = PromptConfig(
            title="Filter Prompt", prompt_body="Test", interval_minutes=60,
            model_name="filter-model:1", is_active=True, created_by_id=admin.id)
        db.session.add(prompt)
        db.session.commit()
        db.session.add(PromptRun(
            prompt_config_id=prompt.id, triggered_by="manual",
            status=PromptRunStatus.SUCCESS,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc)))
        failed = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        failed.mark_failed("boom")
        db.session.add(failed)
        db.session.commit()

    res = client.get("/api/v1/admin/activity/stats?run_status=FAILED", headers=headers)
    assert res.status_code == 200
    runs = res.get_json()["data"]["recent_runs"]
    assert runs and all(r["status"] == "FAILED" for r in runs)

    res = client.get("/api/v1/admin/activity/stats?model=filter-model:1", headers=headers)
    assert res.status_code == 200
    runs = res.get_json()["data"]["recent_runs"]
    assert runs and all(r["model"] == "filter-model:1" for r in runs)

    res = client.get("/api/v1/admin/activity/stats?run_status=BOGUS", headers=headers)
    assert res.status_code == 400

    # Ideas by Status uses idea lifecycle states (not run outcomes).
    res = client.get("/api/v1/admin/activity/stats", headers=headers)
    assert res.status_code == 200
    ideas_by_status = res.get_json()["data"]["ideas_by_status"]
    assert set(ideas_by_status) == {"NEW", "CONSIDERATION", "DISCARDED"}

    # Model timings feed the per-model timing graph.
    res = client.get("/api/v1/admin/activity/stats?model=filter-model:1", headers=headers)
    assert res.status_code == 200
    assert "model_timings" in res.get_json()["data"]


def test_check_due_skips_live_runs(logged_in_client, app):
    """Scheduler must not re-enqueue prompts that already have a live run."""
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch

    client, headers = logged_in_client
    with app.app_context():
        from app.extensions import db
        from app.models import PromptConfig, PromptRun, PromptRunStatus, User

        admin = User.query.filter_by(email="admin@example.com").first()
        prompt = PromptConfig(
            title="Due Prompt", prompt_body="Test",
            interval_minutes=60, model_name="llama3:8b", is_active=True,
            next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            created_by_id=admin.id)
        db.session.add(prompt)
        db.session.commit()
        # A live run already exists for this prompt
        db.session.add(PromptRun(prompt_config_id=prompt.id,
                                 triggered_by="manual"))
        db.session.commit()

        from app.tasks import ollama_tasks
        with patch.object(ollama_tasks.generate_idea, "delay") as mock_delay:
            ollama_tasks.check_due_prompts()
        mock_delay.assert_not_called()
        assert PromptRun.query.filter_by(prompt_config_id=prompt.id).count() == 1
