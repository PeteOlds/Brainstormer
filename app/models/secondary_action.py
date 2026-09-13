import uuid
from datetime import datetime, timezone
from enum import Enum

from app.extensions import db
from app.models.types import GUID


class ActionType(str, Enum):
    REFINE = "REFINE"
    COMPETITORS = "COMPETITORS"
    FEASIBILITY_SCORE = "FEASIBILITY_SCORE"


class SecondaryActionResult(db.Model):
    __tablename__ = "secondary_action_results"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    idea_id = db.Column(GUID(), db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = db.Column(db.Enum(ActionType), nullable=False)
    model_used = db.Column(db.String(100), nullable=False)
    result_data = db.Column(db.JSON, nullable=False)
    executed_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "idea_id": str(self.idea_id),
            "action_type": self.action_type.value,
            "model_used": self.model_used,
            "output": self.result_data,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }

    def __repr__(self):
        return f"<SecondaryActionResult {self.action_type} for idea {self.idea_id}>"