"""Instance build targets: named server-side repos code builds write into."""

import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class InstanceBuildTarget(db.Model):
    """A repo an instance admin registered for BUILD_CODE runs.

    ``path`` is server-side (worker-visible). Creation and every write
    confine it under ``OPENCODE_BUILD_ROOTS``; see
    ``app.services.build_service``.
    """

    __tablename__ = "instance_build_targets"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(),
        db.ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    path = db.Column(db.Text, nullable=False)
    created_by_id = db.Column(GUID(), db.ForeignKey("users.id"), nullable=True)
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
        db.UniqueConstraint("instance_id", "name", name="uq_target_instance_name"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "instance_id": str(self.instance_id),
            "name": self.name,
            "path": self.path,
            "created_by_id": str(self.created_by_id) if self.created_by_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<BuildTarget {self.instance_id}:{self.name}>"
