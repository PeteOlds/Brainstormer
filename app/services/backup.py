"""Site and instance backup, export and restore (Phases 0 + 6).

Versioned JSON bundles with a manifest and a SHA-256 checksum. Site
bundles round-trip the whole database; instance bundles carry one
instance's rows plus its members (sessions and global event ids are
excluded by design). Encrypted blobs travel as-is: restoring requires
the same FERNET_KEY.
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
    ChatSession,
    ChatTurn,
    Comment,
    Idea,
    IdeaEdit,
    IdeaStatusHistory,
    Instance,
    InstanceAIConfig,
    InstanceEntitlement,
    Membership,
    OAuthIdentity,
    PromptConfig,
    PromptRun,
    RefreshToken,
    SecondaryActionResult,
    SlackEvent,
    SlackPost,
    SystemSettings,
    TenantOAuthConfig,
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
    OAuthIdentity,
    TenantOAuthConfig,
    InstanceAIConfig,
    InstanceEntitlement,
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
    ChatSession,
    ChatTurn,
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


def _export_rows(model: Any, instance_id: Any = None) -> list[dict[str, Any]]:
    pk = _row_key(model)
    query = model.query.order_by(getattr(model, pk).asc())
    if hasattr(model, "created_at"):
        query = model.query.order_by(model.created_at.asc(), getattr(model, pk).asc())
    if instance_id is not None and "instance_id" in model.__table__.columns:
        query = query.filter(model.instance_id == instance_id)
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


# Tables carrying instance_id (tenant-scoped). Everything else is global:
# users + oauth identities travel by reference (members and authors),
# refresh tokens never export (sessions are re-established by login),
# slack event ids are global idempotency keys.
USER_REF_FIELDS = (
    "user_id",
    "created_by_id",
    "changed_by_id",
    "editor_id",
    "edited_by_id",
)


def _tenant_models() -> list:
    return [m for m in EXPORT_TABLES if "instance_id" in m.__table__.columns]


def export_instance(instance_id: Any) -> dict:
    """Export one instance: its row, tenant rows, memberships, member users.

    Refresh tokens and slack events are intentionally excluded (see above).
    """
    from app.models import Instance

    instance = db.session.get(Instance, instance_id)
    if instance is None:
        raise BackupIntegrityError(f"Unknown instance: {instance_id}.")
    data = _export_instance_tables(instance)
    manifest = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "app_version": _app_version(),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "scope": "instance",
        "instance_id": str(instance_id),
        "instance_number": instance.number,
        "tables": {name: len(rows) for name, rows in data.items()},
        "fingerprints": {name: table_fingerprint(rows) for name, rows in data.items()},
    }
    bundle = {"manifest": manifest, "data": data}
    return rescope_bundle(
        bundle,
        "instance",
        instance_id=str(instance_id),
        instance_number=instance.number,
    )


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


def _recompute_counters(instance_id: Any = None) -> None:
    """Recompute vote/comment counters absolutely (see docstring above).

    Scoped to one instance when given, so restoring an instance bundle
    never dirties other instances' rows.
    """
    query = Idea.query
    if instance_id is not None:
        query = query.filter(Idea.instance_id == instance_id)
    for idea in query.all():
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
    """Verify, wipe and re-import a site bundle. Returns row counts."""
    manifest = verify_bundle(bundle)
    if manifest.get("scope") != "site":
        raise BackupIntegrityError(
            "Not a site bundle (scope != site). Use restore-instance."
        )
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


def fingerprint_instance(instance_id: Any) -> dict[str, str]:
    """Fingerprints of one instance's exported rows (zero-diff checks)."""
    from app.models import Instance

    instance = db.session.get(Instance, instance_id)
    if instance is None:
        raise BackupIntegrityError(f"Unknown instance: {instance_id}.")
    bundle_tables = _export_instance_tables(instance)
    return {name: table_fingerprint(rows) for name, rows in bundle_tables.items()}


