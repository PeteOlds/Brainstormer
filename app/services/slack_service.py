"""Slack outgoing posts (Phase 3a).

Never raises: without a token/channel, or on any API failure, returns
None and logs. Generation must never depend on Slack.
"""
import time

import structlog

logger = structlog.get_logger()


def get_client(token=None):
    """WebClient or None when unconfigured."""
    import os
    token = token or os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        return None
    try:
        from slack_sdk import WebClient
    except ImportError:
        logger.warning("slack_sdk_missing")
        return None
    return WebClient(token=token)


def idea_blocks(idea, app_base_url):
    """Block Kit message for a new idea."""
    summary = (idea.get("summary") or "")[:280]
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*{idea.get('reference_code', 'Idea')}* — {idea.get('prompt_title', '')}\n{summary}"},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn",
                          "text": f"Status: {idea.get('status', '')} | "
                                  f"<{app_base_url}/ideas|Open in Brainstormer>"}],
        },
    ]


def post_idea(channel, idea, app_base_url=None, client=None, _retried=False):
    """Post one idea to a channel. Returns message ts or None (never raises)."""
    if not channel:
        return None
    client = client or get_client()
    if client is None:
        logger.info("slack_skipped_unconfigured")
        return None
    try:
        resp = client.chat_postMessage(
            channel=channel,
            blocks=idea_blocks(idea, app_base_url or "http://localhost:8000"),
            text=f"New idea {idea.get('reference_code', '')}",
        )
        ts = resp.get("ts")
        _record_post(idea.get("id"), resp.get("channel", channel), ts)
        return ts
    except Exception as e:
        # Single retry on rate-limit honoring Retry-After.
        retry_after = getattr(e, "response", None)
        retry_after = (retry_after.get("headers", {}).get("Retry-After")
                       if isinstance(retry_after, dict) else None)
        if not _retried and retry_after:
            try:
                time.sleep(int(retry_after))
            except (ValueError, TypeError):
                pass
            return post_idea(channel, idea, app_base_url, client, _retried=True)
        logger.warning("slack_post_failed", channel=channel,
                       error=f"{type(e).__name__}: {str(e)[:200]}")
        return None


def _record_post(idea_id, channel_id, ts):
    """Map a posted message back to its idea for votes/threads (Phase 3b/c)."""
    if not idea_id or not ts:
        return
    try:
        from app.extensions import db
        from app.models import SlackPost
        db.session.add(SlackPost(idea_id=idea_id, channel_id=channel_id, message_ts=ts))
        db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning("slack_post_map_failed", error=f"{type(e).__name__}: {str(e)[:200]}")


# Reaction emoji -> vote direction (Phase 3b).
VOTE_REACTIONS = {"+1": 1, "thumbsup": 1, "-1": -1, "thumbsdown": -1}


def get_or_provision_user(client, slack_user_id):
    """Map a Slack user to a Brainstormer account by email.

    Links existing accounts by email, else auto-provisions a USER with an
    unusable password. Returns the User or None.
    """
    import secrets
    from app.extensions import db
    from app.models import User, UserRole

    existing = User.query.filter_by(slack_user_id=slack_user_id).first()
    if existing:
        return existing
    try:
        info = client.users_info(user=slack_user_id).get("user", {})
    except Exception as e:
        logger.warning("slack_user_lookup_failed", error=f"{type(e).__name__}: {str(e)[:200]}")
        return None
    email = (info.get("profile", {}).get("email") or "").strip().lower()
    if not email:
        logger.warning("slack_user_no_email", slack_user_id=slack_user_id)
        return None
    user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(email=email,
                    name=info.get("real_name") or info.get("name"),
                    role=UserRole.USER)
        user.password_hash = secrets.token_urlsafe(32)
        db.session.add(user)
    user.slack_user_id = slack_user_id
    db.session.commit()
    return user


def apply_slack_vote(user, idea_id, direction, present):
    """Apply a reaction add (present=True) or remove.

    Adds set/flip the vote; removals rescind only a matching vote.
    Returns the net score.
    """
    from app.extensions import db
    from app.models import Idea, Vote

    idea = Idea.query.get(idea_id)
    if idea is None:
        return None
    existing = Vote.query.filter_by(user_id=user.id, idea_id=idea.id).first()
    if present:
        if existing:
            existing.value = direction
        else:
            db.session.add(Vote(user_id=user.id, idea_id=idea.id, value=direction))
    elif existing and existing.value == direction:
        db.session.delete(existing)
    idea.update_vote_counts()
    db.session.commit()
    return idea.net_score


def mark_event_seen(event_id):
    """True if this is the first sighting (records it); False if duplicate."""
    from sqlalchemy.exc import IntegrityError
    from app.extensions import db
    from app.models import SlackEvent

    if not event_id:
        return True
    try:
        db.session.add(SlackEvent(event_id=event_id))
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False
    except Exception as e:
        db.session.rollback()
        logger.warning("slack_event_seen_failed", error=f"{type(e).__name__}: {str(e)[:200]}")
        return True


