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


def test_backup_instance_marks_phase0_scope(app, tmp_path):
    runner = app.test_cli_runner()
    with app.app_context():
        seed_site()
    path = str(tmp_path / "instance.json")
    result = runner.invoke(args=["backup-instance", "--output", path])
    assert result.exit_code == 0, result.output
    with open(path, encoding="utf-8") as fh:
        bundle = json.load(fh)
    assert bundle["manifest"]["scope"] == "instance"
    assert "Phase 1" in bundle["manifest"]["note"]
    # Still a verifiable, restorable bundle.
    with app.app_context():
        assert backup_svc.verify_bundle(bundle)["scope"] == "instance"
