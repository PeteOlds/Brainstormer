import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    idea_id = db.Column(GUID(), db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = db.Column(GUID(), db.ForeignKey("comments.id"), nullable=True, index=True)
    body = db.Column(db.Text, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Self-referential thread; children keep parent row (soft-delete stub).
    replies = db.relationship(
        "Comment",
        backref=db.backref("parent", remote_side=[id]),
        cascade="all, delete-orphan",
        single_parent=True,
        lazy="dynamic",
    )

    def to_dict(self, author_name=None, children=None):
        return {
            "id": str(self.id),
            "idea_id": str(self.idea_id),
            "user_id": str(self.user_id),
            "author": author_name,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "body": "[deleted]" if self.is_deleted else self.body,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "replies": children or [],
        }

    def __repr__(self):
        return f"<Comment {self.id} idea={self.idea_id} parent={self.parent_id}>"
