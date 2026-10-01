"""Phase 10: DLP masking, queue/degrade cutoffs, proxy embeddings, pricing."""

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
from app.services.dlp import mask_text
from app.services.llm_backends import (
    BudgetExhausted,
    _proxy_cost_cents,
    refresh_pricing_cache,
)

VALID_REFINE = json.dumps(
    {
        "elevator_pitch": "AI-powered inventory management for small retailers",
        "target_audience": "Small retail businesses",
        "core_value_proposition": "Automated stock optimization",
        "monetization_strategy": "SaaS subscription",
    }
)


def setup_paid(number, email, cutoff="refuse", budget=10, degrade_model=None):
    inst = Instance(number=number, name=f"P10 {number}", is_free=False)
    db.session.add(inst)
    db.session.flush()
    admin = User(email=email, role=UserRole.ADMIN)
    admin.set_password("password123")
    db.session.add(admin)
    db.session.flush()
    db.session.add(
        Membership(user_id=admin.id, instance_id=inst.id, role="INSTANCE_ADMIN")
    )
    db.session.add(
        InstanceAIConfig(
            instance_id=inst.id,
            provider="openai",
            budget_cents=budget,
            cutoff_behaviour=cutoff,
            degrade_model=degrade_model,
        )
    )
    db.session.flush()
    InstanceAIConfig.query.filter_by(
        instance_id=inst.id, provider="openai"
    ).first().api_key = "sk-test"
    db.session.commit()
    return inst


def hosted_prompt(instance_id, admin_id):
    prompt = PromptConfig(
        title="P",
        prompt_body="Generate {{topic}}",
        interval_minutes=60,
        model_name="openai/gpt-4o-mini",
        provider="openai",
        is_active=True,
        created_by_id=admin_id,
        instance_id=instance_id,
    )
    db.session.add(prompt)
    db.session.flush()
    return prompt


def test_dlp_masks_pii():
    text = "Contact jane.doe@example.com or +64 21 123 4567, key sk-abcdefgh12345678"
    masked, counts = mask_text(text)
    assert "jane.doe@example.com" not in masked
    assert "+64 21 123 4567" not in masked
    assert "sk-abcdefgh12345678" not in masked
    assert counts == {"email": 1, "phone": 1, "api_key": 1}
    assert mask_text("")[0] == ""


def test_hosted_generation_masks_pii_in_flight(app, celery_app):
    from app.models import Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = setup_paid(110, "dlp@t.test")
        admin = User.query.filter_by(email="dlp@t.test").first()
        prompt = PromptConfig(
            title="P",
            prompt_body="Write about jane.doe@example.com",
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

        fake = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=VALID_REFINE))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )
        with (
            patch("litellm.completion", return_value=fake) as mock_call,
            patch("litellm.completion_cost", return_value=0.01),
            patch("app.services.embedding_service.get_embedding_service") as mock_emb,
            patch("app.services.slack_service.post_idea"),
        ):
            mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
            mock_emb.return_value.find_similar_to_embedding.return_value = []
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))

        sent = mock_call.call_args.kwargs
        dumped = json.dumps(sent["messages"])
        assert "jane.doe@example.com" not in dumped
        assert "[redacted:email]" in dumped
        db.session.expire_all()
        assert db.session.get(PromptRun, rid).status == PromptRunStatus.SUCCESS


def test_queue_cutoff_retries_instead_of_failing(app, celery_app):
    from app.models import AISpendLedger, Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = setup_paid(111, "queue@t.test", cutoff="queue")
        admin = User.query.filter_by(email="queue@t.test").first()
        prompt = hosted_prompt(inst.id, admin.id)
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
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        pid, rid, iid = prompt.id, run.id, inst.id

        with patch("litellm.completion") as mock_call:
            # Direct calls re-raise the original error (a live worker
            # converts self.retry() into a scheduled Retry); assert the
            # queue branch was taken: retry_after set, run NOT failed.
            from app.services.llm_backends import BudgetExhausted

            try:
                generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))
            except BudgetExhausted as exc:
                assert exc.retry_after == 3600
            else:
                raise AssertionError("expected BudgetExhausted with retry_after")
            mock_call.assert_not_called()
        db.session.expire_all()
        assert db.session.get(PromptRun, rid).status != PromptRunStatus.FAILED
        assert Idea.query.count() == 0


