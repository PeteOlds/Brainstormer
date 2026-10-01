"""Phase 9: edit-own, role matrix, instance date enforcement."""

from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import (
    Instance,
    Membership,
    PromptConfig,
    User,
    UserRole,
    can_edit_idea,
    has_permission,
    role_permissions,
)


def make_instance(number, name=None, **attrs):
    inst = Instance(number=number, name=name or f"R{number}", **attrs)
    db.session.add(inst)
    db.session.flush()
    return inst


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


def make_idea(instance, author, ref="IDEA-R1", prompt=None, status="SPARK"):
    from app.models import Idea

    idea = Idea(
        reference_code=ref,
        prompt_title="T",
        raw_content="c",
        prompt_config_id=prompt.id if prompt else None,
        instance_id=instance.id if instance else None,
        created_by_id=author.id if author else None,
        status=status,
    )
    db.session.add(idea)
    db.session.flush()
    return idea


def test_role_matrix_unit():
    assert "run_actions" not in role_permissions("USER")
    assert "run_actions" in role_permissions("DEVELOPER")
    assert "edit_docs" in role_permissions("BA")
    assert "flag_comments" in role_permissions("BA")
    assert "change_status" in role_permissions("DEPLOYMENT")
    assert "manage_members" in role_permissions("INSTANCE_ADMIN")
    assert "manage_billing" in role_permissions("SITE_ADMIN")
    from app.models import ASSIGNABLE_ROLES

    assert "SITE_ADMIN" not in ASSIGNABLE_ROLES
    assert set(ASSIGNABLE_ROLES) >= {
        "USER",
        "DEVELOPER",
        "BA",
        "DEPLOYMENT",
        "INSTANCE_ADMIN",
    }


def test_edit_own_idea(app, client):
    with app.app_context():
        from app.models import Idea

        inst = make_instance(100, "Own")
        author = make_user("author@t.test")
        stranger = make_user("stranger@t.test")
        grant(author, inst, "USER")
        grant(stranger, inst, "USER")
        make_idea(inst, author, ref="IDEA-R1")
        make_idea(inst, None, ref="IDEA-R2")  # generated: no author
        db.session.commit()
        iid = str(Idea.query.filter_by(reference_code="IDEA-R1").first().id)
        gid = str(Idea.query.filter_by(reference_code="IDEA-R2").first().id)
        aid = str(inst.id)
    author_h = login(client, "author@t.test", aid)
    stranger_h = login(client, "stranger@t.test", aid)

    res = client.patch(
        f"/api/v1/ideas/{iid}", json={"prompt_title": "Mine now"}, headers=author_h
    )
    assert res.status_code == 200, res.get_json()
    res = client.patch(
        f"/api/v1/ideas/{iid}", json={"prompt_title": "Hijack"}, headers=stranger_h
    )
    assert res.status_code == 403
    res = client.patch(
        f"/api/v1/ideas/{gid}", json={"prompt_title": "Hijack"}, headers=author_h
    )
    assert res.status_code == 403

    res = client.post(
        f"/api/v1/ideas/{gid}/chat/iterate",
        json={"content": {"prompt_title": "x"}},
        headers=author_h,
    )
    assert res.status_code == 403
    res = client.post(
        f"/api/v1/ideas/{iid}/chat/iterate",
        json={"content": {"prompt_title": "Iterated"}},
        headers=author_h,
    )
    assert res.status_code == 200, res.get_json()
    with app.app_context():
        assert Idea.query.get(iid).prompt_title == "Iterated"


def test_role_gates(app, client):
    from app.models import ActionType, SecondaryActionResult

    with app.app_context():
        inst = make_instance(101, "Roles")
        dev = make_user("dev@t.test")
        ba = make_user("ba@t.test")
        depl = make_user("depl@t.test")
        plain = make_user("plain2@t.test")
        grant(dev, inst, "DEVELOPER")
        grant(ba, inst, "BA")
        grant(depl, inst, "DEPLOYMENT")
        grant(plain, inst, "USER")
        idea = make_idea(inst, plain, ref="IDEA-R3", status="SCOPE")
        db.session.add(
            SecondaryActionResult(
                idea_id=idea.id,
                action_type=ActionType.PRD_DOC,
                model_used="m",
                result_data={},
            )
        )
        db.session.commit()
        iid, aid = str(idea.id), str(inst.id)
        result_id = str(SecondaryActionResult.query.first().id)
    dev_h = login(client, "dev@t.test", aid)
    ba_h = login(client, "ba@t.test", aid)
    depl_h = login(client, "depl@t.test", aid)
    plain_h = login(client, "plain2@t.test", aid)

    job = MagicMock()
    job.id = "job-roles"
    with patch("app.tasks.ollama_tasks.run_secondary_action") as mock_task:
        mock_task.delay.return_value = job
        assert (
            client.post(
                f"/api/v1/ideas/{iid}/actions",
                json={"action_type": "REFINE", "confirm": True},
                headers=dev_h,
            ).status_code
            == 202
        )
        assert (
            client.post(
                f"/api/v1/ideas/{iid}/actions",
                json={"action_type": "REFINE", "confirm": True},
                headers=plain_h,
            ).status_code
            == 403
        )

    res = client.get("/api/v1/discovery", headers=dev_h)
    assert res.status_code == 200
    assert client.get("/api/v1/discovery", headers=plain_h).status_code == 403

    res = client.patch(
        f"/api/v1/actions/{result_id}",
        json={
            "result_data": {
                "summary": "s",
                "problem": "p",
                "goals": ["g"],
                "scope": "s",
                "requirements": ["r"],
                "open_questions": [],
                "success_metrics": ["m"],
            }
        },
        headers=ba_h,
    )
    assert res.status_code in (200, 400)

    res = client.patch(
        f"/api/v1/ideas/{iid}/status", json={"status": "MAP"}, headers=depl_h
    )
    assert res.status_code == 200, res.get_json()
    res = client.patch(
        f"/api/v1/ideas/{iid}/status", json={"status": "SHIP"}, headers=plain_h
    )
    assert res.status_code == 403

    res = client.patch(f"/api/v1/comments/{iid}/flag", json={}, headers=ba_h)
    assert res.status_code in (400, 404)


