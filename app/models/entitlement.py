"""Billing entitlements framework (Phase 8).

Payment provider and pricing are still unconfirmed, so entitlements are
assigned by Site Admins (API/CLI), not sold. The framework is real:
`resolve_entitlements()` maps an instance to its granted keys (stored
rows win; otherwise the Free flag decides the baseline set), and
`require_entitlement()` enforces gates. Only `hosted_ai` is enforced
in code today; chat/extra_guides/custom_deploy resolve and are managed
for future wiring. Start/End dates stay recorded-but-unenforced (open
item); `status != active` already blocks writes.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models.types import GUID

ENTITLEMENTS = ("core", "hosted_ai", "chat", "extra_guides", "custom_deploy")

# Baseline sets while billing is manual. Paid instances get everything;
# free instances get the core local product.
FREE_BASELINE = ("core",)
PAID_BASELINE = ("core", "hosted_ai", "chat", "extra_guides", "custom_deploy")


class EntitlementError(Exception):
    def __init__(self, key: str):
        super().__init__(
            f"Instance is not entitled to '{key}'. Contact your administrator."
        )
        self.key = key


class InstanceEntitlement(db.Model):
    __tablename__ = "instance_entitlements"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(),
        db.ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = db.Column(db.String(40), nullable=False)
    granted = db.Column(db.Boolean, default=True, nullable=False)
    limits = db.Column(db.JSON, default=dict)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint("instance_id", "key", name="uq_instance_entitlement"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "instance_id": str(self.instance_id),
            "key": self.key,
            "granted": self.granted,
            "limits": dict(self.limits or {}),
        }

    def __repr__(self):
        return f"<Entitlement {self.instance_id}:{self.key}={self.granted}>"


def resolve_entitlements(instance: Any) -> set:
    """Granted keys: Free-flag baseline plus stored overrides.

    Stored rows layer on top (grants add, revocations remove), so a
    single grant never silently drops the baseline set.
    """
    if instance is None:
        return set(PAID_BASELINE)  # Legacy unscoped path keeps full access.
    granted = set(PAID_BASELINE if not instance.is_free else FREE_BASELINE)
    rows = InstanceEntitlement.query.filter_by(instance_id=instance.id).all()
    for row in rows:
        if row.granted:
            granted.add(row.key)
        else:
            granted.discard(row.key)
    return granted


def require_entitlement(instance_id: Any, key: str) -> None:
    """Raise EntitlementError unless the instance holds the key."""
    from app.models import Instance

    if instance_id is None:
        return
    instance = db.session.get(Instance, instance_id)
    if instance is None:
        raise EntitlementError(key)
    if getattr(instance, "status", "active") != "active":
        raise EntitlementError(key)
    if key not in resolve_entitlements(instance):
        raise EntitlementError(key)
