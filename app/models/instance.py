"""Multi-tenancy: instances and memberships (Phase 1).

One shared `users` table; access to an instance comes from a `memberships`
row. Roles are plain strings (not a Postgres enum) so future roles
(Developer, Deployment, BA, ...) need no migration.

`instance_id = NULL` on a membership is a site-wide grant. Only
`SITE_ADMIN` uses it.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models.types import GUID

ROLE_SITE_ADMIN = "SITE_ADMIN"
ROLE_INSTANCE_ADMIN = "INSTANCE_ADMIN"
ROLE_USER = "USER"

MEMBER_ROLES = (ROLE_SITE_ADMIN, ROLE_INSTANCE_ADMIN, ROLE_USER)

# Instance numbers 2-19 are reserved for future testing (Instance 5 holds
# the migrated production data). The API refuses to create them.
RESERVED_INSTANCE_NUMBERS = set(range(2, 20)) - {5}


class Instance(db.Model):
    __tablename__ = "instances"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    # Human-facing number: 1 = template, 5 = migrated production data,
    # >= 20 = new. 2-19 (except 5) are reserved.
    number = db.Column(db.Integer, unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.DateTime(timezone=True), nullable=True)
    end_date = db.Column(db.DateTime(timezone=True), nullable=True)
    # Placeholders in V2: stored, not enforced.
    is_free = db.Column(db.Boolean, default=True, nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)
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

    memberships = db.relationship(
        "Membership", backref="instance", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "number": self.number,
            "name": self.name,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_free": self.is_free,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Instance {self.number}:{self.name}>"


class Membership(db.Model):
    __tablename__ = "memberships"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        GUID(),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NULL = site-wide grant (SITE_ADMIN only).
    instance_id = db.Column(
        GUID(),
        db.ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    role = db.Column(db.String(20), default=ROLE_USER, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "instance_id", name="uq_membership_user_instance"
        ),
    )

    user = db.relationship(
        "User",
        backref=db.backref("memberships", lazy="dynamic", cascade="all, delete-orphan"),
    )

    @classmethod
    def get_role(cls, user_id: Any, instance_id: Any) -> str | None:
        """Membership role for (user, instance), or None."""
        row = cls.query.filter_by(user_id=user_id, instance_id=instance_id).first()
        return row.role if row else None

    @classmethod
    def is_site_admin(cls, user_id) -> bool:
        return (
            cls.query.filter_by(
                user_id=user_id, instance_id=None, role=ROLE_SITE_ADMIN
            ).first()
            is not None
        )

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "instance_id": str(self.instance_id) if self.instance_id else None,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Membership {self.user_id}@{self.instance_id}:{self.role}>"
