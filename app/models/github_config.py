"""Per-instance GitHub configuration (Scale-phase pushes).

One row per instance: an encrypted personal access token (repo scope),
the target `owner/repo`, and the branch to push to. The PAT follows the
provider-key pattern (Fernet at rest, never returned by the API, never
logged). Only the worker task that performs the push ever decrypts it.
"""

import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID
from app.utils.crypto import decrypt, encrypt


class InstanceGitHubConfig(db.Model):
    __tablename__ = "instance_github_configs"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(),
        db.ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    repo = db.Column(db.String(200), nullable=False)  # "owner/name"
    branch = db.Column(db.String(100), nullable=False, default="main")
    _pat = db.Column("pat", db.Text, nullable=True)
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

    @property
    def pat(self) -> str | None:
        if self._pat:
            return decrypt(self._pat)
        return None

    @pat.setter
    def pat(self, value: str | None) -> None:
        self._pat = encrypt(value) if value else None

    def to_dict(self):
        return {
            "id": str(self.id),
            "instance_id": str(self.instance_id),
            "repo": self.repo,
            "branch": self.branch,
            "has_pat": bool(self._pat),
        }

    def __repr__(self):
        return f"<InstanceGitHubConfig {self.instance_id}:{self.repo}>"
