"""Tests for the automatic post-build review contract and prompt."""

import json
from pathlib import Path

from app.schemas.ollama_schemas import BuildReviewOutput, validate_ollama_output

ROOT = Path(__file__).resolve().parents[2]

VALID = {
    "summary": "The app ships a working idea list and detail screen.",
    "scope": "IDEA-0001 and its release children",
    "strengths": ["Clear routes — easy to extend"],
    "gaps": ["Empty list state is missing — users see a blank page"],
    "suggested_features": ["Add search — the list will grow"],
    "approach_suggestions": ["Extract the form component — two screens share it"],
    "risks": ["No auth on the API — restrict before hosting"],
    "open_questions": ["Should ideas be deletable?"],
}


def test_valid_review():
    result = validate_ollama_output("BUILD_REVIEW", json.dumps(VALID))
    assert isinstance(result, BuildReviewOutput)
    assert result.suggested_features == ["Add search — the list will grow"]


def test_review_defaults_for_missing_lists():
    payload = {"summary": "A short but valid review summary."}
    result = validate_ollama_output("BUILD_REVIEW", json.dumps(payload))
    assert result.strengths == []
    assert result.open_questions == []


def test_prompt_describes_release_scope_and_schema():
    prompt = (ROOT / "app/prompt_templates/build_review.txt").read_text()
    assert "### SUPPORTING MATERIAL" in prompt
    assert "whole release" in prompt
    for key in ("suggested_features", "approach_suggestions", "risks"):
        assert key in prompt
