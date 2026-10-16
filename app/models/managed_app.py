"""Supervised app processes (one-click start/stop for generated builds).

One row per (idea, build target): Start (re)configures it from the current
BUILD_CODE version and launches the app as a subprocess on this host; Stop
kills the process group. Pids live here, logs live in files (see
app.services.runner); state is a plain string, never an enum, so no
out-of-band enum surgery is ever needed.
"""
import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID

# state values: stopped | starting | running | stopping | failed
STATES = ("stopped", "starting", "running", "stopping", "failed")


class ManagedApp(db.Model):
    __tablename__ = "managed_apps"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    instance_id = db.Column(
        GUID(),
        db.ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idea_id = db.Column(
        GUID(),
        db.ForeignKey("ideas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Plain GUID, no FK: deleting a target must not cascade supervision
    # history (same rule as SecondaryActionResult.target_id).
    target_id = db.Column(GUID(), nullable=True)
    target_name = db.Column(db.String(200), nullable=True)
    # BUILD_CODE version the recorded spec was derived from.
    build_version = db.Column(db.Integer, nullable=True)
    state = db.Column(db.String(20), nullable=False, default="stopped")
    pid = db.Column(db.Integer, nullable=True)
    port = db.Column(db.Integer, nullable=True)
    workdir = db.Column(db.Text(), nullable=True)
    command = db.Column(db.Text(), nullable=True)
    # Structured start spec ({run_argv, setup_argv, pip_argv}) for the
    # runner: display strings are never executed. JSON: never mutate in
    # place (replace the whole dict).
    spec = db.Column(db.JSON(), nullable=True)
    health_url = db.Column(db.String(500), nullable=True)
    # Where the Open button goes: the human UI when one exists (may differ
    # from the API root the health check polls).
    open_url = db.Column(db.String(500), nullable=True)
    log_path = db.Column(db.Text(), nullable=True)
    last_error = db.Column(db.Text(), nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    stopped_at = db.Column(db.DateTime(timezone=True), nullable=True)
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
        db.UniqueConstraint("idea_id", "target_id", name="uq_managedapp_idea_target"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "instance_id": str(self.instance_id),
            "idea_id": str(self.idea_id),
            "target_id": str(self.target_id) if self.target_id else None,
            "target_name": self.target_name,
            "build_version": self.build_version,
            "state": self.state,
            "pid": self.pid,
            "port": self.port,
            "workdir": self.workdir,
            "command": self.command,
            "spec": self.spec,
            "health_url": self.health_url,
            "open_url": self.open_url,
            "log_path": self.log_path,
            "last_error": self.last_error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
        }

    def __repr__(self):
        return f"<ManagedApp {self.id} {self.state}>"
