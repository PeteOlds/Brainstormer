import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class SitePrompt(db.Model):  # type: ignore[name-defined]
    """Site-wide override for a shared internal AI prompt.

    A row means "overridden"; absence means use the shipped template file.
    Never scoped by instance — only Site Administrators may maintain these.
    """

    __tablename__ = "site_prompts"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    key = db.Column(db.String(60), nullable=False, unique=True, index=True)
    body = db.Column(db.Text, nullable=False)
    created_by_id = db.Column(
        GUID(), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
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

    created_by = db.relationship("User", foreign_keys=[created_by_id])

    def to_dict(self):
        return {
            "id": str(self.id),
            "key": self.key,
            "body": self.body,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
