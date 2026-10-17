"""Unit tests for message_slack.py - Slack bridging for in-app messages."""

from unittest.mock import MagicMock, patch

import pytest


class FakeMessage:
    def __init__(self, message_id, body, instance_id=None, sender=None,
                 recipient=None, idea_id=None, comment_id=None,
                 created_at=None):
        self.id = message_id
        self.body = body
        self.instance_id = instance_id
        self.sender = sender
        self.recipient = recipient
        self.idea_id = idea_id
        self.comment_id = comment_id
        self.created_at = created_at


class FakeUser:
    def __init__(self, user_id, name="testuser", email="test@example.com"):
        self.id = user_id
        self.name = name
        self.email = email


class TestMirrorMessageToSlack:
    def test_no_channel_returns_none(self, app):
        from app.services.message_slack import mirror_message_to_slack
        msg = FakeMessage("m1", "hello")
        with app.app_context():
            result = mirror_message_to_slack(msg)
        assert result is None

    def test_no_client_returns_none(self, app):
        from app.services.message_slack import mirror_message_to_slack
        msg = FakeMessage("m1", "hello", instance_id="inst1")
        with app.app_context():
            with patch("app.services.message_slack._get_client",
                       return_value=None):
                result = mirror_message_to_slack(msg)
        assert result is None

    def test_mirror_sends_to_slack(self, app):
        from app.services.message_slack import mirror_message_to_slack
        msg = FakeMessage("m1", "Hello from user", instance_id="inst1",
                          sender=FakeUser("u1", "Alice", "alice@example.com"),
                          recipient=FakeUser("u2", "Bob", "bob@example.com"))
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "1234567890.123456"}
        with app.app_context():
            with patch("app.services.message_slack._instance_slack_channel",
                       return_value="#general"):
                with patch("app.services.message_slack._get_client",
                           return_value=mock_client):
                    result = mirror_message_to_slack(msg)
        assert result == "1234567890.123456"
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#general"
        assert "Hello from user" in call_kwargs["text"]
        assert "blocks" in call_kwargs
        blocks = call_kwargs["blocks"]
        section_text = blocks[0]["text"]["text"]
        assert "Alice" in section_text
        assert "Bob" in section_text
        assert "Hello from user" in section_text


class TestHandleMessageThreadReply:
    def test_duplicate_event_id(self, app):
        from app.services.message_slack import handle_message_thread_reply
        with app.app_context():
            with patch("app.services.message_slack._mark_event_seen",
                       return_value=False):
                result = handle_message_thread_reply(None,
                                                     {"event_id": "dup1",
                                                      "text": "hello",
                                                      "thread_ts": "dup1"},
                                                     "dup1")
        assert result == "duplicate"

    def test_empty_body_ignored(self, app):
        from app.services.message_slack import handle_message_thread_reply
        with app.app_context():
            with patch("app.services.message_slack._mark_event_seen",
                       return_value=True):
                result = handle_message_thread_reply(None,
                                                     {"event_id": "e1",
                                                      "text": ""},
                                                     "e1")
        assert result == "empty-body"

    def test_self_message_ignored(self, app):
        from app.services.message_slack import handle_message_thread_reply
        with app.app_context():
            with patch("app.services.message_slack._mark_event_seen",
                       return_value=True):
                result = handle_message_thread_reply(None, {
                    "event_id": "e1",
                    "text": "\u2063brainstormer-msg:m1 some text",
                    "thread_ts": "e1"
                }, "e1")
        assert result == "self-message-ignored"

    def test_bot_message_ignored(self, app):
        from app.services.message_slack import handle_message_thread_reply
        with app.app_context():
            with patch("app.services.message_slack._mark_event_seen",
                       return_value=True):
                result = handle_message_thread_reply(None, {
                    "event_id": "e1",
                    "text": "hello",
                    "thread_ts": "e1",
                    "bot_id": "B123"
                }, "e1")
        assert result == "bot-message-ignored"

    def test_no_thread_ts_ignored(self, app):
        from app.services.message_slack import handle_message_thread_reply
        with app.app_context():
            with patch("app.services.message_slack._mark_event_seen",
                       return_value=True):
                result = handle_message_thread_reply(None, {
                    "event_id": "e1",
                    "text": "hello",
                    "thread_ts": None
                }, "e1")
        assert result == "ignored-not-thread"

    def test_unknown_thread_returns_unknown_thread(self, app):
        from app.services.message_slack import handle_message_thread_reply
        with app.app_context():
            with patch("app.services.message_slack._mark_event_seen",
                       return_value=True):
                result = handle_message_thread_reply(None, {
                    "event_id": "e1",
                    "thread_ts": "t1",
                    "text": "hello",
                    "channel": "C1"
                }, "e1")
        assert result == "unknown-thread"
