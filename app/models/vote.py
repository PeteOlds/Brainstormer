import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class Vote(db.Model):
    __tablename__ = "votes"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    idea_id = db.Column(GUID(), db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    value = db.Column(db.SmallInteger, nullable=False)  # +1 or -1
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Unique constraint: one vote per user per idea
    __table_args__ = (
        db.UniqueConstraint("user_id", "idea_id", name="uq_user_idea_vote"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "idea_id": str(self.idea_id),
            "value": self.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Vote user={self.user_id} idea={self.idea_id} value={self.value}>"