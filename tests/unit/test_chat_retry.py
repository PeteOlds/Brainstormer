"""Chat retries a single model timeout before surfacing an error."""

from unittest.mock import patch

import pytest

from app.extensions import db
from app.models import Idea, PromptConfig, User
from app.services import chat as chat_svc
from app.services.llm_backends import GenerationResult
from app.services.ollama_client import OllamaError


def _idea():
    admin = User.query.filter_by(email="admin@test.com").first()
    prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
    idea = Idea(
        reference_code="IDEA-CHATRETRY",
        prompt_title="Retry",
        raw_content="content",
        prompt_config_id=prompt.id,
    )
    db.session.add(idea)
    db.session.commit()
    return admin, idea


def test_retries_once_then_succeeds(app, admin_user, admin_prompt):
    with app.app_context():
        admin, idea = _idea()
        ok = GenerationResult(text="A useful reply.", model="llama3:8b")
        with patch.object(
            chat_svc,
            "generate_for_prompt",
            side_effect=[OllamaError("timeout"), ok],
        ) as generate:
            _, reply = chat_svc.chat_turn(idea, admin, "hello")
        assert generate.call_count == 2
        assert reply.content == "A useful reply."


def test_two_timeouts_become_friendly_chat_error(app, admin_user, admin_prompt):
    with app.app_context():
        admin, idea = _idea()
        with patch.object(
            chat_svc,
            "generate_for_prompt",
            side_effect=[OllamaError("timeout"), OllamaError("timeout")],
        ) as generate:
            with pytest.raises(chat_svc.ChatError) as exc:
                chat_svc.chat_turn(idea, admin, "hello")
        assert generate.call_count == 2
        assert "did not respond" in str(exc.value)
