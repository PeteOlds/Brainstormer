import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class SystemSettings(db.Model):
    """Singleton model for system-wide settings."""

    __tablename__ = "system_settings"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(), db.ForeignKey("instances.id"), nullable=True, index=True
    )
    platform = db.Column(db.JSON, default={})
    location = db.Column(db.JSON, default={})
    ai_connections = db.Column(db.JSON, default={})
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

    @classmethod
    def get_instance(cls):
        """Get or create the singleton settings instance.

        Phase 1: prefers the request instance's row when scoped, else the
        legacy global (NULL) row. Per-instance settings UI lands later;
        until then each instance keeps exactly one row.
        """
        try:
            from flask import g, has_request_context

            if has_request_context():
                instance_id = getattr(g, "instance_id", None)
                if instance_id is not None:
                    settings = cls.query.filter_by(instance_id=instance_id).first()
                    if settings:
                        return settings
                    settings = cls(instance_id=instance_id)
                    db.session.add(settings)
                    db.session.flush()
                    return settings
        except Exception:
            pass
        settings = cls.query.filter_by(instance_id=None).first()
        if not settings:
            settings = cls()
            db.session.add(settings)
            db.session.flush()
        return settings

    def to_dict(self):
        return {
            "platform": self.platform or {},
            "location": self.location or {},
            "ai_connections": self.ai_connections or {},
        }

    def update_platform(self, data: dict):
        self.platform = data

    def update_location(self, data: dict):
        self.location = data

    def update_ai_connections(self, data: dict):
        self.ai_connections = data

    def __repr__(self):
        return "<SystemSettings>"
