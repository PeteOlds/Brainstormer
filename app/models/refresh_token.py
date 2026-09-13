import uuid
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models.types import GUID, ensure_aware


class RefreshToken(db.Model):
    __tablename__ = "refresh_tokens"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(GUID(), db.ForeignKey("users.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(128), nullable=False, index=True)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    replaced_by_id = db.Column(GUID(), db.ForeignKey("refresh_tokens.id"), nullable=True)

    # Relationships
    user = db.relationship("User", backref=db.backref("refresh_tokens", lazy=True))
    replaced_by = db.relationship("RefreshToken", remote_side=[id], backref="replaces")

    def is_valid(self) -> bool:
        """Check if token is valid (not revoked, not expired)."""
        return (
            not self.is_revoked
            and ensure_aware(self.expires_at) > datetime.now(timezone.utc)
        )

    def revoke(self, replaced_by=None):
        """Revoke this refresh token."""
        self.is_revoked = True
        self.revoked_at = datetime.now(timezone.utc)
        if replaced_by:
            self.replaced_by_id = replaced_by.id

    @classmethod
    def create_token(cls, user_id: str, expires_in_days: int = 7):
        """Create a new refresh token."""        
        import secrets
        import hashlib

        # Generate a random token
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        refresh_token = cls(
            user_id=user_id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7)
        )
        
        return raw_token, refresh_token
    
    @classmethod
    def verify_token(cls, raw_token: str):
        """Verify a refresh token and return the RefreshToken object if valid."""
        import hashlib
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        return cls.query.filter_by(token_hash=token_hash).first()
