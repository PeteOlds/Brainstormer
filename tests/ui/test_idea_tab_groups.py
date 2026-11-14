import pytest

from app.extensions import db
from app.models import ActionType, Idea, SecondaryActionResult
from tests.ui.conftest import assert_no_page_errors, goto

pytestmark = pytest.mark.ui


def test_tab_groups_render_action_first_then_analysis(
    admin_page, live_app, live_server
):
    """Action tabs render before Analysis, newest first, capped with overflow."""
    with live_app.app_context():
        idea = Idea.query.filter_by(reference_code="IDEA-9003").first()
        SecondaryActionResult.query.filter_by(idea_id=idea.id).delete()
        for t in (
            ActionType.COMPETITORS,
            ActionType.FEASIBILITY_SCORE,
            ActionType.FIVE_FORCES,
            ActionType.PESTEL,
            ActionType.VRIO,
            ActionType.THREE_CS,
            ActionType.MARKET_SIZING,
            ActionType.PRD_DOC,
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

    goto(admin_page, f"{live_server}/ideas")
    admin_page.wait_for_selector("[data-testid='idea-card']", timeout=15000)
    admin_page.locator("[data-testid='idea-card']", has_text="IDEA-9003").first.click()
    admin_page.wait_for_selector("[data-testid='detail-modal']", state="visible")
    admin_page.wait_for_function(
        "() => document.querySelector(\"[role='tablist']\")?.innerText.includes('Analysis')",
        timeout=15000,
    )
    strip = admin_page.locator("[role='tablist']")
    text = strip.inner_text()
    assert "Next steps" in text
    assert "Analysis" in text
    assert "Prompt" not in text
    assert text.index("PRD") < text.index("Analysis")
    assert "+1 earlier" in text  # 7 analysis tabs, cap is 6
    assert_no_page_errors(admin_page)
