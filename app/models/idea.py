import json
import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.enums import IdeaStatus
from app.models.types import GUID


class Idea(db.Model):
    __tablename__ = "ideas"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(), db.ForeignKey("instances.id"), nullable=True, index=True
    )
    reference_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    prompt_title = db.Column(db.String(200), nullable=False)
    raw_content = db.Column(db.Text, nullable=False)
    # NOTE: plain JSON column (no MutableDict). Never mutate the loaded dict
    # in place and reassign it — SQLAlchemy then compares new-vs-mutated
    # (equal) and silently skips the UPDATE. Always build a fresh dict.
    structured_content = db.Column(db.JSON)
    status = db.Column(
        db.Enum(IdeaStatus), default=IdeaStatus.NEW, nullable=False, index=True
    )

    # Cached voting metrics
    upvotes_count = db.Column(db.Integer, default=0, nullable=False)
    downvotes_count = db.Column(db.Integer, default=0, nullable=False)
    comments_count = db.Column(db.Integer, default=0, nullable=False)
    net_score = db.Column(db.Integer, default=0, nullable=False, index=True)

    # Feasibility score (from secondary evaluator)
    feasibility_score = db.Column(db.Float)

    # Embedding for similarity search (JSON array of floats)
    embedding = db.Column(db.JSON)

    # Foreign keys
    prompt_config_id = db.Column(GUID(), db.ForeignKey("prompt_configs.id"), index=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    votes = db.relationship(
        "Vote", backref="idea", lazy="dynamic", cascade="all, delete-orphan"
    )
    comments = db.relationship(
        "Comment", backref="idea", lazy="dynamic", cascade="all, delete-orphan"
    )
    actions = db.relationship(
        "SecondaryActionResult",
        backref="idea",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    status_history = db.relationship(
        "IdeaStatusHistory",
        backref="idea",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def excerpt(self, limit: int = 200) -> str:
        """Readable one-liner: prefers a structured pitch over a raw dump.

        Generated content is usually a JSON blob, so truncating raw text
        yields '{"elevator_pitch": "...' padding. Parse first, then cut.
        """
        text = (self.raw_content or "").strip()
        if text.startswith("{"):
            try:
                obj = json.loads(text)
            except (ValueError, TypeError):
                obj = None
            if isinstance(obj, dict):
                for key in (
                    "elevator_pitch",
                    "summary",
                    "pitch",
                    "description",
                    "overview",
                    "tagline",
                ):
                    value = obj.get(key)
                    if isinstance(value, str) and value.strip():
                        clean = value.strip()
                        return clean[:limit] + ("..." if len(clean) > limit else "")
        return text[:limit] + ("..." if len(text) > limit else "")

    def to_dict(self, include_content: bool = False, user_vote: int | None = None):
        data = {
            "id": str(self.id),
            "reference_code": self.reference_code,
            "prompt_title": self.prompt_title,
            "summary": self.excerpt(),
            "status": self.status.value,
            "net_votes": self.net_score,
            "upvotes_count": self.upvotes_count,
            "downvotes_count": self.downvotes_count,
            "feasibility_score": self.feasibility_score,
            "prompt_config_id": (
                str(self.prompt_config_id) if self.prompt_config_id else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "actions_run": [a.action_type for a in self.actions],
        }
        if user_vote is not None:
            data["user_vote"] = user_vote
        data["comments_count"] = self.comments_count
        if include_content:
            data["content"] = self.raw_content
            data["structured_content"] = self.structured_content
        return data

    def update_vote_counts(self):
        """Recalculate vote counts from votes table."""
        from sqlalchemy import func

        from app.models.vote import Vote

        counts = (
            db.session.query(
                func.count(Vote.id).filter(Vote.value == 1),
                func.count(Vote.id).filter(Vote.value == -1),
                func.coalesce(func.sum(Vote.value), 0),
            )
            .filter(Vote.idea_id == self.id)
            .first()
        )
        self.upvotes_count = counts[0] or 0
        self.downvotes_count = counts[1] or 0
        self.net_score = counts[2] or 0

    @property
    def actions_run(self):
        """List of action types that have been run on this idea."""
        return [a.action_type for a in self.actions]

    def __repr__(self):
        return f"<Idea {self.reference_code}>"
