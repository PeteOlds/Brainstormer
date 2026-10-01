"""Phase 6: per-instance backup GA, scheduled backups, export API."""

import json

import pytest

from app.extensions import db
from app.models import (
    Comment,
    Idea,
    Instance,
    Membership,
    PromptConfig,
    User,
    UserRole,
    Vote,
)
from app.services import backup as backup_svc
from app.services.backup import BackupIntegrityError


def seed_two_instances():
    admin = User(email="ga-admin@t.test", role=UserRole.ADMIN)
    admin.set_password("password123")
    other = User(email="ga-other@t.test")
    other.set_password("password123")
    db.session.add_all([admin, other])
    db.session.flush()
    a = Instance(number=60, name="GA-A")
    b = Instance(number=61, name="GA-B")
    db.session.add_all([a, b])
    db.session.flush()
    db.session.add(
        Membership(user_id=admin.id, instance_id=a.id, role="INSTANCE_ADMIN")
    )
    db.session.add(Membership(user_id=other.id, instance_id=b.id, role="USER"))
    for inst, tag in ((a, "A"), (b, "B")):
        prompt = PromptConfig(
            title=f"P{tag}",
            prompt_body="body",
            interval_minutes=60,
            model_name="m",
            created_by_id=admin.id,
            instance_id=inst.id,
        )
        db.session.add(prompt)
        db.session.flush()
        idea = Idea(
            reference_code=f"IDEA-G{tag}1",
            prompt_title=f"P{tag}",
            raw_content="c",
            structured_content={"elevator_pitch": "x"},
            prompt_config_id=prompt.id,
            instance_id=inst.id,
        )
        db.session.add(idea)
        db.session.flush()
        db.session.add(
            Vote(
                user_id=(admin.id if tag == "A" else other.id),
                idea_id=idea.id,
                value=1,
                instance_id=inst.id,
            )
        )
        db.session.add(
            Comment(
                idea_id=idea.id,
                user_id=admin.id,
                body=f"note {tag}",
                instance_id=inst.id,
            )
        )
    db.session.commit()
    return a, b


def test_instance_export_isolation(app):
    with app.app_context():
        a, b = seed_two_instances()
        bundle = backup_svc.export_instance(a.id)
        assert bundle["manifest"]["scope"] == "instance"
        assert bundle["manifest"]["instance_number"] == 60
        refs = [r["reference_code"] for r in bundle["data"]["ideas"]]
        assert refs == ["IDEA-GA1"]
        assert {r["title"] for r in bundle["data"]["prompt_configs"]} == {"PA"}
        assert bundle["data"]["refresh_tokens"] == []
        assert bundle["data"]["slack_events"] == []
        # Members + referenced authors travel; the stranger stays out.
        emails = {r["email"] for r in bundle["data"]["users"]}
        assert emails == {"ga-admin@t.test"}
        # Verifiable on its own.
        assert backup_svc.verify_bundle(bundle)["scope"] == "instance"


def test_instance_restore_round_trip_leaves_others_alone(app):
    with app.app_context():
        a, b = seed_two_instances()
        before_a = backup_svc.fingerprint_instance(a.id)
        before_b = backup_svc.fingerprint_instance(b.id)
        bundle = backup_svc.export_instance(a.id)

        # Drift A: new idea, changed title, dropped prompt.
        Idea.query.filter_by(reference_code="IDEA-GA1").first().prompt_title = "Mangled"
        db.session.add(
            Idea(
                reference_code="IDEA-GA9",
                prompt_title="Extra",
                raw_content="c",
                instance_id=a.id,
            )
        )
        PromptConfig.query.filter_by(title="PA").delete()
        db.session.commit()

        counts = backup_svc.restore_instance(bundle)
        assert counts["ideas"] == 1
        assert backup_svc.fingerprint_instance(a.id) == before_a
        assert backup_svc.fingerprint_instance(b.id) == before_b


def test_cli_instance_round_trip(app, tmp_path):
    runner = app.test_cli_runner()
    with app.app_context():
        a, b = seed_two_instances()
        before = backup_svc.fingerprint_instance(a.id)
    path = str(tmp_path / "a.json")
    result = runner.invoke(
        args=["backup-instance", "--instance-id", "60", "--output", path]
    )
    assert result.exit_code == 0, result.output

    with app.app_context():
        Idea.query.filter_by(reference_code="IDEA-GA1").delete()
        db.session.commit()
    result = runner.invoke(args=["restore-instance", "--input", path, "--yes"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert backup_svc.fingerprint_instance(a.id) == before


def test_export_api_download_and_access(app, client):
    with app.app_context():
        a, b = seed_two_instances()
        aid, bid = str(a.id), str(b.id)
    admin_h = {
        "Authorization": f"Bearer {client.post('/api/v1/login', json={'email': 'ga-admin@t.test', 'password': 'password123', 'instance_id': aid}).get_json()['data']['access_token']}"
    }

    res = client.get(f"/api/v1/instances/{aid}/export", headers=admin_h)
    assert res.status_code == 200
    bundle = res.get_json()
    assert backup_svc.verify_bundle(bundle)["scope"] == "instance"
    assert "attachment" in res.headers.get("Content-Disposition", "")

    # Scoped to A: B's bundle is invisible.
    assert (
        client.get(f"/api/v1/instances/{bid}/export", headers=admin_h).status_code
        == 404
    )


def test_scheduled_task_writes_verified_bundle(app, tmp_path):
    from app.tasks.maintenance_tasks import scheduled_site_backup

    with app.app_context():
        seed_two_instances()
    out = scheduled_site_backup(str(tmp_path))
    assert out["status"] == "ok" and out["rows"] > 0
    with open(out["path"], encoding="utf-8") as fh:
        manifest = json.load(fh)["manifest"]
    assert manifest["scope"] == "site" and len(manifest["checksum"]) == 64
