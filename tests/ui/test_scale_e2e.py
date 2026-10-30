"""Scale-phase collaboration browser tests (ported from the script file).

Drives the real Scale tab on a seeded SCALE idea: child-idea creation and
the per-child action pills.
"""

import pytest

from tests.ui.conftest import assert_no_page_errors

pytestmark = pytest.mark.ui

DETAIL = "[data-testid='detail-modal']"
SCALE_REF = "IDEA-9005"


@pytest.fixture()
def scale_idea_page(admin_page, live_server, seeded):
    """Open the seeded SCALE idea in the detail modal, Scale tab active."""
    idea_id = seeded["idea_ids"][SCALE_REF]
    admin_page.goto(
        f"{live_server}/ideas?idea={idea_id}", wait_until="domcontentloaded"
    )
    admin_page.wait_for_selector(DETAIL, state="visible", timeout=15000)
    admin_page.locator(DETAIL).locator("button:has-text('Scale')").first.click()
    admin_page.wait_for_timeout(1200)
    return admin_page


def test_scale_tab_shows_collaboration_controls(scale_idea_page):
    body = scale_idea_page.locator(DETAIL).inner_text()
    assert "Improve this app" in body
    assert "Suggest an improvement" in body
    assert "Report a problem" in body
    assert_no_page_errors(scale_idea_page)


def test_create_child_idea_appears_in_scale_tab(scale_idea_page, live_server, seeded):
    page = scale_idea_page
    page.locator(DETAIL).locator("button:has-text('Suggest an improvement')").first.click()
    page.wait_for_timeout(800)
    page.fill("input[x-model='childTitle']", "E2E test enhancement")
    page.fill("textarea[x-model='childBody']", "Add an export button to the dashboard.")
    page.locator("button:has-text('Send to the team')").first.click()
    page.wait_for_timeout(2500)

    # Creating a child opens that child's own detail modal; go back to the
    # parent and confirm the child is listed under the Scale tab.
    idea_id = seeded["idea_ids"][SCALE_REF]
    page.goto(f"{live_server}/ideas?idea={idea_id}", wait_until="domcontentloaded")
    page.wait_for_selector(DETAIL, state="visible", timeout=15000)
    page.locator(DETAIL).locator("button:has-text('Scale')").first.click()
    page.wait_for_timeout(1500)

    body = page.locator(DETAIL).inner_text()
    assert "E2E test enhancement" in body
    assert "PRD" in body
    assert "Design" in body
    assert_no_page_errors(page)