def test_degrade_falls_back_to_local(app, celery_app):
    from app.models import Idea
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        inst = setup_paid(
            112, "degrade@t.test", cutoff="degrade", degrade_model="llama3:8b"
        )
        admin = User.query.filter_by(email="degrade@t.test").first()
        prompt = hosted_prompt(inst.id, admin.id)
        db.session.add(prompt)
        from app.models import AISpendLedger

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
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        pid, rid, iid = prompt.id, run.id, inst.id

        with (
            patch("app.services.ollama_client.OllamaClient") as mock_class,
            patch("litellm.completion") as mock_hosted,
            patch("app.services.embedding_service.get_embedding_service") as mock_emb,
            patch("app.services.slack_service.post_idea"),
        ):
            mock_client = MagicMock()
            mock_class.return_value = mock_client
            mock_client.generate_sync.return_value = {
                "response": VALID_REFINE,
                "done": True,
            }
            mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
            mock_emb.return_value.find_similar_to_embedding.return_value = []
            generate_idea(str(pid), run_id=str(rid), instance_id=str(iid))

        mock_hosted.assert_not_called()
        assert mock_client.generate_sync.call_args.kwargs["model"] == "llama3:8b"
        db.session.expire_all()
        assert db.session.get(PromptRun, rid).status == PromptRunStatus.SUCCESS
        assert Idea.query.filter_by(prompt_config_id=pid).count() == 1


def test_proxy_embeddings_use_virtual_key(app):
    from app.services import llm_backends as backends

    with app.app_context():
        inst = setup_paid(113, "pemb@t.test")
        InstanceAIConfig.query.filter_by(
            instance_id=inst.id, provider="openai"
        ).first().embedding_model = "text-embedding-3-small"
        db.session.commit()
        iid = str(inst.id)

    # Direct mode first (no proxy flag): uses the library path.
    with app.app_context():
        with patch("litellm.embedding") as mock_emb:
            mock_emb.return_value.data = [{"embedding": [0.5, 0.5]}]
            vec = backends.embed_for_instance("hi", uuid.UUID(iid))
            assert vec == [0.5, 0.5]

    with app.app_context():
        row = InstanceAIConfig.query.filter_by(
            instance_id=uuid.UUID(iid), provider="openai"
        ).first()
        row.virtual_key = "sk-proxy-emb"
        row.use_proxy = True
        db.session.commit()

        response = MagicMock()
        response.json.return_value = {
            "data": [{"embedding": [0.7, 0.7]}],
            "usage": {"prompt_tokens": 2},
        }
        client = MagicMock()
        client.__enter__.return_value = client
        client.post.return_value = response
        with patch("app.services.llm_backends.httpx.Client", return_value=client):
            vec = backends.embed_for_instance("hi", uuid.UUID(iid))
        assert vec == [0.7, 0.7]
        _, kwargs = client.post.call_args
        assert kwargs["headers"] == {"Authorization": "Bearer sk-proxy-emb"}
        assert kwargs["json"]["model"] == "text-embedding-3-small"


def test_pricing_override_file(tmp_path, monkeypatch):
    override = {
        "openai/gpt-4o-mini": {
            "input_cost_per_token": 0.001,
            "output_cost_per_token": 0.002,
        }
    }
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(override))
    monkeypatch.setenv("PRICING_OVERRIDE_PATH", str(path))
    assert refresh_pricing_cache() == override
    assert _cost("openai/gpt-4o-mini", 1000, 1000) == 300
    monkeypatch.delenv("PRICING_OVERRIDE_PATH")
    refresh_pricing_cache()


def _cost(model, pt, ct):
    from app.services.llm_backends import _proxy_cost_cents

    return _proxy_cost_cents(model, pt, ct)


def test_chat_budget_reports_retry_after(app, admin_client):
    with app.app_context():
        from app.models import Idea

        inst = setup_paid(114, "chatq@t.test", cutoff="queue")
        idea = Idea(
            reference_code="IDEA-Q1",
            prompt_title="T",
            raw_content="c",
            instance_id=inst.id,
        )
        db.session.add(idea)
        db.session.flush()
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
        # Force the hosted path: stage route with a provider model.
        from app.models import PromptConfig, User

        admin = User.query.filter_by(email="chatq@t.test").first()
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
        idea.prompt_config_id = prompt.id
        db.session.commit()
        iid = str(idea.id)

    with app.app_context():
        from app.models import Idea as _Idea
        from app.models import InstanceAIConfig as _AIC

        fresh = _Idea.query.get(uuid.UUID(iid))
        _AIC.query.filter_by(instance_id=fresh.instance_id).update(
            {"chat_enabled": True}
        )
        db.session.commit()

    with patch(
        "app.services.chat.generate_for_prompt",
        side_effect=BudgetExhausted("spent", retry_after=3600),
    ):
        res = admin_client.post(f"/api/v1/ideas/{iid}/chat", json={"message": "hi"})
    assert res.status_code == 429
    assert res.get_json()["details"]["retry_after_seconds"] == 3600
