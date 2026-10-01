"""Coverage round 3: API validation errors, task retry paths, service units."""

import json
from unittest.mock import MagicMock, patch

from app.extensions import db


def test_idea_validation_errors(client, auth_user, app, admin_user, admin_prompt):
    _email, token = auth_user
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/v1/ideas", json={}, headers=headers)
    assert res.status_code == 400
    res = client.post(
        "/api/v1/ideas",
        json={"prompt_title": "x" * 201, "raw_content": "c"},
        headers=headers,
    )
    assert res.status_code == 400
    res = client.post(
        "/api/v1/ideas",
        json={
            "prompt_title": "t",
            "raw_content": "c",
            "structured_content": {"bogus": 1},
        },
        headers=headers,
    )
    assert res.status_code == 400

    with app.app_context():
        from app.models import Idea, PromptConfig, User

        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code="IDEA-VE",
            prompt_title="T",
            raw_content="c",
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.commit()
        iid = str(idea.id)

    res = client.post(
        f"/api/v1/ideas/{iid}/vote", json={"direction": 0}, headers=headers
    )
    assert res.status_code == 400
    res = client.post(
        f"/api/v1/ideas/{iid}/comments", json={"body": "x" * 2001}, headers=headers
    )
    assert res.status_code == 400
    res = client.post(f"/api/v1/ideas/{iid}/comments", json={}, headers=headers)
    assert res.status_code == 400
    res = client.get(f"/api/v1/ideas/{iid}/similar", headers=headers)
    assert res.status_code == 404
    res = client.patch(
        f"/api/v1/ideas/{iid}/status", json={"status": "BOGUS"}, headers=headers
    )
    assert res.status_code in (400, 403)


def test_bulk_and_status_guards(admin_client, app, admin_user, admin_prompt):
    res = admin_client.patch("/api/v1/ideas/bulk-status", json={})
    assert res.status_code == 400
    res = admin_client.patch(
        "/api/v1/ideas/bulk-status", json={"idea_ids": [], "status": "SCOPE"}
    )
    assert res.status_code == 400
    res = admin_client.patch(
        "/api/v1/ideas/bulk-status",
        json={"idea_ids": ["00000000-0000-0000-0000-000000000000"], "status": "BOGUS"},
    )
    assert res.status_code == 400

    with app.app_context():
        from app.models import Idea, PromptConfig, User

        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code="IDEA-VB",
            prompt_title="T",
            raw_content="c",
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.commit()
        iid = str(idea.id)
    res = admin_client.patch(f"/api/v1/ideas/{iid}/status", json={})
    assert res.status_code == 400
    res = admin_client.post(f"/api/v1/ideas/{iid}/actions", json={})
    assert res.status_code == 400
    res = admin_client.post(
        f"/api/v1/ideas/{iid}/actions", json={"action_type": "NOPE"}
    )
    assert res.status_code == 400


def test_doc_comment_validation(admin_client, app, admin_user, admin_prompt):
    from app.models import ActionType, Idea, PromptConfig, SecondaryActionResult, User

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code="IDEA-DC",
            prompt_title="T",
            raw_content="c",
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.flush()
        result = SecondaryActionResult(
            idea_id=idea.id,
            action_type=ActionType.PRD_DOC,
            model_used="m",
            result_data={},
        )
        db.session.add(result)
        db.session.commit()
        rid = str(result.id)

    res = admin_client.post(f"/api/v1/actions/{rid}/comments", json={})
    assert res.status_code == 400
    res = admin_client.post(
        f"/api/v1/actions/{rid}/comments", json={"body": "x" * 2001}
    )
    assert res.status_code == 400
    res = admin_client.post(
        f"/api/v1/actions/{rid}/comments", json={"body": "hi", "parent_id": "bogus"}
    )
    assert res.status_code == 400
    res = admin_client.patch(
        f"/api/v1/actions/{rid}", json={"result_data": {"nope": 1}}
    )
    assert res.status_code == 400
    res = admin_client.patch(f"/api/v1/actions/{rid}", json={"result_data": "string"})
    assert res.status_code == 400


