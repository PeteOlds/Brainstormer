from enum import Enum


class IdeaStatus(str, Enum):
    """V2 lifecycle (PRD_V2 §5). Values are the canonical state names."""

    SPARK = "SPARK"
    SCOPE = "SCOPE"
    MAP = "MAP"
    SHIP = "SHIP"
    SCALE = "SCALE"
    DROP = "DROP"
    FREEZE = "FREEZE"
    ARCHIVE = "ARCHIVE"


class PromptRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"
