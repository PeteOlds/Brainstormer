"""End-to-end tests for Scale-phase collaboration using Playwright.

Run directly: python tests/ui/test_scale_e2e.py

Requires a running Brainstormer instance at http://localhost:8000.
"""

import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"


def login_as_admin(page):
    """Login as admin@test.local / Admin!2026 (instance 90)."""
    page.goto(f"{BASE}/login?instance=90")
    page.wait_for_url("**/ideas")
    page.fill("#email", "admin@test.local")
    page.fill("#password", "Admin!2026")
    page.click("#submit-btn")
    page.wait_for_url("**/ideas")


def test_scale_collaboration_e2e():
    """Full Scale collaboration flow: child ideas, releases, builds."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            login_as_admin(page)

            # Navigate to IDEA-9603 (SCALE parent idea)
            page.goto(f"{BASE}/ideas?idea=e5c567ba-e04d-4497-b511-94819123a1cf")
            page.wait_for_timeout(3000)

            # Verify we're on the right idea
            assert page.locator("text=IDEA-9603").is_visible()
            assert page.locator("text=SCALE").is_visible()

            # Click Scale tab
            page.locator("button:has-text('Scale')").click()
            page.wait_for_timeout(3000)

            # Verify Scale tab content
            assert page.locator("text=Improve this app").is_visible()
            assert page.locator("text=Suggest an improvement").is_visible()
            assert page.locator("text=Report a problem").is_visible()

            # Create a child idea (enhancement)
            page.locator("button:has-text('Suggest an improvement')").click()
            page.wait_for_timeout(2000)
            page.fill("input[x-model='childTitle']", "E2E test enhancement")
            page.fill(
                "textarea[x-model='childBody']",
                "E2E test: add export functionality",
            )
            page.locator("button:has-text('Send to the team')").click()
            page.wait_for_timeout(3000)

            # Verify child was created
            assert page.locator("text=E2E test enhancement").is_visible()

            # Verify build pills exist
            assert page.locator("text=PRD").is_visible()
            assert page.locator("text=Design").is_visible()
            assert page.locator("text=Built").is_visible()

            print("PASS: Scale collaboration E2E test")
        finally:
            browser.close()


def test_moderation_e2e():
    """Test comment moderation (Hide/Show) flow."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            login_as_admin(page)

            page.goto(f"{BASE}/ideas?idea=e5c567ba-e04d-4497-b511-94819123a1cf")
            page.wait_for_timeout(3000)

            # Verify moderation controls exist for admins
            assert page.locator("text=Hide").is_visible() or page.locator(
                "text=Show"
            ).is_visible()

            print("PASS: Moderation E2E test")
        finally:
            browser.close()


def test_build_url_correction_e2e():
    """Test that Build tab shows correct dashboard URL."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            login_as_admin(page)

            page.goto(f"{BASE}/ideas?idea=e5c567ba-e04d-4497-b511-94819123a1cf")
            page.wait_for_timeout(3000)

            # Click Build tab
            page.locator("button:has-text('Build')").click()
            page.wait_for_timeout(3000)

            # Verify Open link points to dashboard URL (:3000), not API (:8001)
            assert page.locator("text=http://localhost:3000").is_visible()

            print("PASS: Build URL correction E2E test")
        finally:
            browser.close()


if __name__ == "__main__":
    test_scale_collaboration_e2e()
    test_moderation_e2e()
    test_build_url_correction_e2e()
    print("\nAll E2E tests passed!")
