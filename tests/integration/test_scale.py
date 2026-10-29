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


class TestReleaseAIConfig:
    def _release(self, admin_client, app, tag):
        with app.app_context():
            parent = _idea(f"IDEA-AI{tag}A", status="SCALE")
            pid = str(parent.id)
        rid = admin_client.post(
            f"/api/v1/ideas/{pid}/releases", json={"name": "R"}
        ).get_json()["data"]["release"]["id"]
        return rid

    def test_crud(self, admin_client, app):
        rid = self._release(admin_client, app, "1")
        res = admin_client.get(f"/api/v1/releases/{rid}/ai-config")
        assert res.get_json()["data"]["ai_config"] is None
        res = admin_client.put(
            f"/api/v1/releases/{rid}/ai-config",
            json={"provider": "openai", "model_name": "gpt-4o", "temperature": 0.7},
        )
        assert res.status_code == 200, res.get_json()
        cfg = res.get_json()["data"]["ai_config"]
        assert cfg["provider"] == "openai"
        assert cfg["model_name"] == "gpt-4o"
        assert cfg["temperature"] == 0.7
        res = admin_client.get(f"/api/v1/releases/{rid}/ai-config")
        assert res.get_json()["data"]["ai_config"]["provider"] == "openai"
        res = admin_client.delete(f"/api/v1/releases/{rid}/ai-config")
        assert res.status_code == 200
        res = admin_client.get(f"/api/v1/releases/{rid}/ai-config")
        assert res.get_json()["data"]["ai_config"] is None

    def test_resolve_release_applies(self, app):
        with app.app_context():
            from app.models import Release, ReleaseAIConfig, resolve_release

            parent = _idea("IDEA-AI2A", status="SCALE")
            child = _idea(
                "IDEA-AI2B",
                status="SPARK",
                parent_id=parent.id,
                child_kind="bugfix",
            )
            rel = Release(parent_idea_id=parent.id, name="R")
            db.session.add(rel)
            db.session.flush()
            child.release_id = rel.id
            db.session.add(
                ReleaseAIConfig(
                    release_id=rel.id,
                    provider="anthropic",
                    model_name="claude-sonnet-4-5",
                    skills=["db"],
                )
            )
            db.session.commit()
            cfg = resolve_release(child)
            assert cfg["provider"] == "anthropic"
            assert cfg["model_name"] == "claude-sonnet-4-5"
            assert cfg["skills"] == ["db"]
            # Top-level idea: no release config
            assert resolve_release(parent) == {}

    def test_invalid_provider_rejected(self, admin_client, app):
        rid = self._release(admin_client, app, "3")
        res = admin_client.put(
            f"/api/v1/releases/{rid}/ai-config", json={"provider": "not-a-provider"}
        )
        assert res.status_code == 400

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
        # The worker must actually receive it: a mocked task used to hide
        # the missing target_id, and the run failed at execution time with
        # "Unknown build target for this instance".
        extra = mock_run.delay.call_args.kwargs["extra_context"]
        assert extra["target_id"] == str(tid)
        assert extra["target_name"] == "repo"

    def test_bulk_build_skips_when_target_ambiguous(self, admin_client, app):
        from unittest.mock import patch as _patch

        from app.models import Instance, InstanceBuildTarget

        rid, ids = self._release_with(admin_client, app, "5", ("SHIP",))
        with app.app_context():
            from app.models import Idea as _Idea

            inst = Instance(number=9995, name="Scale ambiguous")
            db.session.add(inst)
            db.session.flush()
            kid = _Idea.query.filter_by(reference_code="IDEA-B50").one()
            kid.instance_id = inst.id
            # Two repos and no previous build: the route must not guess.
            for name in ("one", "two"):
                db.session.add(
                    InstanceBuildTarget(
                        instance_id=inst.id, name=name, path=f"/tmp/{name}"
                    )
                )
            db.session.commit()
        with _patch("app.tasks.ollama_tasks.run_secondary_action") as mock_run:
            mock_run.delay.return_value.id = "job-5"
            res = admin_client.post(
                f"/api/v1/releases/{rid}/run-action",
                json={"action_type": "BUILD_CODE"},
            )
        assert res.status_code == 202, res.get_json()
        body = res.get_json()["data"]
        assert body["started"] == []
        assert "repo" in body["skipped"][0]["reason"].lower()
        assert mock_run.delay.call_count == 0

    def test_bulk_build_honours_requested_target(self, admin_client, app):
        from unittest.mock import patch as _patch

        from app.models import Instance, InstanceBuildTarget

        rid, ids = self._release_with(admin_client, app, "6", ("SHIP",))
        with app.app_context():
            from app.models import Idea as _Idea

            inst = Instance(number=9996, name="Scale explicit")
            db.session.add(inst)
            db.session.flush()
            kid = _Idea.query.filter_by(reference_code="IDEA-B60").one()
            kid.instance_id = inst.id
            chosen = InstanceBuildTarget(
                instance_id=inst.id, name="chosen", path="/tmp/chosen"
            )
            db.session.add_all(
                [
                    chosen,
                    InstanceBuildTarget(
                        instance_id=inst.id, name="other", path="/tmp/other"
                    ),
                ]
            )
            db.session.commit()
            chosen_id = str(chosen.id)
        with _patch("app.tasks.ollama_tasks.run_secondary_action") as mock_run:
            mock_run.delay.return_value.id = "job-6"
            res = admin_client.post(
                f"/api/v1/releases/{rid}/run-action",
                json={"action_type": "BUILD_CODE", "target_id": chosen_id},
            )
        assert res.status_code == 202, res.get_json()
        extra = mock_run.delay.call_args.kwargs["extra_context"]
        assert extra["target_id"] == chosen_id

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


