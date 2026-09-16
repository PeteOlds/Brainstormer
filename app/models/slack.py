import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class SlackPost(db.Model):
    """Map posted Slack messages back to ideas (votes, threads)."""

    __tablename__ = "slack_posts"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    idea_id = db.Column(GUID(), db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id = db.Column(db.String(20), nullable=False)
    message_ts = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("channel_id", "message_ts", name="uq_slack_post"),
    )

    def __repr__(self):
        return f"<SlackPost idea={self.idea_id} {self.channel_id}:{self.message_ts}>"


class SlackEvent(db.Model):
    """Processed Slack event IDs for idempotency (retries redeliver)."""

    __tablename__ = "slack_events"

    event_id = db.Column(db.String(60), primary_key=True)
    received_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
