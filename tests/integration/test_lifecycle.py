"""Phase 2: V2 lifecycle matrix, per-phase comments, Ignore flag, gates."""

from unittest.mock import MagicMock
from unittest.mock import patch as _patch

from app.extensions import db
from app.models import Comment, Idea, IdeaStatusHistory, PromptConfig, User
from app.models.enums import IdeaStatus
from app.models.lifecycle import allowed_from, can_transition


def make_idea(status="SPARK", ref="IDEA-L1"):
    from app.models import User as UserModel

    admin = UserModel.query.filter_by(email="admin@test.com").first()
    prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
    idea = Idea(
        reference_code=ref,
        prompt_title="T",
        raw_content="c",
        status=status,
        prompt_config_id=prompt.id,
    )
    db.session.add(idea)
    db.session.commit()
    return idea.id


def test_transition_matrix_unit():
    assert can_transition(IdeaStatus.SPARK, IdeaStatus.SCOPE)
    assert can_transition(IdeaStatus.SPARK, IdeaStatus.MAP)
    assert not can_transition(IdeaStatus.SPARK, IdeaStatus.SHIP)
    assert not can_transition(IdeaStatus.SPARK, IdeaStatus.ARCHIVE)
    assert can_transition(IdeaStatus.SHIP, IdeaStatus.SCALE)
    assert can_transition(IdeaStatus.DROP, IdeaStatus.SCALE)
    assert not can_transition(IdeaStatus.ARCHIVE, IdeaStatus.SPARK)
    assert can_transition(IdeaStatus.SCOPE, IdeaStatus.SCOPE)
    assert allowed_from(IdeaStatus.ARCHIVE) == []


def test_illegal_transition_rejected_with_history(
    admin_client, app, admin_user, admin_prompt
):
    with app.app_context():
        idea_id = make_idea("SPARK")

    resp = admin_client.patch(
        f"/api/v1/ideas/{idea_id}/status", json={"status": "ARCHIVE"}
    )
    assert resp.status_code == 400
    assert resp.get_json()["message"].startswith("Illegal transition SPARK -> ARCHIVE")

    resp = admin_client.patch(
        f"/api/v1/ideas/{idea_id}/status", json={"status": "SCOPE"}
    )
    assert resp.status_code == 200
    with app.app_context():
        rows = IdeaStatusHistory.query.filter_by(idea_id=idea_id).all()
        assert [(r.old_status.value, r.new_status.value) for r in rows] == [
            ("SPARK", "SCOPE")
        ]


