"""In-app messages (Phase 4: Talk).

Users message instance admins (feedback, screenshots described in text);
admins message members or forward feedback to the site admin. Read
timestamps drive the unread badge on the user homepage. Optional
idea/comment links ride along so a message can point at the exact
thing ("share links").
"""

import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(), db.ForeignKey("instances.id"), nullable=True, index=True
    )
    sender_id = db.Column(
        GUID(),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_id = db.Column(
        GUID(),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body = db.Column(db.Text, nullable=False)
    idea_id = db.Column(
        GUID(), db.ForeignKey("ideas.id", ondelete="SET NULL"), nullable=True
    )
    comment_id = db.Column(
        GUID(), db.ForeignKey("comments.id", ondelete="SET NULL"), nullable=True
    )
    read_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    sender = db.relationship("User", foreign_keys="Message.sender_id", viewonly=True)
    recipient = db.relationship(
        "User", foreign_keys="Message.recipient_id", viewonly=True
    )

    def to_dict(self, base_url=""):
        data = {
            "id": str(self.id),
            "sender_id": str(self.sender_id),
            "sender": (self.sender.name or self.sender.email) if self.sender else None,
            "recipient_id": str(self.recipient_id),
            "recipient": (
                (self.recipient.name or self.recipient.email)
                if self.recipient
                else None
            ),
            "body": self.body,
            "idea_id": str(self.idea_id) if self.idea_id else None,
            "comment_id": str(self.comment_id) if self.comment_id else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        link = None
        if base_url:
            if self.comment_id:
                link = f"{base_url}/ideas?comment={self.comment_id}"
            elif self.idea_id:
                link = f"{base_url}/ideas?idea={self.idea_id}"
        data["link"] = link
        return data

    def __repr__(self):
        return f"<Message {self.id} {self.sender_id}->{self.recipient_id}>"
