import uuid
from datetime import datetime, timezone
from enum import Enum

from app.extensions import db
from app.utils.crypto import encrypt, decrypt
from app.models.types import GUID


class PromptStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"


class PromptConfig(db.Model):
    __tablename__ = "prompt_configs"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    title = db.Column(db.String(200), nullable=False)
    _prompt_body = db.Column("prompt_body", db.Text, nullable=False)
    interval_minutes = db.Column(db.Integer, nullable=False)
    cron_expression = db.Column(db.String(100))
    model_name = db.Column(db.String(100), nullable=False)
    temperature = db.Column(db.Float, default=0.7)
    top_p = db.Column(db.Float, default=0.9)
    repeat_penalty = db.Column(db.Float, default=1.1)
    num_predict = db.Column(db.Integer, default=1000)
    seed = db.Column(db.Integer, nullable=True)
    keep_alive = db.Column(db.String(20), default="2h")
    slack_channel = db.Column(db.String(80), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_run_at = db.Column(db.DateTime(timezone=True))
    next_run_at = db.Column(db.DateTime(timezone=True), index=True)
    created_by_id = db.Column(GUID(), db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    ideas = db.relationship("Idea", backref="prompt_config", lazy="dynamic")

    @property
    def prompt_body(self) -> str:
        """Decrypt prompt body when accessed."""
        if self._prompt_body:
            return decrypt(self._prompt_body)
        return ""

    @prompt_body.setter
    def prompt_body(self, value: str):
        """Encrypt prompt body when set."""
        self._prompt_body = encrypt(value) if value else ""

    def run_stats(self) -> dict:
        """Aggregate run history: counts, pending flag, last outcome."""
        from app.models.prompt_run import PromptRun, PromptRunStatus

        total = PromptRun.query.filter_by(prompt_config_id=self.id).count()
        failures = PromptRun.query.filter_by(
            prompt_config_id=self.id, status=PromptRunStatus.FAILED).count()
        pending = PromptRun.query.filter(
            PromptRun.prompt_config_id == self.id,
            PromptRun.status.in_([PromptRunStatus.PENDING, PromptRunStatus.RUNNING]),
        ).count() > 0
        last = (PromptRun.query.filter_by(prompt_config_id=self.id)
                .order_by(PromptRun.created_at.desc()).first())
        return {
            "run_count": total,
            "failure_count": failures,
            "pending_run": pending,
            "last_run_status": last.status.value if last else None,
        }

    def to_dict(self, include_prompt: bool = False, include_stats: bool = False):
        data = {
            "id": str(self.id),
            "title": self.title,
            "interval_minutes": self.interval_minutes,
            "cron_expression": self.cron_expression,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "repeat_penalty": self.repeat_penalty,
            "num_predict": self.num_predict,
            "seed": self.seed,
            "keep_alive": self.keep_alive,
            "slack_channel": self.slack_channel,
            "is_active": self.is_active,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "created_by_id": str(self.created_by_id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_prompt:
            data["prompt_body"] = self.prompt_body
        if include_stats:
            data["run_stats"] = self.run_stats()
        return data

    def __repr__(self):
        return f"<PromptConfig {self.title}>"