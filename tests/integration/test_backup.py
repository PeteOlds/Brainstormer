"""Phase 0 exit: backup -> wipe -> restore round-trips with zero diff."""

import json

import pytest

from app.extensions import db
from app.models import (
    ActionType,
    Comment,
    Idea,
    IdeaEdit,
    IdeaStatus,
    IdeaStatusHistory,
    PromptConfig,
    PromptRun,
    PromptRunStatus,
    SecondaryActionResult,
    SlackEvent,
    SlackPost,
    SystemSettings,
    User,
    UserRole,
    Vote,
)
from app.services import backup as backup_svc
from app.services.backup import BackupIntegrityError, BackupVersionError


def seed_site():
    """Representative rows across every exported table."""
    admin = User(email="backup-admin@test.com", role=UserRole.ADMIN)
    admin.set_password("password123")
    user = User(email="backup-user@test.com")
    user.set_password("password123")
    db.session.add_all([admin, user])
    db.session.flush()

    from app.models import Instance, Membership

    site = Instance(number=5, name="Production")
    db.session.add(site)
    db.session.flush()
    db.session.add(
        Membership(user_id=admin.id, instance_id=site.id, role="INSTANCE_ADMIN")
    )

    prompt = PromptConfig(
        title="Backup Prompt",
        prompt_body="Generate an idea about {{topic}}",
        interval_minutes=60,
        model_name="llama3:8b",
        is_active=True,
        created_by_id=admin.id,
    )
    db.session.add(prompt)
    db.session.flush()

    idea = Idea(
        reference_code="IDEA-0001",
        prompt_title="Backup Prompt",
        raw_content="An idea worth backing up",
        structured_content={"elevator_pitch": "Backup everything"},
        prompt_config_id=prompt.id,
    )
    db.session.add(idea)
    db.session.flush()

    run = PromptRun(
        prompt_config_id=prompt.id, idea_id=idea.id, status=PromptRunStatus.SUCCESS
    )
    db.session.add(run)

    db.session.add(Vote(user_id=user.id, idea_id=idea.id, value=1))
    top = Comment(idea_id=idea.id, user_id=user.id, body="Top-level comment")
    db.session.add(top)
    db.session.flush()
    db.session.add(
        Comment(idea_id=idea.id, user_id=admin.id, parent_id=top.id, body="Reply")
    )
    db.session.add(
        Comment(idea_id=idea.id, user_id=user.id, body="Deleted", is_deleted=True)
    )

    db.session.add(
        IdeaEdit(
            idea_id=idea.id,
            editor_id=admin.id,
            field="raw_content",
            old_value="a",
            new_value="b",
        )
    )
    db.session.add(
        SecondaryActionResult(
            idea_id=idea.id,
            action_type=ActionType.REFINE,
            model_used="llama3:8b",
            result_data={"elevator_pitch": "x"},
        )
    )
    db.session.add(
        IdeaStatusHistory(
            idea_id=idea.id,
            changed_by_id=admin.id,
            old_status=IdeaStatus.SPARK,
            new_status=IdeaStatus.SCOPE,
        )
    )
    db.session.add(SlackPost(idea_id=idea.id, channel_id="C123", message_ts="1.0"))
    db.session.add(SlackEvent(event_id="Ev001"))

    settings = SystemSettings(platform={"title": "BS"}, location={}, ai_connections={})
    db.session.add(settings)
    db.session.commit()
    return idea.id


def test_round_trip_zero_diff(app):
    with app.app_context():
        seed_site()
        before = backup_svc.fingerprint_db()
        bundle = backup_svc.export_site()
        assert sum(bundle["manifest"]["tables"].values()) > 0

        # Wipe everything, then restore.
        for model in reversed(backup_svc.EXPORT_TABLES):
            db.session.query(model).delete()
        db.session.commit()
        assert Idea.query.count() == 0

        counts = backup_svc.restore_site(bundle)
        assert counts["ideas"] == 1
        assert backup_svc.fingerprint_db() == before


def test_round_trip_via_file(app, tmp_path):
    with app.app_context():
        seed_site()
        before = backup_svc.fingerprint_db()
        path = str(tmp_path / "site.json")
        backup_svc.write_bundle(backup_svc.export_site(), path)

        for model in reversed(backup_svc.EXPORT_TABLES):
            db.session.query(model).delete()
        db.session.commit()

        restored = backup_svc.read_bundle(path)
        backup_svc.restore_site(restored)
        assert backup_svc.fingerprint_db() == before


