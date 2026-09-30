"""Site backup, export and restore (Phase 0).

Versioned JSON bundles with a manifest and a SHA-256 checksum. The bundle
holds every tenant-scoped table plus users and settings, so
backup -> wipe -> restore round-trips the database with zero diff.

Encrypted blobs (prompt bodies, and later per-instance keys) travel as-is:
restoring requires the same FERNET_KEY. Per-instance filtering lands in
Phase 1 with `instance_id`; until then `backup-instance` exports the whole
database and says so.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Enum

from app.extensions import db
from app.models import (
    AISpendLedger,
    Comment,
    Idea,
    IdeaEdit,
    IdeaStatusHistory,
    Instance,
    InstanceAIConfig,
    Membership,
    PromptConfig,
    PromptRun,
    RefreshToken,
    SecondaryActionResult,
    SlackEvent,
    SlackPost,
    SystemSettings,
    User,
    Vote,
)
from app.models.types import GUID

EXPORT_SCHEMA_VERSION = 1

# Parents before children so inserts never violate a foreign key on
# Postgres (SQLite does not enforce FKs by default, but keep it portable).
# Within a table rows export oldest-first: self-references (token rotation
# chains, comment replies) always point backwards in time.
EXPORT_TABLES: list[Any] = [
    Instance,
    User,
    Membership,
    InstanceAIConfig,
    SystemSettings,
    PromptConfig,
    Idea,
    PromptRun,
    RefreshToken,
    Vote,
    Comment,
    IdeaEdit,
    SecondaryActionResult,
    IdeaStatusHistory,
    SlackPost,
    SlackEvent,
    AISpendLedger,
]


class BackupIntegrityError(ValueError):
    """Checksum mismatch or unreadable bundle."""


class BackupVersionError(ValueError):
    """Bundle was written by an incompatible export schema."""


def _app_version() -> str:
    try:
        from flask import current_app

        version = current_app.config.get("VERSION")
        if version:
            return str(version)
    except RuntimeError:
        pass
    try:
        import pathlib

        return (
            (pathlib.Path(__file__).resolve().parent.parent.parent / "VERSION")
            .read_text()
            .strip()
        )
    except OSError:
        return "unknown"


def _serialise_value(column: Column, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, GUID):
        return str(value)
    if isinstance(column.type, DateTime):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(column.type, Enum):
        return value.value if hasattr(value, "value") else str(value)
    return value


def _deserialise_value(column: Column, value: Any) -> Any:
    from datetime import datetime as dt

    if value is None:
        return None
    if isinstance(column.type, GUID):
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    if isinstance(column.type, DateTime):
        return value if isinstance(value, dt) else dt.fromisoformat(value)
    if isinstance(column.type, Enum):
        enum_class = getattr(column.type, "enum_class", None)
        if enum_class is not None:
            return enum_class(value)
        return value
    return value


def _row_key(model: Any) -> str:
    pk = model.__table__.primary_key.columns.keys()[0]
    return str(pk)


def _export_rows(model: Any) -> list[dict[str, Any]]:
    pk = _row_key(model)
    query = model.query.order_by(getattr(model, pk).asc())
    if hasattr(model, "created_at"):
        query = model.query.order_by(model.created_at.asc(), getattr(model, pk).asc())
    rows = []
    for obj in query.all():
        row = {}
        for column in model.__table__.columns:
            row[column.name] = _serialise_value(column, getattr(obj, column.name))
        rows.append(row)
    return rows


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def table_fingerprint(rows: list[dict[str, Any]]) -> str:
    """Stable hash of a table's exported rows (order-independent)."""
    ordered = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, default=str))
    return hashlib.sha256(_canonical(ordered)).hexdigest()


def export_site() -> dict:
    """Export every table. Returns the bundle dict (manifest + data)."""
    data = {model.__tablename__: _export_rows(model) for model in EXPORT_TABLES}
    manifest = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "app_version": _app_version(),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "scope": "site",
        "tables": {name: len(rows) for name, rows in data.items()},
        "fingerprints": {name: table_fingerprint(rows) for name, rows in data.items()},
    }
    bundle = {"manifest": manifest, "data": data}
    return rescope_bundle(bundle, "site")


