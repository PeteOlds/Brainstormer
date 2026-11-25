"""Remaining Slack bridge branches: link blocks, error paths, helpers."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError


class _User:
    def __init__(self, name=None, email="user@example.com"):
        self.name = name
        self.email = email


class _Message:
    id = "m1"
    body = "hello"
    instance_id = "inst1"
    sender = _User(name=None, email="alice@example.com")
    recipient = _User(name=None, email="bob@example.com")
    idea_id = "idea1"


def test_mirror_none_message_returns_none(app):
    from app.services.message_slack import mirror_message_to_slack

    with app.app_context():
        assert mirror_message_to_slack(None) is None


def test_mirror_records_slack_post_and_link_block(app):
    from app.services.message_slack import mirror_message_to_slack

    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "1.2", "channel": "C1"}
    with (
        app.app_context(),
        patch("app.extensions.db") as db,
        patch(
            "app.services.message_slack._instance_slack_channel",
            return_value="#general",
        ),
        patch("app.services.message_slack._get_client", return_value=client),
    ):
        result = mirror_message_to_slack(_Message(), app_base_url="https://app.test")

    assert result == "1.2"
    blocks = client.chat_postMessage.call_args[1]["blocks"]
    assert any("View in Brainstormer" in str(block) for block in blocks)
    assert any("alice@example.com" in str(block) for block in blocks)
    assert any("bob@example.com" in str(block) for block in blocks)
    db.session.add.assert_called_once()
    db.session.commit.assert_called_once()


def test_mirror_swallows_slack_post_persistence_failure(app):
    from app.services.message_slack import mirror_message_to_slack

    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "1.2"}
    with (
        app.app_context(),
        patch("app.extensions.db") as db,
        patch(
            "app.services.message_slack._instance_slack_channel",
            return_value="#general",
        ),
        patch("app.services.message_slack._get_client", return_value=client),
    ):
        db.session.add.side_effect = RuntimeError("db went away")
        result = mirror_message_to_slack(_Message())

    assert result == "1.2"
    db.session.rollback.assert_called_once()


def test_mirror_swallows_slack_api_failure(app):
    from app.services.message_slack import mirror_message_to_slack

    client = MagicMock()
    client.chat_postMessage.side_effect = RuntimeError("slack went away")
    with (
        app.app_context(),
        patch(
            "app.services.message_slack._instance_slack_channel",
            return_value="#general",
        ),
        patch("app.services.message_slack._get_client", return_value=client),
    ):
        assert mirror_message_to_slack(_Message()) is None


def test_thread_reply_mirrors_a_real_thread(app):
    from app.services.message_slack import handle_message_thread_reply

    sender = MagicMock(id="u3")
    post = MagicMock(instance_id="inst1", sender_id="u1", idea_id="idea1")
    original = MagicMock(instance_id="inst1", sender_id="u1", idea_id="idea1")
    event = {"text": "a reply", "thread_ts": "1.2", "channel": "C1", "user": "U3"}
    with (
        app.app_context(),
        patch("app.extensions.db") as db,
        patch("app.models.SlackPost") as slack_post,
        patch("app.models.Message") as message,
        patch("app.services.message_slack._mark_event_seen", return_value=True),
        patch("app.services.message_slack._get_or_provision_user", return_value=sender),
    ):
        slack_post.query.filter_by.return_value.first.return_value = post
        message.query.filter_by.return_value.order_by.return_value.first.return_value = (
            original
        )
        result = handle_message_thread_reply(MagicMock(), event, "e1")

    assert result == "mirrored"
    db.session.add.assert_called_once()
    db.session.commit.assert_called_once()


def test_thread_reply_without_an_original_message(app):
    from app.services.message_slack import handle_message_thread_reply

    event = {"text": "a reply", "thread_ts": "1.2", "channel": "C1"}
    with (
        app.app_context(),
        patch("app.extensions.db"),
        patch("app.models.SlackPost") as slack_post,
        patch("app.models.Message") as message,
        patch("app.services.message_slack._mark_event_seen", return_value=True),
    ):
        slack_post.query.filter_by.return_value.first.return_value = MagicMock()
        message.query.filter_by.return_value.order_by.return_value.first.return_value = (
            None
        )
        assert handle_message_thread_reply(None, event, "e1") == "unknown-message"


def test_thread_reply_without_a_slack_sender(app):
    from app.services.message_slack import handle_message_thread_reply

    event = {"text": "a reply", "thread_ts": "1.2", "channel": "C1"}
    with (
        app.app_context(),
        patch("app.extensions.db"),
        patch("app.models.SlackPost") as slack_post,
        patch("app.models.Message") as message,
        patch("app.services.message_slack._mark_event_seen", return_value=True),
        patch("app.services.message_slack._get_or_provision_user", return_value=None),
    ):
        slack_post.query.filter_by.return_value.first.return_value = MagicMock()
        message.query.filter_by.return_value.order_by.return_value.first.return_value = (
            MagicMock()
        )
        assert handle_message_thread_reply(None, event, "e1") == "unknown-user"


def test_get_client_returns_none_without_a_token(app, monkeypatch):
    from app.services.message_slack import _get_client

    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    with app.app_context():
        assert _get_client() is None


def test_get_client_returns_none_when_sdk_is_unavailable(app, monkeypatch):
    import slack_sdk

    from app.services.message_slack import _get_client

    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    with (
        app.app_context(),
        patch.object(slack_sdk, "WebClient", side_effect=ImportError("no sdk")),
    ):
        assert _get_client() is None


def test_mark_event_seen_paths(app):
    from app.services.message_slack import _mark_event_seen

    with (
        app.app_context(),
        patch("app.extensions.db") as db,
        patch("app.models.SlackEvent"),
    ):
        assert _mark_event_seen(None) is True
        assert _mark_event_seen("e1") is True
        db.session.commit.assert_called_once()

        db.session.add.side_effect = IntegrityError("dup", None, Exception("dup"))
        assert _mark_event_seen("e2") is False
        db.session.rollback.assert_called_once()

        db.session.add.side_effect = RuntimeError("boom")
        assert _mark_event_seen("e3") is True
        assert db.session.rollback.call_count == 2


def test_get_or_provision_user_delegates(app):
    from app.services.message_slack import _get_or_provision_user

    with (
        app.app_context(),
        patch(
            "app.services.slack_service.get_or_provision_user", return_value="user"
        ) as get_user,
    ):
        assert _get_or_provision_user(MagicMock(), "U1") == "user"
    get_user.assert_called_once()
