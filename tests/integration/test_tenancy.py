"""Phase 1: instances, memberships, scoping, copy-on-create, CLI."""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models import (
    ROLE_INSTANCE_ADMIN,
    ROLE_USER,
    Comment,
    Idea,
    Instance,
    Membership,
    PromptConfig,
    User,
    UserRole,
    Vote,
)


def make_user(email, role=UserRole.USER):
    user = User(email=email, role=role)
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    return user


def make_instance(number, name=None):
    from app.services import instances as instance_svc

    instance = Instance(number=number, name=name or f"Instance {number}")
    db.session.add(instance)
    db.session.flush()
    return instance


def grant(user, instance, role):
    db.session.add(Membership(user_id=user.id, instance_id=instance.id, role=role))
    db.session.flush()


def make_idea(instance, ref="IDEA-0001", prompt=None):
    idea = Idea(
        reference_code=ref,
        prompt_title="T",
        raw_content="content",
        structured_content={"elevator_pitch": "x"},
        prompt_config_id=prompt.id if prompt else None,
        instance_id=instance.id if instance else None,
    )
    db.session.add(idea)
    db.session.flush()
    return idea


def login(client, email, instance_id=None):
    body = {"email": email, "password": "password123"}
    if instance_id:
        body["instance_id"] = str(instance_id)
    res = client.post("/api/v1/login", json=body)
    assert res.status_code in (200, 403), res.get_json()
    if res.status_code == 200:
        token = res.get_json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return None


def test_reserved_and_duplicate_numbers_rejected(app):
    from app.services import instances as instance_svc

    with app.app_context():
        with pytest.raises(instance_svc.InstanceError):
            instance_svc.create_instance(7, "Reserved")
        ok = instance_svc.create_instance(20, "Twenty")
        assert ok.number == 20
        with pytest.raises(instance_svc.InstanceError):
            instance_svc.create_instance(20, "Twenty again")


def test_init_site_data_backfills_and_grants(app):
    from app.services import instances as instance_svc

    with app.app_context():
        admin = make_user("seed-admin@t.test", UserRole.ADMIN)
        user = make_user("seed-user@t.test")
        prompt = PromptConfig(
            title="Seed",
            prompt_body="body",
            interval_minutes=60,
            model_name="m",
            created_by_id=admin.id,
        )
        db.session.add(prompt)
        db.session.flush()
        make_idea(None, ref="IDEA-0001", prompt=prompt)
        db.session.commit()

        report = instance_svc.init_site_data()
        prod = Instance.query.filter_by(number=5).first()
        assert prod is not None
        assert str(prod.id) == report["production_id"]
        assert Idea.query.filter_by(instance_id=None).count() == 0
        assert PromptConfig.query.filter_by(instance_id=None).count() == 0
        assert Membership.get_role(admin.id, prod.id) == ROLE_INSTANCE_ADMIN
        assert Membership.get_role(user.id, prod.id) == ROLE_USER

        again = instance_svc.init_site_data()
        assert again["memberships"] == 0
        assert sum(again["backfilled"].values()) == 0


