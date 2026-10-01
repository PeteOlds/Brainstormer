"""Phase 3: provider routing, keys, budgets, spend."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import (
    AISpendLedger,
    Instance,
    InstanceAIConfig,
    Membership,
    PromptConfig,
    PromptRun,
    PromptRunStatus,
    User,
    UserRole,
)


def make_instance(number, name=None, free=False):
    instance = Instance(number=number, name=name or f"Inst {number}", is_free=free)
    db.session.add(instance)
    db.session.flush()
    return instance


def make_user(email, role=UserRole.USER):
    user = User(email=email, role=role)
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    return user


def grant(user, instance, role):
    db.session.add(Membership(user_id=user.id, instance_id=instance.id, role=role))
    db.session.flush()


def login(client, email, instance_id=None):
    body = {"email": email, "password": "password123"}
    if instance_id:
        body["instance_id"] = str(instance_id)
    res = client.post("/api/v1/login", json=body)
    assert res.status_code == 200, res.get_json()
    return {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}


def llm_response(text, prompt_tokens=10, completion_tokens=20):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        ),
    )


VALID_REFINE = json.dumps(
    {
        "elevator_pitch": "AI-powered inventory management for small retailers",
        "target_audience": "Small retail businesses",
        "core_value_proposition": "Automated stock optimization",
        "monetization_strategy": "SaaS subscription",
    }
)


def test_prompt_provider_validation(admin_client, app):
    res = admin_client.post(
        "/api/v1/prompts",
        json={
            "title": "T",
            "prompt_body": "b",
            "interval_minutes": 60,
            "model_name": "m",
            "provider": "bogus",
        },
    )
    assert res.status_code == 400

    # Unscoped legacy requests keep working with any provider label.
    res = admin_client.post(
        "/api/v1/prompts",
        json={
            "title": "T",
            "prompt_body": "b",
            "interval_minutes": 60,
            "model_name": "openai/gpt-4o-mini",
            "provider": "openai",
        },
    )
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["data"]["provider"] == "openai"


def test_allowlist_enforced_when_scoped(app, client):
    with app.app_context():
        from app.models import ROLE_INSTANCE_ADMIN

        inst = make_instance(20, "A")
        admin = make_user("allow@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        db.session.add(
            InstanceAIConfig(
                instance_id=inst.id,
                provider="openai",
                model_allowlist=["openai/gpt-4o-mini"],
            )
        )
        db.session.commit()
        db.session.expunge_all()
    with app.app_context():
        iid = str(Instance.query.filter_by(number=20).first().id)
    headers = login(client, "allow@t.test", iid)

    base = {"title": "T", "prompt_body": "b", "interval_minutes": 60}
    res = client.post(
        "/api/v1/prompts",
        json={**base, "model_name": "openai/gpt-4o", "provider": "openai"},
        headers=headers,
    )
    assert res.status_code == 400
    res = client.post(
        "/api/v1/prompts",
        json={**base, "model_name": "openai/gpt-4o-mini", "provider": "openai"},
        headers=headers,
    )
    assert res.status_code == 201, res.get_json()


def test_ai_config_keys_never_leak(app, client):
    with app.app_context():
        from app.models import ROLE_INSTANCE_ADMIN

        inst = make_instance(21, "B")
        admin = make_user("keys@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        db.session.commit()
        iid = str(inst.id)
    headers = login(client, "keys@t.test", iid)

    res = client.put(
        f"/api/v1/instances/{iid}/ai-configs",
        json={
            "provider": "openai",
            "key": "sk-live-secret",
            "model_allowlist": ["openai/gpt-4o-mini"],
            "budget_cents": 500,
        },
        headers=headers,
    )
    assert res.status_code == 200, res.get_json()
    body = res.get_json()["data"]["config"]
    assert body["has_key"] is True
    assert "key" not in body
    assert "sk-live-secret" not in json.dumps(body)

    res = client.get(f"/api/v1/instances/{iid}/ai-configs", headers=headers)
    assert "sk-live-secret" not in res.get_data(as_text=True)

    with app.app_context():
        row = InstanceAIConfig.query.filter_by(instance_id=uuid.UUID(iid)).first()
        assert row._api_key != "sk-live-secret"
        assert row.api_key == "sk-live-secret"

    # Non-members see nothing (not even existence).
    with app.app_context():
        outsider = make_user("outsider@t.test")
        db.session.commit()
    outsider_h = login(client, "outsider@t.test")
    assert (
        client.get(
            f"/api/v1/instances/{iid}/ai-configs", headers=outsider_h
        ).status_code
        == 404
    )


def _hosted_prompt(instance_id, admin_id, model="openai/gpt-4o-mini"):
    prompt = PromptConfig(
        title="Hosted",
        prompt_body="Generate {{topic}}",
        interval_minutes=60,
        model_name=model,
        provider="openai",
        is_active=True,
        created_by_id=admin_id,
        instance_id=instance_id,
    )
    db.session.add(prompt)
    db.session.flush()
    return prompt


def test_hosted_generation_records_spend(app, celery_app):
    from app.models import Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = make_instance(22, "C")
        admin = make_user("hosted@t.test", UserRole.ADMIN)
        grant(admin, inst, "INSTANCE_ADMIN")
        db.session.add(InstanceAIConfig(instance_id=inst.id, provider="openai"))
        db.session.flush()
        InstanceAIConfig.query.filter_by(
            instance_id=inst.id, provider="openai"
        ).first().api_key = "sk-test"
        prompt = _hosted_prompt(inst.id, admin.id)
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        pid, rid, iid = prompt.id, run.id, inst.id

        with (
            patch(
                "litellm.completion", return_value=llm_response(VALID_REFINE)
            ) as mock_call,
            patch("litellm.completion_cost", return_value=0.05),
            patch("app.services.embedding_service.get_embedding_service") as mock_emb,
            patch("app.services.slack_service.post_idea"),
        ):
            mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
            mock_emb.return_value.find_similar_to_embedding.return_value = []
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))

        sent = mock_call.call_args.kwargs
        assert sent["model"] == "openai/gpt-4o-mini"
        assert sent["response_format"] == {"type": "json_object"}
        assert sent["api_key"] == "sk-test"

        db.session.expire_all()
        idea = Idea.query.filter_by(prompt_config_id=pid).first()
        assert idea is not None and idea.instance_id == iid
        assert db.session.get(PromptRun, rid).status == PromptRunStatus.SUCCESS

        rows = AISpendLedger.query.filter_by(instance_id=iid).all()
        assert len(rows) == 1
        assert (
            rows[0].prompt_tokens,
            rows[0].completion_tokens,
            rows[0].cost_cents,
        ) == (10, 20, 5)


def test_budget_exhausted_fails_run_without_call(app, celery_app):
    from app.models import Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = make_instance(23, "D")
        admin = make_user("budget@t.test", UserRole.ADMIN)
        db.session.add(
            InstanceAIConfig(instance_id=inst.id, provider="openai", budget_cents=10)
        )
        db.session.flush()
        InstanceAIConfig.query.filter_by(
            instance_id=inst.id, provider="openai"
        ).first().api_key = "sk-test"
        db.session.add(
            AISpendLedger(
                instance_id=inst.id,
                provider="openai",
                model="m",
                prompt_tokens=1,
                completion_tokens=1,
                cost_cents=10,
            )
        )
        prompt = _hosted_prompt(inst.id, admin.id)
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        pid, rid, iid = prompt.id, run.id, inst.id

        with patch("litellm.completion") as mock_call:
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))
            mock_call.assert_not_called()

        db.session.expire_all()
        assert db.session.get(PromptRun, rid).status == PromptRunStatus.FAILED
        assert "budget" in (db.session.get(PromptRun, rid).error or "").lower()
        assert Idea.query.count() == 0


def test_missing_key_fails_cleanly(app, celery_app):
    from app.models import Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = make_instance(24, "E")
        admin = make_user("nokey@t.test", UserRole.ADMIN)
        prompt = _hosted_prompt(inst.id, admin.id)
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        pid, rid, iid = prompt.id, run.id, inst.id

        with patch("litellm.completion") as mock_call:
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))
            mock_call.assert_not_called()

        db.session.expire_all()
        assert db.session.get(PromptRun, rid).status == PromptRunStatus.FAILED
        assert Idea.query.count() == 0


def test_auth_error_is_not_retryable():
    import litellm

    from app.services.llm_backends import ProviderError, _litellm_generate

    with patch(
        "litellm.completion",
        side_effect=litellm.AuthenticationError("bad key", "openai", "m"),
    ):
        try:
            _litellm_generate(
                "m", "hi", None, {}, api_key="bad", endpoint=None, timeout=5
            )
        except ProviderError as exc:
            assert exc.retryable is False
        else:
            raise AssertionError("expected ProviderError")


def test_spend_api_totals(app, client):
    with app.app_context():
        from app.models import ROLE_INSTANCE_ADMIN

        inst = make_instance(25, "F")
        admin = make_user("spend@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        db.session.add(
            AISpendLedger(
                instance_id=inst.id,
                provider="openai",
                model="openai/gpt-4o-mini",
                prompt_tokens=100,
                completion_tokens=50,
                cost_cents=7,
            )
        )
        db.session.add(
            InstanceAIConfig(instance_id=inst.id, provider="openai", budget_cents=100)
        )
        db.session.commit()
        iid = str(inst.id)
    headers = login(client, "spend@t.test", iid)

    res = client.get(f"/api/v1/instances/{iid}/spend", headers=headers)
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert data["by_provider"]["openai"]["cost_cents"] == 7
    assert data["budgets"]["openai"]["spent_cents"] == 7
    assert data["budgets"]["openai"]["exhausted"] is False