def test_member_role_assignment(app, client):
    with app.app_context():
        from app.services import instances as instance_svc

        inst = make_instance(102, "Assign")
        admin = make_user("assign-admin@t.test", UserRole.ADMIN)
        member = make_user("assign-member@t.test")
        grant(admin, inst, "INSTANCE_ADMIN")
        grant(member, inst, "USER")
        db.session.commit()
        iid, mid = str(inst.id), str(member.id)
    admin_h = login(client, "assign-admin@t.test", iid)

    for role in ("DEVELOPER", "BA", "DEPLOYMENT"):
        res = client.patch(
            f"/api/v1/instances/{iid}/members/{mid}",
            json={"role": role},
            headers=admin_h,
        )
        assert res.status_code == 200, (role, res.get_json())
    for bad in ("BOSS", "SITE_ADMIN"):
        res = client.patch(
            f"/api/v1/instances/{iid}/members/{mid}",
            json={"role": bad},
            headers=admin_h,
        )
        assert res.status_code == 400


def test_expired_instance_blocks_writes_not_reads(app, client):
    from datetime import datetime, timedelta, timezone

    with app.app_context():
        inst = make_instance(
            103, "Expired", end_date=datetime.now(timezone.utc) - timedelta(days=1)
        )
        user = make_user("exp@t.test")
        grant(user, inst, "USER")
        make_idea(inst, user, ref="IDEA-R4")
        db.session.commit()
        iid = str(inst.id)
    headers = login(client, "exp@t.test", iid)

    res = client.get("/api/v1/ideas", headers=headers)
    assert res.status_code == 200
    res = client.post(
        "/api/v1/ideas", json={"prompt_title": "t", "raw_content": "c"}, headers=headers
    )
    assert res.status_code == 403
    assert res.get_json().get("error_code") == "INSTANCE_INACTIVE"


def test_scheduler_skips_expired(app, celery_app):
    from datetime import datetime, timedelta, timezone

    from app.models import PromptConfig, PromptRun, UserRole
    from app.tasks import ollama_tasks as tasks

    with celery_app.app_context():
        admin = User(email="sched@t.test", role=UserRole.ADMIN)
        admin.set_password("password123")
        db.session.add(admin)
        db.session.flush()
        live = make_instance(104, "Live")
        dead = make_instance(
            105, "Dead", end_date=datetime.now(timezone.utc) - timedelta(days=1)
        )
        for inst in (live, dead):
            grant(admin, inst, "INSTANCE_ADMIN")
            db.session.add(
                PromptConfig(
                    title=f"P{inst.number}",
                    prompt_body="b",
                    interval_minutes=60,
                    model_name="m",
                    is_active=True,
                    next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                    created_by_id=admin.id,
                    instance_id=inst.id,
                )
            )
        db.session.commit()

        with patch.object(tasks.generate_idea, "delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="job-1")
            tasks.check_due_prompts()
        called = {c.args[0] for c in mock_delay.call_args_list}
        live_prompt = PromptConfig.query.filter_by(title="P104").first()
        dead_prompt = PromptConfig.query.filter_by(title="P105").first()
        assert str(live_prompt.id) in called
        assert str(dead_prompt.id) not in called
        assert PromptRun.query.filter_by(prompt_config_id=dead_prompt.id).count() == 0


def test_can_edit_idea_unit(app):
    from flask import g

    from app.models import Idea

    with app.app_context():
        inst = make_instance(106, "Unit")
        author = make_user("unitauthor@t.test")
        other = make_user("unitother@t.test")
        grant(author, inst, "USER")
        grant(other, inst, "USER")
        admin = make_user("unitadmin@t.test", UserRole.ADMIN)
        grant(admin, inst, "INSTANCE_ADMIN")
        idea = make_idea(inst, author, ref="IDEA-R5")
        db.session.commit()

        g.instance_id = inst.id
        try:
            assert can_edit_idea(admin, idea) is True
            assert can_edit_idea(author, idea) is True
            assert can_edit_idea(other, idea) is False
            assert has_permission(author, "vote", inst.id) is True
            assert has_permission(other, "run_actions", inst.id) is False
            assert has_permission(author, "change_status", None) is False
        finally:
            g.pop("instance_id", None)
