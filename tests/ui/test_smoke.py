"""Smoke tests: the app boots, renders, and raises no JavaScript errors.

These are the guard rail for the failure mode recorded in AGENTS.md: a
syntax error in an inline `x-data` script makes Alpine fail to initialise
and renders the page blank, while every API still returns 200.
"""

import pytest

from tests.ui.conftest import (
    USER_EMAIL,
    USER_PASSWORD,
    assert_no_page_errors,
    goto,
    login,
)

pytestmark = pytest.mark.ui


def test_login_lands_on_ideas(admin_page):
    assert "/ideas" in admin_page.url
    assert_no_page_errors(admin_page)


def test_dashboard_renders_seeded_ideas(admin_page, seeded):
    admin_page.wait_for_selector("[data-testid='idea-card']", timeout=15000)
    cards = admin_page.locator("[data-testid='idea-card']")
    assert cards.count() >= len(seeded["ideas"])
    body = admin_page.inner_text("body")
    for reference in seeded["ideas"]:
        assert reference in body
    assert_no_page_errors(admin_page)


def test_dashboard_filters_by_status(admin_page, seeded):
    admin_page.wait_for_selector("[data-testid='idea-card']", timeout=15000)
    admin_page.select_option("#status-filter", "SCALE")
    admin_page.wait_for_timeout(800)
    body = admin_page.inner_text("body")
    assert "IDEA-9005" in body
    assert "IDEA-9001" not in body
    assert_no_page_errors(admin_page)


def test_member_login_and_navigation(page, live_server, seeded):
    login(page, live_server, USER_EMAIL, USER_PASSWORD)
    assert "/ideas" in page.url
    goto(page, f"{live_server}/home")
    page.wait_for_selector("text=Your ideas", timeout=15000)
    assert_no_page_errors(page)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/home", "Your ideas"),
        ("/prompts", "Prompt"),
        ("/admin/users", "User"),
        ("/admin/activity", "Activit"),
        ("/admin/backup", "Backup"),
        ("/admin/ai", "AI"),
    ],
)
def test_admin_pages_render_without_js_errors(admin_page, live_server, path, expected):
    goto(admin_page, f"{live_server}{path}")
    admin_page.wait_for_timeout(800)
    assert expected.lower() in admin_page.inner_text("body").lower()
    assert_no_page_errors(admin_page)
