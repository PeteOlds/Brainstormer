"""Registry metadata used by the idea detail tab strip.

The UI groups action tabs into "action" (stage-gated forward steps) and
"analysis" (exploratory reads). That split lives on each registry entry so
new actions pick up grouping automatically.
"""

from app.services.secondary_actions import get_action, list_actions


def test_every_action_has_a_category():
    actions = list_actions()
    assert actions, "registry must not be empty"
    assert {a["category"] for a in actions} == {"action", "analysis"}


def test_action_category_matches_stage_gated_steps():
    action_keys = {a["key"] for a in list_actions() if a["category"] == "action"}
    assert action_keys == {"PRD_DOC", "DESIGN_DOC", "BUILD_CODE"}


def test_analysis_category_holds_exploratory_actions():
    analysis_keys = {a["key"] for a in list_actions() if a["category"] == "analysis"}
    assert {
        "COMPETITORS",
        "FIVE_FORCES",
        "PESTEL",
        "BUSINESS_MODEL_CANVAS",
    } <= analysis_keys


def test_list_actions_returns_copies():
    actions = list_actions()
    actions[0]["label"] = "mutated"
    assert get_action(actions[0]["key"])["label"] != "mutated"
