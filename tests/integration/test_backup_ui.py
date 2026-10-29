"""Backup & Restore admin UI API (Phase 6 UI).

Covers the endpoints behind /admin/backup: overview, site export/restore,
per-instance export/restore, the typed confirmations, and the automation
toggle. Bundles are real round-trip exports, not mocks.
"""

import io
import json

import pytest

from app.extensions import db
from app.models import Instance, Membership, SystemSettings, User, UserRole


@pytest.fixture()
def site_with_admin(app):
    """One instance plus an INSTANCE_ADMIN member and a plain member."""
    with app.app_context():
        instance = Instance(number=77, name="Backup Test")
        db.session.add(instance)
        db.session.flush()

        admin = User(email="inst-admin@example.com", role=UserRole.USER)
        admin.set_password("password123")
        member = User(email="inst-member@example.com", role=UserRole.USER)
        member.set_password("password123")
        db.session.add_all([admin, member])
        db.session.flush()
        db.session.add(
            Membership(user_id=admin.id, instance_id=instance.id, role="INSTANCE_ADMIN")
        )
        db.session.add(
            Membership(user_id=member.id, instance_id=instance.id, role="MEMBER")
        )
        db.session.commit()
        return {"instance_id": str(instance.id), "number": 77}


def _login(client, email, password="password123", instance_id=None):
    body = {"email": email, "password": password}
    if instance_id:
        body["instance_id"] = instance_id
    res = client.post("/api/v1/login", json=body)
    assert res.status_code == 200, res.get_json()
    return {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}


def _multipart(bundle, confirm=None):
    data = {"file": (io.BytesIO(json.dumps(bundle).encode()), "backup.json")}
    if confirm is not None:
        data["confirm"] = confirm
    return data


def test_overview_requires_admin(client, app, site_with_admin):
    headers = _login(client, "inst-member@example.com")
    res = client.get("/api/v1/admin/backup", headers=headers)
    assert res.status_code == 403


def test_overview_lists_own_instance(client, app, site_with_admin):
    headers = _login(client, "inst-admin@example.com", instance_id=site_with_admin["instance_id"])
    res = client.get("/api/v1/admin/backup", headers=headers)
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["is_site_admin"] is False
    assert [i["number"] for i in data["instances"]] == [77]
    assert data["files"] == []


def test_site_backup_roundtrip(admin_client, app, site_with_admin, tmp_path):
    app.config["BACKUP_DIR"] = str(tmp_path)

    res = admin_client.post("/api/v1/admin/backup/site/run")
    assert res.status_code == 200, res.get_json()
    created = res.get_json()["data"]
    name = created["file"]["name"]
    assert created["rows"] > 0

    overview = admin_client.get("/api/v1/admin/backup").get_json()["data"]
    assert overview["is_site_admin"] is True
    assert [f["name"] for f in overview["files"]] == [name]

    download = admin_client.get(f"/api/v1/admin/backup/files/{name}")
    assert download.status_code == 200
    bundle = json.loads(download.data)
    assert bundle["manifest"]["scope"] == "site"

    verify = admin_client.post(
        "/api/v1/admin/backup/site/verify",
        data=_multipart(bundle),
        content_type="multipart/form-data",
    )
    assert verify.status_code == 200, verify.get_json()
    assert verify.get_json()["data"]["manifest"]["tables"] == bundle["manifest"]["tables"]

    restore = admin_client.post(
        "/api/v1/admin/backup/site/restore",
        data=_multipart(bundle, confirm="RESTORE"),
        content_type="multipart/form-data",
    )
    assert restore.status_code == 200, restore.get_json()
    assert restore.get_json()["data"]["rows"] > 0


