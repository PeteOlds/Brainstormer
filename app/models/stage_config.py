"""Per-stage AI configuration (Spark/Scope/Map/Ship/Scale).

Each stage of an instance may override the provider, model, generation
params and default skills/guidelines. Resolution order everywhere:
explicit run arguments > stage config > prompt values > hardcoded
defaults. Instances without rows behave exactly as before.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models.types import GUID

STAGES = ("SPARK", "SCOPE", "MAP", "SHIP", "SCALE")


class StageAIConfig(db.Model):
    __tablename__ = "stage_ai_configs"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(),
        db.ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage = db.Column(db.String(20), nullable=False)
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

    __table_args__ = (
        db.UniqueConstraint("instance_id", "stage", name="uq_instance_stage"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "instance_id": str(self.instance_id),
            "stage": self.stage,
            "provider": self.provider,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "num_predict": self.num_predict,
            "skills": list(self.skills or []),
            "guidelines": list(self.guidelines or []),
        }

    def __repr__(self):
        return f"<StageAIConfig {self.instance_id}:{self.stage}>"


def resolve_stage(instance_id: Any, stage: Any) -> dict:
    """Merged stage settings (only keys the admin set). Empty when unconfigured."""
    if instance_id is None or not stage:
        return {}
    row = StageAIConfig.query.filter_by(instance_id=instance_id, stage=stage).first()
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
