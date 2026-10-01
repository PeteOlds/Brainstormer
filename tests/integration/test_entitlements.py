"""Phase 8: entitlement gates, Free-flag baselines, management."""

from unittest.mock import patch

from app.extensions import db
from app.models import (
    AISpendLedger,
    Idea,
    Instance,
    InstanceAIConfig,
    InstanceEntitlement,
    Membership,
    PromptConfig,
    PromptRun,
    PromptRunStatus,
    User,
    UserRole,
)
from app.services.llm_backends import ProviderError


def setup_paid_instance(number=70, free=False):
    inst = Instance(number=number, name=f"Ent {number}", is_free=free)
    db.session.add(inst)
    db.session.flush()
    admin = User(email=f"ent{number}@t.test", role=UserRole.ADMIN)
    admin.set_password("password123")
    db.session.add(admin)
    db.session.flush()
    db.session.add(
        Membership(user_id=admin.id, instance_id=inst.id, role="INSTANCE_ADMIN")
    )
    db.session.commit()
    return inst, admin


def test_free_baseline_denies_hosted_paid_allows(app, celery_app):
    import json
    from types import SimpleNamespace

    from app.tasks.ollama_tasks import generate_idea

    payload = json.dumps(
        {
            "elevator_pitch": "AI-powered inventory management for small retailers",
            "target_audience": "Small retail businesses",
            "core_value_proposition": "Automated stock optimization",
            "monetization_strategy": "SaaS subscription",
        }
    )
    fake = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5),
    )

    with celery_app.app_context():
        from app.models import Idea as IdeaModel

        for number, free in ((70, True), (71, False)):
            inst, _ = setup_paid_instance(number, free=free)
            db.session.add(InstanceAIConfig(instance_id=inst.id, provider="openai"))
            db.session.flush()
            InstanceAIConfig.query.filter_by(
                instance_id=inst.id, provider="openai"
            ).first().api_key = "sk-test"
            owner = User.query.filter_by(email=f"ent{number}@t.test").first()
            prompt = PromptConfig(
                title="P",
                prompt_body="Generate {{topic}}",
                interval_minutes=60,
                model_name="openai/gpt-4o-mini",
                provider="openai",
                is_active=True,
                created_by_id=owner.id,
                instance_id=inst.id,
            )
            db.session.add(prompt)
            db.session.flush()
            run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
            db.session.add(run)
            db.session.commit()
            with (
                patch("litellm.completion", return_value=fake) as mock_call,
                patch("litellm.completion_cost", return_value=0.01),
                patch(
                    "app.services.embedding_service.get_embedding_service"
                ) as mock_emb,
                patch("app.services.slack_service.post_idea"),
            ):
                mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
                mock_emb.return_value.find_similar_to_embedding.return_value = []
                generate_idea(
                    str(prompt.id), run_id=str(run.id), instance_id=str(inst.id)
                )
                db.session.expire_all()
                status = db.session.get(PromptRun, run.id).status
                if free:
                    assert status == PromptRunStatus.FAILED
                    mock_call.assert_not_called()
                    assert "not entitled" in (
                        db.session.get(PromptRun, run.id).error or ""
                    )
                    assert (
                        IdeaModel.query.filter_by(prompt_config_id=prompt.id).count()
                        == 0
                    )
                else:
                    assert status == PromptRunStatus.SUCCESS
                    assert (
                        IdeaModel.query.filter_by(prompt_config_id=prompt.id).count()
                        == 1
                    )


