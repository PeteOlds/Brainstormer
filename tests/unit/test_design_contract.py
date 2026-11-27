"""Tests for the typed DESIGN_DOC contract and its prompt rendering."""

import json
from pathlib import Path

from app.schemas.ollama_schemas import DesignDocOutput, validate_ollama_output
from app.services.design_contract import render_design_contract

ROOT = Path(__file__).resolve().parents[2]

LEGACY = {
    "architecture": "Flask API with a SQLite database and a small web client.",
    "screens": "Home list and idea detail.",
    "data_model": "Idea: id, title, status.",
    "api_contracts": "GET /api/ideas returns a list.",
    "build_notes": "Implement the list first, then the detail screen.",
    "open_questions": ["Should ideas be deletable?"],
}

TYPED = {
    "architecture": "Flask API with SQLite and a minimal browser client.",
    "build_notes": "Build data layer first.",
    "screen_specs": [
        {
            "name": "IdeaList",
            "purpose": "Browse ideas",
            "components": ["table", "filters"],
            "states": ["loading", "empty", "error"],
        }
    ],
    "entity_specs": [
        {"name": "Idea", "fields": ["id: UUID", "title: str"]}
    ],
    "endpoint_specs": [
        {
            "method": "GET",
            "path": "/api/ideas",
            "request": "none",
            "response": "list of ideas",
            "auth": "JWT",
        }
    ],
}


def test_legacy_document_still_validates():
    result = validate_ollama_output("DESIGN_DOC", json.dumps(LEGACY))
    assert isinstance(result, DesignDocOutput)
    assert result.screens == "Home list and idea detail."
    assert result.screen_specs == []
    assert result.open_questions == ["Should ideas be deletable?"]


def test_typed_document_validates_and_fills_legacy_summaries():
    result = validate_ollama_output("DESIGN_DOC", json.dumps(TYPED))
    assert len(result.screen_specs) == 1
    assert "IdeaList" in result.screens
    assert "loading, empty, error" in result.screens
    assert "id: UUID" in result.data_model
    assert "GET /api/ideas" in result.api_contracts


def test_renderer_uses_typed_specs():
    text = render_design_contract(TYPED)
    assert "###" not in text
    assert "IdeaList" in text
    assert "components: table, filters" in text
    assert "GET /api/ideas" in text
    assert "response: list of ideas" in text
    assert "auth: JWT" in text
    assert "Home list" not in text


def test_renderer_falls_back_to_legacy_strings():
    text = render_design_contract(LEGACY)
    assert "Home list and idea detail." in text
    assert "GET /api/ideas returns a list." in text
    assert "Should ideas be deletable?" in text


def test_renderer_caps_length():
    text = render_design_contract(LEGACY, max_chars=80)
    assert len(text) <= 80
    assert "truncated" in text


def test_prompts_describe_the_typed_contract():
    design_prompt = (ROOT / "app/prompt_templates/design_doc.txt").read_text()
    build_prompt = (ROOT / "app/prompt_templates/build_code.txt").read_text()
    for key in ("screen_specs", "entity_specs", "endpoint_specs"):
        assert key in design_prompt
    assert "### Design contract" in build_prompt
