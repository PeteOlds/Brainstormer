from enum import Enum


class IdeaStatus(str, Enum):
    NEW = "NEW"
    CONSIDERATION = "CONSIDERATION"
    HOLD = "HOLD"
    DEVELOPMENT = "DEVELOPMENT"
    COMPLETE = "COMPLETE"
    DISCARDED = "DISCARDED"


class PromptRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"