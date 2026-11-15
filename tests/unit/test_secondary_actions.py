"""Registry metadata used by the idea detail tab strip.

The UI gives ``action`` entries their own lifecycle tab (Brief, Design, Build)
and folds everything else into the single Analysis tab, so the split has to
live on the registry rather than in a hardcoded UI list.
"""

from app.services.secondary_actions import get_action, list_actions


def test_every_action_has_a_category():
    actions = list_actions()
    assert actions, "registry must not be empty"
    assert {a["category"] for a in actions} == {"action", "analysis"}


def test_action_category_matches_lifecycle_steps():
    action_keys = {a["key"] for a in list_actions() if a["category"] == "action"}
    assert action_keys == {"PRD_DOC", "DESIGN_DOC", "BUILD_CODE"}


def test_analysis_category_holds_exploratory_actions():
    analysis_keys = {a["key"] for a in list_actions() if a["category"] == "analysis"}
    assert {"COMPETITORS", "FIVE_FORCES", "PESTEL", "BUSINESS_MODEL_CANVAS"} <= (
        analysis_keys
    )


def test_known_actions_resolve_by_key():
    assert get_action("prd_doc")["category"] == "action"
    assert get_action("pestel")["category"] == "analysis"
    assert get_action("NOT_A_REAL_ACTION") is None