def test_comment_edit_delete_paths(client, auth_user, app, admin_user, admin_prompt):
    _email, token = auth_user
    headers = {"Authorization": f"Bearer {token}"}
    with app.app_context():
        from app.models import Comment, Idea, PromptConfig, User

        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code="IDEA-CE",
            prompt_title="T",
            raw_content="c",
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.flush()
        comment = Comment(idea_id=idea.id, user_id=admin.id, body="admin note")
        db.session.add(comment)
        db.session.commit()
        cid, iid = str(comment.id), str(idea.id)

    # Stranger cannot edit/delete; empty body rejected for own? (admin's comment)
    res = client.patch(
        f"/api/v1/comments/{cid}", json={"body": "hijack"}, headers=headers
    )
    assert res.status_code == 403
    res = client.delete(f"/api/v1/comments/{cid}", headers=headers)
    assert res.status_code == 403

    res = client.post(
        f"/api/v1/ideas/{iid}/comments", json={"body": "mine"}, headers=headers
    )
    assert res.status_code == 201
    mine = res.get_json()["data"]["comment"]["id"]
    res = client.patch(f"/api/v1/comments/{mine}", json={}, headers=headers)
    assert res.status_code == 400
    res = client.patch(
        f"/api/v1/comments/{mine}", json={"body": "edited"}, headers=headers
    )
    assert res.status_code == 200
    res = client.delete(f"/api/v1/comments/{mine}", headers=headers)
    assert res.status_code == 200
    res = client.patch(
        f"/api/v1/comments/{mine}", json={"body": "again"}, headers=headers
    )
    assert res.status_code == 400


def test_admin_user_and_settings_paths(admin_client, app, admin_user):
    with app.app_context():
        from app.models import User

        target = User(email="managed@t.test")
        target.set_password("password123")
        db.session.add(target)
        db.session.commit()
        uid = str(target.id)

    res = admin_client.patch(f"/admin/users/{uid}", json={"is_active": False})
    assert res.status_code == 200
    res = admin_client.patch(f"/admin/users/{uid}", json={"role": "ADMIN"})
    assert res.status_code == 200
    res = admin_client.patch(
        "/admin/users/00000000-0000-0000-0000-000000000000", json={"role": "ADMIN"}
    )
    assert res.status_code == 404
    res = admin_client.post(
        "/admin/users/create",
        json={"email": "managed@t.test", "password": "password123"},
    )
    assert res.status_code == 409
    res = admin_client.post("/admin/users/create", json={"email": "new2@t.test"})
    assert res.status_code == 400
    res = admin_client.delete(f"/admin/users/{uid}")
    assert res.status_code == 200

    res = admin_client.get("/api/v1/admin/settings")
    assert res.status_code == 200
    res = admin_client.patch("/api/v1/admin/settings/platform", json={"title": "T2"})
    assert res.status_code == 200
    res = admin_client.patch("/api/v1/admin/settings/location", json={"country": "NZ"})
    assert res.status_code == 200
    res = admin_client.patch("/api/v1/admin/settings/ai_connections", json={"a": 1})
    assert res.status_code == 200


def test_instance_member_and_oauth_errors(app, client, admin_client):
    with app.app_context():
        from app.models import Instance, Membership, User, UserRole

        inst = Instance(number=95, name="Cov")
        db.session.add(inst)
        db.session.flush()
        admin = User(email="cov-admin@t.test", role=UserRole.ADMIN)
        admin.set_password("password123")
        db.session.add(admin)
        db.session.flush()
        db.session.add(
            Membership(user_id=admin.id, instance_id=inst.id, role="INSTANCE_ADMIN")
        )
        db.session.commit()
        iid = str(inst.id)
    res = client.post(
        "/api/v1/login",
        json={
            "email": "cov-admin@t.test",
            "password": "password123",
            "instance_id": iid,
        },
    )
    headers = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}

    res = client.patch(
        f"/api/v1/instances/{iid}/members/00000000-0000-0000-0000-000000000000",
        json={"role": "USER"},
        headers=headers,
    )
    assert res.status_code == 404
    res = client.put(
        f"/api/v1/instances/{iid}/oauth",
        json={"provider": "google", "client_id": ""},
        headers=headers,
    )
    assert res.status_code == 400
    res = client.put(
        f"/api/v1/instances/{iid}/oauth",
        json={"provider": "google", "client_id": "c", "client_secret": 123},
        headers=headers,
    )
    assert res.status_code == 400
    res = client.put(
        f"/api/v1/instances/{iid}/ai-configs",
        json={"provider": "openai", "budget_cents": -5},
        headers=headers,
    )
    assert res.status_code == 400
    res = client.put(
        f"/api/v1/instances/{iid}/ai-configs",
        json={"provider": "openai", "cutoff_behaviour": "queue"},
        headers=headers,
    )
    assert res.status_code == 200
    res = client.post("/api/v1/instances", json={"number": 96}, headers=headers)
    assert res.status_code in (400, 403)


