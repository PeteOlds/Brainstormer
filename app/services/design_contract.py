"""Render a stored DESIGN_DOC result into a compact build contract.

Pure formatting only: no database or network access. The typed ``*_specs``
arrays are authoritative when present; legacy flat strings are used for older
documents. Output is capped so a long design cannot crowd out the rest of the
BUILD_CODE supporting material.
"""

from typing import Any

DEFAULT_MAX_CHARS = 6000


def _lines(items: Any, key: str) -> list[str]:
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict) and str(item.get(key, "")).strip()
    ]


def _join(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    return ", ".join(str(v).strip() for v in values if str(v).strip())


def render_design_contract(
    result_data: dict | None, max_chars: int = DEFAULT_MAX_CHARS
) -> str:
    """Return a plain-text contract for the BUILD_CODE prompt, or ''."""
    if not isinstance(result_data, dict):
        return ""

    sections: list[str] = []

    architecture = str(result_data.get("architecture") or "").strip()
    if architecture:
        sections.append("Architecture:\n" + architecture)

    screen_specs = _lines(result_data.get("screen_specs"), "name")
    if screen_specs:
        lines = []
        for spec in screen_specs:
            name = str(spec["name"]).strip()
            purpose = str(spec.get("purpose") or "").strip()
            line = f"- {name}: {purpose}" if purpose else f"- {name}"
            lines.append(line)
            components = _join(spec.get("components"))
            states = _join(spec.get("states"))
            if components:
                lines.append(f"  components: {components}")
            if states:
                lines.append(f"  states: {states}")
        sections.append("Screens:\n" + "\n".join(lines))
    elif str(result_data.get("screens") or "").strip():
        sections.append("Screens:\n" + str(result_data["screens"]).strip())

    entity_specs = _lines(result_data.get("entity_specs"), "name")
    if entity_specs:
        lines = []
        for spec in entity_specs:
            name = str(spec["name"]).strip()
            fields = _join(spec.get("fields"))
            lines.append(f"- {name}: {fields}" if fields else f"- {name}")
            relationships = str(spec.get("relationships") or "").strip()
            if relationships:
                lines.append(f"  relationships: {relationships}")
        sections.append("Data model:\n" + "\n".join(lines))
    elif str(result_data.get("data_model") or "").strip():
        sections.append("Data model:\n" + str(result_data["data_model"]).strip())

    endpoint_specs = [
        item
        for item in (result_data.get("endpoint_specs") or [])
        if isinstance(item, dict)
        and str(item.get("method") or "").strip()
        and str(item.get("path") or "").strip()
    ]
    if endpoint_specs:
        lines = []
        for spec in endpoint_specs:
            method = str(spec["method"]).strip().upper()
            path = str(spec["path"]).strip()
            lines.append(f"- {method} {path}")
            for key in ("request", "response", "auth"):
                value = str(spec.get(key) or "").strip()
                if value:
                    lines.append(f"  {key}: {value}")
        sections.append("API contracts:\n" + "\n".join(lines))
    elif str(result_data.get("api_contracts") or "").strip():
        sections.append("API contracts:\n" + str(result_data["api_contracts"]).strip())

    build_notes = str(result_data.get("build_notes") or "").strip()
    if build_notes:
        sections.append("Build notes:\n" + build_notes)

    questions = result_data.get("open_questions")
    if isinstance(questions, list) and questions:
        lines = [f"- {str(q).strip()}" for q in questions if str(q).strip()]
        if lines:
            sections.append("Open questions:\n" + "\n".join(lines))

    text = "\n\n".join(sections)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 40)] + "\n\n[...design contract truncated...]"
