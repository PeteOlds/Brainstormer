"""Item 18: per-stage AI config resolution and enforcement."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import (
    Instance,
    InstanceAIConfig,
    Membership,
    PromptConfig,
    PromptRun,
    StageAIConfig,
    User,
    UserRole,
    resolve_stage,
)


def setup_paid(number=80, email="stage@t.test"):
    inst = Instance(number=number, name=f"Stage {number}", is_free=False)
    db.session.add(inst)
    db.session.flush()
    admin = User(email=email, role=UserRole.ADMIN)
    admin.set_password("password123")
    db.session.add(admin)
    db.session.flush()
    db.session.add(
        Membership(user_id=admin.id, instance_id=inst.id, role="INSTANCE_ADMIN")
    )
    db.session.commit()
    return inst


def login(client, email, iid):
    res = client.post(
        "/api/v1/login",
        json={"email": email, "password": "password123", "instance_id": iid},
    )
    assert res.status_code == 200, res.get_json()
    return {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}


def test_stage_crud_and_validation(app, client):
    with app.app_context():
        inst = setup_paid()
        iid = str(inst.id)
    headers = login(client, "stage@t.test", iid)

    res = client.put(
        f"/api/v1/instances/{iid}/stage-config",
        json={"stage": "SPARKK", "model_name": "m"},
        headers=headers,
    )
    assert res.status_code == 400
    res = client.put(
        f"/api/v1/instances/{iid}/stage-config",
        json={"stage": "SPARK", "provider": "bogus"},
        headers=headers,
    )
    assert res.status_code == 400
    res = client.put(
        f"/api/v1/instances/{iid}/stage-config",
        json={"stage": "SPARK", "temperature": 5},
        headers=headers,
    )
    assert res.status_code == 400

    res = client.put(
        f"/api/v1/instances/{iid}/stage-config",
        json={
            "stage": "SPARK",
            "provider": "ollama",
            "model_name": "llama3:8b",
            "temperature": 0.2,
            "skills": ["a"],
            "guidelines": ["g"],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.get_json()
    body = res.get_json()["data"]["stage_config"]
    assert body["temperature"] == 0.2 and body["skills"] == ["a"]

    res = client.get(f"/api/v1/instances/{iid}/stage-config", headers=headers)
    stages = res.get_json()["data"]["stages"]
    assert len(stages) == 5
    assert stages[0]["stage"] == "SPARK" and stages[0]["model_name"] == "llama3:8b"

    with app.app_context():
        assert resolve_stage(uuid_parse(iid), "SPARK")["temperature"] == 0.2
        assert resolve_stage(uuid_parse(iid), "MAP") == {}


def uuid_parse(value):
    import uuid

    return uuid.UUID(str(value))


def test_generation_uses_stage_temperature(app, celery_app):
    from unittest.mock import patch as _patch

    from app.models import Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = setup_paid(81, "stagetemp@t.test")
        admin = User.query.filter_by(email="stagetemp@t.test").first()
        prompt = PromptConfig(
            title="P",
            prompt_body="Generate {{topic}}",
            interval_minutes=60,
            model_name="llama3:8b",
            temperature=0.9,
            is_active=True,
            created_by_id=admin.id,
            instance_id=inst.id,
        )
        db.session.add(prompt)
        db.session.flush()
        db.session.add(
            StageAIConfig(instance_id=inst.id, stage="SPARK", temperature=0.2)
        )
        db.session.commit()
        pid, iid = prompt.id, inst.id

        with _patch("app.tasks.ollama_tasks.OllamaClient") as mock_class:
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
            with (
                _patch(
                    "app.services.embedding_service.get_embedding_service"
                ) as mock_emb,
                _patch("app.services.slack_service.post_idea"),
            ):
                mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
                mock_emb.return_value.find_similar_to_embedding.return_value = []
                generate_idea(str(pid), instance_id=str(iid))

        sent_options = mock_client.generate_sync.call_args.kwargs["options"]
        assert sent_options["temperature"] == 0.2
        assert Idea.query.filter_by(prompt_config_id=pid).first() is not None


def test_generation_stage_model_routes_hosted(app, celery_app):
    import json as json_mod
    from types import SimpleNamespace
    from unittest.mock import patch as _patch

    from app.models import Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = setup_paid(82, "stagemodel@t.test")
        admin = User.query.filter_by(email="stagemodel@t.test").first()
        prompt = PromptConfig(
            title="P",
            prompt_body="Generate {{topic}}",
            interval_minutes=60,
            model_name="llama3:8b",
            provider="ollama",
            is_active=True,
            created_by_id=admin.id,
            instance_id=inst.id,
        )
        db.session.add(prompt)
        db.session.flush()
        db.session.add(
            StageAIConfig(
                instance_id=inst.id,
                stage="SPARK",
                provider="openai",
                model_name="openai/gpt-stage",
            )
        )
        db.session.add(InstanceAIConfig(instance_id=inst.id, provider="openai"))
        db.session.flush()
        InstanceAIConfig.query.filter_by(
            instance_id=inst.id, provider="openai"
        ).first().api_key = "sk-test"
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        pid, rid, iid = prompt.id, run.id, inst.id

        payload = json_mod.dumps(
            {
                "elevator_pitch": "AI-powered inventory management for small retailers",
                "target_audience": "Small retail businesses",
                "core_value_proposition": "Automated stock optimization",
                "monetization_strategy": "SaaS subscription",
            }
        )
        fake = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=payload))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )
        with (
            _patch("app.tasks.ollama_tasks.OllamaClient") as mock_ollama,
            patch("litellm.completion", return_value=fake) as mock_call,
            patch("litellm.completion_cost", return_value=0.01),
            _patch("app.services.embedding_service.get_embedding_service") as mock_emb,
            _patch("app.services.slack_service.post_idea"),
        ):
            mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
            mock_emb.return_value.find_similar_to_embedding.return_value = []
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))

        mock_ollama.return_value.generate_sync.assert_not_called()
        mock_ollama.return_value.is_model_available.assert_not_called()
        assert mock_call.call_args.kwargs["model"] == "openai/gpt-stage"
        db.session.expire_all()
        from app.models import PromptRunStatus

        assert db.session.get(PromptRun, rid).status == PromptRunStatus.SUCCESS


def test_chat_follows_stage_model(app):
    from app.models import Idea
    from app.services import chat as chat_svc

    with app.app_context():
        inst = setup_paid(83, "stagechat@t.test")
        idea = Idea(
            reference_code="IDEA-S1",
            prompt_title="T",
            raw_content="c",
            prompt_config_id=None,
            instance_id=inst.id,
        )
        db.session.add(idea)
        db.session.flush()
        db.session.add(
            StageAIConfig(
                instance_id=inst.id,
                stage="SPARK",
                provider="ollama",
                model_name="llama3:70b",
            )
        )
        user = User.query.filter_by(email="stagechat@t.test").first()
        db.session.commit()
        iid = idea.id

        route = chat_svc.resolve_route(Idea.query.get(iid))
        assert route.model_name == "llama3:70b"

        route2 = chat_svc.resolve_route(Idea.query.get(iid), model_override="custom")
        assert route2.model_name == "custom"
