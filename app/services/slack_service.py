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
        return resp.get("ts")
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
