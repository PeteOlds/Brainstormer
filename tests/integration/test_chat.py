"""Phase 4: chat turns, iterate versions, rollback, gates."""

from unittest.mock import patch

from app.extensions import db
from app.models import ChatSession, ChatTurn, Idea, IdeaEdit
from app.services.llm_backends import GenerationResult


def make_idea(ref="IDEA-C1", instance_id=None):
    idea = Idea(
        reference_code=ref,
        prompt_title="Original title",
        raw_content="Original content",
        structured_content={"elevator_pitch": "Original pitch"},
        prompt_config_id=None,
        instance_id=instance_id,
    )
    db.session.add(idea)
    db.session.commit()
    return idea.id


def mock_reply(text="Sounds like a plan.", model="llama3:8b"):
    return patch(
        "app.services.chat.generate_for_prompt",
        return_value=GenerationResult(text=text, model=model),
    )


def test_chat_iterate_rollback_round_trip(admin_client, app):
    with app.app_context():
        idea_id = make_idea()

    with mock_reply():
        res = admin_client.post(
            f"/api/v1/ideas/{idea_id}/chat", json={"message": "What do you think?"}
        )
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert data["reply"]["role"] == "assistant"
    assert data["reply"]["content"] == "Sounds like a plan."

    res = admin_client.post(
        f"/api/v1/ideas/{idea_id}/chat/iterate",
        json={
            "content": {"prompt_title": "Rewritten title"},
            "message": "Tighten it up",
        },
    )
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["data"]["idea"]["prompt_title"] == "Rewritten title"
    turn_id = res.get_json()["data"]["turn"]["id"]

    with app.app_context():
        edits = IdeaEdit.query.filter_by(idea_id=idea_id).all()
        assert any(e.field == "iterate.prompt_title" for e in edits)

    res = admin_client.post(
        f"/api/v1/ideas/{idea_id}/chat/rollback", json={"turn_id": turn_id}
    )
    assert res.status_code == 200, res.get_json()
    body = res.get_json()["data"]
    assert body["idea"]["prompt_title"] == "Original title"
    assert body["turn"]["kind"] == "rollback"

    with app.app_context():
        fields = {e.field for e in IdeaEdit.query.filter_by(idea_id=idea_id).all()}
        assert "iterate.prompt_title" in fields
        assert "rollback.prompt_title" in fields


def test_chat_excludes_ignored_comments(admin_client, app):
    from app.models import Comment, User

    with app.app_context():
        idea_id = make_idea(ref="IDEA-C2")
        user = User.query.first()
        db.session.add(
            Comment(
                idea_id=idea_id, user_id=user.id, body="visible thought", phase="SPARK"
            )
        )
        hidden = Comment(
            idea_id=idea_id,
            user_id=user.id,
            body="secret thought",
            phase="SPARK",
            is_ignored=True,
        )
        db.session.add(hidden)
        db.session.commit()

    captured = {}
    real = GenerationResult(text="ok", model="m")

    def fake_generate(route, prompt_text, **kwargs):
        captured["prompt"] = prompt_text
        return real

    with patch("app.services.chat.generate_for_prompt", side_effect=fake_generate):
        res = admin_client.post(f"/api/v1/ideas/{idea_id}/chat", json={"message": "hi"})
    assert res.status_code == 200, res.get_json()
    assert "visible thought" in captured["prompt"]
    assert "secret thought" not in captured["prompt"]


def test_chat_user_cannot_iterate_or_override(client, auth_user, app, admin_client):
    _email, token = auth_user
    headers = {"Authorization": f"Bearer {token}"}
    with app.app_context():
        idea_id = make_idea(ref="IDEA-C3")

    assert (
        client.post(
            f"/api/v1/ideas/{idea_id}/chat/iterate",
            json={"content": {"prompt_title": "x"}},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/ideas/{idea_id}/chat/rollback",
            json={"turn_id": "00000000-0000-0000-0000-000000000000"},
            headers=headers,
        ).status_code
        == 403
    )
    res = client.post(
        f"/api/v1/ideas/{idea_id}/chat",
        json={"message": "hi", "model_override": "m"},
        headers=headers,
    )
    assert res.status_code == 403

    with mock_reply():
        res = client.post(
            f"/api/v1/ideas/{idea_id}/chat", json={"message": "hi"}, headers=headers
        )
    assert res.status_code == 200, res.get_json()

    res = client.get(f"/api/v1/ideas/{idea_id}/chat", headers=headers)
    assert res.status_code == 200
    assert len(res.get_json()["data"]["sessions"]) == 1
    assert len(res.get_json()["data"]["sessions"][0]["turns"]) == 2


