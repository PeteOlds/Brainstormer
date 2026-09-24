import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID
from sqlalchemy import event


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


@event.listens_for(Vote, "after_insert")
def _increment_vote_counts(mapper, connection, target):
    from app.models import Idea
    from app.extensions import db
    # Increment the appropriate count directly
    db.session.execute(
        Idea.__table__.update()
        .where(Idea.id == target.idea_id)
        .values(
            upvotes_count=Idea.upvotes_count + (1 if target.value > 0 else 0),
            downvotes_count=Idea.downvotes_count + (1 if target.value < 0 else 0),
            net_score=Idea.net_score + target.value
        )
    )


@event.listens_for(Vote, "after_delete")
def _decrement_vote_counts(mapper, connection, target):
    from app.models import Idea
    from app.extensions import db
    # Decrement the appropriate count directly
    db.session.execute(
        Idea.__table__.update()
        .where(Idea.id == target.idea_id)
        .values(
            upvotes_count=Idea.upvotes_count - (1 if target.value > 0 else 0),
            downvotes_count=Idea.downvotes_count - (1 if target.value < 0 else 0),
            net_score=Idea.net_score - target.value
        )
    )


@event.listens_for(Vote, "after_update")
def _update_vote_counts_on_update(mapper, connection, target):
    from app.models import Idea
    from app.extensions import db
    from sqlalchemy.orm.attributes import get_history
    # Only update if the vote value changed
    try:
        history = get_history(target, "value")
        if history.has_changes():
            old_value = history.deleted[0] if history.deleted else 0
            new_value = target.value
            diff = new_value - old_value
            db.session.execute(
                Idea.__table__.update()
                .where(Idea.id == target.idea_id)
                .values(
                    upvotes_count=Idea.upvotes_count + (1 if diff > 0 and new_value > 0 else -1 if diff < 0 and old_value > 0 else 0),
                    downvotes_count=Idea.downvotes_count + (1 if diff > 0 and new_value < 0 else -1 if diff < 0 and old_value < 0 else 0),
                    net_score=Idea.net_score + diff
                )
            )
    except Exception:
        pass