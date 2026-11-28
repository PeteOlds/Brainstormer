"""Internal prompt catalogue and rendering."""

import pytest

from app.services.internal_prompts import (
    PROMPT_CATALOGUE,
    default_body,
    get_internal_prompt,
    list_internal_prompts,
)


def test_catalogue_covers_all_shipped_templates():
    rows = list_internal_prompts()
    assert len(rows) == len(PROMPT_CATALOGUE)
    assert {row["key"] for row in rows} == set(PROMPT_CATALOGUE)
    for row in rows:
        assert row["label"]
        assert row["body"]


def test_hardcoded_prompts_are_now_files():
    chat = get_internal_prompt("chat_system").body
    assert "brainstorming conversationally" in chat
    assert "never JSON" in chat
    assert "diagnose_tests" in PROMPT_CATALOGUE
    assert "diagnose_app" in PROMPT_CATALOGUE
    assert "strict_retry" in PROMPT_CATALOGUE


def test_placeholder_rendering_and_discovery():
    prompt = get_internal_prompt("strict_retry")
    assert prompt.required_placeholders == ["ERRORS"]
    rendered = prompt.render(ERRORS="bad json")
    assert "bad json" in rendered
    assert "${ERRORS}" not in rendered

    diag = get_internal_prompt("diagnose_tests")
    assert set(diag.required_placeholders) == {"FAILED_TESTS", "LOG_TAIL"}
    rendered = diag.render(FAILED_TESTS="test_x", LOG_TAIL="traceback")
    assert "test_x" in rendered and "traceback" in rendered


def test_shared_engineering_contract_is_present():
    base = get_internal_prompt("base").body
    assert "ENGINEERING CONTRACT" in base
    assert "150-300 lines" in base
    assert "AGENTS.md" in base
    review = get_internal_prompt("build_review").body
    assert "engineering contract" in review.lower()
    assert "typed boundaries" in review


def test_unknown_key_rejected():
    with pytest.raises(ValueError):
        default_body("no-such-prompt")