def handle_reaction_event(client, event, event_id=None, event_type="reaction_added"):
    """Process one reaction event. Returns an outcome string for logging."""
    from app.models import SlackPost

    if event_id and not mark_event_seen(event_id):
        return "duplicate"
    reaction = event.get("reaction", "")
    if reaction not in VOTE_REACTIONS:
        return "ignored-reaction"
    item = event.get("item", {}) or {}
    if item.get("type") != "message":
        return "ignored-item"
    post = SlackPost.query.filter_by(
        channel_id=item.get("channel"), message_ts=item.get("ts")).first()
    if post is None:
        return "unknown-message"
    user = get_or_provision_user(client, event.get("user", ""))
    if user is None:
        return "unknown-user"
    net = apply_slack_vote(user, post.idea_id,
                           VOTE_REACTIONS[reaction],
                           present=(event_type == "reaction_added"))
    if net is None:
        return "unknown-idea"
    return f"vote:net={net}"


# Loop guard marker (zero-width space + prefix) — prepended to every
# bot-generated comment so we can ignore echoes on the inbound path.
MIRROR_MARKER = "\u2063brainstormer:"


def mirror_comment_to_thread(idea, comment, client=None, app_base_url=None):
    """Post a comment from the app into the idea's Slack thread.

    Only runs when the idea has a SlackPost record (i.e., was posted to Slack).
    Returns the Slack message ts or None.
    """
    from app.extensions import db
    from app.models import SlackPost

    post = SlackPost.query.filter_by(idea_id=idea.id).first()
    if not post:
        logger.info("slack_mirror_skipped_no_post", idea_id=str(idea.id))
        return None

    client = client or get_client()
    if client is None:
        logger.info("slack_mirror_skipped_unconfigured")
        return None

    # Build comment block with author and optional backlink
    author = getattr(comment, "author_name", "Unknown")
    body = comment.body or ""
    if comment.is_deleted:
        body = "[deleted]"

    # Build block kit message
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{author}*: {body[:2900]}"
            }
        },
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"<{app_base_url}/ideas?comment={comment.id}|View in Brainstormer>"
            }]
        }
    ]
    # Invisible loop-guard marker
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"{MIRROR_MARKER}{comment.id}"}})

    client = client or get_client()
    if client is None:
        logger.warning("slack_mirror_skipped_unconfigured")
        return None

    try:
        resp = client.chat_postMessage(
            channel=post.channel_id,
            thread_ts=post.message_ts,
            blocks=blocks,
            text=f"{author}: {body[:200]}",
        )
        return resp.get("ts")
    except Exception as e:
        logger.warning("slack_mirror_failed", error=f"{type(e).__name__}: {str(e)[:200]}")
        return None


def handle_thread_reply(client, event, event_id=None):
    """Handle a reply in a Slack thread — create a comment in the app.

    Only processes replies in threads that correspond to a known SlackPost.
    Ignores messages from bots, our own posts (MIRROR_MARKER), and non-thread messages.
    """
    if not event_id or not mark_event_seen(event_id):
        return "duplicate"

    subtype = event.get("subtype")
    if subtype == "bot_message":
        return "bot-message-ignored"

    # Skip our own mirrored comments
    text = event.get("text", "") or ""
    if MIRROR_MARKER in text:
        return "self-message-ignored"

    item = event.get("item", {}) or {}
    if item.get("type") != "message":
        return "ignored-not-message"
    if item.get("type") != "message":
        return "ignored-not-message"
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return "ignored-no-thread"

    # Find the SlackPost by thread_ts (which is the original message_ts)
    from app.models import SlackPost
    post = SlackPost.query.filter_by(channel_id=event.get("channel"), message_ts=thread_ts).first()
    if not post:
        return "unknown-thread"

    # Get or provision the user
    user = get_or_provision_user(client, event.get("user", ""))
    if user is None:
        return "unknown-user"

    # Create the comment
    body = event.get("text", "").strip()
    if not body:
        return "empty-body"

    from app.extensions import db
    from app.models import Comment

    comment = Comment(
        idea_id=post.idea_id,
        user_id=user.id,
        parent_id=None,  # Slack threads are flat; we treat all replies as top-level
        body=body,
    )
    db.session.add(comment)
    db.session.commit()

    logger.info("slack_thread_reply_mirrored", comment_id=str(comment.id), idea_id=str(post.idea_id))
    return "mirrored"


def is_own_message(event):
    """Check if a message was sent by our bot."""
    return event.get("bot_id") is not None


def process_slack_event(client, event, event_id=None):
    """Route an incoming Slack event to the appropriate handler."""
    event_type = event.get("type", "")

    if event_type in ("reaction_added", "reaction_removed"):
        return handle_reaction_event(client, event, event_id=event.get("event_ts"), event_type=event.get("type"))

    if event_type == "message":
        # Skip bot messages and our own
        if event.get("bot_id") or is_own_message(event):
            return "bot-message-ignored"

        subtype = event.get("subtype")
        if subtype == "bot_message":
            return "bot-message-ignored"

        thread_ts = event.get("thread_ts")
        if thread_ts:
            return handle_thread_reply(client, event, event_id=event.get("event_ts"), event_type=event.get("type"))
        # Non-thread messages are not mirrored
        return "ignored-not-thread"

    return "ignored-event-type"
