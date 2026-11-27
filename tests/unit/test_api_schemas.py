"""Boundary contracts for idea creation and action runs."""

import pytest
from pydantic import ValidationError

from app.schemas.api_schemas import ActionRequest, IdeaCreateRequest


def test_idea_request_accepts_minimal_payload_and_ignores_extras():
    payload = IdeaCreateRequest.model_validate(
        {"prompt_title": "Idea", "raw_content": "Body", "future_field": 1}
    )
    assert payload.prompt_title == "Idea"
    assert not hasattr(payload, "future_field")


def test_idea_request_rejects_empty_title_and_bad_child_kind():
    with pytest.raises(ValidationError):
        IdeaCreateRequest.model_validate({"prompt_title": "", "raw_content": "Body"})
    with pytest.raises(ValidationError):
        IdeaCreateRequest.model_validate(
            {
                "prompt_title": "Idea",
                "raw_content": "Body",
                "child_kind": "random",
            }
        )


def test_action_request_defaults_and_bounds():
    assert ActionRequest.model_validate({"action_type": "REFINE"}).build_stage == 1
    with pytest.raises(ValidationError):
        ActionRequest.model_validate({"action_type": "BUILD_CODE", "build_stage": 9})


def test_action_request_keeps_existing_extra_fields_optional():
    payload = ActionRequest.model_validate(
        {
            "action_type": "BUILD_CODE",
            "target_id": "abc",
            "confirm": True,
            "skills": ["a"],
            "answers": ["yes"],
        }
    )
    assert payload.confirm is True
    assert payload.skills == ["a"]
    assert payload.answers == ["yes"]
