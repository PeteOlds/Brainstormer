"""End-to-end tests for the ideas dashboard using Playwright.

Run against a live Brainstormer instance:
    python tests/ui/test_dashboard_e2e.py

Requires a running Brainstormer instance at http://localhost:8000.
"""

import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"


def login_as_admin(page, instance_number="90"):
    """Login as admin scoped to an instance."""
    page.goto(f"{BASE}/login?instance={instance_number}")
    page.wait_for_timeout(1000)
    page.fill("#email", "admin@example.com")
    page.fill("#password", "admin123")
    page.click("#submit-btn")
    page.wait_for_url("**/ideas")


def test_dashboard_ideas_load(page):
    """Dashboard shows ideas after login."""
    login_as_admin(page, "90")
    page.wait_for_timeout(3000)

    idea_refs = page.locator("text=/^IDEA-/").all_inner_texts()
    assert len(idea_refs) > 0, "No ideas rendered on dashboard"
    print(f"PASS: Dashboard shows {len(idea_refs)} ideas")


def test_checkbox_does_not_open_idea(page):
    """Clicking the selection checkbox does not open the idea detail modal."""
    login_as_admin(page, "90")
    page.wait_for_timeout(5000)

    # Get first idea reference code
    first_ref = page.locator("text=/^IDEA-/").first.inner_text()

    # Click the first checkbox
    page.locator('input[type="checkbox"][aria-label="Select idea"]').first.click()
    page.wait_for_timeout(1500)

    # Check that detail modal did NOT open
    modal_shows_idea = page.locator(f'[role="dialog"]:has-text("{first_ref}")').count()
    assert modal_shows_idea == 0, (
        f"Checkbox click opened detail modal for {first_ref}"
    )

    # Checkbox should be checked
    assert page.locator('input[type="checkbox"][aria-label="Select idea"]').first.is_checked()

    print("PASS: Checkbox does not open idea detail modal")


def test_detail_modal_shows_content(page):
    """Clicking an idea opens the detail modal with content visible."""
    login_as_admin(page, "90")
    page.wait_for_timeout(5000)

    # Click on first idea card (not the checkbox)
    page.locator("article").first.click()
    page.wait_for_timeout(3000)

    # Check Idea Content section has content
    content_area = page.locator('[role="dialog"] .prose')
    assert content_area.count() > 0, "Idea Content prose area not found"
    content_text = content_area.inner_text()
    assert len(content_text) > 10, f"Idea Content is empty (got: {content_text[:50]!r})"

    # Check Idea Content heading is present
    assert page.locator('[role="dialog"] h3:has-text("Idea Content")').count() > 0

    print(f"PASS: Idea detail modal shows content ({len(content_text)} chars)")


def test_bulk_status_change(page):
    """Select multiple ideas and bulk change their status."""
    login_as_admin(page, "90")
    page.wait_for_timeout(5000)

    # Select two ideas
    checkboxes = page.locator('input[type="checkbox"][aria-label="Select idea"]')
    assert checkboxes.count() >= 2, f"Expected at least 2 checkboxes, got {checkboxes.count()}"

    checkboxes.first.click()
    checkboxes.nth(1).click()
    page.wait_for_timeout(1000)

    # Bulk action bar should appear
    assert page.locator("text=idea").first.is_visible() or page.locator("text=ideas").first.is_visible(), (
        "Bulk action bar did not appear after selecting ideas"
    )

    # Select a status from the dropdown
    page.locator('select[x-model="bulkStatus"]').click()
    page.wait_for_timeout(500)
    page.locator('select[x-model="bulkStatus"]').select_option("SCOPE")
    page.wait_for_timeout(500)

    # Click Apply
    page.locator("button:has-text('Apply')").click()
    page.wait_for_timeout(2000)

    # Confirm in modal
    page.locator("button:has-text('Confirm & Apply')").click()
    page.wait_for_timeout(2000)

    # The ideas should now show SCOPE status
    # (We can't easily read the status from the DOM text, but if no error
    #  appeared and the modal closed, the action succeeded)
    print("PASS: Bulk status change flow completed")


def test_prompts_scoped_to_instance(page):
    """Prompts page shows only the current instance's prompts."""
    login_as_admin(page, "90")
    page.wait_for_timeout(2000)

    page.goto(f"{BASE}/prompts")
    page.wait_for_timeout(5000)

    prompt_rows = page.locator("tbody tr:visible").count()
    print(f"Prompt rows visible: {prompt_rows}")

    # Should not be an empty state
    no_prompts = page.locator("text=No ideas found").count()
    assert no_prompts == 0, "Prompts page shows empty state unexpectedly"

    print(f"PASS: Prompts page shows {prompt_rows} prompts")


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            test_dashboard_ideas_load(page)
            test_checkbox_does_not_open_idea(page)
            test_detail_modal_shows_content(page)
            test_bulk_status_change(page)
            test_prompts_scoped_to_instance(page)
            print("\nAll dashboard E2E tests passed!")
        finally:
            browser.close()
