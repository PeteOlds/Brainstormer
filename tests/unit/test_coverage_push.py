"""Coverage push toward 80%: prompts validators/SSE, health variants,
maintenance tasks, crypto, settings, context, slack post/thread paths,
embedding service with mocked Ollama, secondary-action task success."""

import json
from unittest.mock import MagicMock, patch

from app.extensions import db


def test_prompt_validators_reject(admin_client):
    base = {"title": "T", "prompt_body": "b", "interval_minutes": 60, "model_name": "m"}
    for bad in (
        {"temperature": 5},
        {"temperature": "hot"},
        {"top_p": 2},
        {"repeat_penalty": -1},
        {"num_predict": 0},
        {"num_predict": 99999},
        {"seed": -1},
        {"keep_alive": "x" * 21},
        {"slack_channel": "nope"},
        {"provider": "bogus"},
        {"interval_minutes": 0},
        {"interval_minutes": "soon"},
    ):
        res = admin_client.post("/api/v1/prompts", json={**base, **bad})
        assert res.status_code == 400, bad


def test_prompt_test_validations_and_timeout(admin_client):
    res = admin_client.post("/api/v1/prompts/test", json={"model_name": "m"})
    assert res.status_code == 400
    res = admin_client.post(
        "/api/v1/prompts/test",
        json={"prompt_body": "b", "model_name": "m", "temperature": 9},
    )
    assert res.status_code == 400

    import httpx

    with patch("httpx.Client") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value.json.return_value = {"response": "hi"}
        res = admin_client.post(
            "/api/v1/prompts/test",
            json={"prompt_body": "Hey {{topic}}", "model_name": "m"},
        )
        assert res.status_code == 200
        assert (
            res.get_json()["data"]["topic"]
            == "a sustainable packaging startup for small cafes"
        )

    with patch("httpx.Client", side_effect=httpx.TimeoutException("slow")):
        res = admin_client.post(
            "/api/v1/prompts/test", json={"prompt_body": "b", "model_name": "m"}
        )
        assert res.status_code == 504


def test_prompt_stream_paths(admin_client):
    res = admin_client.post("/api/v1/prompts/test-stream", json={"model_name": "m"})
    assert res.status_code == 400

    lines = [
        b"not json",
        b'{"response": "tok", "done": false}',
        b'{"response": "", "done": true}',
    ]
    stream = MagicMock()
    stream.__enter__.return_value = stream
    stream.iter_lines.return_value = iter(lines)
    with patch("httpx.stream", return_value=stream):
        res = admin_client.post(
            "/api/v1/prompts/test-stream", json={"prompt_body": "b", "model_name": "m"}
        )
        assert res.status_code == 200
        assert "data: [DONE]" in res.get_data(as_text=True)
        assert "tok" in res.get_data(as_text=True)

    with patch("httpx.stream", side_effect=RuntimeError("boom")):
        res = admin_client.post(
            "/api/v1/prompts/test-stream", json={"prompt_body": "b", "model_name": "m"}
        )
        assert res.status_code == 200
        assert "error" in res.get_data(as_text=True)


def test_prompt_delete_and_update_interval(app, admin_client, admin_user, admin_prompt):
    from app.models import PromptConfig

    with app.app_context():
        pid = str(PromptConfig.query.first().id)
    res = admin_client.patch(f"/api/v1/prompts/{pid}", json={"interval_minutes": -3})
    assert res.status_code == 400
    res = admin_client.patch(f"/api/v1/prompts/{pid}", json={"interval_minutes": 120})
    assert res.status_code == 200
    assert res.get_json()["data"]["interval_minutes"] == 120
    res = admin_client.delete(f"/api/v1/prompts/{pid}")
    assert res.status_code == 200
    with app.app_context():
        assert PromptConfig.query.get(pid) is None


def test_health_variants(client):
    from unittest.mock import patch as _patch

    with _patch("app.routes.health.check_redis", return_value=False):
        assert client.get("/api/health").status_code == 503
    with (
        _patch("app.routes.health.check_redis", return_value=True),
        _patch("app.routes.health.check_scheduler", return_value=False),
    ):
        assert client.get("/api/health").status_code == 503


def test_ready_ollama_down(client):
    with patch("httpx.Client", side_effect=Exception("down")):
        res = client.get("/api/ready")
        assert res.status_code in (200, 503)
        assert res.get_json()["data"]["checks"]["ollama"] is False


