"""Idea detail tab strip: fixed lifecycle tabs plus one Analysis tab.

A wall of analysis tabs used to bury the latest result. Regression cover for
the replacement: PRD/Design/Build/Tests stay in lifecycle order, every
analysis lives behind a single Analysis tab whose chips pick a document.
"""

import pytest

from app.extensions import db
from app.models import ActionType, Idea, SecondaryActionResult
from tests.ui.conftest import assert_no_page_errors, goto

pytestmark = pytest.mark.ui

STRIP = "[role='tablist'][aria-label='Idea sections']"
CHIPS = "[role='tablist'][aria-label='Analysis documents']"


def _seed_actions(live_app):
    """Give IDEA-9003 a full lifecycle plus more analyses than fit as tabs."""
    with live_app.app_context():
        idea = Idea.query.filter_by(reference_code="IDEA-9003").first()
        SecondaryActionResult.query.filter_by(idea_id=idea.id).delete()
        for t in (
            ActionType.PRD_DOC,
            ActionType.DESIGN_DOC,
            ActionType.BUILD_CODE,
            ActionType.COMPETITORS,
            ActionType.FEASIBILITY_SCORE,
            ActionType.FIVE_FORCES,
            ActionType.PESTEL,
            ActionType.VRIO,
        ):
            db.session.add(
                SecondaryActionResult(
                    idea_id=idea.id,
                    action_type=t,
                    model_used="test",
                    result_data={},
                )
            )
        db.session.commit()


def _open_idea(page, live_server, reference="IDEA-9003"):
    goto(page, f"{live_server}/ideas")
    page.wait_for_selector("[data-testid='idea-card']", timeout=15000)
    page.locator("[data-testid='idea-card']", has_text=reference).first.click()
    page.wait_for_selector("[data-testid='detail-modal']", state="visible")
    # Actions arrive with the detail request, after the modal opens.
    page.locator(STRIP).get_by_role("tab", name="Analysis").wait_for(timeout=15000)


def test_lifecycle_tabs_are_ordered_and_analysis_is_one_tab(
    admin_page, live_app, live_server
):
    _seed_actions(live_app)
    _open_idea(admin_page, live_server)

    strip = admin_page.locator(STRIP)
    text = strip.inner_text()

    # Fixed lifecycle order, then the single Analysis tab.
    order = ["Idea", "PRD", "Design", "Build", "Tests", "Analysis"]
    positions = [text.index(name) for name in order]
    assert positions == sorted(positions), text

    # Analysis labels never become tabs of their own.
    for label in ("PESTEL", "VRIO", "Five Forces", "Feasibility Score"):
        assert label not in text

    # Only one Analysis tab, even with eight stored analyses.
    assert text.count("Analysis") == 1
    # The old duplicate prompt link is gone from the strip.
    assert "Prompt" not in text

    assert_no_page_errors(admin_page)


def test_analysis_chips_switch_documents(admin_page, live_app, live_server):
    _seed_actions(live_app)
    _open_idea(admin_page, live_server)

    admin_page.locator(STRIP).get_by_role("tab", name="Analysis").click()
    chips = admin_page.locator(CHIPS)
    chips.wait_for(state="visible", timeout=10000)

    labels = [t.strip() for t in chips.locator("[role='tab']").all_inner_texts()]
    assert "PESTEL" in labels and "VRIO Framework" in labels

    chips.get_by_role("tab", name="PESTEL").click()
    assert (
        chips.get_by_role("tab", name="PESTEL").get_attribute("aria-selected") == "true"
    )
    assert admin_page.get_by_role("heading", name="PESTEL").is_visible()

    assert_no_page_errors(admin_page)
