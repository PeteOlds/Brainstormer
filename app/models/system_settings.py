import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class SystemSettings(db.Model):
    """Singleton model for system-wide settings."""

    __tablename__ = "system_settings"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    platform = db.Column(db.JSON, default={})
    location = db.Column(db.JSON, default={})
    ai_connections = db.Column(db.JSON, default={})
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    @classmethod
    def get_instance(cls):
        """Get or create the singleton settings instance."""
        settings = cls.query.first()
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