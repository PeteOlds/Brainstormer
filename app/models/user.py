import uuid
from datetime import datetime, timezone
from enum import Enum

from app.extensions import db
from app.utils import auth
from app.models.types import GUID


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100))
    role = db.Column(db.Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    login_count = db.Column(db.Integer, default=0, nullable=False)
    slack_user_id = db.Column(db.String(20), nullable=True, unique=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def record_login(self):
        """Stamp last login + bump counter (called on successful login)."""
        self.last_login_at = datetime.now(timezone.utc)
        self.login_count = (self.login_count or 0) + 1

    def set_password(self, password):
        self.password_hash = auth.hash_password(password)

    def check_password(self, password):
        return auth.verify_password(password, self.password_hash)

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "name": self.name,
            "role": self.role.value,
            "is_active": self.is_active,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "login_count": self.login_count or 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<User {self.email}>"