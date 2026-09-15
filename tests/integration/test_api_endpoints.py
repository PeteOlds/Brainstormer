import pytest
import json
from unittest.mock import patch, Mock
from datetime import datetime, timezone, timedelta
import uuid

from app.models import User, UserRole, PromptConfig, Idea, Vote, SecondaryActionResult


class TestAuthEndpoints:
    def test_register_success(self, client):
        resp = client.post("/api/v1/register", json={
            "email": "new@test.com",
            "password": "password123"
        })
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["user"]["email"] == "new@test.com"
        assert "access_token" in data
        assert "refresh_token" in data

    def test_register_duplicate_email(self, client):
        client.post("/api/v1/register", json={"email": "dup@test.com", "password": "password123"})
        resp = client.post("/api/v1/register", json={"email": "dup@test.com", "password": "password123"})
        assert resp.status_code == 409

    def test_register_short_password(self, client):
        resp = client.post("/api/v1/register", json={"email": "test@test.com", "password": "short"})
        assert resp.status_code == 400

    def test_login_success(self, client):
        client.post("/api/v1/register", json={"email": "login@test.com", "password": "password123"})
        resp = client.post("/api/v1/login", json={"email": "login@test.com", "password": "password123"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["access_token"]

    def test_login_wrong_password(self, client):
        client.post("/api/v1/register", json={"email": "login@test.com", "password": "password123"})
        resp = client.post("/api/v1/login", json={"email": "login@test.com", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_me_requires_token(self, client):
        resp = client.get("/api/v1/me")
        assert resp.status_code == 401

    def test_me_with_token(self, client, auth_user):
        _email, token = auth_user
        resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["user"]["email"] == "user@example.com"

    def test_refresh_token(self, client):
        reg = client.post("/api/v1/register", json={
            "email": "refresh@test.com", "password": "password123"})
        assert reg.status_code == 201
        refresh = reg.get_json()["data"]["refresh_token"]
        # Contract: refresh token goes in the JSON body, not the header.
        resp = client.post("/api/v1/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        assert "access_token" in resp.get_json()["data"]

    def test_logout(self, client, auth_user):
        _email, token = auth_user
        resp = client.post("/api/v1/logout", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestPromptEndpoints:
    def test_list_prompts_admin(self, admin_client):
        resp = admin_client.get("/api/v1/prompts")
        assert resp.status_code == 200
        assert "prompts" in resp.get_json()["data"]

    def test_list_prompts_user_allowed(self, client, auth_user):
        # Listing is @token_required (not admin-only); creating is.
        _email, token = auth_user
        resp = client.get("/api/v1/prompts", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_create_prompt_admin(self, admin_client):
        resp = admin_client.post("/api/v1/prompts", json={
            "title": "Test Prompt",
            "prompt_body": "Generate an idea about {{topic}}",
            "interval_minutes": 1440,
            "model_name": "llama3:8b",
            "temperature": 0.7,
            "top_p": 0.95,
            "repeat_penalty": 1.2,
            "num_predict": 500,
            "seed": 42,
            "keep_alive": "30m",
            "is_active": True
        })
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["title"] == "Test Prompt"
        assert data["top_p"] == 0.95
        assert data["repeat_penalty"] == 1.2
        assert data["num_predict"] == 500
        assert data["seed"] == 42
        assert data["keep_alive"] == "30m"

    def test_create_prompt_temperature_out_of_range(self, admin_client):
        # API must 400, not silently clamp (same rule as interval_minutes).
        for bad in (-0.5, 2.5, "hot"):
            resp = admin_client.post("/api/v1/prompts", json={
                "title": "Bad Temp",
                "prompt_body": "Test",
                "interval_minutes": 60,
                "model_name": "llama3:8b",
                "temperature": bad,
                "is_active": False,
            })
            assert resp.status_code == 400

    def test_update_prompt_temperature_out_of_range(self, admin_client, app):
        prompt_id = admin_client.post("/api/v1/prompts", json={
            "title": "Temp Patch",
            "prompt_body": "Test",
            "interval_minutes": 60,
            "model_name": "llama3:8b",
            "is_active": False,
        }).get_json()["data"]["id"]
        resp = admin_client.patch(f"/api/v1/prompts/{prompt_id}", json={"temperature": 5})
        assert resp.status_code == 400

    def test_create_prompt_max_active(self, admin_client, app, admin_user):
        with app.app_context():
            from app.models import PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            for i in range(10):
                p = PromptConfig(
                    title=f"Prompt {i}",
                    prompt_body="Test",
                    interval_minutes=60,
                    model_name="llama3:8b",
                    is_active=True,
                    created_by_id=admin.id
                )
                db.session.add(p)
            db.session.commit()
        
        resp = admin_client.post("/api/v1/prompts", json={
            "title": "New Prompt",
            "prompt_body": "Test",
            "interval_minutes": 60,
            "model_name": "llama3:8b",
            "is_active": True
        })
        assert resp.status_code == 409

    def test_create_prompt_invalid(self, admin_client):
        resp = admin_client.post("/api/v1/prompts", json={
            "title": "Test",
            "interval_minutes": 60,
            "model_name": "llama3:8b"
        })
        assert resp.status_code == 400

    def test_get_prompt_admin(self, admin_client, app, admin_user):
        with app.app_context():
            from app.models import PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig(
                title="Test Get",
                prompt_body="Test body",
                interval_minutes=60,
                model_name="llama3:8b",
                is_active=True,
                created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            prompt_id = prompt.id
        
        resp = admin_client.get(f"/api/v1/prompts/{prompt_id}")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["title"] == "Test Get"

    def test_update_prompt_admin(self, admin_client, app, admin_user):
        with app.app_context():
            from app.models import PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig(
                title="Original",
                prompt_body="Original body",
                interval_minutes=60,
                model_name="llama3:8b",
                is_active=True,
                created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            prompt_id = prompt.id
        
        resp = admin_client.patch(f"/api/v1/prompts/{prompt_id}", json={
            "title": "Updated",
            "is_active": False
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["title"] == "Updated"
        assert resp.get_json()["data"]["is_active"] is False

    def test_run_prompt_now(self, admin_client, app, admin_user):
        with app.app_context():
            from app.models import PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig(
                title="Run Now Test",
                prompt_body="Test",
                interval_minutes=60,
                model_name="llama3:8b",
                is_active=True,
                created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            prompt_id = prompt.id
        
        with patch('app.tasks.ollama_tasks.generate_idea') as mock_generate:
            mock_generate.delay.return_value.id = "fake-job-id"
            resp = admin_client.post(f"/api/v1/prompts/{prompt_id}/run-now")
            assert resp.status_code == 202
            mock_generate.delay.assert_called_once()

    def test_run_prompt_burst(self, admin_client, app, admin_user):
        with app.app_context():
            from app.models import PromptConfig, PromptRun, User
            from app.extensions import db

            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig(
                title="Burst Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", is_active=True, created_by_id=admin.id)
            db.session.add(prompt)
            db.session.commit()
            prompt_id = prompt.id

        with patch('app.tasks.ollama_tasks.generate_idea') as mock_generate:
            mock_generate.delay.return_value.id = "fake-job-id"
            resp = admin_client.post(f"/api/v1/prompts/{prompt_id}/run-now",
                                     json={"count": 5})
            assert resp.status_code == 202
            assert mock_generate.delay.call_count == 5
            assert len(resp.get_json()["data"]["runs"]) == 5

        with app.app_context():
            from app.models import PromptRun
            assert PromptRun.query.filter_by(prompt_config_id=prompt_id).count() == 5

        # Out of range rejected.
        with patch('app.tasks.ollama_tasks.generate_idea'):
            for bad in (0, 6, "many"):
                resp = admin_client.post(f"/api/v1/prompts/{prompt_id}/run-now",
                                         json={"count": bad})
                assert resp.status_code == 400

    def test_delete_prompt(self, admin_client, app, admin_user):
        with app.app_context():
            from app.models import PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig(
                title="To Delete",
                prompt_body="Test",
                interval_minutes=60,
                model_name="llama3:8b",
                created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            prompt_id = prompt.id
        
        resp = admin_client.delete(f"/api/v1/prompts/{prompt_id}")
        assert resp.status_code == 200


class TestOllamaEndpoints:
    def test_list_models_admin(self, admin_client):
        # Route calls list_models_sync (not the async list_models).
        with patch('app.services.ollama_client.OllamaClient.list_models_sync') as mock_list:
            mock_list.return_value = [
                {"name": "llama3:8b", "size": 4000000000},
                {"name": "mistral:7b", "size": 3000000000}
            ]
            resp = admin_client.get("/api/v1/ollama/models")
            assert resp.status_code == 200
            assert len(resp.get_json()["data"]["models"]) == 2

    def test_list_models_user_forbidden(self, client, auth_user):
        # Convention (AGENTS.md): /ollama/models is @token_required, NOT
        # @admin_required — any authenticated user may list models.
        _email, token = auth_user
        with patch('app.services.ollama_client.OllamaClient.list_models_sync') as mock_list:
            mock_list.return_value = [{"name": "llama3:8b", "size": 4000000000}]
            resp = client.get("/api/v1/ollama/models", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            assert len(resp.get_json()["data"]["models"]) == 1


class TestIdeaEndpoints:
    def test_list_ideas(self, client, auth_user):
        _email, token = auth_user
        resp = client.get("/api/v1/ideas", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "ideas" in data
        assert "total" in data

    def test_list_ideas_filter_by_model(self, client, auth_user, app, admin_user):
        """?model= must filter server-side (client only sees one page)."""
        _email, token = auth_user
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db

            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig(
                title="Model Filter Prompt", prompt_body="Test",
                interval_minutes=60, model_name="filter-model:1",
                is_active=True, created_by_id=admin.id)
            db.session.add(prompt)
            db.session.commit()
            db.session.add(Idea(reference_code="IDEA-M1", prompt_title="T",
                                raw_content="c", prompt_config_id=prompt.id))
            db.session.commit()

        resp = client.get("/api/v1/ideas?model=filter-model:1",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        ideas = resp.get_json()["data"]["ideas"]
        assert len(ideas) == 1
        assert ideas[0]["reference_code"] == "IDEA-M1"

        resp = client.get("/api/v1/ideas?model=no-such-model:1",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["ideas"] == []

    def test_list_ideas_with_filters(self, client, auth_user, app, admin_user, admin_prompt):
        _email, token = auth_user
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
            
            idea1 = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test",
                raw_content="Content 1",
                status="NEW",
                prompt_config_id=prompt.id
            )
            idea2 = Idea(
                reference_code="IDEA-0002",
                prompt_title="Test",
                raw_content="Content 2",
                status="CONSIDERATION",
                prompt_config_id=prompt.id
            )
            db.session.add_all([idea1, idea2])
            db.session.commit()
        
        resp = client.get("/api/v1/ideas?status=NEW", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert all(i["status"] == "NEW" for i in data["ideas"])

    def test_get_idea_detail(self, client, auth_user, app, admin_user, admin_prompt):
        _email, token = auth_user
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test",
                raw_content="Test content",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
        
        resp = client.get(f"/api/v1/ideas/{idea_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["idea"]["reference_code"] == "IDEA-0001"

    def test_update_idea_status_admin(self, admin_client, app, admin_user, admin_prompt):
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test",
                raw_content="Test",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
        
        resp = admin_client.patch(f"/api/v1/ideas/{idea_id}/status", json={
            "status": "CONSIDERATION"
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "CONSIDERATION"

    def test_update_idea_status_user_forbidden(self, client, auth_user, app, admin_user, admin_prompt):
        _email, token = auth_user
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test",
                raw_content="Test",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
        
        resp = client.patch(f"/api/v1/ideas/{idea_id}/status", json={
            "status": "CONSIDERATION"
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_vote_idea(self, client, auth_user, app, admin_user, admin_prompt):
        _email, token = auth_user
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test",
                raw_content="Test",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
        
        # Upvote
        resp = client.post(f"/api/v1/ideas/{idea_id}/vote", json={"direction": 1}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["net_votes"] == 1
        assert resp.get_json()["data"]["current_user_vote"] == 1
        
        # Downvote (flip)
        resp = client.post(f"/api/v1/ideas/{idea_id}/vote", json={"direction": -1}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["net_votes"] == -1
        assert resp.get_json()["data"]["current_user_vote"] == -1
        
        # Remove vote (same direction)
        resp = client.post(f"/api/v1/ideas/{idea_id}/vote", json={"direction": -1}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["net_votes"] == 0

    def test_vote_invalid_direction(self, client, auth_user, app, admin_user, admin_prompt):
        _email, token = auth_user
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test",
                raw_content="Test",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
        
        resp = client.post(f"/api/v1/ideas/{idea_id}/vote", json={"direction": 0}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400


class TestActionEndpoints:
    def test_run_action_admin(self, admin_client, app, admin_user, admin_prompt):
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test",
                raw_content="Test content for action",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
        
        with patch('app.tasks.ollama_tasks.run_secondary_action') as mock_run:
            mock_run.delay.return_value.id = "fake-action-job-id"
            resp = admin_client.post(f"/api/v1/ideas/{idea_id}/actions", json={
                "action_type": "REFINE"
            })
            assert resp.status_code == 202
            mock_run.delay.assert_called_once()

    def test_run_action_five_forces(self, admin_client, app, admin_user, admin_prompt):
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db

            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()

            idea = Idea(
                reference_code="IDEA-FF1",
                prompt_title="Test",
                raw_content="Test content for five forces",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id

        with patch('app.tasks.ollama_tasks.run_secondary_action') as mock_run:
            mock_run.delay.return_value.id = "fake-forces-job-id"
            resp = admin_client.post(f"/api/v1/ideas/{idea_id}/actions", json={
                "action_type": "FIVE_FORCES"
            })
            assert resp.status_code == 202
            mock_run.delay.assert_called_once()

    def test_run_action_pestel(self, admin_client, app, admin_user, admin_prompt):
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db

            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()

            idea = Idea(
                reference_code="IDEA-PE1",
                prompt_title="Test",
                raw_content="Test content for pestel",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id

        with patch('app.tasks.ollama_tasks.run_secondary_action') as mock_run:
            mock_run.delay.return_value.id = "fake-pestel-job-id"
            resp = admin_client.post(f"/api/v1/ideas/{idea_id}/actions", json={
                "action_type": "PESTEL"
            })
            assert resp.status_code == 202
            mock_run.delay.assert_called_once()

    def test_run_action_user_forbidden(self, client, auth_user, app, admin_user, admin_prompt):
        _email, token = auth_user
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test",
                raw_content="Test",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
        
        resp = client.post(f"/api/v1/ideas/{idea_id}/actions", json={
            "action_type": "REFINE"
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_get_actions(self, client, auth_user, app, admin_user, admin_prompt):
        _email, token = auth_user
        with app.app_context():
            from app.models import Idea, PromptConfig, User, SecondaryActionResult, ActionType
            from app.extensions import db
            
            admin = User.query.filter_by(email="admin@test.com").first()
            prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test",
                raw_content="Test",
                status="NEW",
                prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            
            action = SecondaryActionResult(
                idea_id=idea.id,
                action_type=ActionType.REFINE,
                model_used="llama3:8b",
                result_data={"elevator_pitch": "Test pitch"}
            )
            db.session.add(action)
            db.session.commit()
            idea_id = idea.id
        
        resp = client.get(f"/api/v1/ideas/{idea_id}/actions", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]["results"]) == 1


class TestAdminEndpoints:
    def test_get_stats_admin(self, admin_client):
        resp = admin_client.get("/api/v1/admin/stats")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "users" in data
        assert "ideas" in data
        assert "prompts" in data

    def test_prompts_health_flags(self, admin_client, app, admin_user):
        with app.app_context():
            from app.models import Idea, IdeaStatus, PromptConfig, User
            from app.extensions import db

            admin = User.query.filter_by(email="admin@test.com").first()
            bad = PromptConfig(
                title="Bad Prompt", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", is_active=True, created_by_id=admin.id)
            db.session.add(bad)
            db.session.commit()
            for i in range(3):
                db.session.add(Idea(
                    reference_code=f"IDEA-H{i}", prompt_title="T",
                    raw_content="c", status="DISCARDED", prompt_config_id=bad.id))
            db.session.add(PromptConfig(
                title="Starved Prompt", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", is_active=True, created_by_id=admin.id))
            db.session.commit()

        resp = admin_client.get("/api/v1/admin/prompts/health")
        assert resp.status_code == 200
        rows = {p["title"]: p for p in resp.get_json()["data"]["prompts"]}
        assert {c["code"] for c in rows["Bad Prompt"]["flags"]} == {"HIGH_DISCARD"}
        assert rows["Bad Prompt"]["discard_pct"] == 100
        assert {c["code"] for c in rows["Starved Prompt"]["flags"]} == {"STARVED"}
        flag = rows["Bad Prompt"]["flags"][0]
        assert flag["edit"].startswith("/prompts?edit=")
        assert flag["ideas"].startswith("/ideas?prompt=")

    def test_get_stats_user_forbidden(self, client, auth_user):
        _email, token = auth_user
        resp = client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestHealthEndpoints:
    def test_health_ok(self, client):
        with patch('app.routes.health.check_database', return_value=True), \
             patch('app.routes.health.check_redis', return_value=True):
            resp = client.get("/api/health")
            assert resp.status_code == 200
            assert resp.get_json()["data"]["status"] == "healthy"

    def test_unknown_route_404(self, client):
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404

class TestCommentEndpoints:
    def _make_idea(self, app, ref="IDEA-C1"):
        from app.models import Idea, PromptConfig, User
        from app.extensions import db

        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code=ref,
            prompt_title="Test",
            raw_content="Test content",
            status="NEW",
            prompt_config_id=prompt.id
        )
        db.session.add(idea)
        db.session.commit()
        return idea.id

    def _auth(self, client, email):
        reg = client.post("/api/v1/register", json={
            "email": email, "password": "password123"})
        assert reg.status_code == 201
        return reg.get_json()["data"]["access_token"]

    def test_post_and_list_thread(self, client, app, admin_user, admin_prompt):
        token = self._auth(client, "commenter@test.com")
        with app.app_context():
            idea_id = self._make_idea(app)

        r1 = client.post(f"/api/v1/ideas/{idea_id}/comments",
                         json={"body": "Top level"},
                         headers={"Authorization": f"Bearer {token}"})
        assert r1.status_code == 201
        top_id = r1.get_json()["data"]["comment"]["id"]

        r2 = client.post(f"/api/v1/ideas/{idea_id}/comments",
                         json={"body": "A reply", "parent_id": top_id},
                         headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 201

        resp = client.get(f"/api/v1/ideas/{idea_id}/comments",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        tree = resp.get_json()["data"]["comments"]
        assert len(tree) == 1
        assert tree[0]["body"] == "Top level"
        assert tree[0]["author"] == "commenter@test.com"
        assert len(tree[0]["replies"]) == 1
        assert tree[0]["replies"][0]["body"] == "A reply"

    def test_parent_must_belong_to_same_idea(self, client, app, admin_user, admin_prompt):
        token = self._auth(client, "otheridea@test.com")
        with app.app_context():
            idea_a = self._make_idea(app, ref="IDEA-CA")
            idea_b = self._make_idea(app, ref="IDEA-CB")

        r1 = client.post(f"/api/v1/ideas/{idea_a}/comments",
                         json={"body": "On A"},
                         headers={"Authorization": f"Bearer {token}"})
        other_parent = r1.get_json()["data"]["comment"]["id"]

        resp = client.post(f"/api/v1/ideas/{idea_b}/comments",
                           json={"body": "Sneaky", "parent_id": other_parent},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

    def test_validation(self, client, app, admin_user, admin_prompt):
        token = self._auth(client, "valid@test.com")
        with app.app_context():
            idea_id = self._make_idea(app, ref="IDEA-CV")

        resp = client.post(f"/api/v1/ideas/{idea_id}/comments",
                           json={"body": "   "},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

        resp = client.post(f"/api/v1/ideas/{idea_id}/comments",
                           json={"body": "x" * 2001},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

    def test_edit_own_comment(self, client, app, admin_user, admin_prompt):
        token = self._auth(client, "editor@test.com")
        with app.app_context():
            idea_id = self._make_idea(app, ref="IDEA-CE")

        cid = client.post(f"/api/v1/ideas/{idea_id}/comments",
                          json={"body": "Original"},
                          headers={"Authorization": f"Bearer {token}"}
                          ).get_json()["data"]["comment"]["id"]

        resp = client.patch(f"/api/v1/comments/{cid}",
                            json={"body": "Edited"},
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["comment"]["body"] == "Edited"

    def test_edit_stranger_forbidden_admin_allowed(self, client, app, admin_user, admin_prompt, admin_client):
        token = self._auth(client, "stranger@test.com")
        with app.app_context():
            idea_id = self._make_idea(app, ref="IDEA-CS")

        owner_token = self._auth(client, "owner@test.com")
        cid = client.post(f"/api/v1/ideas/{idea_id}/comments",
                          json={"body": "Mine"},
                          headers={"Authorization": f"Bearer {owner_token}"}
                          ).get_json()["data"]["comment"]["id"]

        resp = client.patch(f"/api/v1/comments/{cid}",
                            json={"body": "Hijacked"},
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

        resp = admin_client.patch(f"/api/v1/comments/{cid}", json={"body": "Mod edit"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["comment"]["body"] == "Mod edit"

    def test_delete_reparents_children(self, client, app, admin_user, admin_prompt):
        token = self._auth(client, "deleter@test.com")
        with app.app_context():
            idea_id = self._make_idea(app, ref="IDEA-CD")

        top = client.post(f"/api/v1/ideas/{idea_id}/comments",
                          json={"body": "Parent"},
                          headers={"Authorization": f"Bearer {token}"}
                          ).get_json()["data"]["comment"]["id"]
        client.post(f"/api/v1/ideas/{idea_id}/comments",
                    json={"body": "Child", "parent_id": top},
                    headers={"Authorization": f"Bearer {token}"})

        resp = client.delete(f"/api/v1/comments/{top}",
                             headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

        tree = client.get(f"/api/v1/ideas/{idea_id}/comments",
                          headers={"Authorization": f"Bearer {token}"}
                          ).get_json()["data"]["comments"]
        assert len(tree) == 2
        bodies = sorted([c["body"] for c in tree])
        assert bodies == ["Child", "[deleted]"]


class TestIdeaEditEndpoints:
    def _make_idea(self, app, ref="IDEA-E1"):
        from app.models import Idea, PromptConfig, User
        from app.extensions import db

        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code=ref,
            prompt_title="Original title",
            raw_content="Original body",
            status="NEW",
            prompt_config_id=prompt.id
        )
        db.session.add(idea)
        db.session.commit()
        return idea.id

    def test_admin_edit_records_audit(self, admin_client, app, admin_user, admin_prompt):
        with app.app_context():
            idea_id = self._make_idea(app)

        resp = admin_client.patch(f"/api/v1/ideas/{idea_id}", json={
            "prompt_title": "Edited title",
            "raw_content": "Edited body",
        })
        assert resp.status_code == 200

        detail = admin_client.get(f"/api/v1/ideas/{idea_id}").get_json()["data"]
        assert detail["idea"]["prompt_title"] == "Edited title"
        fields = {e["field"]: e for e in detail["edit_history"]}
        assert set(fields) == {"prompt_title", "raw_content"}
        assert fields["prompt_title"]["old_value"] == "Original title"
        assert fields["prompt_title"]["new_value"] == "Edited title"
        assert "admin@example.com" in fields["prompt_title"]["editor"]

    def test_edit_validation(self, admin_client, app, admin_user, admin_prompt):
        with app.app_context():
            idea_id = self._make_idea(app, ref="IDEA-EV")

        resp = admin_client.patch(f"/api/v1/ideas/{idea_id}", json={})
        assert resp.status_code == 400

        resp = admin_client.patch(f"/api/v1/ideas/{idea_id}", json={"prompt_title": "   "})
        assert resp.status_code == 400

        resp = admin_client.patch(f"/api/v1/ideas/{idea_id}", json={"status": "NEW"})
        assert resp.status_code == 400

    def test_edit_user_forbidden(self, client, auth_user, app, admin_user, admin_prompt):
        _email, token = auth_user
        with app.app_context():
            idea_id = self._make_idea(app, ref="IDEA-EF")

        resp = client.patch(f"/api/v1/ideas/{idea_id}",
                            json={"prompt_title": "Hijacked"},
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_unchanged_fields_no_audit(self, admin_client, app, admin_user, admin_prompt):
        with app.app_context():
            idea_id = self._make_idea(app, ref="IDEA-EN")

        resp = admin_client.patch(f"/api/v1/ideas/{idea_id}", json={
            "prompt_title": "Original title",
        })
        assert resp.status_code == 200
        history = admin_client.get(f"/api/v1/ideas/{idea_id}").get_json()["data"]["edit_history"]
        assert history == []