def test_maintenance_tasks(app, admin_user, admin_prompt):
    from app.models import Idea, PromptConfig, User
    from app.tasks import maintenance_tasks as tasks

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        if admin is None:
            from app.models import UserRole

            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        if prompt is None:
            prompt = PromptConfig(
                title="M",
                prompt_body="b",
                interval_minutes=60,
                model_name="m",
                created_by_id=admin.id,
            )
            db.session.add(prompt)
            db.session.commit()
        assert tasks.cleanup_old_discarded(days=90)["status"] == "not_implemented"
        assert tasks.recalculate_vote_counts()["updated"] >= 0
        assert tasks.update_next_run_times()["updated"] >= 0
        # NOTE: beat_heartbeat is covered by test_beat_heartbeat_without_redis
        # below. Never call the live path here: it writes a REAL heartbeat
        # key to the shared redis DB, which later poisons
        # test_health_ok (stale key reads as scheduler-degraded).


def test_crypto_round_trip(app):
    from app.utils import crypto

    with app.app_context():
        token = crypto.encrypt("secret-value")
        assert token and token != "secret-value"
        assert crypto.decrypt(token) == "secret-value"
        assert crypto.decrypt("") == ""
        assert crypto.encrypt("") == ""


def test_system_settings_updates(app):
    from app.models import SystemSettings

    with app.app_context():
        settings = SystemSettings.get_instance()
        settings.update_platform({"title": "T"})
        settings.update_location({"country": "NZ"})
        settings.update_ai_connections({"x": 1})
        db.session.commit()
        data = SystemSettings.get_instance().to_dict()
        assert data["platform"] == {"title": "T"}
        assert "SystemSettings" in repr(settings)


def test_action_context_sections(app, admin_user, admin_prompt):
    from app.models import (
        Comment,
        Idea,
        PromptConfig,
        SecondaryActionResult,
        User,
        Vote,
    )
    from app.services.action_context import build_idea_context

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code="IDEA-CTX",
            prompt_title="T",
            raw_content="c",
            structured_content={"elevator_pitch": "Pitch here"},
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.flush()
        db.session.add(Comment(idea_id=idea.id, user_id=admin.id, body="Nice one"))
        db.session.add(Vote(user_id=admin.id, idea_id=idea.id, value=1))
        db.session.add(
            SecondaryActionResult(
                idea_id=idea.id,
                action_type="REFINE",
                model_used="m",
                result_data={"elevator_pitch": "x"},
            )
        )
        db.session.commit()
        text = build_idea_context(idea)
        assert "Pitch here" in text
        assert "Nice one" in text
        assert "Upvotes: 1" in text
        assert "Refine" in text


def test_slack_post_and_provision_paths():
    from app.services import slack_service

    assert slack_service.post_idea("", {"id": "x"}, "http://b") is None
    with patch("app.services.slack_service.get_client", return_value=None):
        assert slack_service.post_idea("#c", {"id": "x"}, "http://b") is None

    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "1.0", "channel": "#c"}
    with patch("app.services.slack_service.get_client", return_value=client):
        with patch("app.services.slack_service._record_post") as record:
            ts = slack_service.post_idea(
                "#c", {"id": "y", "reference_code": "IDEA-1"}, "http://b"
            )
            assert ts == "1.0"
            record.assert_called_once()

    class RateLimited(Exception):
        def __init__(self):
            self.response = {"headers": {"Retry-After": "0"}}

    flaky = MagicMock()
    flaky.chat_postMessage.side_effect = [RateLimited(), {"ts": "2.0"}]
    with (
        patch("app.services.slack_service.get_client", return_value=flaky),
        patch("app.services.slack_service._record_post"),
        patch("app.services.slack_service.time.sleep"),
    ):
        assert slack_service.post_idea("#c", {"id": "z"}, "http://b") == "2.0"


def test_slack_thread_and_provision(app):
    from app.models import User
    from app.services import slack_service

    with app.app_context():
        client = MagicMock()
        client.users_info.return_value = {
            "user": {"profile": {"email": "slack-new@t.test"}}
        }
        user = slack_service.get_or_provision_user(client, "U123")
        assert user is not None and user.slack_user_id == "U123"
        again = slack_service.get_or_provision_user(client, "U123")
        assert str(again.id) == str(user.id)

        event = {
            "type": "message",
            "user": "U123",
            "text": "hi",
            "thread_ts": "9.9",
            "ts": "2.0",
            "channel": "#c",
            "item": {"type": "message"},
        }
        assert slack_service.handle_thread_reply(client, event) == "duplicate"
        assert (
            slack_service.handle_thread_reply(
                client, {**event, "subtype": "bot_message"}, event_id="E9"
            )
            == "bot-message-ignored"
        )
        assert (
            slack_service.handle_thread_reply(client, event, event_id="E10")
            == "unknown-thread"
        )


