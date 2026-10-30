"""Backup & Restore admin API (Phase 6 UI).

Site admins can export/restore the whole database, list and download the
daily files kept in ``BACKUP_DIR``, and turn the daily automation on/off.
Instance admins can export/restore only their own instance (manual only).

Every restore is destructive and takes an explicit typed confirmation:

* site restore     -> ``confirm="RESTORE"``
* instance restore -> ``confirm="<instance number>"``

Uploaded bundles are verified (schema version + SHA-256 checksum) before
any data is touched. The verification endpoint exists so the UI can show
what a file contains *before* the destructive button is enabled.
"""

import json
import os
from datetime import datetime, timezone

from flask import Blueprint, current_app, request, send_file

from app.extensions import db
from app.models import Instance, Membership, SystemSettings
from app.services import backup as backup_svc
from app.utils.decorators import admin_required, site_admin_required, token_required
from app.utils.responses import api_error, api_ok
from app.utils.tenancy import is_site_admin

bp = Blueprint("backup_api", __name__)

# Upload guard: bundles are JSON; refuse anything absurd before parsing.
MAX_BUNDLE_BYTES = 200 * 1024 * 1024


def _backup_dir() -> str:
    target = os.getenv("BACKUP_DIR") or str(
        current_app.config.get("BACKUP_DIR", "./backups")
    )
    # Absolute: Werkzeug resolves *relative* paths in send_file() against
    # app.root_path (/app/app), which 404s files that os.listdir() found
    # from the process CWD (/app).
    target = os.path.abspath(target)
    os.makedirs(target, exist_ok=True)
    return target


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _list_files() -> list[dict]:
    target = _backup_dir()
    files = []
    for name in sorted(os.listdir(target), reverse=True):
        if not name.endswith(".json"):
            continue
        path = os.path.join(target, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        files.append(
            {
                "name": name,
                "size": st.st_size,
                "modified_at": _iso(st.st_mtime),
            }
        )
    return files


def _read_upload() -> tuple[dict | None, str | None]:
    """Parse the multipart upload. Returns (bundle, error message)."""
    upload = request.files.get("file")
    if upload is None:
        return None, "Choose a backup file (.json) to continue."
    blob = upload.read(MAX_BUNDLE_BYTES + 1)
    if len(blob) > MAX_BUNDLE_BYTES:
        return None, "That file is too large (limit 200 MB)."
    try:
        bundle = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "That file is not a valid Brainstormer backup (JSON)."
    if not isinstance(bundle, dict):
        return None, "That file is not a valid Brainstormer backup."
    return bundle, None


def _verify_or_error(bundle: dict, scope: str, instance_id=None):
    """Return (manifest, error) after checking scope + checksum."""
    try:
        manifest = backup_svc.verify_bundle(bundle)
    except (backup_svc.BackupIntegrityError, backup_svc.BackupVersionError) as exc:
        return None, str(exc)
    if manifest.get("scope") != scope:
        want = "a site backup" if scope == "site" else "an instance backup"
        return None, f"This file is not {want}."
    if scope == "instance":
        bundled = str(manifest.get("instance_id") or "")
        if bundled != str(instance_id):
            return None, "This backup belongs to a different instance."
    return manifest, None


def _is_site_admin(user) -> bool:
    """Legacy ADMIN or a NULL-instance SITE_ADMIN grant.

    The rest of the admin UI treats the legacy ADMIN role as site-wide
    (``_membership_allows_admin``), so the backup page must agree or an
    admin who can see the link would be refused by the API.
    """
    try:
        if getattr(user.role, "value", user.role) == "ADMIN":
            return True
    except AttributeError:
        pass
    return is_site_admin(user)


def _require_instance_admin(user, instance_id):
    instance = db.session.get(Instance, instance_id)
    if instance is None:
        return None, api_error("Not found.", 404)
    if _is_site_admin(user):
        return instance, None
    role = Membership.get_role(user.id, instance.id)
    if role is None:
        return None, api_error("Not found.", 404)
    if role not in ("INSTANCE_ADMIN", "SITE_ADMIN"):
        return None, api_error("Instance admin access required.", 403)
    return instance, None


@bp.route("/admin/backup", methods=["GET"])
@admin_required
def backup_overview(user):
    """Everything the Backup & Restore page needs in one call."""
    site = _is_site_admin(user)
    if site:
        instances = Instance.query.order_by(Instance.number.asc()).all()
    else:
        memberships = Membership.query.filter_by(user_id=user.id).all()
        ids = [m.instance_id for m in memberships if m.instance_id is not None]
        instances = (
            Instance.query.filter(Instance.id.in_(ids))
            .order_by(Instance.number.asc())
            .all()
            if ids
            else []
        )
    settings = SystemSettings.get_instance()
    platform = settings.platform or {}
    db.session.commit()
    return api_ok(
        {
            "is_site_admin": site,
            "instances": [i.to_dict() for i in instances],
            "files": _list_files() if site else [],
            "automation": {
                "site_backup_automated": bool(
                    platform.get("site_backup_automated", True)
                ),
            },
        }
    )


@bp.route("/admin/backup/settings", methods=["PUT"])
@site_admin_required
def update_backup_settings(user):
    """Turn the daily site backup automation on or off."""
    data = request.get_json(silent=True) or {}
    if "site_backup_automated" not in data:
        return api_error("site_backup_automated is required.", 400)
    settings = SystemSettings.get_instance()
    platform = dict(settings.platform or {})
    platform["site_backup_automated"] = bool(data["site_backup_automated"])
    settings.platform = platform
    db.session.commit()
    return api_ok(
        {"automation": {"site_backup_automated": platform["site_backup_automated"]}},
        "Backup settings saved.",
    )


@bp.route("/admin/backup/site/run", methods=["POST"])
@site_admin_required
def run_site_backup(user):
    """Create a site backup file now (same path the daily task uses)."""
    target = _backup_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"site-{stamp}.json"
    path = os.path.join(target, name)
    bundle = backup_svc.export_site()
    backup_svc.write_bundle(bundle, path)
    manifest = bundle["manifest"]
    return api_ok(
        {
            "file": {
                "name": name,
                "size": os.path.getsize(path),
                "modified_at": _iso(os.path.getmtime(path)),
            },
            "rows": sum(manifest["tables"].values()),
            "checksum": manifest["checksum"],
        },
        "Site backup created.",
    )


@bp.route("/admin/backup/site/download", methods=["GET"])
@site_admin_required
def download_site_backup(user):
    """Export and download a fresh site bundle without keeping a copy."""
    import tempfile

    from flask import after_this_request

    bundle = backup_svc.export_site()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"site-{stamp}.json"
    handle = tempfile.NamedTemporaryFile(
        prefix="brainstormer-export-", suffix=".json", delete=False
    )
    handle.close()
    backup_svc.write_bundle(bundle, handle.name)

    @after_this_request
    def _cleanup(response):
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        return response

    return send_file(
        handle.name, as_attachment=True, download_name=name, mimetype="application/json"
    )


@bp.route("/admin/backup/files/<path:name>", methods=["GET"])
@site_admin_required
def download_backup_file(user, name):
    """Download one stored backup file (name only, no path traversal)."""
    if os.path.basename(name) != name or not name.endswith(".json"):
        return api_error("Not found.", 404)
    path = os.path.join(_backup_dir(), name)
    if not os.path.isfile(path):
        return api_error("Not found.", 404)
    return send_file(path, as_attachment=True, download_name=name)


@bp.route("/admin/backup/site/verify", methods=["POST"])
@site_admin_required
def verify_site_backup(user):
    """Checksum + manifest preview of an uploaded site bundle."""
    bundle, error = _read_upload()
    if error:
        return api_error(error, 400)
    manifest, error = _verify_or_error(bundle, "site")
    if error:
        return api_error(error, 400)
    return api_ok({"manifest": manifest})


@bp.route("/admin/backup/site/restore", methods=["POST"])
@site_admin_required
def restore_site_backup(user):
    """Verify, wipe and restore the whole site from an uploaded bundle."""
    if (request.form.get("confirm") or "").strip().upper() != "RESTORE":
        return api_error('Type "RESTORE" to confirm this destructive action.', 400)
    bundle, error = _read_upload()
    if error:
        return api_error(error, 400)
    _manifest, error = _verify_or_error(bundle, "site")
    if error:
        return api_error(error, 400)
    try:
        counts = backup_svc.restore_site(bundle)
    except (backup_svc.BackupIntegrityError, backup_svc.BackupVersionError) as exc:
        db.session.rollback()
        return api_error(str(exc), 400)
    return api_ok(
        {"tables": counts, "rows": sum(counts.values())},
        "Site restored.",
    )


@bp.route("/instances/<uuid:instance_id>/backup/verify", methods=["POST"])
@token_required
def verify_instance_backup(user, instance_id):
    """Checksum + manifest preview of an uploaded instance bundle."""
    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    bundle, error = _read_upload()
    if error:
        return api_error(error, 400)
    manifest, error = _verify_or_error(bundle, "instance", instance.id)
    if error:
        return api_error(error, 400)
    return api_ok({"manifest": manifest})


@bp.route("/instances/<uuid:instance_id>/backup/restore", methods=["POST"])
@token_required
def restore_instance_backup(user, instance_id):
    """Replace one instance's rows from an uploaded bundle."""
    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    confirm = (request.form.get("confirm") or "").strip()
    if confirm != str(instance.number):
        return api_error(
            f'Type the instance number ({instance.number}) to confirm.', 400
        )
    bundle, error = _read_upload()
    if error:
        return api_error(error, 400)
    _manifest, error = _verify_or_error(bundle, "instance", instance.id)
    if error:
        return api_error(error, 400)
    try:
        counts = backup_svc.restore_instance(bundle)
    except (backup_svc.BackupIntegrityError, backup_svc.BackupVersionError) as exc:
        db.session.rollback()
        return api_error(str(exc), 400)
    return api_ok(
        {"tables": counts, "rows": sum(counts.values())},
        f"Instance {instance.number} restored.",
    )