def test_site_restore_needs_typed_confirmation(admin_client, app, tmp_path):
    app.config["BACKUP_DIR"] = str(tmp_path)
    bundle = admin_client.get("/api/v1/admin/backup/site/download").data
    res = admin_client.post(
        "/api/v1/admin/backup/site/restore",
        data=_multipart(json.loads(bundle), confirm="yes"),
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert "RESTORE" in res.get_json()["message"]


def test_site_restore_rejects_instance_bundle(
    client, admin_client, app, site_with_admin, tmp_path
):
    app.config["BACKUP_DIR"] = str(tmp_path)
    headers = _login(client, "inst-admin@example.com")
    bundle = client.get(
        f"/api/v1/instances/{site_with_admin['instance_id']}/export", headers=headers
    ).data
    res = admin_client.post(
        "/api/v1/admin/backup/site/restore",
        data=_multipart(json.loads(bundle), confirm="RESTORE"),
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert "not a site backup" in res.get_json()["message"]


def test_instance_backup_roundtrip(client, app, site_with_admin):
    iid = site_with_admin["instance_id"]
    headers = _login(client, "inst-admin@example.com")
    bundle = client.get(f"/api/v1/instances/{iid}/export", headers=headers).data
    bundle = json.loads(bundle)
    assert bundle["manifest"]["scope"] == "instance"

    verify = client.post(
        f"/api/v1/instances/{iid}/backup/verify",
        data=_multipart(bundle),
        headers=headers,
        content_type="multipart/form-data",
    )
    assert verify.status_code == 200, verify.get_json()

    wrong = client.post(
        f"/api/v1/instances/{iid}/backup/restore",
        data=_multipart(bundle, confirm="1"),
        headers=headers,
        content_type="multipart/form-data",
    )
    assert wrong.status_code == 400

    ok = client.post(
        f"/api/v1/instances/{iid}/backup/restore",
        data=_multipart(bundle, confirm=str(site_with_admin["number"])),
        headers=headers,
        content_type="multipart/form-data",
    )
    assert ok.status_code == 200, ok.get_json()
    assert ok.get_json()["data"]["rows"] > 0


def test_instance_restore_rejects_other_instances_bundle(
    client, app, site_with_admin
):
    other = Instance(number=78, name="Other")
    with app.app_context():
        db.session.add(other)
        db.session.commit()
        other_id = str(other.id)

    headers = _login(client, "inst-admin@example.com")
    bundle = client.get(
        f"/api/v1/instances/{site_with_admin['instance_id']}/export", headers=headers
    ).data
    res = client.post(
        f"/api/v1/instances/{other_id}/backup/verify",
        data=_multipart(json.loads(bundle)),
        headers=headers,
        content_type="multipart/form-data",
    )
    # Not an admin of 78 -> 404 before any parsing.
    assert res.status_code == 404


def test_automation_toggle(admin_client, app):
    res = admin_client.put(
        "/api/v1/admin/backup/settings", json={"site_backup_automated": False}
    )
    assert res.status_code == 200
    with app.app_context():
        settings = SystemSettings.get_instance()
        assert settings.platform["site_backup_automated"] is False
    overview = admin_client.get("/api/v1/admin/backup").get_json()["data"]
    assert overview["automation"]["site_backup_automated"] is False


def test_scheduled_task_respects_toggle(app, monkeypatch):
    from app.tasks import maintenance_tasks

    with app.app_context():
        settings = SystemSettings.get_instance()
        settings.platform = {"site_backup_automated": False}
        db.session.commit()

    result = maintenance_tasks.scheduled_site_backup.apply().get()
    assert result["status"] == "skipped"


def test_relative_backup_dir_still_downloads(
    admin_client, app, tmp_path, monkeypatch
):
    """Regression: the default BACKUP_DIR is relative (./backups).

    os.listdir() resolved it from the process CWD, but send_file() resolves
    relative paths against app.root_path, so downloads 500ed with
    FileNotFoundError while the list endpoint looked fine.
    """
    monkeypatch.delenv("BACKUP_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    app.config["BACKUP_DIR"] = "./backups"

    created = admin_client.post("/api/v1/admin/backup/site/run")
    assert created.status_code == 200, created.get_json()
    name = created.get_json()["data"]["file"]["name"]

    overview = admin_client.get("/api/v1/admin/backup").get_json()["data"]
    assert [f["name"] for f in overview["files"]] == [name]

    download = admin_client.get(f"/api/v1/admin/backup/files/{name}")
    assert download.status_code == 200
    assert download.data[:1] == b"{"
