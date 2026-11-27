"""Managed-app log endpoints: tail and truncate in place."""

from app.extensions import db
from app.models import ManagedApp
from tests.integration.test_build import login, make_instance, seed_idea


def test_clear_logs_truncates_file(app, client, tmp_path):
    with app.app_context():
        inst = make_instance(130, "ML")
        idea = seed_idea(db, inst.id, email="logs@t.test")
        iid, idea_id = inst.id, idea.id
    headers = login(client, "logs@t.test", str(iid))
    log_file = tmp_path / "app.log"
    log_file.write_text("line\n" * 5)
    with app.app_context():
        db.session.add(
            ManagedApp(
                instance_id=iid,
                idea_id=idea_id,
                state="stopped",
                log_path=str(log_file),
            )
        )
        db.session.commit()

    base = f"/api/v1/instances/{iid}/managed-apps"
    app_id = None
    with app.app_context():
        app_id = str(ManagedApp.query.filter_by(idea_id=idea_id).one().id)

    res = client.get(f"{base}/{app_id}/logs", headers=headers)
    assert res.status_code == 200
    assert len(res.get_json()["data"]["lines"]) == 5

    res = client.post(f"{base}/{app_id}/logs/clear", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["data"]["cleared"] is True
    assert log_file.read_text() == ""

    res = client.get(f"{base}/{app_id}/logs", headers=headers)
    assert res.get_json()["data"]["lines"] == []
