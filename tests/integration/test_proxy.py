"""Item 10: LiteLLM proxy virtual-key isolation."""

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
    PromptRunStatus,
    User,
    UserRole,
)

VALID_REFINE = json.dumps(
    {
        "elevator_pitch": "AI-powered inventory management for small retailers",
        "target_audience": "Small retail businesses",
        "core_value_proposition": "Automated stock optimization",
        "monetization_strategy": "SaaS subscription",
    }
)


def setup_proxy_instance(number=90, email="proxy@t.test"):
    inst = Instance(number=number, name=f"Proxy {number}", is_free=False)
    db.session.add(inst)
    db.session.flush()
    admin = User(email=email, role=UserRole.ADMIN)
    admin.set_password("password123")
    db.session.add(admin)
    db.session.flush()
    db.session.add(
        Membership(user_id=admin.id, instance_id=inst.id, role="INSTANCE_ADMIN")
    )
    db.session.add(InstanceAIConfig(instance_id=inst.id, provider="openai"))
    db.session.flush()
    config = InstanceAIConfig.query.filter_by(
        instance_id=inst.id, provider="openai"
    ).first()
    config.api_key = "sk-direct-never-used-in-proxy-mode"
    config.virtual_key = "sk-proxy-virtual-key"
    config.use_proxy = True
    db.session.commit()
    return inst


def proxy_http(content=VALID_REFINE, prompt_tokens=3, completion_tokens=4, status=200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    return client


def test_proxy_generation_uses_virtual_key(app, celery_app):
    from app.models import AISpendLedger, Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = setup_proxy_instance()
        admin = User.query.filter_by(email="proxy@t.test").first()
        prompt = PromptConfig(
            title="P",
            prompt_body="Generate {{topic}}",
            interval_minutes=60,
            model_name="openai/gpt-4o-mini",
            provider="openai",
            is_active=True,
            created_by_id=admin.id,
            instance_id=inst.id,
        )
        db.session.add(prompt)
        db.session.flush()
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        pid, rid, iid = prompt.id, run.id, inst.id

        with (
            patch(
                "app.services.llm_backends.httpx.Client", return_value=proxy_http()
            ) as mock_client,
            patch("litellm.completion") as mock_direct,
            patch("app.services.embedding_service.get_embedding_service") as mock_emb,
            patch("app.services.slack_service.post_idea"),
        ):
            mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
            mock_emb.return_value.find_similar_to_embedding.return_value = []
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))

        mock_direct.assert_not_called()
        _, kwargs = mock_client.return_value.post.call_args
        assert kwargs["headers"] == {"Authorization": "Bearer sk-proxy-virtual-key"}
        assert "sk-direct" not in json.dumps(kwargs)
        assert kwargs["json"]["model"] == "openai/gpt-4o-mini"

        db.session.expire_all()
        assert db.session.get(PromptRun, rid).status == PromptRunStatus.SUCCESS
        assert Idea.query.filter_by(prompt_config_id=pid).first() is not None
        ledger = AISpendLedger.query.filter_by(instance_id=iid).all()
        assert sum(r.prompt_tokens for r in ledger) == 3
        assert sum(r.cost_cents for r in ledger) >= 0


def test_proxy_401_fails_fast(app, celery_app):
    from app.models import Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = setup_proxy_instance(91, "proxy401@t.test")
        admin = User.query.filter_by(email="proxy401@t.test").first()
        prompt = PromptConfig(
            title="P",
            prompt_body="b",
            interval_minutes=60,
            model_name="openai/gpt-4o-mini",
            provider="openai",
            is_active=True,
            created_by_id=admin.id,
            instance_id=inst.id,
        )
        db.session.add(prompt)
        db.session.flush()
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        pid, rid, iid = prompt.id, run.id, inst.id

        bad = proxy_http(status=401)
        with patch("app.services.llm_backends.httpx.Client", return_value=bad):
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))

        db.session.expire_all()
        run_row = db.session.get(PromptRun, rid)
        assert run_row.status == PromptRunStatus.FAILED
        assert "virtual key" in (run_row.error or "").lower()
        assert Idea.query.count() == 0


def test_provision_cli_stores_encrypted_key(app):
    runner = app.test_cli_runner()
    app.config["LITELLM_MASTER_KEY"] = "sk-master-test"
    with app.app_context():
        inst = setup_proxy_instance(92, "provision@t.test")
        iid = str(inst.id)
        db.session.query(InstanceAIConfig).filter_by(instance_id=inst.id).delete()
        db.session.add(InstanceAIConfig(instance_id=inst.id, provider="openai"))
        db.session.flush()
        InstanceAIConfig.query.filter_by(
            instance_id=inst.id, provider="openai"
        ).first().api_key = "sk-direct"
        db.session.commit()

    fake_key = SimpleNamespace()
    with patch("app.services.llm_backends.httpx.Client") as mock_client:
        response = MagicMock()
        response.json.return_value = {"key": "sk-litellm-issued-key"}
        mock_client.return_value.__enter__.return_value.post.return_value = response
        result = runner.invoke(
            args=[
                "provision-proxy-key",
                "--instance",
                "92",
                "--provider",
                "openai",
                "--models",
                "openai/gpt-4o-mini",
            ]
        )
    assert result.exit_code == 0, result.output
    assert "sk-litellm-issued-key" not in result.output
    with app.app_context():
        row = InstanceAIConfig.query.filter_by(
            instance_id=uuid_parse(iid), provider="openai"
        ).first()
        assert row.use_proxy is True
        assert row.virtual_key == "sk-litellm-issued-key"
        assert row._virtual_key != "sk-litellm-issued-key"


def uuid_parse(value):
    import uuid

    return uuid.UUID(str(value))


def test_api_proxy_toggle_needs_key(app, client):
    with app.app_context():
        inst = setup_proxy_instance(93, "proxytoggle@t.test")
        db.session.query(InstanceAIConfig).filter_by(instance_id=inst.id).delete()
        db.session.add(InstanceAIConfig(instance_id=inst.id, provider="openai"))
        db.session.commit()
        iid = str(inst.id)
    res = client.post(
        "/api/v1/login",
        json={
            "email": "proxytoggle@t.test",
            "password": "password123",
            "instance_id": iid,
        },
    )
    headers = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}

    res = client.put(
        f"/api/v1/instances/{iid}/ai-configs",
        json={"provider": "openai", "use_proxy": True},
        headers=headers,
    )
    assert res.status_code == 400
    body = client.get(f"/api/v1/instances/{iid}/ai-configs", headers=headers).get_json()
    assert _no_secret_keys(body)
    assert body["data"]["configs"][0]["has_virtual_key"] is False


def _no_secret_keys(payload) -> bool:
    """No dict anywhere carries a raw secret field."""
    if isinstance(payload, dict):
        if any(k in payload for k in ("virtual_key", "_virtual_key", "api_key", "key")):
            return False
        return all(_no_secret_keys(v) for v in payload.values())
    if isinstance(payload, list):
        return all(_no_secret_keys(v) for v in payload)
    return True