def test_bulk_skips_illegal_moves(admin_client, app, admin_user, admin_prompt):
    with app.app_context():
        make_idea("SPARK", ref="IDEA-LB1")
        make_idea("SPARK", ref="IDEA-LB2")
        ids = [
            str(i.id)
            for i in Idea.query.filter(
                Idea.reference_code.in_(["IDEA-LB1", "IDEA-LB2"])
            ).all()
        ]

    resp = admin_client.patch(
        "/api/v1/ideas/bulk-status", json={"idea_ids": ids, "status": "SHIP"}
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["updated_count"] == 0
    assert data["skipped_illegal"] == 2


def test_comment_phase_recorded_and_filterable(
    client, auth_user, app, admin_user, admin_prompt, admin_client
):
    _email, token = auth_user
    headers = {"Authorization": f"Bearer {token}"}
    with app.app_context():
        idea_id = make_idea("SPARK", ref="IDEA-LC1")

    res = client.post(
        f"/api/v1/ideas/{idea_id}/comments",
        json={"body": "spark thought"},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.get_json()["data"]["comment"]["phase"] == "SPARK"
    assert "is_ignored" not in res.get_json()["data"]["comment"]

    admin_client.patch(f"/api/v1/ideas/{idea_id}/status", json={"status": "SCOPE"})
    res = client.post(
        f"/api/v1/ideas/{idea_id}/comments",
        json={"body": "scope thought"},
        headers=headers,
    )
    assert res.get_json()["data"]["comment"]["phase"] == "SCOPE"

    res = client.get(f"/api/v1/ideas/{idea_id}/comments?phase=SCOPE", headers=headers)
    bodies = [c["body"] for c in res.get_json()["data"]["comments"]]
    assert bodies == ["scope thought"]

    res = client.get(f"/api/v1/ideas/{idea_id}/comments?phase=BOGUS", headers=headers)
    assert res.status_code == 400


def test_ignore_flag_admin_only_with_audit_and_context_exclusion(
    client, auth_user, app, admin_user, admin_prompt, admin_client
):
    _email, token = auth_user
    headers = {"Authorization": f"Bearer {token}"}
    with app.app_context():
        idea_id = make_idea("SPARK", ref="IDEA-LF1")

    kept = client.post(
        f"/api/v1/ideas/{idea_id}/comments", json={"body": "keep me"}, headers=headers
    )
    dropped = client.post(
        f"/api/v1/ideas/{idea_id}/comments", json={"body": "ignore me"}, headers=headers
    )
    dropped_id = dropped.get_json()["data"]["comment"]["id"]

    # Normal users cannot flag.
    res = client.patch(
        f"/api/v1/comments/{dropped_id}/flag",
        json={"is_ignored": True},
        headers=headers,
    )
    assert res.status_code == 403

    res = admin_client.patch(
        f"/api/v1/comments/{dropped_id}/flag", json={"is_ignored": "yes"}
    )
    assert res.status_code == 400

    res = admin_client.patch(
        f"/api/v1/comments/{dropped_id}/flag", json={"is_ignored": True}
    )
    assert res.status_code == 200
    assert res.get_json()["data"]["comment"]["is_ignored"] is True

    with app.app_context():
        from app.models import IdeaEdit

        audits = IdeaEdit.query.filter_by(idea_id=idea_id).all()
        assert any(
            a.field == f"comment:{dropped_id}:is_ignored" and a.new_value == "True"
            for a in audits
        )

        from app.services.action_context import build_idea_context

        idea = Idea.query.get(idea_id)
        context = build_idea_context(idea)
        assert "keep me" in context
        assert "ignore me" not in context

    # Admins see the flag; users do not.
    admin_list = admin_client.get(f"/api/v1/ideas/{idea_id}/comments").get_json()[
        "data"
    ]["comments"]
    assert {c["body"]: c.get("is_ignored") for c in admin_list} == {
        "keep me": False,
        "ignore me": True,
    }
    user_list = client.get(
        f"/api/v1/ideas/{idea_id}/comments", headers=headers
    ).get_json()["data"]["comments"]
    assert all("is_ignored" not in c for c in user_list)


def test_action_stage_gates(admin_client, app, admin_user, admin_prompt):
    from app.models import ActionType, SecondaryActionResult

    with app.app_context():
        spark_id = make_idea("SPARK", ref="IDEA-LG1")
        drop_id = make_idea("DROP", ref="IDEA-LG2")
        scope_id = make_idea("SCOPE", ref="IDEA-LG3")
        map_id = make_idea("MAP", ref="IDEA-LG4")
        db.session.add(
            SecondaryActionResult(
                idea_id=map_id,
                action_type=ActionType.PRD_DOC,
                model_used="m",
                result_data={},
            )
        )
        db.session.commit()

    # Dropped ideas run nothing.
    resp = admin_client.post(
        f"/api/v1/ideas/{drop_id}/actions",
        json={"action_type": "REFINE", "confirm": True},
    )
    assert resp.status_code == 400

    # Spark runs everything except PRD.
    resp = admin_client.post(
        f"/api/v1/ideas/{spark_id}/actions",
        json={"action_type": "PRD_DOC", "confirm": True},
    )
    assert resp.status_code == 400
    resp = admin_client.post(
        f"/api/v1/ideas/{spark_id}/actions",
        json={"action_type": "DESIGN_DOC", "confirm": True},
    )
    assert resp.status_code == 400

    job = MagicMock()
    job.id = "job-lifecycle"
    with _patch("app.tasks.ollama_tasks.run_secondary_action") as mock_task:
        mock_task.delay.return_value = job
        resp = admin_client.post(
            f"/api/v1/ideas/{spark_id}/actions",
            json={"action_type": "REFINE", "confirm": True},
        )
        assert resp.status_code == 202
        resp = admin_client.post(
            f"/api/v1/ideas/{scope_id}/actions",
            json={"action_type": "PRD_DOC", "confirm": True},
        )
        assert resp.status_code == 202
        resp = admin_client.post(
            f"/api/v1/ideas/{map_id}/actions",
            json={"action_type": "DESIGN_DOC", "confirm": True},
        )
        assert resp.status_code == 202


def test_active_only_hides_drop_and_archive(
    client, auth_user, app, admin_user, admin_prompt
):
    _email, token = auth_user
    headers = {"Authorization": f"Bearer {token}"}
    with app.app_context():
        make_idea("SPARK", ref="IDEA-LA1")
        make_idea("DROP", ref="IDEA-LA2")
        make_idea("ARCHIVE", ref="IDEA-LA3")
        make_idea("FREEZE", ref="IDEA-LA4")

    res = client.get("/api/v1/ideas?status=ACTIVE_ONLY", headers=headers)
    refs = {i["reference_code"] for i in res.get_json()["data"]["ideas"]}
    assert {"IDEA-LA1", "IDEA-LA4"} <= refs
    assert "IDEA-LA2" not in refs and "IDEA-LA3" not in refs
