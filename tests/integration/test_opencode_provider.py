"""OpenCode provider: registration, routing, gates, workspace flag."""

import json
import uuid
from unittest.mock import patch

import pytest

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

VALID_IDEA = json.dumps(
    {
        "elevator_pitch": "AI-powered inventory management for small retailers",
        "target_audience": "Small retail businesses",
        "core_value_proposition": "Automated stock optimization",
        "monetization_strategy": "SaaS subscription",
    }
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


def test_opencode_provider_accepted_in_prompt(admin_client):
    res = admin_client.post(
        "/api/v1/prompts",
        json={
            "title": "OC",
            "prompt_body": "b",
            "interval_minutes": 60,
            "model_name": "opencode/big-pickle",
            "provider": "opencode",
        },
    )
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["data"]["provider"] == "opencode"


def test_opencode_prompt_create_rejects_non_allowlisted_model(app, client):
    """Prompt create with an opencode model outside the allowlist → 400."""
    from app.models import ROLE_INSTANCE_ADMIN

    with app.app_context():
        inst = make_instance(74, "OC-AL")
        admin = make_user("oc-al-reject@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        db.session.add(
            InstanceAIConfig(
                instance_id=inst.id,
                provider="opencode",
                model_allowlist=["opencode/big-pickle"],
            )
        )
        db.session.commit()
        db.session.expunge_all()
    with app.app_context():
        iid = str(Instance.query.filter_by(number=74).first().id)
    headers = login(client, "oc-al-reject@t.test", iid)

    res = client.post(
        "/api/v1/prompts",
        json={
            "title": "OC",
            "prompt_body": "b",
            "interval_minutes": 60,
            "model_name": "opencode/some-unlisted-model",
            "provider": "opencode",
        },
        headers=headers,
    )
    assert res.status_code == 400, res.get_json()

    res = client.post(
        "/api/v1/prompts",
        json={
            "title": "OC",
            "prompt_body": "b",
            "interval_minutes": 60,
            "model_name": "opencode/big-pickle",
            "provider": "opencode",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.get_json()
    pid = res.get_json()["data"]["id"]

    # PATCH provider to an unknown value is rejected.
    res = client.patch(
        f"/api/v1/prompts/{pid}",
        json={"provider": "bogus"},
        headers=headers,
    )
    assert res.status_code == 400, res.get_json()


def test_opencode_allowlist_enforced_when_scoped(app, client):
    from app.models import ROLE_INSTANCE_ADMIN

    with app.app_context():
        inst = make_instance(70, "OC-A")
        admin = make_user("oc-allow@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        db.session.add(
            InstanceAIConfig(
                instance_id=inst.id,
                provider="opencode",
                model_allowlist=["opencode/big-pickle"],
            )
        )
        db.session.commit()
        db.session.expunge_all()
    with app.app_context():
        iid = str(Instance.query.filter_by(number=70).first().id)
    headers = login(client, "oc-allow@t.test", iid)

    base = {"title": "T", "prompt_body": "b", "interval_minutes": 60}
    res = client.post(
        "/api/v1/prompts",
        json={**base, "model_name": "opencode/claude-sonnet-4", "provider": "opencode"},
        headers=headers,
    )
    assert res.status_code == 400
    res = client.post(
        "/api/v1/prompts",
        json={**base, "model_name": "opencode/big-pickle", "provider": "opencode"},
        headers=headers,
    )
    assert res.status_code == 201, res.get_json()


def test_opencode_workspace_flag_site_admin_only(app, client):
    from app.models import ROLE_INSTANCE_ADMIN, ROLE_SITE_ADMIN

    with app.app_context():
        inst = make_instance(71, "OC-WS")
        admin = make_user("oc-ws-admin@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        site = make_user("oc-ws-site@t.test")
        db.session.add(
            Membership(user_id=site.id, instance_id=None, role=ROLE_SITE_ADMIN)
        )
        db.session.commit()
        iid = str(inst.id)

    # Instance admin cannot change it...
    h_admin = login(client, "oc-ws-admin@t.test", iid)
    res = client.put(
        f"/api/v1/instances/{iid}/ai-configs",
        json={"provider": "opencode", "opencode_workspace": "repo"},
        headers=h_admin,
    )
    assert res.status_code == 403

    # ...but can read the default.
    res = client.get(f"/api/v1/instances/{iid}/ai-configs", headers=h_admin)
    assert res.status_code == 200
    assert res.get_json()["data"]["configs"] == []

    # Site admin can.
    h_site = login(client, "oc-ws-site@t.test", iid)
    res = client.put(
        f"/api/v1/instances/{iid}/ai-configs",
        json={"provider": "opencode", "opencode_workspace": "repo"},
        headers=h_site,
    )
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["data"]["config"]["opencode_workspace"] == "repo"

    # Invalid value rejected.
    res = client.put(
        f"/api/v1/instances/{iid}/ai-configs",
        json={"provider": "opencode", "opencode_workspace": "bogus"},
        headers=h_site,
    )
    assert res.status_code == 400

    # Re-stating the current value is a no-op anyone may do (edit forms
    # always submit the field; otherwise instance admins could never save
    # an opencode config at all).
    res = client.put(
        f"/api/v1/instances/{iid}/ai-configs",
        json={
            "provider": "opencode",
            "opencode_workspace": "repo",
            "model_allowlist": ["opencode/big-pickle"],
        },
        headers=h_admin,
    )
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["data"]["config"]["model_allowlist"] == [
        "opencode/big-pickle"
    ]


def test_run_now_routes_opencode_to_dedicated_queue(admin_client, app, admin_user):
    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig(
            title="OC Queue",
            prompt_body="b",
            interval_minutes=60,
            model_name="opencode/big-pickle",
            provider="opencode",
            is_active=True,
            created_by_id=admin.id,
        )
        db.session.add(prompt)
        db.session.commit()
        pid = prompt.id

    with patch("app.tasks.ollama_tasks.generate_idea") as mock_gen:
        mock_gen.apply_async.return_value.id = "job-oc"
        res = admin_client.post(f"/api/v1/prompts/{pid}/run-now")
        assert res.status_code == 202, res.get_json()
        mock_gen.apply_async.assert_called_once()
        _, kwargs = mock_gen.apply_async.call_args
        assert kwargs["queue"] == "opencode"
        assert kwargs["time_limit"] >= kwargs["soft_time_limit"]
        mock_gen.delay.assert_not_called()


def test_run_now_keeps_ollama_on_delay(admin_client, app, admin_user):
    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        prompt = PromptConfig(
            title="Ollama Queue",
            prompt_body="b",
            interval_minutes=60,
            model_name="llama3:8b",
            provider="ollama",
            is_active=True,
            created_by_id=admin.id,
        )
        db.session.add(prompt)
        db.session.commit()
        pid = prompt.id

    with patch("app.tasks.ollama_tasks.generate_idea") as mock_gen:
        mock_gen.delay.return_value.id = "job-ollama"
        res = admin_client.post(f"/api/v1/prompts/{pid}/run-now")
        assert res.status_code == 202, res.get_json()
        mock_gen.delay.assert_called_once()
        mock_gen.apply_async.assert_not_called()


def test_opencode_requires_hosted_ai_entitlement(app):
    from types import SimpleNamespace

    from app.services.llm_backends import ProviderError, generate_for_prompt

    with app.app_context():
        inst = make_instance(72, "OC-Free", free=True)
        db.session.commit()
        prompt = SimpleNamespace(
            provider="opencode",
            model_name="opencode/big-pickle",
            instance_id=inst.id,
        )
        with pytest.raises(ProviderError) as exc:
            generate_for_prompt(prompt, "hi")
        assert exc.value.retryable is False
        assert "entitled" in str(exc.value)


def test_opencode_generation_records_spend(celery_app):
    from app.services.llm_backends import GenerationResult
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = make_instance(73, "OC-Run")
        admin = make_user("oc-run@t.test", UserRole.ADMIN)
        grant(admin, inst, "INSTANCE_ADMIN")
        db.session.add(InstanceAIConfig(instance_id=inst.id, provider="opencode"))
        prompt = PromptConfig(
            title="OC Run",
            prompt_body="Generate {{topic}}",
            interval_minutes=60,
            model_name="opencode/big-pickle",
            provider="opencode",
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
                "app.services.opencode_backend.opencode_generate",
                return_value=GenerationResult(
                    text=VALID_IDEA,
                    model="opencode/big-pickle",
                    prompt_tokens=11,
                    completion_tokens=22,
                    cost_cents=3,
                ),
            ) as mock_oc,
            patch("app.services.embedding_service.get_embedding_service") as mock_emb,
            patch("app.services.slack_service.post_idea"),
        ):
            mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
            mock_emb.return_value.find_similar_to_embedding.return_value = []
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))

        assert mock_oc.called

        db.session.expire_all()
        assert db.session.get(PromptRun, rid).status == PromptRunStatus.SUCCESS
        rows = AISpendLedger.query.filter_by(instance_id=iid).all()
        assert len(rows) == 1
        assert (
            rows[0].prompt_tokens,
            rows[0].completion_tokens,
            rows[0].cost_cents,
        ) == (11, 22, 3)


def _seed_ollama_idea(db, email="oc-override-seed@t.test"):
    from app.models import Idea, PromptConfig, User, UserRole

    admin = User(email=email, role=UserRole.ADMIN)
    admin.set_password("password123")
    db.session.add(admin)
    db.session.flush()
    prompt = PromptConfig(
        title="O",
        prompt_body="b",
        interval_minutes=60,
        model_name="llama3:8b",
        provider="ollama",
        is_active=True,
        created_by_id=admin.id,
    )
    db.session.add(prompt)
    db.session.flush()
    idea = Idea(
        reference_code="IDEA-OC1",
        prompt_title="T",
        raw_content="content",
        status="SPARK",
        prompt_config_id=prompt.id,
    )
    db.session.add(idea)
    db.session.commit()
    return idea


def test_action_provider_override_routes_opencode(app, client):
    from app.models import ROLE_INSTANCE_ADMIN

    with app.app_context():
        inst = make_instance(75, "OC-OR")
        admin = make_user("oc-override@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        db.session.add(
            InstanceAIConfig(
                instance_id=inst.id,
                provider="opencode",
                model_allowlist=["opencode/big-pickle"],
            )
        )
        idea = _seed_ollama_idea(db)
        iid, idea_id = inst.id, idea.id
        db.session.expunge_all()
    headers = login(client, "oc-override@t.test", str(iid))

    with patch("app.tasks.enqueue_generation") as mock_enq:
        mock_enq.return_value.id = "job-override"
        res = client.post(
            f"/api/v1/ideas/{idea_id}/actions",
            json={
                "action_type": "REFINE",
                "confirm": True,
                "model_override": "opencode/big-pickle",
                "provider_override": "opencode",
            },
            headers=headers,
        )
    assert res.status_code == 202, res.get_json()
    args, _ = mock_enq.call_args
    assert args[3] == "opencode"
    assert args[2]["provider_override"] == "opencode"


def test_action_provider_override_validation(app, client):
    with app.app_context():
        idea = _seed_ollama_idea(db, email="oc-ov2@t.test")
        idea_id = idea.id
        db.session.expunge_all()

    # Unknown provider rejected.
    with patch("app.tasks.enqueue_generation"):
        res = client.post(
            f"/api/v1/ideas/{idea_id}/actions",
            json={
                "action_type": "REFINE",
                "confirm": True,
                "provider_override": "bogus",
            },
            headers=login(client, "oc-ov2@t.test"),
        )
    assert res.status_code == 400

    # Provider without a model for that engine rejected.
    with patch("app.tasks.enqueue_generation"):
        res = client.post(
            f"/api/v1/ideas/{idea_id}/actions",
            json={
                "action_type": "REFINE",
                "confirm": True,
                "provider_override": "opencode",
            },
            headers=login(client, "oc-ov2@t.test"),
        )
    assert res.status_code == 400


def test_models_endpoint_unrestricted_flag(app, client):
    from app.models import ROLE_INSTANCE_ADMIN

    with app.app_context():
        inst = make_instance(76, "OC-UN")
        admin = make_user("oc-un@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        db.session.commit()
        iid = inst.id
        db.session.expunge_all()
    headers = login(client, "oc-un@t.test", str(iid))

    # No config at all: empty list, unrestricted.
    res = client.get("/api/v1/ollama/models?provider=opencode", headers=headers)
    assert res.status_code == 200
    body = res.get_json()["data"]
    assert body["models"] == []
    assert body["unrestricted"] is True

    with app.app_context():
        db.session.add(
            InstanceAIConfig(
                instance_id=iid,
                provider="opencode",
                model_allowlist=["opencode/big-pickle"],
            )
        )
        db.session.commit()
    res = client.get("/api/v1/ollama/models?provider=opencode", headers=headers)
    body = res.get_json()["data"]
    assert body["models"] == ["opencode/big-pickle"]
    assert body["unrestricted"] is False


def test_models_endpoint_serves_server_catalog_when_unrestricted(app, client):
    from app.models import ROLE_INSTANCE_ADMIN

    with app.app_context():
        inst = make_instance(77, "OC-CAT")
        admin = make_user("oc-cat@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        db.session.commit()
        iid = inst.id
        db.session.expunge_all()
    headers = login(client, "oc-cat@t.test", str(iid))

    with patch(
        "app.services.opencode_backend.list_server_models",
        return_value=["opencode/aaa-model", "opencode/big-pickle"],
    ) as mock_list:
        res = client.get("/api/v1/ollama/models?provider=opencode", headers=headers)
    assert res.status_code == 200
    body = res.get_json()["data"]
    assert body["models"] == ["opencode/aaa-model", "opencode/big-pickle"]
    assert body["unrestricted"] is True
    mock_list.assert_called_once()


def test_models_endpoint_allowlist_wins_over_catalog(app, client):
    from app.models import ROLE_INSTANCE_ADMIN

    with app.app_context():
        inst = make_instance(78, "OC-CAT2")
        admin = make_user("oc-cat2@t.test")
        grant(admin, inst, ROLE_INSTANCE_ADMIN)
        db.session.add(
            InstanceAIConfig(
                instance_id=inst.id,
                provider="opencode",
                model_allowlist=["opencode/big-pickle"],
            )
        )
        db.session.commit()
        iid = inst.id
        db.session.expunge_all()
    headers = login(client, "oc-cat2@t.test", str(iid))

    with patch(
        "app.services.opencode_backend.list_server_models",
        side_effect=AssertionError("allowlist must win; no server call"),
    ):
        res = client.get("/api/v1/ollama/models?provider=opencode", headers=headers)
    body = res.get_json()["data"]
    assert body["models"] == ["opencode/big-pickle"]
    assert body["unrestricted"] is False