def _export_instance_tables(instance: Any) -> dict[str, list]:
    data: dict[str, list] = {}
    for model in EXPORT_TABLES:
        name = model.__tablename__
        if name == "instances":
            rows = _export_rows(model)
            data[name] = [r for r in rows if r["id"] == str(instance.id)]
        elif "instance_id" in model.__table__.columns:
            data[name] = _export_rows(model, instance.id)
        else:
            data[name] = []
    referenced = set()
    for rows in data.values():
        for row in rows:
            for field in USER_REF_FIELDS:
                if row.get(field):
                    referenced.add(str(row[field]))
    member_ids = {r["user_id"] for r in data.get("memberships", [])}
    wanted = referenced | {str(i) for i in member_ids}
    data["users"] = [r for r in _export_rows(User) if r["id"] in wanted]
    data["oauth_identities"] = [
        r for r in _export_rows(OAuthIdentity) if r["user_id"] in wanted
    ]
    return data


def restore_instance(bundle: dict[str, Any]) -> dict[str, int]:
    """Verify and restore one instance bundle (other instances untouched).

    The instance shell is upserted from the bundle, its tenant rows are
    replaced wholesale, and member users/oauth links are upserted (global
    users are never deleted: other instances may share them).
    """
    from app.models import Instance

    manifest = verify_bundle(bundle)
    if manifest.get("scope") != "instance":
        raise BackupIntegrityError("Not an instance bundle (scope != instance).")
    data: dict[str, Any] = dict(bundle["data"])
    instance_id = uuid.UUID(str(manifest["instance_id"]))

    instance_rows = data.get("instances", [])
    if instance_rows:
        row = instance_rows[0]
        instance = db.session.get(Instance, instance_id)
        if instance is None:
            instance = Instance()
            db.session.add(instance)
        columns = {c.name: c for c in Instance.__table__.columns}
        for name, value in row.items():
            if name in columns:
                setattr(instance, name, _deserialise_value(columns[name], value))
        db.session.flush()
    elif db.session.get(Instance, instance_id) is None:
        raise BackupIntegrityError("Bundle names an instance it does not contain.")

    for model in reversed(EXPORT_TABLES):
        name = model.__tablename__
        if name in (
            "instances",
            "users",
            "oauth_identities",
            "refresh_tokens",
            "slack_events",
        ):
            continue
        if "instance_id" in model.__table__.columns:
            db.session.query(model).filter(model.instance_id == instance_id).delete(
                synchronize_session=False
            )
    db.session.flush()

    for model in EXPORT_TABLES:
        name = model.__tablename__
        if name in ("refresh_tokens", "slack_events"):
            continue
        if name in ("instances", "users", "oauth_identities", "memberships"):
            _upsert_rows(model, data.get(name, []))
        elif "instance_id" in model.__table__.columns:
            _import_rows(model, data.get(name, []))
    _recompute_counters(instance_id)
    for model in EXPORT_TABLES:
        _reset_client_defaults(model, data.get(model.__tablename__, []))
    db.session.commit()
    return {name: len(data.get(name, [])) for name in data}


def _upsert_rows(model: Any, rows: list[dict[str, Any]]) -> None:
    """Insert rows, replacing on PK conflict (idempotent restores)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    if not rows:
        return
    columns = {c.name: c for c in model.__table__.columns}
    table = model.__table__
    bind = db.session.get_bind()
    values = [
        {
            name: _deserialise_value(columns[name], value)
            for name, value in row.items()
            if name in columns
        }
        for row in rows
    ]
    if bind.dialect.name == "postgresql":
        pg_base = pg_insert(table).values(values)
        stmt: Any = pg_base.on_conflict_do_update(
            index_elements=[table.c[_row_key(model)]],
            set_={
                c.name: pg_base.excluded[c.name]
                for c in table.columns
                if c.name != _row_key(model)
            },
        )
    else:
        lite_base = sqlite_insert(table).values(values)
        stmt = lite_base.on_conflict_do_update(
            index_elements=[table.c[_row_key(model)]],
            set_={
                c.name: lite_base.excluded[c.name]
                for c in table.columns
                if c.name != _row_key(model)
            },
        )
    db.session.execute(stmt)
    db.session.flush()
