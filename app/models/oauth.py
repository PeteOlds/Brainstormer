"""Social login: per-tenant OAuth credentials + global identity links (Phase 5).

Deviation note: `Guide_SocialLogin.md` sketches a single
`global_subject_id` column. Reality is multi-provider (Google, Apple,
Microsoft), so the immutable `(provider, sub)` pairs live in
`oauth_identities` — one identity, many providers, email changes never
break the link. Per-tenant client credentials live in
`tenant_oauth_configs` (encrypted, write-only API).
"""

import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID
from app.utils.crypto import decrypt, encrypt

OAUTH_PROVIDERS = ("google", "apple", "microsoft")


class TenantOAuthConfig(db.Model):
    __tablename__ = "tenant_oauth_configs"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(),
        db.ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name = db.Column(db.String(20), nullable=False)
    client_id = db.Column(db.String(255), nullable=False)
    _client_secret = db.Column("client_secret", db.Text, nullable=True)
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
        db.UniqueConstraint(
            "instance_id", "provider_name", name="uq_tenant_oauth_provider"
        ),
    )

    @property
    def client_secret(self) -> str:
        return decrypt(self._client_secret) if self._client_secret else ""

    @client_secret.setter
    def client_secret(self, value: str):
        self._client_secret = encrypt(value) if value else None

    def to_dict(self):
        return {
            "id": str(self.id),
            "instance_id": str(self.instance_id),
            "provider_name": self.provider_name,
            "client_id": self.client_id,
            "has_secret": bool(self._client_secret),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<TenantOAuthConfig {self.instance_id}:{self.provider_name}>"


class OAuthIdentity(db.Model):
    """Immutable (provider, subject) links to the shared user identity."""

    __tablename__ = "oauth_identities"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        GUID(),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "oauth_identities", lazy="dynamic", cascade="all, delete-orphan"
        ),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "provider": self.provider,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<OAuthIdentity {self.provider}:{self.user_id}>"
