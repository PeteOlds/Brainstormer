"""Per-instance AI provider configs and spend ledger (Phase 3).

Provider API keys are Fernet-encrypted at rest (same pattern as prompt
bodies), write-only over the API (`has_key` is exposed, never the key),
and never copied between instances. Spend rows are append-only.
"""

import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID
from app.utils.crypto import decrypt, encrypt

PROVIDERS = ("ollama", "openai", "anthropic", "gemini")

# Refuse fails fast. Queue retries the Celery task later (explicit
# per-instance choice, visible in the run). Degrade falls back to a
# local model (explicit choice; quality changes are logged, never silent).
CUTOFF_BEHAVIOURS = ("refuse", "queue", "degrade")


class InstanceAIConfig(db.Model):
    __tablename__ = "instance_ai_configs"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(),
        db.ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = db.Column(db.String(20), nullable=False)
    _api_key = db.Column("api_key", db.Text, nullable=True)
    _virtual_key = db.Column("virtual_key", db.Text, nullable=True)
    use_proxy = db.Column(db.Boolean, default=False, nullable=False)
    endpoint = db.Column(db.String(255), nullable=True)
    model_allowlist = db.Column(db.JSON, default=list)
    embedding_model = db.Column(db.String(100), nullable=True)
    budget_cents = db.Column(db.Integer, nullable=True)
    cutoff_behaviour = db.Column(db.String(20), default="refuse", nullable=False)
    degrade_model = db.Column(db.String(100), nullable=True)
    chat_enabled = db.Column(db.Boolean, default=False, nullable=False)
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
        db.UniqueConstraint("instance_id", "provider", name="uq_instance_provider"),
    )

    @property
    def api_key(self) -> str:
        if self._api_key:
            return decrypt(self._api_key)
        return ""

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key = encrypt(value) if value else None

    @property
    def virtual_key(self) -> str:
        if self._virtual_key:
            return decrypt(self._virtual_key)
        return ""

    @virtual_key.setter
    def virtual_key(self, value: str) -> None:
        self._virtual_key = encrypt(value) if value else None

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "instance_id": str(self.instance_id),
            "provider": self.provider,
            "has_key": bool(self._api_key),
            "use_proxy": self.use_proxy,
            "has_virtual_key": bool(self._virtual_key),
            "endpoint": self.endpoint,
            "model_allowlist": list(self.model_allowlist or []),
            "embedding_model": self.embedding_model,
            "budget_cents": self.budget_cents,
            "cutoff_behaviour": self.cutoff_behaviour,
            "degrade_model": self.degrade_model,
            "chat_enabled": self.chat_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<InstanceAIConfig {self.instance_id}:{self.provider}>"


class AISpendLedger(db.Model):
    """Append-only per-request cost log (hosted providers; local rows cost 0)."""

    __tablename__ = "ai_spend_ledger"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(),
        db.ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id = db.Column(
        GUID(), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider = db.Column(db.String(20), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    prompt_tokens = db.Column(db.Integer, default=0, nullable=False)
    completion_tokens = db.Column(db.Integer, default=0, nullable=False)
    cost_cents = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "instance_id": str(self.instance_id) if self.instance_id else None,
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_cents": self.cost_cents,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<AISpend {self.instance_id}:{self.provider}/{self.model} {self.cost_cents}c>"