def test_tampered_bundle_rejected(app):
    with app.app_context():
        seed_site()
        bundle = backup_svc.export_site()
        bundle["data"]["ideas"][0]["raw_content"] = "Tampered"
        with pytest.raises(BackupIntegrityError):
            backup_svc.restore_site(bundle)


def test_unknown_schema_version_rejected(app):
    with app.app_context():
        bundle = backup_svc.export_site()
        bundle["manifest"]["export_schema_version"] = 999
        with pytest.raises(BackupVersionError):
            backup_svc.restore_site(bundle)


def test_cli_backup_and_restore(app, tmp_path):
    runner = app.test_cli_runner()
    with app.app_context():
        seed_site()
        before = backup_svc.fingerprint_db()
    path = str(tmp_path / "site.json")

    result = runner.invoke(args=["backup-site", "--output", path])
    assert result.exit_code == 0, result.output
    assert "Site backup written" in result.output

    with app.app_context():
        for model in reversed(backup_svc.EXPORT_TABLES):
            db.session.query(model).delete()
        db.session.commit()
    result = runner.invoke(args=["restore", "--input", path, "--yes"])
    assert result.exit_code == 0, result.output
    assert "Restored" in result.output

    with app.app_context():
        assert backup_svc.fingerprint_db() == before


def test_cli_restore_requires_confirmation(app, tmp_path):
    runner = app.test_cli_runner()
    with app.app_context():
        seed_site()
        path = str(tmp_path / "site.json")
        backup_svc.write_bundle(backup_svc.export_site(), path)
    result = runner.invoke(args=["restore", "--input", path], input="n\n")
    assert result.exit_code != 0
    with app.app_context():
        assert Idea.query.count() == 1


def test_backup_instance_requires_instance_id(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["backup-instance", "--output", "x.json"])
    assert result.exit_code != 0

    with app.app_context():
        from app.models import Instance

        db.session.add(Instance(number=99, name="Temp"))
        db.session.commit()
    result = runner.invoke(
        args=["backup-instance", "--instance-id", "12345", "--output", "x.json"]
    )
    assert result.exit_code != 0

    with app.app_context():
        db.session.delete(Instance.query.filter_by(number=99).first())
        db.session.commit()


def test_restore_site_rejects_instance_bundle(app, tmp_path):
    from app.services import backup as backup_svc

    with app.app_context():
        from app.models import Instance

        inst = Instance(number=98, name="Scope")
        db.session.add(inst)
        db.session.commit()
        bundle = backup_svc.export_instance(inst.id)
        with pytest.raises(BackupIntegrityError):
            backup_svc.restore_site(bundle)
        db.session.delete(inst)
        db.session.commit()


# --- Authorisation: site-wide backup is a site-admin operation ---------------

SITE_BACKUP_ENDPOINTS = [
    ("put", "/api/v1/admin/backup/settings"),
    ("post", "/api/v1/admin/backup/site/run"),
    ("get", "/api/v1/admin/backup/site/download"),
    ("get", "/api/v1/admin/backup/files/anything.bundle"),
    ("post", "/api/v1/admin/backup/site/verify"),
    ("post", "/api/v1/admin/backup/site/restore"),
]


def _tenant_admin_headers(client, app):
    """An INSTANCE_ADMIN scoped to their own tenant — not a site admin."""
    from app.models import Instance, Membership, User, UserRole

    with app.app_context():
        inst = Instance.query.filter_by(number=901).first()
        if inst is None:
            inst = Instance(number=901, name="Tenant A")
            db.session.add(inst)
            db.session.flush()
        user = User.query.filter_by(email="tenant-admin@test.com").first()
        if user is None:
            user = User(email="tenant-admin@test.com", role=UserRole.USER)
            user.set_password("password123")
            db.session.add(user)
            db.session.flush()
        if (
            Membership.query.filter_by(
                user_id=user.id, instance_id=inst.id
            ).first()
            is None
        ):
            db.session.add(
                Membership(
                    user_id=user.id,
                    instance_id=inst.id,
                    role="INSTANCE_ADMIN",
                )
            )
        db.session.commit()
        instance_id = str(inst.id)

    res = client.post(
        "/api/v1/login",
        json={
            "email": "tenant-admin@test.com",
            "password": "password123",
            "instance_id": instance_id,
        },
    )
    assert res.status_code == 200, res.get_json()
    return {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}


