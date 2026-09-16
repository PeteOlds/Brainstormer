#!/usr/bin/env python
"""Slack Socket Mode listener (Phase 3b votes; 3c threads plug in here).

Receives workspace events over a websocket — no public URL needed.
Requires SLACK_BOT_TOKEN (xoxb-...) and SLACK_APP_TOKEN (xapp-...,
with connections:write). Exits loudly if either is missing.
"""
import os
import sys

import structlog

from app import create_app

logger = structlog.get_logger()

app = create_app(os.getenv("FLASK_ENV", "development"), init_celery_app=True)


def process_reaction(client, event, event_id, event_type):
    """Handle one reaction event inside the Flask app context."""
    from app.services import slack_service
    with app.app_context():
        try:
            outcome = slack_service.handle_reaction_event(
                client, event, event_id=event_id, event_type=event_type)
        except Exception as e:
            logger.error("slack_reaction_failed",
                         error=f"{type(e).__name__}: {str(e)[:200]}")
            return
        logger.info("slack_reaction", outcome=outcome,
                    reaction=event.get("reaction"))


def main():
    bot_token = os.getenv("SLACK_BOT_TOKEN", "")
    app_token = os.getenv("SLACK_APP_TOKEN", "")
    if not bot_token or not app_token:
        print("SLACK_BOT_TOKEN and SLACK_APP_TOKEN are both required.",
              file=sys.stderr)
        return 2

    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.web import WebClient

    web_client = WebClient(token=bot_token)
    socket_client = SocketModeClient(app_token=app_token, web_client=web_client)

    def on_envelope(client, req: SocketModeRequest):
        try:
            if req.type == "events_api":
                client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
                inner = req.payload.get("event", {}) or {}
                if inner.get("type") in ("reaction_added", "reaction_removed"):
                    process_reaction(web_client, inner,
                                     req.payload.get("event_id"),
                                     inner.get("type"))
            # event_id present on all events_api envelopes; non-event
            # types (hello, disconnect) are ignored after the ack above.
        except Exception as e:
            logger.error("slack_envelope_failed",
                         error=f"{type(e).__name__}: {str(e)[:200]}")

    socket_client.socket_mode_request_listeners.append(on_envelope)
    logger.info("slack_listener_starting")
    socket_client.connect()
    import time
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
