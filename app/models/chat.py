"""Chat-to-AI sessions and turns (Phase 4).

Every turn persists who/when/model/phase plus a content hash; message
bodies live in the database (needed for history and rollback) while
logs carry hashes only. Iterate turns snapshot the idea's editable
fields before/after so any version can be restored with full audit.
"""

import hashlib
import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID

CHAT_ROLES = ("user", "assistant", "system")
CHAT_KINDS = ("chat", "iterate", "rollback")


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class ChatSession(db.Model):
    __tablename__ = "chat_sessions"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(), db.ForeignKey("instances.id"), nullable=True, index=True
    )
    idea_id = db.Column(
        GUID(),
        db.ForeignKey("ideas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        GUID(),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase = db.Column(db.String(20), nullable=True)
    model_used = db.Column(db.String(100), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    turns = db.relationship(
        "ChatTurn", backref="session", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self, include_turns=False):
        data = {
            "id": str(self.id),
            "idea_id": str(self.idea_id),
            "user_id": str(self.user_id),
            "phase": self.phase,
            "model_used": self.model_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_turns:
            data["turns"] = [
                t.to_dict()
                for t in ChatTurn.query.filter_by(session_id=self.id)
                .order_by(ChatTurn.created_at.asc())
                .all()
            ]
        return data

    def __repr__(self):
        return f"<ChatSession {self.id} idea={self.idea_id}>"


class ChatTurn(db.Model):
    __tablename__ = "chat_turns"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(), db.ForeignKey("instances.id"), nullable=True, index=True
    )
    session_id = db.Column(
        GUID(),
        db.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = db.Column(db.String(10), nullable=False)
    kind = db.Column(db.String(20), default="chat", nullable=False)
    content = db.Column(db.Text, nullable=False)
    content_hash = db.Column(db.String(64), nullable=False)
    snapshot_before = db.Column(db.JSON, nullable=True)
    snapshot_after = db.Column(db.JSON, nullable=True)
    model_used = db.Column(db.String(100), nullable=True)
    prompt_tokens = db.Column(db.Integer, default=0, nullable=False)
    completion_tokens = db.Column(db.Integer, default=0, nullable=False)
    cost_cents = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "role": self.role,
            "kind": self.kind,
            "content": self.content,
            "content_hash": self.content_hash,
            "has_snapshot": self.snapshot_before is not None,
            "model_used": self.model_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_cents": self.cost_cents,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<ChatTurn {self.role}:{self.kind} session={self.session_id}>"
