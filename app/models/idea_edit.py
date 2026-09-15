import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class IdeaEdit(db.Model):
    """Audit trail of admin content edits (PRD §10.2)."""

    __tablename__ = "idea_edits"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    idea_id = db.Column(GUID(), db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    editor_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    field = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    edited_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self, editor_name=None):
        return {
            "id": str(self.id),
            "idea_id": str(self.idea_id),
            "editor_id": str(self.editor_id),
            "editor": editor_name,
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
        }

    def __repr__(self):
        return f"<IdeaEdit {self.idea_id} {self.field}>"
