"""Password reset tokens (single-use, short-lived)."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.types import GUID


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        GUID(),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    @classmethod
    def hash_token(cls, raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def create(cls, user_id) -> tuple[str, "PasswordResetToken"]:
        """Generate a raw token and a persisted (hashed) row. Returns (raw, row)."""
        raw = secrets.token_urlsafe(32)
        row = cls(
            user_id=user_id,
            token_hash=cls.hash_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.session.add(row)
        db.session.commit()
        return raw, row

    def is_valid(self) -> bool:
        from app.models.types import ensure_aware

        return self.used_at is None and ensure_aware(self.expires_at) > datetime.now(timezone.utc)

    def mark_used(self):
        self.used_at = datetime.now(timezone.utc)
        db.session.commit()

    def __repr__(self):
        return f"<PasswordResetToken user={self.user_id} used={self.used_at is not None}>"