def test_chat_unit_errors(app, admin_user, admin_prompt):
    from app.models import Idea, PromptConfig, User
    from app.services import chat as chat_svc

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code="IDEA-CU",
            prompt_title="T",
            raw_content="c",
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.commit()
        iid = idea.id

        for bad in (
            {},
            {"nope": 1},
            {"prompt_title": ""},
            {"prompt_title": "x" * 201},
            {"structured_content": {"bogus": "x"}},
            {"structured_content": {}},
        ):
            try:
                chat_svc._validate_content_updates(bad)
            except chat_svc.ChatError:
                pass
            else:
                raise AssertionError(f"expected ChatError for {bad}")

        route = chat_svc.resolve_route(Idea.query.get(iid))
        assert route.provider == "ollama"
        try:
            chat_svc.rollback_turn(Idea.query.get(iid), admin, iid)
        except chat_svc.ChatError as err:
            assert err.status_code == 404
        else:
            raise AssertionError("expected ChatError")


def test_social_unit_errors(app):
    from app.services import social_auth as social

    with app.app_context():
        try:
            social.build_start_url(
                "nope", "00000000-0000-0000-0000-000000000000", "cid", "http://x/cb"
            )
        except social.SocialError:
            pass
        else:
            raise AssertionError("expected SocialError")
        try:
            social.read_linking_token("bogus")
        except social.SocialError:
            pass
        else:
            raise AssertionError("expected SocialError")


def test_secondary_strict_retry_and_missing(app, celery_app):
    from app.models import (
        Idea,
        PromptConfig,
        PromptRun,
        PromptRunStatus,
        User,
        UserRole,
    )
    from app.tasks.ollama_tasks import run_secondary_action

    with celery_app.app_context():
        admin = User(email="retry@t.test", role=UserRole.ADMIN)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.flush()
        prompt = PromptConfig(
            title="M",
            prompt_body="b",
            interval_minutes=60,
            model_name="llama3:8b",
            created_by_id=admin.id,
        )
        db.session.add(prompt)
        db.session.flush()
        idea = Idea(
            reference_code="IDEA-RT",
            prompt_title="T",
            raw_content="c",
            status="SPARK",
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.commit()
        iid = idea.id

        with patch("app.tasks.ollama_tasks.OllamaClient") as mock_class:
            mock_client = MagicMock()
            mock_class.return_value = mock_client
            mock_client.is_model_available.return_value = True
            mock_client.generate_sync.side_effect = [
                {"response": "{}", "done": True},
                {
                    "response": json.dumps(
                        {
                            "elevator_pitch": "AI-powered inventory management for small retailers",
                            "target_audience": "Small retail businesses",
                            "core_value_proposition": "Automated stock optimization",
                            "monetization_strategy": "SaaS subscription",
                        }
                    ),
                    "done": True,
                },
            ]
            run_secondary_action(str(iid), "REFINE")
            assert mock_client.generate_sync.call_count == 2

        # Idea gone + model missing paths.
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        with patch("app.tasks.ollama_tasks.OllamaClient") as mock_class:
            mock_class.return_value.is_model_available.return_value = False
            run_secondary_action(str(iid), "REFINE", run_id=str(run.id))
        db.session.expire_all()
        from app.models import PromptRun as PR

        assert db.session.get(PR, run.id).status == PromptRunStatus.FAILED
        run_secondary_action("00000000-0000-0000-0000-000000000000", "REFINE")


def test_check_due_reconciles_and_enqueues(app, celery_app):
    from datetime import datetime, timedelta, timezone

    from app.models import PromptConfig, PromptRun, PromptRunStatus, User, UserRole
    from app.tasks import ollama_tasks as tasks

    with celery_app.app_context():
        admin = User(email="due@t.test", role=UserRole.ADMIN)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.flush()
        prompt = PromptConfig(
            title="Due",
            prompt_body="b",
            interval_minutes=60,
            model_name="m",
            is_active=True,
            next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            created_by_id=admin.id,
        )
        db.session.add(prompt)
        db.session.flush()
        stale = PromptRun(
            prompt_config_id=prompt.id,
            triggered_by="manual",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.session.add(stale)
        db.session.commit()

        with patch.object(tasks.generate_idea, "delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="job-1")
            tasks.check_due_prompts()
        db.session.expire_all()
        assert db.session.get(PromptRun, stale.id).status == PromptRunStatus.FAILED
        assert mock_delay.call_count == 1