def test_scoped_list_and_cross_instance_404(app, client):
    with app.app_context():
        a = make_instance(20, "A")
        b = make_instance(21, "B")
        user = make_user("iso@t.test")
        grant(user, a, ROLE_USER)
        grant(user, b, ROLE_USER)
        make_idea(a, ref="IDEA-0001")
        idea_b = make_idea(b, ref="IDEA-0002")
        db.session.commit()
        aid, bid, iid_b = str(a.id), str(idea_b.id), str(b.id)

    ha = login(client, "iso@t.test", aid)
    hb = login(client, "iso@t.test", iid_b)
    assert ha and hb

    only_a = client.get("/api/v1/ideas", headers=ha).get_json()["data"]["ideas"]
    assert {i["reference_code"] for i in only_a} == {"IDEA-0001"}

    # Cross-instance access hides, never leaks.
    assert client.get(f"/api/v1/ideas/{bid}", headers=ha).status_code == 404
    assert (
        client.post(
            f"/api/v1/ideas/{bid}/vote", json={"direction": 1}, headers=ha
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/ideas/{bid}/comments", json={"body": "hi"}, headers=ha
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/ideas/{bid}", headers=hb).status_code == 200

    # Legacy unscoped tokens keep seeing everything.
    legacy = login(client, "iso@t.test")
    both = client.get("/api/v1/ideas", headers=legacy).get_json()["data"]["ideas"]
    assert {i["reference_code"] for i in both} == {"IDEA-0001", "IDEA-0002"}


def test_non_member_claim_rejected(app, client):
    with app.app_context():
        a = make_instance(20, "A")
        make_user("outsider@t.test")
        db.session.commit()
        aid = str(a.id)
    assert login(client, "outsider@t.test", aid) is None
    res = client.post(
        "/api/v1/login",
        json={
            "email": "outsider@t.test",
            "password": "password123",
            "instance_id": aid,
        },
    )
    assert res.status_code == 403


def test_instance_admin_membership_unlocks_admin_routes(app, client):
    with app.app_context():
        a = make_instance(20, "A")
        user = make_user("iadmin@t.test")  # V1 role stays USER
        grant(user, a, ROLE_INSTANCE_ADMIN)
        idea = make_idea(a, ref="IDEA-0001")
        db.session.commit()
        aid, iid = str(a.id), str(idea.id)

    scoped = login(client, "iadmin@t.test", aid)
    res = client.patch(
        f"/api/v1/ideas/{iid}/status", json={"status": "SCOPE"}, headers=scoped
    )
    assert res.status_code == 200, res.get_json()

    unscoped = login(client, "iadmin@t.test")
    res = client.patch(
        f"/api/v1/ideas/{iid}/status", json={"status": "FREEZE"}, headers=unscoped
    )
    assert res.status_code == 403


def test_instance_api_site_admin_only(app, client):
    from app.services import instances as instance_svc

    with app.app_context():
        make_instance(1, "Template")
        site = make_user("site@t.test")
        plain = make_user("plain@t.test")
        grant(plain, make_instance(20, "Home"), ROLE_USER)
        instance_svc.grant_site_admin(site.id)
        db.session.commit()

    site_h = login(client, "site@t.test")
    plain_h = login(client, "plain@t.test")

    mine = client.get("/api/v1/instances", headers=plain_h).get_json()["data"][
        "instances"
    ]
    assert [i["number"] for i in mine] == [20]
    all_inst = client.get("/api/v1/instances", headers=site_h).get_json()["data"][
        "instances"
    ]
    assert {i["number"] for i in all_inst} >= {1, 20}

    assert (
        client.post(
            "/api/v1/instances", json={"number": 22, "name": "N"}, headers=plain_h
        ).status_code
        == 403
    )
    res = client.post(
        "/api/v1/instances", json={"number": 7, "name": "Reserved"}, headers=site_h
    )
    assert res.status_code == 409
    res = client.post(
        "/api/v1/instances", json={"number": 22, "name": "New"}, headers=site_h
    )
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["data"]["instance"]["number"] == 22

    with app.app_context():
        other_id = str(Instance.query.filter_by(number=22).first().id)
    assert (
        client.get(f"/api/v1/instances/{other_id}", headers=plain_h).status_code == 404
    )
    assert (
        client.get(f"/api/v1/instances/{other_id}", headers=site_h).status_code == 200
    )


def test_copy_on_create_copies_config_not_content(app):
    from app.services import instances as instance_svc

    with app.app_context():
        template = Instance(number=1, name="Template")
        db.session.add(template)
        db.session.flush()
        admin = make_user("copy@t.test", UserRole.ADMIN)
        db.session.add(
            PromptConfig(
                title="P1",
                prompt_body="secret body",
                interval_minutes=60,
                model_name="m",
                slack_channel="#nope",
                is_active=True,
                created_by_id=admin.id,
                instance_id=template.id,
            )
        )
        db.session.add(
            PromptConfig(
                title="P2",
                prompt_body="paused",
                interval_minutes=60,
                model_name="m",
                is_active=False,
                created_by_id=admin.id,
                instance_id=template.id,
            )
        )
        from app.models import SystemSettings

        db.session.add(
            SystemSettings(
                instance_id=template.id,
                platform={"title": "T"},
                location={"country": "NZ"},
                ai_connections={},
            )
        )
        make_idea(template, ref="IDEA-0001")
        db.session.commit()

        new = instance_svc.create_instance(30, "Child")
        copies = PromptConfig.query.filter_by(instance_id=new.id).all()
        assert {p.title for p in copies} == {"P1", "P2"}
        assert copies[0].prompt_body in ("secret body", "paused")
        assert all(p.slack_channel is None for p in copies)
        assert Idea.query.filter_by(instance_id=new.id).count() == 0
        assert Vote.query.filter_by(instance_id=new.id).count() == 0
        settings = SystemSettings.query.filter_by(instance_id=new.id).first()
        assert settings is not None and settings.platform == {"title": "T"}


def test_tenancy_cli(app):
    runner = app.test_cli_runner()
    with app.app_context():
        make_user("cli-admin@t.test", UserRole.ADMIN)
        make_idea(None, ref="IDEA-0001")
        db.session.commit()

    result = runner.invoke(args=["init-tenancy"])
    assert result.exit_code == 0, result.output
    assert "Site 5" in result.output

    result = runner.invoke(args=["promote-site-admin", "cli-admin@t.test"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(args=["create-instance", "--number", "25", "--name", "Cli"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert Instance.query.filter_by(number=25).first() is not None
        assert Membership.is_site_admin(
            User.query.filter_by(email="cli-admin@t.test").first().id
        )


def test_task_instance_mismatch_and_stamping(app, celery_app):
    from app.models import PromptRun, PromptRunStatus
    from app.tasks.ollama_tasks import generate_idea

    with celery_app.app_context():
        a = make_instance(20, "A")
        admin = make_user("task@t.test", UserRole.ADMIN)
        prompt = PromptConfig(
            title="P",
            prompt_body="Generate {{topic}}",
            interval_minutes=60,
            model_name="llama3:8b",
            is_active=True,
            created_by_id=admin.id,
            instance_id=a.id,
        )
        db.session.add(prompt)
        db.session.flush()
        run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()
        pid, rid = prompt.id, run.id

        # Wrong instance: run fails fast, nothing created.
        with patch("app.tasks.ollama_tasks.OllamaClient"):
            generate_idea(str(pid), run_id=str(rid), instance_id=str(uuid.uuid4()))
        db.session.expire_all()
        assert db.session.get(PromptRun, rid).status == PromptRunStatus.FAILED
        assert Idea.query.count() == 0

        # Right instance: idea and run inherit it.
        mock_client = MagicMock()
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
        run2 = PromptRun(prompt_config_id=pid, triggered_by="manual")
        db.session.add(run2)
        db.session.commit()
        with (
            patch("app.tasks.ollama_tasks.OllamaClient", return_value=mock_client),
            patch("app.services.embedding_service.get_embedding_service") as mock_emb,
            patch("app.services.slack_service.post_idea"),
        ):
            mock_emb.return_value.generate_embedding_sync.return_value = [0.0] * 8
            mock_emb.return_value.find_similar_to_embedding.return_value = []
            generate_idea(str(pid), run_id=str(run2.id), instance_id=str(a.id))
        db.session.expire_all()
        idea = Idea.query.first()
        assert idea is not None and idea.instance_id == a.id
        assert db.session.get(PromptRun, run2.id).instance_id == a.id


def test_rls_migration_guards_policies():
    import pathlib

    migration = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "migrations"
        / "versions"
        / "e0f1a2b3c4d5_rls_policies.py"
    ).read_text()
    for table in ("ideas", "prompt_configs", "votes", "comments"):
        assert f'"{table}"' in migration or table in migration
    assert "CREATE POLICY" in migration and "_tenant_isolation" in migration
    assert "app.instance_id" in migration
