import uuid
from datetime import datetime, timezone
from enum import Enum

from app.extensions import db
from app.models.types import GUID


class ActionType(str, Enum):
    REFINE = "REFINE"
    COMPETITORS = "COMPETITORS"
    FEASIBILITY_SCORE = "FEASIBILITY_SCORE"
    FIVE_FORCES = "FIVE_FORCES"
    PESTEL = "PESTEL"
    PRD_DOC = "PRD_DOC"
    VRIO = "VRIO"
    THREE_CS = "THREE_CS"
    MARKET_SIZING = "MARKET_SIZING"
    BUSINESS_MODEL_CANVAS = "BUSINESS_MODEL_CANVAS"
    HYPOTHESIS_TEST = "HYPOTHESIS_TEST"
    GTM_STRATEGY = "GTM_STRATEGY"
    DESIGN_DOC = "DESIGN_DOC"


class SecondaryActionResult(db.Model):
    __tablename__ = "secondary_action_results"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    idea_id = db.Column(GUID(), db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = db.Column(db.Enum(ActionType), nullable=False)
    model_used = db.Column(db.String(100), nullable=False)
    result_data = db.Column(db.JSON, nullable=False)
    executed_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    # Document versioning (PRD/DESIGN_DOC): recreate/edit append a new
    # version and flip is_current instead of deleting history, so
    # per-document comment threads stay pinned to their version.
    version = db.Column(db.Integer, default=1, nullable=False)
    is_current = db.Column(db.Boolean, default=True, nullable=False, index=True)
    edited_by_id = db.Column(GUID(), db.ForeignKey("users.id"), nullable=True)
    # Human answers to the previous version's open questions (PRD flow).
    # Stored verbatim so they survive regeneration; NULL when none given.
    answers = db.Column(db.JSON, nullable=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "idea_id": str(self.idea_id),
            "action_type": self.action_type.value,
            "model_used": self.model_used,
            "output": self.result_data,
            "version": self.version,
            "is_current": self.is_current,
            "edited_by_id": str(self.edited_by_id) if self.edited_by_id else None,
            "answers": self.answers or [],
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }

    def __repr__(self):
        return f"<SecondaryActionResult {self.action_type} for idea {self.idea_id}>"