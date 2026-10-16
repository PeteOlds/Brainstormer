"""Per-release AI configuration (Scale-phase releases).

A release may override provider, model, generation params and default
skills/guidelines for every idea in it. Resolution order everywhere:
explicit run arguments > release config > stage config > prompt values >
hardcoded defaults. Instances/releases without rows behave exactly as
before.
"""

import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class ReleaseAIConfig(db.Model):
    __tablename__ = "release_ai_configs"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    release_id = db.Column(
        GUID(),
        db.ForeignKey("releases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = db.Column(db.String(20), nullable=True)
    model_name = db.Column(db.String(100), nullable=True)
    temperature = db.Column(db.Float, nullable=True)
    top_p = db.Column(db.Float, nullable=True)
    num_predict = db.Column(db.Integer, nullable=True)
    skills = db.Column(db.JSON, default=list)
    guidelines = db.Column(db.JSON, default=list)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (db.UniqueConstraint("release_id", name="uq_release_ai_config"),)

    def to_dict(self):
        return {
            "id": str(self.id),
            "release_id": str(self.release_id),
            "provider": self.provider,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "num_predict": self.num_predict,
            "skills": list(self.skills or []),
            "guidelines": list(self.guidelines or []),
        }

    def __repr__(self):
        return f"<ReleaseAIConfig {self.release_id}>"


def resolve_release(idea) -> dict:
    """Merged release settings for one idea (only keys the admin set).

    Empty when the idea is not in a release or the release has no row.
    """
    if idea is None or getattr(idea, "release_id", None) is None:
        return {}
    row = ReleaseAIConfig.query.filter_by(release_id=idea.release_id).first()
    if row is None:
        return {}
    merged = {}
    if row.provider:
        merged["provider"] = row.provider
    if row.model_name:
        merged["model_name"] = row.model_name
    if row.temperature is not None:
        merged["temperature"] = row.temperature
    if row.top_p is not None:
        merged["top_p"] = row.top_p
    if row.num_predict is not None:
        merged["num_predict"] = row.num_predict
    if row.skills:
        merged["skills"] = list(row.skills)
    if row.guidelines:
        merged["guidelines"] = list(row.guidelines)
    return merged
