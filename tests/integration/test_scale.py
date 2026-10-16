"""Scale-phase collaboration: child ideas + releases + moderation."""

from app.extensions import db
from app.models import Comment, Idea


def _idea(ref, status="SPARK", **kw):
    idea = Idea(
        reference_code=ref,
        prompt_title="T",
        raw_content="c",
        status=status,
        **kw,
    )
    db.session.add(idea)
    db.session.commit()
    return idea


def _user_token(client, email="scale-user@example.com"):
    res = client.post(
        "/api/v1/register",
        json={"email": email, "password": "password123"},
    )
    assert res.status_code in (200, 201), res.get_json()
    return res.get_json()["data"]["access_token"]


class TestChildIdeas:
    def test_create_child_on_scale(self, client, app):
        token = _user_token(client)
        with app.app_context():
            parent = _idea("IDEA-SC1", status="SCALE")
            pid = str(parent.id)
        res = client.post(
            "/api/v1/ideas",
            json={
                "prompt_title": "Fix login",
                "raw_content": "login breaks on retry",
                "parent_id": pid,
                "child_kind": "bugfix",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 201, res.get_json()
        data = res.get_json()["data"]
        assert data["parent_id"] == pid
        assert data["child_kind"] == "bugfix"
        assert data["status"] == "SPARK"

    def test_create_child_rejects_non_scale(self, client, app):
        token = _user_token(client, "scale-u2@example.com")
        with app.app_context():
            parent = _idea("IDEA-SC2", status="SHIP")
            pid = str(parent.id)
        res = client.post(
            "/api/v1/ideas",
            json={
                "prompt_title": "x",
                "raw_content": "y",
                "parent_id": pid,
                "child_kind": "enhancement",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400
        assert "Scale" in res.get_json()["message"]

    def test_create_child_requires_kind(self, client, app):
        token = _user_token(client, "scale-u3@example.com")
        with app.app_context():
            parent = _idea("IDEA-SC3", status="SCALE")
            pid = str(parent.id)
        res = client.post(
            "/api/v1/ideas",
            json={"prompt_title": "x", "raw_content": "y", "parent_id": pid},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400

    def test_create_child_rejects_bad_kind(self, client, app):
        token = _user_token(client, "scale-u4@example.com")
        with app.app_context():
            parent = _idea("IDEA-SC4", status="SCALE")
            pid = str(parent.id)
        res = client.post(
            "/api/v1/ideas",
            json={
                "prompt_title": "x",
                "raw_content": "y",
                "parent_id": pid,
                "child_kind": "feature",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400

    def test_child_cannot_nest(self, client, app):
        token = _user_token(client, "scale-u5@example.com")
        with app.app_context():
            parent = _idea("IDEA-SC5", status="SCALE")
            child = _idea(
                "IDEA-SC6",
                status="SPARK",
                parent_id=parent.id,
                child_kind="bugfix",
            )
            cid = str(child.id)
        res = client.post(
            "/api/v1/ideas",
            json={
                "prompt_title": "x",
                "raw_content": "y",
                "parent_id": cid,
                "child_kind": "bugfix",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400

    def test_list_children_filters(self, client, app):
        token = _user_token(client, "scale-u6@example.com")
        with app.app_context():
            parent = _idea("IDEA-SC7", status="SCALE")
            _idea("IDEA-SC8", parent_id=parent.id, child_kind="bugfix")
            _idea("IDEA-SC9", parent_id=parent.id, child_kind="enhancement")
            pid = str(parent.id)
        h = {"Authorization": f"Bearer {token}"}
        res = client.get(f"/api/v1/ideas/{pid}/children", headers=h)
        assert res.status_code == 200
        assert res.get_json()["data"]["total"] == 2
        res = client.get(f"/api/v1/ideas/{pid}/children?kind=bugfix", headers=h)
        assert res.get_json()["data"]["total"] == 1

    def test_scale_status_endpoint(self, client, app):
        from app.models import PromptRun

        token = _user_token(client, "scale-u10@example.com")
        with app.app_context():
            parent = _idea("IDEA-SS1", status="SCALE")
            k1 = _idea(
                "IDEA-SS2", status="SPARK", parent_id=parent.id, child_kind="bugfix"
            )
            k2 = _idea(
                "IDEA-SS3",
                status="SPARK",
                parent_id=parent.id,
                child_kind="enhancement",
            )
            from datetime import datetime, timedelta, timezone

            t0 = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.session.add(
                PromptRun(
                    idea_id=k1.id,
                    action_type="BUILD_CODE",
                    status="SUCCESS",
                    job_id="j1",
                    created_at=t0,
                )
            )
            db.session.add(
                PromptRun(
                    idea_id=k1.id,
                    action_type="BUILD_CODE",
                    status="FAILED",
                    job_id="j0",
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.session.add(
                PromptRun(
                    idea_id=k2.id,
                    action_type="BUILD_CODE",
                    status="SUCCESS",
                    job_id="j2",
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.session.commit()
            pid = str(parent.id)
            k1_id, k2_id = str(k1.id), str(k2.id)
        res = client.get(
            f"/api/v1/ideas/{pid}/scale-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        builds = res.get_json()["data"]["builds"]
        assert builds[k1_id]["status"] == "FAILED"  # latest wins
        assert builds[k1_id]["error"] is None or builds[k1_id]["error"]
        assert builds[k2_id]["status"] == "SUCCESS"
        # Children list carries the same state.
        res = client.get(
            f"/api/v1/ideas/{pid}/children?limit=100",
            headers={"Authorization": f"Bearer {token}"},
        )
        rows = {r["reference_code"]: r for r in res.get_json()["data"]["ideas"]}
        assert rows["IDEA-SS2"]["build_status"]["status"] == "FAILED"
        assert rows["IDEA-SS3"]["build_status"]["status"] == "SUCCESS"

    def test_list_names_child_parents(self, client, app):
        token = _user_token(client, "scale-u9@example.com")
        with app.app_context():
            parent = _idea("IDEA-SC20", status="SCALE")
            parent.prompt_title = "Main app"
            _idea("IDEA-SC21", parent_id=parent.id, child_kind="bugfix")
            _idea("IDEA-SC22")
        h = {"Authorization": f"Bearer {token}"}
        res = client.get("/api/v1/ideas?limit=100", headers=h)
        assert res.status_code == 200
        rows = {r["reference_code"]: r for r in res.get_json()["data"]["ideas"]}
        child = rows["IDEA-SC21"]
        assert child["parent_id"] is not None
        assert child["parent_reference_code"] == "IDEA-SC20"
        assert child["parent_title"] == "Main app"
        assert "parent_reference_code" not in rows["IDEA-SC22"]

    def test_get_idea_embeds_family(self, client, app):
        token = _user_token(client, "scale-u7@example.com")
        with app.app_context():
            parent = _idea("IDEA-SC10", status="SCALE")
            child = _idea(
                "IDEA-SC11",
                parent_id=parent.id,
                child_kind="enhancement",
            )
            pid, cid = str(parent.id), str(child.id)
        h = {"Authorization": f"Bearer {token}"}
        res = client.get(f"/api/v1/ideas/{cid}", headers=h)
        assert res.get_json()["data"]["parent"]["reference_code"] == "IDEA-SC10"
        res = client.get(f"/api/v1/ideas/{pid}", headers=h)
        assert res.get_json()["data"]["child_count"] == 1


class TestReleases:
    def test_crud_assign_complete(self, admin_client, app):
        with app.app_context():
            parent = _idea("IDEA-RL1", status="SCALE")
            c1 = _idea("IDEA-RL2", parent_id=parent.id, child_kind="bugfix")
            c2 = _idea("IDEA-RL3", parent_id=parent.id, child_kind="enhancement")
            pid = str(parent.id)
            ids = [str(c1.id), str(c2.id)]
        res = admin_client.post(
            f"/api/v1/ideas/{pid}/releases", json={"name": "Release 1.1"}
        )
        assert res.status_code == 201, res.get_json()
        rid = res.get_json()["data"]["release"]["id"]

        res = admin_client.patch(
            f"/api/v1/releases/{rid}/assign", json={"idea_ids": ids}
        )
        assert res.get_json()["data"]["moved"] == 2

        # Children start at SPARK; SHIP needs an intermediate step
        # (SPARK → SCOPE → SHIP). Move them to SCOPE first, as an admin
        # would while working the release.
        for cid in ids:
            r = admin_client.patch(
                f"/api/v1/ideas/{cid}/status", json={"status": "SCOPE"}
            )
            assert r.status_code == 200, r.get_json()

        res = admin_client.get(f"/api/v1/ideas/{pid}/children?release_id={rid}")
        assert res.get_json()["data"]["total"] == 2

        res = admin_client.post(
            f"/api/v1/releases/{rid}/complete", json={"status": "SHIP"}
        )
        body = res.get_json()["data"]
        assert body["updated_count"] == 2
        assert body["status"] == "SHIP"

        with app.app_context():
            from app.models import Release

            assert Release.query.get(rid).status == "done"
            assert {
                i.status.value
                for i in Idea.query.filter(
                    Idea.reference_code.in_(["IDEA-RL2", "IDEA-RL3"])
                ).all()
            } == {"SHIP"}

    def test_delete_blocked_when_nonempty(self, admin_client, app):
        with app.app_context():
            parent = _idea("IDEA-RL4", status="SCALE")
            _idea("IDEA-RL5", parent_id=parent.id, child_kind="bugfix")
            pid = str(parent.id)
        rid = admin_client.post(
            f"/api/v1/ideas/{pid}/releases", json={"name": "R"}
        ).get_json()["data"]["release"]["id"]
        with app.app_context():
            child = Idea.query.filter_by(reference_code="IDEA-RL5").one()
            cid = str(child.id)
        admin_client.patch(f"/api/v1/releases/{rid}/assign", json={"idea_ids": [cid]})
        res = admin_client.delete(f"/api/v1/releases/{rid}")
        assert res.status_code == 400
        res = admin_client.patch(
            f"/api/v1/releases/{rid}/unassign", json={"idea_ids": [cid]}
        )
        assert res.get_json()["data"]["moved"] == 1
        res = admin_client.delete(f"/api/v1/releases/{rid}")
        assert res.status_code == 200

    def test_complete_rejects_bad_target(
        self, admin_client, app, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("RELEASE_NOTES_DIR", str(tmp_path / "rn"))
        with app.app_context():
            parent = _idea("IDEA-RL6", status="SCALE")
            pid = str(parent.id)
        rid = admin_client.post(
            f"/api/v1/ideas/{pid}/releases", json={"name": "R"}
        ).get_json()["data"]["release"]["id"]
        res = admin_client.post(
            f"/api/v1/releases/{rid}/complete", json={"status": "MAP"}
        )
        assert res.status_code == 400

    def test_releases_listed_latest_first(self, admin_client, app):
        with app.app_context():
            parent = _idea("IDEA-RL12", status="SCALE")
            pid = str(parent.id)
        for name in ("R1", "R2", "R3"):
            admin_client.post(f"/api/v1/ideas/{pid}/releases", json={"name": name})
        res = admin_client.get(f"/api/v1/ideas/{pid}/releases")
        names = [r["name"] for r in res.get_json()["data"]["releases"]]
        assert names[:3] == ["R3", "R2", "R1"]
        assert names[3] == "No release yet"

    def test_complete_stamps_completed_at(self, admin_client, app):
        from datetime import datetime, timezone

        with app.app_context():
            parent = _idea("IDEA-RL13", status="SCALE")
            c1 = _idea(
                "IDEA-RL14",
                status="SCOPE",
                parent_id=parent.id,
                child_kind="enhancement",
            )
            c1.prompt_title = "Add export"
            db.session.commit()
            pid = str(parent.id)
            cid = str(c1.id)
        rid = admin_client.post(
            f"/api/v1/ideas/{pid}/releases", json={"name": "Release 3.0"}
        ).get_json()["data"]["release"]["id"]
        admin_client.patch(f"/api/v1/releases/{rid}/assign", json={"idea_ids": [cid]})
        admin_client.patch(f"/api/v1/ideas/{cid}/status", json={"status": "SHIP"})
        body = admin_client.post(
            f"/api/v1/releases/{rid}/complete", json={"status": "SHIP"}
        ).get_json()["data"]
        assert body["release"]["completed_at"] is not None
        expected = datetime.now(timezone.utc).strftime("%d-%b-%y")
        assert f"Finished {expected}: 1 shipped" in body["release"]["notes"]

    def test_notes_written_to_docs(self, admin_client, app, tmp_path, monkeypatch):
        monkeypatch.setenv("RELEASE_NOTES_DIR", str(tmp_path / "rn"))
        with app.app_context():
            parent = _idea("IDEA-RL10", status="SCALE")
            parent.prompt_title = "Main app"
            c1 = _idea(
                "IDEA-RL11",
                status="SCOPE",
                parent_id=parent.id,
                child_kind="bugfix",
            )
            c1.prompt_title = "Fix crash"
            db.session.commit()
            pid = str(parent.id)
            cid = str(c1.id)
        rid = admin_client.post(
            f"/api/v1/ideas/{pid}/releases", json={"name": "Release 1.1"}
        ).get_json()["data"]["release"]["id"]
        admin_client.patch(f"/api/v1/releases/{rid}/assign", json={"idea_ids": [cid]})
        admin_client.patch(f"/api/v1/ideas/{cid}/status", json={"status": "SHIP"})
        admin_client.post(f"/api/v1/releases/{rid}/complete", json={"status": "SHIP"})
        out = tmp_path / "rn" / "idea-rl10-release-1-1.md"
        assert out.exists()
        text = out.read_text()
        assert text.startswith("# Release 1.1")
        assert "Fix crash (IDEA-RL11)" in text
        # Hand-edit syncs the file too.
        admin_client.patch(f"/api/v1/releases/{rid}", json={"notes": "Hand edit."})
        assert out.read_text() == "# Release 1.1\n\nHand edit.\n"

    def test_complete_writes_notes(self, admin_client, app):
        with app.app_context():
            parent = _idea("IDEA-RL7", status="SCALE")
            parent.prompt_title = "Main app"
            c1 = _idea(
                "IDEA-RL8",
                status="SCOPE",
                parent_id=parent.id,
                child_kind="enhancement",
            )
            c1.prompt_title = "Add export"
            c2 = _idea(
                "IDEA-RL9",
                status="SCOPE",
                parent_id=parent.id,
                child_kind="bugfix",
            )
            c2.prompt_title = "Fix crash"
            pid = str(parent.id)
            ids = [str(c1.id), str(c2.id)]
            db.session.commit()
        rid = admin_client.post(
            f"/api/v1/ideas/{pid}/releases", json={"name": "Release 2.0"}
        ).get_json()["data"]["release"]["id"]
        admin_client.patch(f"/api/v1/releases/{rid}/assign", json={"idea_ids": ids})
        for cid in ids:
            admin_client.patch(f"/api/v1/ideas/{cid}/status", json={"status": "SHIP"})
        body = admin_client.post(
            f"/api/v1/releases/{rid}/complete", json={"status": "SHIP"}
        ).get_json()["data"]
        notes = body["release"]["notes"]
        assert "Release 2.0" in notes
        assert "2 shipped, 0 rejected" in notes
        assert "Add export (IDEA-RL8)" in notes
        assert "Fix crash (IDEA-RL9)" in notes
        # Regenerate + hand-edit round-trip.
        again = admin_client.post(f"/api/v1/releases/{rid}/notes").get_json()["data"][
            "release"
        ]["notes"]
        assert again == notes
        edited = admin_client.patch(
            f"/api/v1/releases/{rid}", json={"notes": "Hand-written."}
        ).get_json()["data"]["release"]["notes"]
        assert edited == "Hand-written."


class TestBulkRunAction:
    def _release_with(self, admin_client, app, tag, statuses=("SCOPE", "SPARK")):
        with app.app_context():
            parent = _idea(f"IDEA-B{tag}A", status="SCALE")
            kids = [
                _idea(
                    f"IDEA-B{tag}{i}",
                    status=st,
                    parent_id=parent.id,
                    child_kind="enhancement",
                )
                for i, st in enumerate(statuses)
            ]
            pid = str(parent.id)
            ids = [str(k.id) for k in kids]
        rid = admin_client.post(
            f"/api/v1/ideas/{pid}/releases", json={"name": "R"}
        ).get_json()["data"]["release"]["id"]
        admin_client.patch(f"/api/v1/releases/{rid}/assign", json={"idea_ids": ids})
        return rid, ids

    def test_bulk_prd_starts_and_skips(self, admin_client, app):
        from unittest.mock import patch as _patch

        rid, ids = self._release_with(admin_client, app, "1")
        with _patch("app.tasks.ollama_tasks.run_secondary_action") as mock_run:
            mock_run.delay.return_value.id = "job-1"
            res = admin_client.post(
                f"/api/v1/releases/{rid}/run-action",
                json={"action_type": "PRD_DOC"},
            )
        assert res.status_code == 202, res.get_json()
        body = res.get_json()["data"]
        assert len(body["started"]) == 1  # SCOPE child only
        assert len(body["skipped"]) == 1  # SPARK child: stage reason
        assert "Scope" in body["skipped"][0]["reason"]
        assert mock_run.delay.call_count == 1

    def test_bulk_prd_skips_existing(self, admin_client, app):
        from unittest.mock import patch as _patch

        from app.models import ActionType, SecondaryActionResult

        rid, ids = self._release_with(admin_client, app, "2", ("SCOPE", "SCOPE"))
        with app.app_context():
            from app.models import Idea as _Idea

            kid = _Idea.query.filter_by(reference_code="IDEA-B20").one()
            db.session.add(
                SecondaryActionResult(
                    idea_id=kid.id,
                    action_type=ActionType.PRD_DOC,
                    model_used="m",
                    provider_used="ollama",
                    result_data={"summary": "x" * 30},
                    version=1,
                    is_current=True,
                )
            )
            db.session.commit()
        with _patch("app.tasks.ollama_tasks.run_secondary_action") as mock_run:
            mock_run.delay.return_value.id = "job-2"
            res = admin_client.post(
                f"/api/v1/releases/{rid}/run-action",
                json={"action_type": "PRD_DOC"},
            )
        body = res.get_json()["data"]
        assert len(body["started"]) == 1
        assert "Already has one" in body["skipped"][0]["reason"]

    def test_bulk_build_uses_parent_repo(self, admin_client, app):
        from unittest.mock import patch as _patch

        from app.models import (
            ActionType,
            InstanceBuildTarget,
            SecondaryActionResult,
        )

        rid, ids = self._release_with(admin_client, app, "3", ("SHIP",))
        with app.app_context():
            from app.models import Idea as _Idea
            from app.models import Instance

            inst = Instance(number=9993, name="Scale build")
            db.session.add(inst)
            db.session.flush()
            parent = _Idea.query.filter_by(reference_code="IDEA-B3A").one()
            kid = _Idea.query.filter_by(reference_code="IDEA-B30").one()
            parent.instance_id = inst.id
            kid.instance_id = inst.id
            target = InstanceBuildTarget(
                instance_id=inst.id, name="repo", path="/tmp/repo"
            )
            db.session.add(target)
            db.session.commit()
            tid = target.id
            for owner, atype in (
                (parent, ActionType.BUILD_CODE),
                (kid, ActionType.DESIGN_DOC),
            ):
                db.session.add(
                    SecondaryActionResult(
                        idea_id=owner.id,
                        action_type=atype,
                        model_used="m",
                        provider_used="ollama",
                        result_data=(
                            {"summary": "x" * 30, "written": True}
                            if atype == ActionType.BUILD_CODE
                            else {"summary": "x" * 30}
                        ),
                        version=1,
                        is_current=True,
                        target_id=tid if atype == ActionType.BUILD_CODE else None,
                        target_name="repo" if atype == ActionType.BUILD_CODE else None,
                    )
                )
            db.session.commit()
        # No target_id given: the child's build must pick the parent's repo.
        with _patch("app.tasks.ollama_tasks.run_secondary_action") as mock_run:
            mock_run.delay.return_value.id = "job-3"
            res = admin_client.post(
                f"/api/v1/releases/{rid}/run-action",
                json={"action_type": "BUILD_CODE"},
            )
        assert res.status_code == 202, res.get_json()
        body = res.get_json()["data"]
        # Started (not skipped for "needs a target_id") proves the parent
        # repo was picked automatically.
        assert body["started"] == ["IDEA-B30"]
        assert body["skipped"] == []

    def test_bulk_build_confirm_needs_preview(self, admin_client, app):
        rid, ids = self._release_with(admin_client, app, "4", ("SHIP",))
        with app.app_context():
            from app.models import Idea as _Idea
            from app.models import Instance

            inst = Instance(number=9994, name="Scale confirm")
            db.session.add(inst)
            db.session.flush()
            kid = _Idea.query.filter_by(reference_code="IDEA-B40").one()
            kid.instance_id = inst.id
            from app.models import ActionType, SecondaryActionResult

            db.session.add(
                SecondaryActionResult(
                    idea_id=kid.id,
                    action_type=ActionType.DESIGN_DOC,
                    model_used="m",
                    provider_used="ollama",
                    result_data={"summary": "x" * 30},
                    version=1,
                    is_current=True,
                )
            )
            from app.models import InstanceBuildTarget

            db.session.add(
                InstanceBuildTarget(instance_id=inst.id, name="repo", path="/tmp/repo")
            )
            db.session.commit()
        res = admin_client.post(
            f"/api/v1/releases/{rid}/run-action",
            json={"action_type": "BUILD_CODE", "confirm_build": True},
        )
        body = res.get_json()["data"]
        assert body["started"] == []
        assert "preview" in body["skipped"][0]["reason"].lower()


class TestModerationAndContext:
    def test_ignored_hidden_from_users(self, client, app, admin_client):
        token = _user_token(client, "scale-u8@example.com")
        with app.app_context():
            user = Idea.query.first()  # ensure tables exist
            parent = _idea("IDEA-MD1", status="SCALE")
            from app.models import User

            author = User.query.filter_by(email="scale-u8@example.com").one()
            c = Comment(
                idea_id=parent.id,
                user_id=author.id,
                body="spam",
                scope="idea",
            )
            db.session.add(c)
            db.session.commit()
            cid, pid = str(c.id), str(parent.id)
        admin_client.patch(f"/api/v1/comments/{cid}/flag", json={"is_ignored": True})
        h = {"Authorization": f"Bearer {token}"}
        res = client.get(f"/api/v1/ideas/{pid}/comments", headers=h)
        bodies = [x["body"] for x in res.get_json()["data"]["comments"]]
        assert "spam" not in bodies
        res = admin_client.get(f"/api/v1/ideas/{pid}/comments")
        found = [x for x in res.get_json()["data"]["comments"] if x["body"] == "spam"]
        assert found and found[0]["is_ignored"] is True

    def test_parent_context_included(self, app):
        with app.app_context():
            from app.models import User

            parent = _idea("IDEA-MD2", status="SCALE")
            parent.prompt_title = "Main app"
            parent.raw_content = "does things"
            author = User(email="ctx@example.com")
            author.set_password("password123")
            db.session.add(author)
            db.session.commit()
            db.session.add(
                Comment(
                    idea_id=parent.id,
                    user_id=author.id,
                    body="please fix export",
                    scope="idea",
                )
            )
            child = _idea(
                "IDEA-MD3",
                parent_id=parent.id,
                child_kind="bugfix",
            )
            db.session.commit()
            from app.services.action_context import (
                build_idea_context,
                parent_context,
            )

            ctx = parent_context(child)
            assert "IDEA-MD2" in ctx
            assert "please fix export" in ctx
            full = build_idea_context(child)
            assert "Parent request" in full
            assert parent_context(parent) == ""
