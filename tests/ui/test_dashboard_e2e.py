"""Ideas dashboard browser tests (ported from the script-style e2e file).

Every test drives the real UI against the seeded live server; nothing here
depends on a running deployment.
"""

import pytest

from tests.ui.conftest import assert_no_page_errors, goto

pytestmark = pytest.mark.ui

DETAIL = "[data-testid='detail-modal']"


def _open_first_card(page):
    page.wait_for_selector("[data-testid='idea-card']", timeout=15000)
    card = page.locator("[data-testid='idea-card']").first
    reference = card.inner_text().split()[0]
    card.click()
    page.wait_for_selector(DETAIL, state="visible", timeout=10000)
    return reference


def test_checkbox_does_not_open_idea(admin_page):
    admin_page.wait_for_selector("[data-testid='idea-card']", timeout=15000)
    box = admin_page.locator(
        'input[type="checkbox"][aria-label="Select idea"]'
    ).first
    box.click()
    admin_page.wait_for_timeout(500)
    assert admin_page.locator(DETAIL).is_visible() is False
    assert box.is_checked()
    assert_no_page_errors(admin_page)


def test_detail_modal_shows_content(admin_page):
    reference = _open_first_card(admin_page)
    dialog = admin_page.locator(DETAIL)
    assert reference in dialog.inner_text()
    # Content is fetched after the modal opens; wait for it to land rather
    # than reading the placeholder (`x-html` renders "undefined" until then).
    admin_page.wait_for_function(
        """() => {
            const el = document.querySelector(
                "[data-testid='detail-modal'] .prose");
            if (!el) return false;
            const text = el.innerText.trim();
            return text.length > 10 && text !== 'undefined';
        }""",
        timeout=15000,
    )
    prose = dialog.locator(".prose")
    assert prose.count() > 0
    assert len(prose.first.inner_text()) > 10
    assert_no_page_errors(admin_page)


def test_bulk_status_change(admin_page):
    admin_page.wait_for_selector("[data-testid='idea-card']", timeout=15000)
    cards = admin_page.locator("[data-testid='idea-card']")
    assert cards.count() >= 2
    references = [cards.nth(i).inner_text().split()[0] for i in range(2)]

    boxes = admin_page.locator(
        'input[type="checkbox"][aria-label="Select idea"]'
    )
    boxes.nth(0).click()
    boxes.nth(1).click()
    admin_page.wait_for_timeout(500)

    admin_page.select_option('select[x-model="bulkStatus"]', "SCOPE")
    admin_page.click("button:has-text('Apply')")
    admin_page.wait_for_selector("[data-testid='bulk-confirm-modal']", state="visible")
    admin_page.click("button:has-text('Confirm & Apply')")
    admin_page.wait_for_timeout(2000)

    admin_page.reload(wait_until="domcontentloaded")
    admin_page.wait_for_selector("[data-testid='idea-card']", timeout=15000)
    for reference in references:
        card = admin_page.locator(
            f"[data-testid='idea-card']:has-text('{reference}')"
        ).first
        text = card.inner_text().upper()
        assert "SCOPE" in text
    assert_no_page_errors(admin_page)


def test_prompts_page_lists_seeded_prompt(admin_page, live_server):
    goto(admin_page, f"{live_server}/prompts")
    admin_page.wait_for_timeout(1500)
    assert "UI Seed Prompt" in admin_page.inner_text("body")
    assert_no_page_errors(admin_page)