def test_chat_cross_instance_404(app, client):
    from app.models import Instance, Membership, User

    with app.app_context():
        inst = Instance(number=40, name="ChatOther")
        db.session.add(inst)
        db.session.flush()
        user = User(email="chat-iso@t.test")
        user.set_password("password123")
        db.session.add(user)
        db.session.flush()
        home = Instance(number=41, name="ChatHome")
        db.session.add(home)
        db.session.flush()
        db.session.add(Membership(user_id=user.id, instance_id=home.id, role="USER"))
        other_idea = make_idea(ref="IDEA-C4", instance_id=inst.id)
        db.session.commit()
        hid, oid = str(home.id), str(other_idea)

    res = client.post(
        "/api/v1/login",
        json={
            "email": "chat-iso@t.test",
            "password": "password123",
            "instance_id": hid,
        },
    )
    headers = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}
    assert (
        client.post(
            f"/api/v1/ideas/{oid}/chat", json={"message": "hi"}, headers=headers
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/ideas/{oid}/chat", headers=headers).status_code == 404


def test_chat_enabled_gate(app, client, admin_client):
    from app.models import Instance, InstanceAIConfig, Membership, User

    with app.app_context():
        inst = Instance(number=42, name="ChatGate")
        db.session.add(inst)
        db.session.flush()
        admin = User(email="chat-gate@t.test")
        admin.set_password("password123")
        db.session.add(admin)
        db.session.flush()
        db.session.add(
            Membership(user_id=admin.id, instance_id=inst.id, role="INSTANCE_ADMIN")
        )
        db.session.add(
            InstanceAIConfig(instance_id=inst.id, provider="openai", chat_enabled=False)
        )
        gated_idea = make_idea(ref="IDEA-C5", instance_id=inst.id)
        db.session.commit()
        iid, gid = str(inst.id), str(gated_idea)

    res = client.post(
        "/api/v1/login",
        json={
            "email": "chat-gate@t.test",
            "password": "password123",
            "instance_id": iid,
        },
    )
    headers = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}
    res = client.post(
        f"/api/v1/ideas/{gid}/chat", json={"message": "hi"}, headers=headers
    )
    assert res.status_code == 403
    assert res.get_json().get("error_code") == "CHAT_DISABLED"

    with app.app_context():
        InstanceAIConfig.query.filter_by(instance_id=uuid_parse(iid)).update(
            {"chat_enabled": True}
        )
        db.session.commit()
    with mock_reply():
        res = client.post(
            f"/api/v1/ideas/{gid}/chat", json={"message": "hi"}, headers=headers
        )
    assert res.status_code == 200, res.get_json()


def uuid_parse(value):
    import uuid

    return uuid.UUID(str(value))


def test_rollback_validation(admin_client, app):
    with app.app_context():
        idea_id = make_idea(ref="IDEA-C6")

    res = admin_client.post(
        f"/api/v1/ideas/{idea_id}/chat/rollback", json={"turn_id": "nope"}
    )
    assert res.status_code == 400
    res = admin_client.post(
        f"/api/v1/ideas/{idea_id}/chat/rollback",
        json={"turn_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert res.status_code == 404

    with mock_reply():
        admin_client.post(f"/api/v1/ideas/{idea_id}/chat", json={"message": "hi"})
    with app.app_context():
        turn = ChatTurn.query.filter_by(kind="chat").first()
        turn_id = str(turn.id)
    res = admin_client.post(
        f"/api/v1/ideas/{idea_id}/chat/rollback", json={"turn_id": turn_id}
    )
    assert res.status_code == 400


def test_iterate_validation(admin_client, app):
    with app.app_context():
        idea_id = make_idea(ref="IDEA-C7")

    res = admin_client.post(
        f"/api/v1/ideas/{idea_id}/chat/iterate", json={"content": {}}
    )
    assert res.status_code == 400
    res = admin_client.post(
        f"/api/v1/ideas/{idea_id}/chat/iterate", json={"content": {"nope": "x"}}
    )
    assert res.status_code == 400
    res = admin_client.post(
        f"/api/v1/ideas/{idea_id}/chat/iterate",
        json={"content": {"prompt_title": "x" * 201}},
    )
    assert res.status_code == 400
