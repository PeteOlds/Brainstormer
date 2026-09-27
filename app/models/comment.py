import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID
from sqlalchemy import event


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    idea_id = db.Column(GUID(), db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = db.Column(GUID(), db.ForeignKey("comments.id"), nullable=True, index=True)
    body = db.Column(db.Text, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    # Document scope: 'idea' (default, whole-idea thread) or a follow-up
    # document thread bound to one SecondaryActionResult version.
    scope = db.Column(db.String(20), default="idea", nullable=False)
    action_result_id = db.Column(GUID(), db.ForeignKey("secondary_action_results.id", ondelete="CASCADE"), nullable=True, index=True)
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
            "scope": self.scope,
            "action_result_id": str(self.action_result_id) if self.action_result_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "replies": children or [],
        }

    def __repr__(self):
        return f"<Comment {self.id} idea={self.idea_id} parent={self.parent_id}>"


@event.listens_for(Comment, "after_insert")
def _increment_comment_count(mapper, connection, target):
    from app.models import Idea
    from app.extensions import db
    # Only count top-level comments (not replies) and non-deleted
    if not target.parent_id and not target.is_deleted:
        db.session.execute(
            Idea.__table__.update()
            .where(Idea.id == target.idea_id)
            .values(comments_count=Idea.comments_count + 1)
        )


@event.listens_for(Comment, "after_delete")
def _decrement_comment_count(mapper, connection, target):
    from app.models import Idea
    from app.extensions import db
    # Only count top-level comments (not replies)
    if not target.parent_id:
        db.session.execute(
            Idea.__table__.update()
            .where(Idea.id == target.idea_id)
            .values(comments_count=Idea.comments_count - 1)
        )


@event.listens_for(Comment, "before_update")
def _handle_soft_delete(mapper, connection, target):
    from app.models import Idea
    from app.extensions import db
    from sqlalchemy.orm.attributes import get_history
    # Handle soft-delete: if is_deleted changed from False to True
    try:
        history = get_history(target, "is_deleted")
        if history.has_changes() and history.added and history.added[0] is True:
            if target.is_deleted and not target.parent_id:
                db.session.execute(
                    Idea.__table__.update()
                    .where(Idea.id == target.idea_id)
                    .values(comments_count=Idea.comments_count - 1)
                )
    except Exception:
        pass  # Ignore history errors for detached instances


@event.listens_for(Comment, "before_update")
def _handle_soft_restore(mapper, connection, target):
    from app.models import Idea
    from app.extensions import db
    from sqlalchemy.orm.attributes import get_history
    # Handle soft-restore: if is_deleted changed from True to False
    try:
        history = get_history(target, "is_deleted")
        if history.has_changes() and history.deleted and history.deleted[0] is True:
            if not target.is_deleted and not target.parent_id:
                db.session.execute(
                    Idea.__table__.update()
                    .where(Idea.id == target.idea_id)
                    .values(comments_count=Idea.comments_count + 1)
                )
    except Exception:
        pass  # Ignore history errors for detached instances