def test_embedding_service_mocked(app, admin_user, admin_prompt):
    from app.models import Idea, PromptConfig, User, UserRole
    from app.services.embedding_service import EmbeddingService, embedding_text

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        if admin is None:
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        if prompt is None:
            prompt = PromptConfig(
                title="M",
                prompt_body="b",
                interval_minutes=60,
                model_name="m",
                created_by_id=admin.id,
            )
            db.session.add(prompt)
            db.session.commit()
        idea = Idea(
            reference_code="IDEA-EMB",
            prompt_title="Title here",
            raw_content="c",
            structured_content={"elevator_pitch": "Ep"},
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.commit()
        assert "Title here" in embedding_text(idea)

        svc = EmbeddingService()
        with patch.object(
            svc.ollama_client, "generate_sync", return_value={"embedding": [0.1] * 768}
        ):
            vec = svc.generate_embedding_sync("hello")
            assert len(vec) == 768
        assert svc.store_embedding(idea.id, [0.1] * 768) is True
        db.session.expire_all()
        assert Idea.query.get(idea.id).embedding == [0.1] * 768

        similar = svc.find_similar_to_embedding([0.1] * 768, threshold=0.5)
        assert any(str(i.id) == str(idea.id) for i, _ in similar)
        assert svc.find_similar_to_embedding([], threshold=0.5) == []


def test_secondary_action_success_path(app, celery_app, admin_user, admin_prompt):
    from app.models import Idea, PromptConfig, SecondaryActionResult, User, UserRole
    from app.tasks.ollama_tasks import run_secondary_action

    with celery_app.app_context():
        admin = User(email="admin_sa@t.test", role=UserRole.ADMIN)
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
            reference_code="IDEA-SA",
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
            mock_client.generate_sync.return_value = {
                "response": json.dumps(
                    {
                        "elevator_pitch": "AI-powered inventory management for small retailers",
                        "target_audience": "Small retail businesses",
                        "core_value_proposition": "Automated stock optimization",
                        "monetization_strategy": "SaaS subscription",
                    }
                ),
                "done": True,
            }
            run_secondary_action(str(iid), "REFINE")

        db.session.expire_all()
        rows = SecondaryActionResult.query.filter_by(idea_id=iid).all()
        assert len(rows) == 1 and rows[0].is_current is True


def test_auth_edge_paths(client, app):
    res = client.post("/api/v1/refresh", json={})
    assert res.status_code == 400
    res = client.post("/api/v1/refresh", json={"refresh_token": "bogus"})
    assert res.status_code == 401
    res = client.patch(
        "/api/v1/me/settings",
        json={"can_create_ideas": "yes"},
        headers={"Authorization": "Bearer bogus"},
    )
    assert res.status_code in (401, 422)


def test_slack_reaction_outcomes(app, admin_user, admin_prompt):
    from app.models import Idea, PromptConfig, SlackPost, User
    from app.services import slack_service

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code="IDEA-SLK",
            prompt_title="T",
            raw_content="c",
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.flush()
        db.session.add(SlackPost(idea_id=idea.id, channel_id="#c", message_ts="5.0"))
        db.session.commit()
        iid = idea.id

        client = MagicMock()
        client.users_info.return_value = {
            "user": {"profile": {"email": "react@t.test"}}
        }
        base = {
            "item": {"type": "message", "channel": "#c", "ts": "5.0"},
            "user": "U9",
            "reaction": "+1",
        }
        assert (
            slack_service.handle_reaction_event(
                client, {**base, "reaction": "eyes"}, event_id="E1"
            )
            == "ignored-reaction"
        )
        assert (
            slack_service.handle_reaction_event(
                client,
                {"item": {"type": "file"}, "reaction": "+1", "user": "U9"},
                event_id="E2",
            )
            == "ignored-item"
        )
        assert (
            slack_service.handle_reaction_event(
                client,
                {
                    "item": {"type": "message", "channel": "#x", "ts": "0"},
                    "reaction": "+1",
                    "user": "U9",
                },
                event_id="E3",
            )
            == "unknown-message"
        )
        assert slack_service.handle_reaction_event(
            client, base, event_id="E4"
        ).startswith("vote:net=")
        assert (
            slack_service.handle_reaction_event(client, base, event_id="E4")
            == "duplicate"
        )
        assert slack_service.handle_reaction_event(
            client, base, event_id="E5", event_type="reaction_removed"
        ).startswith("vote:net=")
        assert (
            slack_service.apply_slack_vote(
                admin, "00000000-0000-0000-0000-000000000000", 1, True
            )
            is None
        )

        assert (
            slack_service.mirror_comment_to_thread(
                Idea.query.get(iid), MagicMock(body="hello", id="c1")
            )
            is None
        )
        with patch("app.services.slack_service.get_client", return_value=client):
            client.chat_postMessage.return_value = {"ts": "6.0"}
            from app.models import Comment

            comment = Comment(idea_id=iid, user_id=admin.id, body="mirror me")
            db.session.add(comment)
            db.session.commit()
            ts = slack_service.mirror_comment_to_thread(Idea.query.get(iid), comment)
            assert ts == "6.0"


def test_prompt_run_now_and_burst_validation(
    app, admin_client, admin_user, admin_prompt
):
    from app.models import PromptConfig

    with app.app_context():
        pid = str(PromptConfig.query.first().id)
    res = admin_client.post(f"/api/v1/prompts/{pid}/run-now", json={"count": 0})
    assert res.status_code == 400
    res = admin_client.post(f"/api/v1/prompts/{pid}/run-now", json={"count": "many"})
    assert res.status_code == 400
    res = admin_client.patch(f"/api/v1/prompts/{pid}", json={"temperature": 9})
    assert res.status_code == 400
    res = admin_client.patch(f"/api/v1/prompts/{pid}", json={"model_name": "m2"})
    assert res.status_code == 200
    assert res.get_json()["data"]["model_name"] == "m2"


def test_embedding_backfill_async(app, admin_user, admin_prompt):
    import asyncio

    from app.models import Idea, PromptConfig, User
    from app.services.embedding_service import get_embedding_service

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        db.session.add(
            Idea(
                reference_code="IDEA-BF",
                prompt_title="T",
                raw_content="c",
                prompt_config_id=prompt.id,
            )
        )
        db.session.commit()
        svc = get_embedding_service()

        async def fake(text):
            return [0.2] * 768

        with patch.object(svc, "generate_embedding", side_effect=fake):
            stats = asyncio.run(svc.backfill_embeddings(batch_size=5))
        assert stats["processed"] >= 1 and stats["succeeded"] >= 1


def test_beat_heartbeat_without_redis(app):
    from app.tasks import maintenance_tasks as tasks

    with app.app_context():
        sentinel = object()
        saved = app.extensions.pop("redis_client", sentinel)
        try:
            assert tasks.beat_heartbeat() == {"status": "no_redis"}
        finally:
            if saved is not sentinel:
                app.extensions["redis_client"] = saved


def test_chat_api_validation(admin_client, app, admin_user, admin_prompt):
    from app.models import Idea, PromptConfig, User

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        idea = Idea(
            reference_code="IDEA-CV",
            prompt_title="T",
            raw_content="c",
            prompt_config_id=prompt.id,
        )
        db.session.add(idea)
        db.session.commit()
        iid = str(idea.id)

    res = admin_client.post(f"/api/v1/ideas/{iid}/chat", json={})
    assert res.status_code == 400
    res = admin_client.post(f"/api/v1/ideas/{iid}/chat", json={"message": "x" * 4001})
    assert res.status_code == 400
    res = admin_client.post(f"/api/v1/ideas/{iid}/chat/rollback", json={})
    assert res.status_code == 400


def test_social_state_helpers(app):
    from app.services import social_auth as social

    with app.app_context():
        bundle = social.build_start_url(
            "google", "00000000-0000-0000-000000000000", "cid", "http://x/cb"
        )
        assert "accounts.google.com" in bundle["auth_url"]
        state = bundle["auth_url"].split("state=")[1].split("&")[0]
        from urllib.parse import unquote

        data = social.read_state(unquote(state), "google")
        assert data["provider"] == "google"
        try:
            social.read_state("bogus", "google")
        except social.SocialError:
            pass
        else:
            raise AssertionError("expected SocialError")
        token = social.linking_token(
            "00000000-0000-0000-0000-000000000000",
            "google",
            "sub",
            "e@x.y",
            "00000000-0000-0000-0000-000000000000",
        )
        assert social.read_linking_token(token)["type"] == "oauth_link"