def rescope_bundle(bundle: dict[str, Any], scope: str, **extra: Any) -> dict[str, Any]:
    """Relabel a bundle's manifest scope and recompute its checksum."""
    bundle["manifest"]["scope"] = scope
    bundle["manifest"].update(extra)
    bundle["manifest"]["checksum"] = hashlib.sha256(
        _canonical(
            {
                "manifest": {
                    k: v for k, v in bundle["manifest"].items() if k != "checksum"
                },
                "data": bundle["data"],
            }
        )
    ).hexdigest()
    return bundle


def verify_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Raise on bad checksum or version. Returns the manifest."""
    manifest: dict[str, Any] = dict(bundle.get("manifest", {}))
    if manifest.get("export_schema_version") != EXPORT_SCHEMA_VERSION:
        raise BackupVersionError(
            f"unsupported export_schema_version={manifest.get('export_schema_version')!r}, "
            f"expected {EXPORT_SCHEMA_VERSION}"
        )
    expected = manifest.get("checksum")
    actual = hashlib.sha256(
        _canonical(
            {
                "manifest": {k: v for k, v in manifest.items() if k != "checksum"},
                "data": bundle.get("data", {}),
            }
        )
    ).hexdigest()
    if expected != actual:
        raise BackupIntegrityError(
            "bundle checksum mismatch: file is corrupt or tampered with"
        )
    return manifest


def write_bundle(bundle: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, sort_keys=True)


def read_bundle(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupIntegrityError(f"cannot read bundle {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise BackupIntegrityError(f"bundle {path} is not a JSON object")
    verify_bundle(loaded)
    return loaded


def _wipe_all() -> None:
    for model in reversed(EXPORT_TABLES):
        db.session.query(model).delete()
    db.session.flush()


def _import_rows(model: Any, rows: list[dict[str, Any]]) -> None:
    columns = {c.name: c for c in model.__table__.columns}
    for row in rows:
        obj = model()
        for name, value in row.items():
            if name in columns:
                setattr(obj, name, _deserialise_value(columns[name], value))
        db.session.add(obj)
    db.session.flush()


def _recompute_counters() -> None:
    """Vote/comment listeners fire on insert, so recompute stored counters.

    Counters must be recomputed absolutely: idea rows are imported with
    their stored counts and every re-inserted vote/comment fires its
    listener on top, double-counting.
    """
    for idea in Idea.query.all():
        if hasattr(idea, "update_vote_counts"):
            idea.update_vote_counts()
        idea.comments_count = Comment.query.filter(
            Comment.idea_id == idea.id,
            Comment.parent_id.is_(None),
            Comment.is_deleted.is_(False),
        ).count()
    db.session.flush()


def _reset_client_defaults(model: Any, rows: list[dict[str, Any]]) -> None:
    """Restore `onupdate` columns (e.g. `updated_at`) to exported values.

    Listener and counter Core UPDATEs trigger client-side `onupdate`
    defaults, stamping "now" over the exported values. A backup must
    reproduce the database exactly, so reset those columns explicitly —
    an explicit value suppresses the `onupdate` default.
    """
    pk = _row_key(model)
    columns = {c.name: c for c in model.__table__.columns}
    drifted = [
        c for c in model.__table__.columns if c.onupdate is not None and c.name != pk
    ]
    if not drifted:
        return
    for row in rows:
        values = {
            c.name: _deserialise_value(c, row[c.name]) for c in drifted if c.name in row
        }
        if values:
            db.session.execute(
                model.__table__.update()
                .where(columns[pk] == _deserialise_value(columns[pk], row[pk]))
                .values(**values)
            )
    db.session.flush()


def restore_site(bundle: dict[str, Any]) -> dict[str, int]:
    """Verify, wipe and re-import a bundle. Returns per-table row counts."""
    verify_bundle(bundle)
    data: dict[str, Any] = dict(bundle["data"])
    _wipe_all()
    for model in EXPORT_TABLES:
        _import_rows(model, data.get(model.__tablename__, []))
    _recompute_counters()
    for model in EXPORT_TABLES:
        _reset_client_defaults(model, data.get(model.__tablename__, []))
    db.session.commit()
    return {
        model.__tablename__: len(data.get(model.__tablename__, []))
        for model in EXPORT_TABLES
    }


def fingerprint_db() -> dict[str, str]:
    """Per-table fingerprints of the live database (for zero-diff checks)."""
    return {
        model.__tablename__: table_fingerprint(_export_rows(model))
        for model in EXPORT_TABLES
    }
