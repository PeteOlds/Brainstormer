import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class Release(db.Model):
    """A named batch of child ideas (fixes/enhancements) for one SCALE parent.

    Children are completed together via the bulk-status path; the release
    row itself only tracks planning state, never idea lifecycle.
    """

    __tablename__ = "releases"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(), db.ForeignKey("instances.id"), nullable=True, index=True
    )
    parent_idea_id = db.Column(
        GUID(),
        db.ForeignKey("ideas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default="planned", nullable=False)
    target_date = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by_id = db.Column(
        GUID(), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # GitHub push state: once a SHA is recorded the release cannot be
    # re-committed — further updates need a new release.
    github_sha = db.Column(db.String(64), nullable=True)
    github_pushed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    # Plain-language "what shipped", auto-written when the release
    # completes (deterministic template, no AI) and admin-editable after.
    notes = db.Column(db.Text, nullable=True)
    # When the release was marked done — the Release Date shown beside
    # the name and inside the notes.
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self, child_count: int = 0):
        from app.models import Idea

        parent = Idea.query.get(self.parent_idea_id) if self.parent_idea_id else None
        from app.services.release_notes import release_notes_path

        path = release_notes_path(self, parent)
        return {
            "id": str(self.id),
            "parent_idea_id": str(self.parent_idea_id),
            "name": self.name,
            "status": self.status,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "child_count": child_count,
            "notes": self.notes,
            "notes_path": str(path),
            "notes_file": path.name,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "github_sha": self.github_sha,
            "github_pushed_at": (
                self.github_pushed_at.isoformat() if self.github_pushed_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Release {self.name} parent={self.parent_idea_id}>"


RELEASE_STATUSES = frozenset({"planned", "in_progress", "done"})
CHILD_KINDS = frozenset({"enhancement", "bugfix"})
