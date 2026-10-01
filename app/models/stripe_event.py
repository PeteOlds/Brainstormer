"""Stripe webhook idempotency log (Phase 12).

Mirrors the SlackEvent pattern: provider event IDs are globally unique,
so replays (Stripe retries every failed webhook) are dropped before any
billing mutation runs.
"""

import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.models.types import GUID


class StripeEvent(db.Model):
    __tablename__ = "stripe_events"

    event_id = db.Column(db.String(120), primary_key=True)
    event_type = db.Column(db.String(80), nullable=True)
    received_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<StripeEvent {self.event_type}:{self.event_id}>"


def mark_stripe_event_seen(event_id: str, event_type: str | None = None) -> bool:
    """True on first sighting (records it); False on replay."""
    if not event_id:
        return True
    from sqlalchemy.exc import IntegrityError

    try:
        db.session.add(StripeEvent(event_id=event_id, event_type=event_type))
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False
    except Exception:
        db.session.rollback()
        return True
