import uuid
from datetime import datetime, timezone
from enum import Enum

from app.extensions import db
from app.models.types import GUID


class IdeaStatus(str, Enum):
    NEW = "NEW"
    CONSIDERATION = "CONSIDERATION"
    DISCARDED = "DISCARDED"


class IdeaStatusHistory(db.Model):
    __tablename__ = "idea_status_history"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    idea_id = db.Column(GUID(), db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    old_status = db.Column(db.Enum(IdeaStatus), nullable=False)
    new_status = db.Column(db.Enum(IdeaStatus), nullable=False)
    changed_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Relationships
    changed_by = db.relationship("User", foreign_keys=[changed_by_id])

    def to_dict(self):
        return {
            "id": str(self.id),
            "idea_id": str(self.idea_id),
            "changed_by_id": str(self.changed_by_id),
            "old_status": self.old_status.value,
            "new_status": self.new_status.value,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
        }

    def __repr__(self):
        return f"<IdeaStatusHistory {self.old_status} -> {self.new_status} for idea {self.idea_id}>"