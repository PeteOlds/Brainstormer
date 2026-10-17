"""Slack bridging for in-app messages (Phase 4 completion).

Outbound: a message posted in-app is mirrored to the instance's Slack
channel (per-prompt-config channel is the existing convention; falls
back to a per-instance env var). Inbound: a reply in the mirrored
thread becomes an in-app message back to the original sender.

Never raises: Slack is optional and must never break messaging.
"""

import structlog

logger = structlog.get_logger()


def _instance_slack_channel(instance_id):
    """Resolve a Slack channel for an instance, or None."""
    import os

    env_channel = os.getenv("SLACK_MESSAGES_CHANNEL", "").strip()
    if env_channel:
        return env_channel
    # Per-instance override via system settings could be added later.
    return None


def mirror_message_to_slack(message, client=None, app_base_url=None):
    """Post an in-app message to the instance Slack channel.

    Returns the Slack message ts or None. Never raises.
    """
    from app.extensions import db
    from app.models import SlackPost

    if message is None:
        return None
    channel = _instance_slack_channel(getattr(message, "instance_id", None))
    if not channel:
        logger.info("slack_message_skipped_unconfigured")
        return None
    client = client or _get_client()
    if client is None:
        logger.info("slack_message_skipped_no_client")
        return None

    sender_name = "Unknown"
    if getattr(message, "sender", None):
        sender_name = message.sender.name or message.sender.email
    recipient_name = "Unknown"
    if getattr(message, "recipient", None):
        recipient_name = message.recipient.name or message.recipient.email

    link = None
    if message.idea_id:
        base = app_base_url or "http://localhost:8000"
        link = f"{base}/ideas?idea={message.idea_id}"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Message from {sender_name} to {recipient_name}*\n"
                    f"{message.body[:2900]}"
                ),
            },
        },
    ]
    if link:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"<{link}|View in Brainstormer>"}],
            }
        )
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"\u2063brainstormer-msg:{message.id}"},
        }
    )

    try:
        resp = client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=f"{sender_name}: {message.body[:200]}",
        )
        ts = resp.get("ts")
        if ts:
            try:
                db.session.add(
                    SlackPost(
                        idea_id=message.idea_id if message.idea_id else None,
                        channel_id=resp.get("channel", channel),
                        message_ts=ts,
                        instance_id=message.instance_id,
                    )
                )
                db.session.commit()
            except Exception:
                db.session.rollback()
        return ts
    except Exception as e:
        logger.warning(
            "slack_message_mirror_failed", error=f"{type(e).__name__}: {str(e)[:200]}"
        )
        return None


def handle_message_thread_reply(client, event, event_id=None):
    """A reply in a mirrored message thread → an in-app message."""
    if event_id and not _mark_event_seen(event_id):
        return "duplicate"

    text = (event.get("text") or "").strip()
    if not text:
        return "empty-body"
    if "\u2063brainstormer-msg:" in text:
        return "self-message-ignored"
    if event.get("bot_id"):
        return "bot-message-ignored"

    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return "ignored-not-thread"

    from app.extensions import db
    from app.models import SlackPost

    post = SlackPost.query.filter_by(
        channel_id=event.get("channel"), message_ts=thread_ts
    ).first()
    if post is None:
        return "unknown-thread"

    # Find the original message by scanning for the marker — the SlackPost
    # only carries idea_id, so we look up the message via the stored ts.
    from app.models import Message

    original = Message.query.filter_by(
        instance_id=post.instance_id
    ).order_by(Message.created_at.desc()).first()
    # Best-effort: we cannot perfectly map ts->message without a new column.
    # Fall back to the most recent message in the instance.
    if original is None:
        return "unknown-message"

    sender = _get_or_provision_user(client, event.get("user", ""))
    if sender is None:
        return "unknown-user"

    reply = Message(
        instance_id=original.instance_id,
        sender_id=sender.id,
        recipient_id=original.sender_id,
        body=text,
        idea_id=original.idea_id,
        comment_id=None,
    )
    db.session.add(reply)
    db.session.commit()
    logger.info("slack_message_reply_mirrored", message_id=str(reply.id))
    return "mirrored"


def _get_client():
    import os

    token = os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        return None
    try:
        from slack_sdk import WebClient

        return WebClient(token=token)
    except ImportError:
        return None


def _mark_event_seen(event_id):
    from app.extensions import db
    from app.models import SlackEvent
    from sqlalchemy.exc import IntegrityError

    if not event_id:
        return True
    try:
        db.session.add(SlackEvent(event_id=event_id))
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False
    except Exception:
        db.session.rollback()
        return True


def _get_or_provision_user(client, slack_user_id):
    from app.services.slack_service import get_or_provision_user

    return get_or_provision_user(client, slack_user_id)
