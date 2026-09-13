import uuid
from datetime import datetime, timezone
from enum import Enum

from app.extensions import db
from app.models.types import GUID, ensure_aware


class PromptRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class PromptRun(db.Model):
    """History of a single prompt execution (manual or scheduled)."""

    __tablename__ = "prompt_runs"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    # Null for follow-up AI actions, which belong to an idea, not a prompt.
    prompt_config_id = db.Column(GUID(), db.ForeignKey("prompt_configs.id"), nullable=True, index=True)
    # Set for follow-up actions (REFINE, COMPETITORS, ...); null for generations.
    action_type = db.Column(db.String(30), nullable=True)
    triggered_by = db.Column(db.String(20), default="manual", nullable=False)
    job_id = db.Column(db.String(100), nullable=True)
    idea_id = db.Column(GUID(), db.ForeignKey("ideas.id"), nullable=True)
    status = db.Column(db.Enum(PromptRunStatus), default=PromptRunStatus.PENDING, nullable=False, index=True)
    error = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    prompt_config = db.relationship("PromptConfig", backref=db.backref("runs", lazy="dynamic", cascade="all, delete-orphan"))

    def mark_running(self):
        self.status = PromptRunStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def mark_success(self, idea_id=None):
        now = datetime.now(timezone.utc)
        self.status = PromptRunStatus.SUCCESS
        self.finished_at = now
        if idea_id is not None:
            self.idea_id = idea_id
        if self.started_at:
            self.duration_seconds = (now - ensure_aware(self.started_at)).total_seconds()

    def mark_failed(self, error):
        now = datetime.now(timezone.utc)
        self.status = PromptRunStatus.FAILED
        self.finished_at = now
        self.error = str(error)[:2000] if error else "Unknown error"
        if self.started_at:
            self.duration_seconds = (now - ensure_aware(self.started_at)).total_seconds()

    @property
    def display_title(self):
        """Human label: prompt title, or action name for follow-ups."""
        if self.prompt_config is not None:
            try:
                return self.prompt_config.title
            except Exception:
                pass
        if self.action_type:
            return self.action_type.title().replace("_", " ")
        return "—"

    def to_dict(self):
        return {
            "id": str(self.id),
            "prompt_config_id": str(self.prompt_config_id) if self.prompt_config_id else None,
            "action_type": self.action_type,
            "triggered_by": self.triggered_by,
            "job_id": self.job_id,
            "idea_id": str(self.idea_id) if self.idea_id else None,
            "status": self.status.value,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<PromptRun {self.prompt_config_id} {self.status.value}>"
