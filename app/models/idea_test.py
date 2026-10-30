"""Manual + imported test cases tracked against a built idea.

These are NOT the brainstormer-generated tests: they give a team a single
place to record what has been verified (unit/integration/e2e/manual), its
last outcome, and coverage, so quality is visible next to the idea.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from app.extensions import db
from app.models.types import GUID


class TestType(str, Enum):
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    MANUAL = "manual"
    PERFORMANCE = "performance"


class TestStatus(str, Enum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class IdeaTest(db.Model):
    __tablename__ = "idea_tests"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    idea_id = db.Column(
        GUID(),
        db.ForeignKey("ideas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    instance_id = db.Column(
        GUID(), db.ForeignKey("instances.id"), nullable=True, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    test_type = db.Column(db.Enum(TestType), default=TestType.UNIT, nullable=False)
    status = db.Column(db.Enum(TestStatus), default=TestStatus.NOT_RUN, nullable=False)
    last_run_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_run_output = db.Column(db.Text, nullable=True)
    coverage_pct = db.Column(db.Float, nullable=True)
    created_by_id = db.Column(GUID(), db.ForeignKey("users.id"), nullable=True)
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

    def to_dict(self):
        return {
            "id": str(self.id),
            "idea_id": str(self.idea_id),
            "instance_id": str(self.instance_id) if self.instance_id else None,
            "name": self.name,
            "description": self.description,
            "test_type": self.test_type.value,
            "status": self.status.value,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_output": self.last_run_output,
            "coverage_pct": self.coverage_pct,
            "created_by_id": str(self.created_by_id) if self.created_by_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<IdeaTest {self.name} [{self.status.value}]>"