def test_hosted_succeeds_with_mocked_provider_and_grant(app, celery_app):
    import json
    from types import SimpleNamespace

    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst, _ = setup_paid_instance(72, free=False)
        owner = User.query.filter_by(email="ent72@t.test").first()
        prompt = PromptConfig(
            title="P",
            prompt_body="Generate {{topic}}",
            interval_minutes=60,
            model_name="openai/gpt-4o-mini",
            provider="openai",
            is_active=True,
            created_by_id=owner.id,
            instance_id=inst.id,
        )
        db.session.add(prompt)
        db.session.flush()
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        db.session.add(InstanceAIConfig(instance_id=inst.id, provider="openai"))
        db.session.flush()
        InstanceAIConfig.query.filter_by(
            instance_id=inst.id, provider="openai"
        ).first().api_key = "sk-test"
        db.session.commit()
        pid, rid, iid = prompt.id, run.id, inst.id

        payload = json.dumps(
            {
                "elevator_pitch": "AI-powered inventory management for small retailers",
                "target_audience": "Small retail businesses",
                "core_value_proposition": "Automated stock optimization",
                "monetization_strategy": "SaaS subscription",
            }
        )
        fake = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=payload))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5),
        )
        with (
            patch("litellm.completion", return_value=fake),
            patch("litellm.completion_cost", return_value=0.01),
            patch("app.services.embedding_service.get_embedding_service") as mock_emb,
            patch("app.services.slack_service.post_idea"),
        ):
            mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
            mock_emb.return_value.find_similar_to_embedding.return_value = []
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))

        db.session.expire_all()
        assert db.session.get(PromptRun, rid).status == PromptRunStatus.SUCCESS
        idea = Idea.query.filter_by(prompt_config_id=pid).first()
        assert idea is not None
        ledger = AISpendLedger.query.filter_by(instance_id=iid).all()
        assert sum(r.cost_cents for r in ledger) == 1


def test_entitlement_api_and_cli(app, client):
    from app.services import instances as instance_svc

    with app.app_context():
        inst, _ = setup_paid_instance(73, free=True)
        site = User(email="ent-site@t.test")
        site.set_password("password123")
        db.session.add(site)
        db.session.commit()
        instance_svc.grant_site_admin(site.id)
        iid = str(inst.id)

    res = client.post(
        "/api/v1/login", json={"email": "ent-site@t.test", "password": "password123"}
    )
    site_h = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}
    res = client.post(
        "/api/v1/login",
        json={"email": "ent73@t.test", "password": "password123", "instance_id": iid},
    )
    inst_h = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}

    res = client.get(f"/api/v1/instances/{iid}/entitlements", headers=inst_h)
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["data"]["granted"] == ["core"]

    assert (
        client.put(
            f"/api/v1/instances/{iid}/entitlements",
            json={"key": "hosted_ai", "granted": True},
            headers=inst_h,
        ).status_code
        == 403
    )
    res = client.put(
        f"/api/v1/instances/{iid}/entitlements",
        json={"key": "hosted_ai", "granted": True},
        headers=site_h,
    )
    assert res.status_code == 200, res.get_json()
    res = client.put(
        f"/api/v1/instances/{iid}/entitlements",
        json={"key": "bogus", "granted": True},
        headers=site_h,
    )
    assert res.status_code == 400

    res = client.get(f"/api/v1/instances/{iid}/entitlements", headers=inst_h)
    assert set(res.get_json()["data"]["granted"]) == {"core", "hosted_ai"}

    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["set-entitlement", "--instance", "73", "--key", "chat"]
    )
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert (
            InstanceEntitlement.query.filter_by(instance_id=uuid_parse(iid), key="chat")
            .first()
            .granted
            is True
        )


def uuid_parse(value):
    import uuid

    return uuid.UUID(str(value))


def test_suspended_instance_refuses_hosted(app, celery_app):
    with celery_app.app_context():
        inst, _ = setup_paid_instance(74, free=False)
        inst.status = "suspended"
        owner = User.query.filter_by(email="ent74@t.test").first()
        prompt = PromptConfig(
            title="P",
            prompt_body="b",
            interval_minutes=60,
            model_name="openai/gpt-4o-mini",
            provider="openai",
            is_active=True,
            created_by_id=owner.id,
            instance_id=inst.id,
        )
        db.session.add(prompt)
        db.session.flush()
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        db.session.add(InstanceAIConfig(instance_id=inst.id, provider="openai"))
        db.session.flush()
        InstanceAIConfig.query.filter_by(
            instance_id=inst.id, provider="openai"
        ).first().api_key = "sk-test"
        db.session.commit()

        from app.tasks.ollama_tasks import generate_idea

        with patch("litellm.completion") as mock_call:
            generate_idea(str(prompt.id), run_id=str(run.id), instance_id=str(inst.id))
            mock_call.assert_not_called()
        db.session.expire_all()
        assert db.session.get(PromptRun, run.id).status == PromptRunStatus.FAILED