@pytest.mark.parametrize("method,path", SITE_BACKUP_ENDPOINTS)
def test_instance_admin_cannot_reach_site_backup(app, client, method, path):
    """A tenant admin must not be able to export every tenant's data.

    The site bundle contains all users, ideas and settings, so exposing
    these endpoints to an instance admin is a cross-tenant data breach.
    """
    headers = _tenant_admin_headers(client, app)
    kwargs = {"headers": headers}
    if method in ("post", "put"):
        kwargs["json"] = {}
    res = getattr(client, method)(path, **kwargs)
    assert res.status_code == 403, (path, res.status_code, res.get_data(as_text=True)[:200])


# --- Authenticity: a bundle must be signed by this server -------------------

def _tamper(bundle):
    """Edit one idea title and recompute the (non-secret) checksum."""
    import copy
    import hashlib
    import json

    forged = copy.deepcopy(bundle)
    row = forged["data"]["ideas"][0]
    row["prompt_title"] = "Injected by an attacker"
    manifest = {k: v for k, v in forged["manifest"].items() if k != "checksum"}
    payload = json.dumps(
        {"manifest": manifest, "data": forged["data"]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    forged["manifest"]["checksum"] = hashlib.sha256(payload).hexdigest()
    return forged


def test_tampered_bundle_rejected_even_with_valid_checksum(app):
    """A self-checksum proves nothing: anyone can recompute it."""
    with app.app_context():
        seed_site()
        bundle = backup_svc.export_site()
        forged = _tamper(bundle)
        assert forged["manifest"]["checksum"] != bundle["manifest"]["checksum"]
        with pytest.raises(BackupIntegrityError):
            backup_svc.verify_bundle(forged)


def test_unsigned_bundle_rejected(app):
    with app.app_context():
        seed_site()
        bundle = backup_svc.export_site()
        bundle["manifest"].pop("signature", None)
        with pytest.raises(BackupIntegrityError):
            backup_svc.verify_bundle(bundle)


def test_bundle_signed_with_another_key_rejected(app):
    """Bundles are only accepted from a server holding the same secret."""
    import copy

    with app.app_context():
        seed_site()
        bundle = backup_svc.export_site()
        forged = _tamper(bundle)
        forged["manifest"]["signature"] = "0" * 64
        with pytest.raises(BackupIntegrityError):
            backup_svc.verify_bundle(forged)
        # Sanity: the untouched bundle still verifies.
        backup_svc.verify_bundle(copy.deepcopy(bundle))


# --- Restore must stay inside its tenant and must not grant privilege -------

def test_instance_restore_rejects_rows_for_another_instance(app):
    """A bundle relabelled for tenant A must not write tenant B's rows."""
    from app.models import Instance

    with app.app_context():
        tenant_b = Instance(number=902, name="Tenant B")
        db.session.add(tenant_b)
        db.session.flush()
        db.session.add(
            Idea(
                reference_code="IDEA-B001",
                prompt_title="B idea",
                raw_content="b",
                instance_id=tenant_b.id,
            )
        )
        db.session.commit()
        bundle = backup_svc.export_instance(tenant_b.id)

        tenant_a = Instance(number=903, name="Tenant A")
        db.session.add(tenant_a)
        db.session.commit()

        # Re-signed by this server, so it passes authenticity; the manifest
        # now claims tenant A while the rows still belong to B.
        relabelled = backup_svc.rescope_bundle(
            bundle, "instance", instance_id=str(tenant_a.id)
        )
        with pytest.raises(BackupIntegrityError):
            backup_svc.restore_instance(relabelled)

        assert (
            Idea.query.filter_by(reference_code="IDEA-B001").one().instance_id
            == tenant_b.id
        )


def test_instance_restore_cannot_promote_a_member_to_admin(app):
    """Restoring an instance bundle must not rewrite global roles/passwords."""
    from app.models import Instance, Membership

    with app.app_context():
        tenant = Instance(number=904, name="Tenant C")
        db.session.add(tenant)
        db.session.flush()
        member = User(email="member-c@test.com", role=UserRole.USER)
        member.set_password("memberpass123")
        db.session.add(member)
        db.session.flush()
        db.session.add(
            Membership(user_id=member.id, instance_id=tenant.id, role="USER")
        )
        db.session.commit()
        original_hash = member.password_hash
        bundle = backup_svc.export_instance(tenant.id)

        for row in bundle["data"]["users"]:
            if row.get("email") == "member-c@test.com":
                row["role"] = "ADMIN"
                row["password_hash"] = "forged-hash"
        forged = backup_svc.rescope_bundle(
            bundle, "instance", instance_id=str(tenant.id)
        )
        backup_svc.restore_instance(forged)

        restored = User.query.filter_by(email="member-c@test.com").one()
        assert restored.role == UserRole.USER
        assert restored.password_hash == original_hash
