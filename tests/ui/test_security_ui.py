"""Security regression tests driven through the real browser.

Each test here reproduces a concrete exploit against the UI. They are the
proof that a fix works, not a proxy for one: an HTTP 200 says nothing about
whether a payload executed.
"""

import pytest

from tests.ui.conftest import assert_no_page_errors

pytestmark = pytest.mark.ui

DETAIL = "[data-testid='detail-modal']"


def test_stored_xss_in_idea_content_is_not_executed(admin_page, live_server, seeded):
    """Idea content is rendered with x-html; markup must not execute."""
    idea_id = seeded["idea_ids"]["IDEA-9006"]
    admin_page.goto(
        f"{live_server}/ideas?idea={idea_id}", wait_until="domcontentloaded"
    )
    admin_page.wait_for_selector(DETAIL, state="visible", timeout=15000)
    admin_page.wait_for_timeout(1500)

    assert admin_page.evaluate("() => window.__xss") is None

    # The payload survives as visible text, but no executable node may exist.
    assert admin_page.locator(f"{DETAIL} script").count() == 0
    assert admin_page.locator(f"{DETAIL} [onerror]").count() == 0
    assert admin_page.locator(f"{DETAIL} [onclick]").count() == 0

    # The payload is still visible as text, just inert.
    assert "Payload" in admin_page.locator(DETAIL).inner_text()
    assert_no_page_errors(admin_page)


def test_javascript_uri_in_idea_content_is_inert(admin_page, live_server, seeded):
    idea_id = seeded["idea_ids"]["IDEA-9006"]
    admin_page.goto(
        f"{live_server}/ideas?idea={idea_id}", wait_until="domcontentloaded"
    )
    admin_page.wait_for_selector(DETAIL, state="visible", timeout=15000)
    admin_page.wait_for_timeout(1200)

    hrefs = admin_page.locator(f"{DETAIL} a").evaluate_all(
        "els => els.map(e => e.getAttribute('href'))"
    )
    for href in hrefs:
        assert not (href or "").lower().startswith("javascript:")
    assert admin_page.evaluate("() => window.__xss") is None


def test_admin_create_user_modal_opens_without_inline_handlers(
    admin_page, live_server
):
    """The button used to rely on onclick, which CSP now blocks."""
    from tests.ui.conftest import goto

    goto(admin_page, f"{live_server}/admin/users")
    admin_page.wait_for_selector("#create-user-btn", timeout=15000)
    admin_page.click("#create-user-btn")
    dialog = admin_page.locator("[role='dialog']").first
    dialog.wait_for(state="visible", timeout=5000)
    assert "Create User" in dialog.inner_text()
    assert_no_page_errors(admin_page)


def test_https_serves_the_login_page(browser, tls_server):
    base_url, _app = tls_server
    ctx = browser.new_context(ignore_https_errors=True)
    ctx.route(
        "**/*",
        lambda route: (
            route.continue_()
            if route.request.url.startswith(base_url)
            else route.abort()
        ),
    )
    ctx.add_init_script("window.tailwind = window.tailwind || { config: {} };")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    try:
        page.goto(f"{base_url}/login", wait_until="domcontentloaded")
        assert "Sign in" in page.inner_text("body")
        assert page.url.startswith("https://")
        assert errors == []
    finally:
        ctx.close()


def test_https_sets_hsts_and_secure_session_cookie(browser, tls_server):
    base_url, _app = tls_server
    ctx = browser.new_context(ignore_https_errors=True)
    page = ctx.new_page()
    try:
        response = page.goto(f"{base_url}/login", wait_until="domcontentloaded")
        assert response.headers.get("strict-transport-security")
        page.fill("#email", "ui-admin@example.com")
        page.fill("#password", "admin123")
        page.click("#submit-btn")
        page.wait_for_url("**/ideas", timeout=15000)

        cookies = ctx.cookies()
        names = {c["name"] for c in cookies}
        assert "access_token" in names
        for cookie in cookies:
            if cookie["name"] == "access_token":
                assert cookie["secure"] is True
                assert cookie["httpOnly"] is True
    finally:
        ctx.close()


def test_tokens_are_not_readable_by_javascript(admin_page, seeded):
    """An XSS payload must not be able to steal a session token."""
    keys = admin_page.evaluate("() => Object.keys(localStorage)")
    assert "access_token" not in keys
    assert "refresh_token" not in keys

    cookies = admin_page.evaluate("() => document.cookie")
    cookie_names = [c.split("=")[0].strip() for c in cookies.split(";") if c.strip()]
    assert "access_token" not in cookie_names
    assert "refresh_token" not in cookie_names


def test_cookie_auth_can_write_only_with_the_csrf_header(admin_page):
    """The session cookie alone is not enough to change state."""
    with_csrf = admin_page.evaluate(
        """async () => {
            const r = await authFetch('/api/v1/ideas', {
                method: 'POST',
                body: JSON.stringify({prompt_title: 'CSRF ok', raw_content: 'x'})
            });
            return r.status;
        }"""
    )
    assert with_csrf == 201, with_csrf

    without_csrf = admin_page.evaluate(
        """async () => {
            const r = await fetch('/api/v1/ideas', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({prompt_title: 'CSRF blocked', raw_content: 'x'})
            });
            return r.status;
        }"""
    )
    assert without_csrf == 401, without_csrf
