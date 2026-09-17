"""Registry of follow-up AI actions runnable on existing ideas.

Adding a new action takes three steps, nothing else to touch:
1. Add a prompt template ``app/prompt_templates/<name>.txt`` using the
   ``${ORIGINAL_IDEA_CONTENT}`` placeholder.
2. Add its Pydantic output schema in ``app/schemas/ollama_schemas.py``
   and map the key in ``_ACTION_SCHEMAS`` there.
3. Append one entry to ``ACTION_REGISTRY`` below.

``GET /api/v1/actions`` serves this list, the admin UI renders its
buttons from it, and ``POST /api/v1/ideas/<id>/actions`` validates
against it — so the new action works end to end with no UI changes.
"""

ACTION_REGISTRY = [
    {
        "key": "REFINE",
        "label": "Refine Idea",
        "description": "Distill the concept into a 1-paragraph elevator pitch, core target audience, and primary revenue model.",
        "template": "refine",
        "done_label": "Refined",
    },
    {
        "key": "COMPETITORS",
        "label": "Competitor Analysis",
        "description": "Identify direct and indirect competitors (global and local), key differentiators, and barriers to entry.",
        "template": "competitors",
        "done_label": "Analyzed",
    },
    {
        "key": "FEASIBILITY_SCORE",
        "label": "Feasibility Score",
        "description": "Score technical and market feasibility from 1–10 with reasoning and a verdict.",
        "template": "feasibility",
        "done_label": "Scored",
    },
    {
        "key": "FIVE_FORCES",
        "label": "Five Forces",
        "description": "Porter's Five Forces: rivalry, substitutes, entrants, buyers, suppliers, plus risks and recommendations.",
        "template": "forces",
        "done_label": "Assessed",
    },
    {
        "key": "PESTEL",
        "label": "PESTEL",
        "description": "Macro-environment scan: political, economic, social, technological, environmental, legal, plus opportunities, threats and recommendations.",
        "template": "pestel",
        "done_label": "Scanned",
    },
    {
        "key": "PRD_DOC",
        "label": "Generate PRD",
        "description": "Full Product Requirements Document: vision, personas, scope, user stories, NFRs, UX, risks — plus open questions you can answer and rerun.",
        "template": "prd_doc",
        "done_label": "Documented",
    },
]

_ACTION_INDEX = {entry["key"]: entry for entry in ACTION_REGISTRY}


def list_actions() -> list:
    """Return registry entries safe for API/UI consumption."""
    return [dict(entry) for entry in ACTION_REGISTRY]


def get_action(action_type: str | None) -> dict | None:
    """Return the registry entry for a key, or None if unknown."""
    if not action_type:
        return None
    return _ACTION_INDEX.get(str(action_type).upper())


def is_known_action(action_type: str | None) -> bool:
    """True when the key names a registered follow-up action."""
    return get_action(action_type) is not None