class TestMessages:
    def _two_users(self, client, app):
        from app.models import Instance, Membership, User

        with app.app_context():
            inst = Instance(number=9971, name="Msg inst")
            db.session.add(inst)
            db.session.flush()
            iid = inst.id
            maker = User(email="msg-maker@example.com")
            maker.set_password("password123")
            db.session.add(maker)
            admin = User(email="msg-admin@example.com")
            admin.set_password("password123")
            db.session.add(admin)
            db.session.flush()
            db.session.add(Membership(user_id=maker.id, instance_id=iid, role="USER"))
            db.session.add(
                Membership(user_id=admin.id, instance_id=iid, role="INSTANCE_ADMIN")
            )
            db.session.commit()
        res = client.post(
            "/api/v1/register",
            json={"email": "msg-user@example.com", "password": "password123"},
        )
        user_token = res.get_json()["data"]["access_token"]
        res = client.post(
            "/api/v1/login",
            json={
                "email": "msg-maker@example.com",
                "password": "password123",
                "instance_id": str(iid),
            },
        )
        maker_token = res.get_json()["data"]["access_token"]
        res = client.post(
            "/api/v1/login",
            json={
                "email": "msg-admin@example.com",
                "password": "password123",
                "instance_id": str(iid),
            },
        )
        admin_token = res.get_json()["data"]["access_token"]
        with app.app_context():
            maker = User.query.filter_by(email="msg-maker@example.com").one()
            admin = User.query.filter_by(email="msg-admin@example.com").one()
            other = User.query.filter_by(email="msg-user@example.com").one()
            made, aid, oid = str(maker.id), str(admin.id), str(other.id)
        return maker_token, admin_token, user_token, made, aid, oid, str(iid)

    def test_user_to_admin_and_read(self, client, app):
        maker_token, admin_token, user_token, made, aid, oid, iid = self._two_users(
            client, app
        )
        # Normal user cannot message another normal user.
        res = client.post(
            "/api/v1/messages",
            json={"recipient_id": made, "body": "hi"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert res.status_code == 403
        # Scoped member messages the instance admin.
        res = client.post(
            "/api/v1/messages",
            json={"recipient_id": aid, "body": "please help"},
            headers={"Authorization": f"Bearer {maker_token}"},
        )
        assert res.status_code == 201, res.get_json()
        mid2 = res.get_json()["data"]["message"]["id"]
        # Admin can message anyone.
        res = client.post(
            "/api/v1/messages",
            json={"recipient_id": made, "body": "on it"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 201
        # Unread count + read receipt.
        res = client.get(
            "/api/v1/messages/unread-count",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.get_json()["data"]["unread"] == 1
        res = client.patch(
            f"/api/v1/messages/{mid2}/read",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.get_json()["data"]["message"]["read_at"] is not None
        res = client.get(
            "/api/v1/messages/unread-count",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.get_json()["data"]["unread"] == 0

    def test_message_with_idea_link(self, client, app):
        maker_token, _, _, _, aid, _, iid = self._two_users(client, app)

        with app.app_context():
            parent = _idea("IDEA-MSG1", status="SCALE")
            parent.instance_id = iid
            db.session.commit()
            pid = str(parent.id)
        res = client.post(
            "/api/v1/messages",
            json={
                "recipient_id": aid,
                "body": "look at this",
                "idea_id": pid,
            },
            headers={"Authorization": f"Bearer {maker_token}"},
        )
        assert res.status_code == 201, res.get_json()
        msg = res.get_json()["data"]["message"]
        assert msg["idea_id"] == pid
        assert msg["link"] and pid in msg["link"]

    def test_admins_picker_and_filters(self, client, app):
        maker_token, admin_token, _, _, aid, _, iid = self._two_users(client, app)
        headers = {"Authorization": f"Bearer {maker_token}"}
        res = client.get("/api/v1/messages/admins", headers=headers)
        assert res.status_code == 200
        admins = res.get_json()["data"]["admins"]
        assert any(a["id"] == aid for a in admins)
        # mine filter + comments sort + phase counts
        res = client.get("/api/v1/ideas?mine=true&limit=5", headers=headers)
        assert res.status_code == 200
        res = client.get("/api/v1/ideas?sort_by=comments&limit=5", headers=headers)
        assert res.status_code == 200
        ideas = res.get_json()["data"]["ideas"]
        counts = [i["comments_count"] for i in ideas]
        assert counts == sorted(counts, reverse=True)
        res = client.get("/api/v1/ideas/phase-counts", headers=headers)
        body = res.get_json()["data"]
        assert body["total"] >= 0
        assert isinstance(body["counts"], dict)


class TestGitHubFlow:
    def _admin(self, app, client, email, inst_id):
        from app.models import ROLE_INSTANCE_ADMIN, Membership, User

        with app.app_context():
            admin = User.query.filter_by(email=email).first()
            if admin is None:
                from app.models import User as _User

                admin = _User(email=email)
                admin.set_password("password123")
                db.session.add(admin)
                db.session.flush()
            if (
                Membership.query.filter_by(
                    user_id=admin.id, instance_id=inst_id
                ).first()
                is None
            ):
                db.session.add(
                    Membership(
                        user_id=admin.id,
                        instance_id=inst_id,
                        role=ROLE_INSTANCE_ADMIN,
                    )
                )
                db.session.commit()
        res = client.post(
            "/api/v1/login",
            json={
                "email": email,
                "password": "password123",
                "instance_id": str(inst_id),
            },
        )
        assert res.status_code == 200, res.get_json()
        token = res.get_json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def _instance(self, app, number=9981):
        from app.models import Instance

        inst = Instance(number=number, name=f"GH {number}")
        db.session.add(inst)
        db.session.flush()
        iid = inst.id
        db.session.commit()
        return iid

    def test_config_crud_hides_pat(self, app, client):
        with app.app_context():
            iid = self._instance(app)
        headers = self._admin(app, client, "gh-admin@t.test", iid)
        res = client.get(f"/api/v1/instances/{iid}/github-config", headers=headers)
        assert res.get_json()["data"]["github_config"] is None
        res = client.put(
            f"/api/v1/instances/{iid}/github-config",
            json={"repo": "my-org/my-app", "branch": "main", "pat": "ghp_secret123"},
            headers=headers,
        )
        assert res.status_code == 200, res.get_json()
        cfg = res.get_json()["data"]["github_config"]
        assert cfg["repo"] == "my-org/my-app"
        assert cfg["has_pat"] is True
        assert "pat" not in cfg and "ghp_secret123" not in res.get_data(as_text=True)
        res = client.put(
            f"/api/v1/instances/{iid}/github-config",
            json={"repo": "bad repo name!!"},
            headers=headers,
        )
        assert res.status_code == 400
        res = client.delete(f"/api/v1/instances/{iid}/github-config", headers=headers)
        assert res.status_code == 200
        res = client.get(f"/api/v1/instances/{iid}/github-config", headers=headers)
        assert res.get_json()["data"]["github_config"] is None

    def test_push_guards(self, app, client):
        from app.models import InstanceGitHubConfig, Release

        with app.app_context():
            iid = self._instance(app, 9982)
            parent = _idea("IDEA-GH1", status="SCALE")
            parent.instance_id = iid
            db.session.add(
                InstanceGitHubConfig(instance_id=iid, repo="o/r", branch="main")
            )
            db.session.flush()
            cfg = InstanceGitHubConfig.query.filter_by(instance_id=iid).one()
            cfg.pat = "ghp_x"
            rel = Release(parent_idea_id=parent.id, name="R")
            rel.instance_id = iid
            db.session.add(rel)
            db.session.commit()
            rid = str(rel.id)
        headers = self._admin(app, client, "gh-admin2@t.test", iid)
        # Not done yet.
        res = client.post(f"/api/v1/releases/{rid}/github-push", headers=headers)
        assert res.status_code == 400
        assert "Finish the release" in res.get_json()["message"]
        # Done but no GitHub PAT.
        with app.app_context():
            rel = Release.query.get(rid)
            rel.status = "done"
            InstanceGitHubConfig.query.filter_by(instance_id=iid).delete()
            db.session.commit()
        res = client.post(f"/api/v1/releases/{rid}/github-push", headers=headers)
        assert res.status_code == 400
        assert "not set up" in res.get_json()["message"]

    def test_push_starts_and_no_recommit(self, app, client):
        from unittest.mock import patch as _patch

        from app.models import InstanceGitHubConfig, Release

        with app.app_context():
            iid = self._instance(app, 9983)
            parent = _idea("IDEA-GH2", status="SCALE")
            parent.instance_id = iid
            kid = _idea(
                "IDEA-GH3",
                status="SHIP",
                parent_id=parent.id,
                child_kind="bugfix",
            )
            kid.instance_id = iid
            db.session.add(
                InstanceGitHubConfig(instance_id=iid, repo="o/r", branch="main")
            )
            db.session.flush()
            InstanceGitHubConfig.query.filter_by(instance_id=iid).one().pat = "ghp_x"
            from app.models import InstanceBuildTarget, SecondaryActionResult

            tgt = InstanceBuildTarget(instance_id=iid, name="repo", path="/tmp/repo")
            db.session.add(tgt)
            db.session.flush()
            db.session.add(
                SecondaryActionResult(
                    idea_id=parent.id,
                    action_type="BUILD_CODE",
                    model_used="m",
                    provider_used="ollama",
                    result_data={"summary": "x" * 30, "written": True},
                    version=1,
                    is_current=True,
                    target_id=tgt.id,
                    target_name="repo",
                )
            )
            rel = Release(parent_idea_id=parent.id, name="R", status="done")
            rel.instance_id = iid
            db.session.add(rel)
            db.session.commit()
            rid = str(rel.id)
        headers = self._admin(app, client, "gh-admin3@t.test", iid)
        with _patch("app.tasks.enqueue_generation") as mock_enq:
            mock_enq.return_value.id = "job-gh"
            res = client.post(f"/api/v1/releases/{rid}/github-push", headers=headers)
        assert res.status_code == 202, res.get_json()
        assert res.get_json()["data"]["job_id"] == "job-gh"
        # No re-commit once pushed.
        with app.app_context():
            rel = Release.query.get(rid)
            rel.github_sha = "abc123"
            db.session.commit()
        res = client.post(f"/api/v1/releases/{rid}/github-push", headers=headers)
        assert res.status_code == 400
        assert "already on GitHub" in res.get_json()["message"]
