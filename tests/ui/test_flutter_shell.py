"""Flutter web shell smoke tests (the app served at `/`).

Flutter paints into a canvas, so there is no DOM text to assert on. These
tests drive the accessibility tree instead: click the "Enable accessibility"
placeholder, then read roles and aria-labels from `flt-semantics` nodes. That
is the only reliable headless proof that a control exists and responds —
screenshots of a CanvasKit canvas prove nothing here.

Skipped unless `flutter/build/web` exists (`./scripts/build_web.sh`).

    pytest -m ui tests/ui/test_flutter_shell.py
"""

import os
import shutil
import socket
import tempfile
import threading
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.serving import make_server

from app import create_app
from app.config import TestingConfig
from app.extensions import db

FLUTTER_BUILD = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "flutter", "build", "web")
)

pytestmark = [
    pytest.mark.ui,
    pytest.mark.skipif(
        not os.path.isfile(os.path.join(FLUTTER_BUILD, "index.html")),
        reason="flutter/build/web is missing; run ./scripts/build_web.sh",
    ),
]

INSTANCE_NUMBER = 90
INSTANCE_NAME = "Flutter Test Site"
ADMIN_EMAIL = "flutter-admin@example.com"
ADMIN_PASSWORD = "flutter123"

# Mirror the live Site 90 accounts from MANUAL_TEST_PLAN.md. These are seeded
# into the throwaway test DB (never the live one) so the reported login shapes
# are covered: instance admin and standard member.
LIVE_ADMIN_EMAIL = "admin@test.local"
LIVE_ADMIN_PASSWORD = "Admin!2026"
LIVE_ADMIN_NAME = "Test Admin"
LIVE_USER_EMAIL = "user@test.local"
LIVE_USER_PASSWORD = "User!2026"
LIVE_USER_NAME = "Test User"

NODES_JS = """
() => Array.from(document.querySelectorAll('flt-semantics')).map((n) => {
  const r = n.getBoundingClientRect();
  return {
    role: n.getAttribute('role'),
    label: n.getAttribute('aria-label') || '',
    text: n.innerText || '',
    x: Math.round(r.x), y: Math.round(r.y),
    w: Math.round(r.width), h: Math.round(r.height),
  };
})
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _make_flutter_app(token_seconds=None):
    """App wired to the real Flutter bundle and a throwaway database."""
    tmpdir = tempfile.mkdtemp(prefix="brainstormer-flutter-")
    db_path = os.path.join(tmpdir, "flutter.db")
    builds_dir = os.path.join(tmpdir, "builds")
    os.makedirs(builds_dir, exist_ok=True)

    class LiveConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {"check_same_thread": False, "timeout": 30},
        }
        RATELIMIT_ENABLED = False
        FLUTTER_WEB_ROOT = FLUTTER_BUILD
        LEGACY_WEB_ENABLED = True
        FORCE_HTTPS = False
        TLS_CERT_FILE = ""
        TLS_KEY_FILE = ""
        OPENCODE_BUILD_ROOTS = builds_dir
        OPENCODE_SERVER_BUILD_ROOTS = builds_dir

    if token_seconds is not None:
        LiveConfig.JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=token_seconds)

    app = create_app(LiveConfig, init_celery_app=False)
    with app.app_context():
        db.create_all()
        _seed()
    return app, tmpdir


def _close_flutter_app(app, tmpdir):
    with app.app_context():
        db.session.remove()
        db.drop_all()
    shutil.rmtree(tmpdir, ignore_errors=True)


@contextmanager
def _no_real_celery():
    """Keep action POSTs fast: no Redis broker and no LLM calls in UI tests.

    create_app(init_celery_app=False) leaves the module-level Celery singleton
    unconfigured, so task.delay() blocks trying to reach redis:6379. Patch
    the single enqueue seam with a fake job result instead.
    """
    job = MagicMock()
    job.id = "ui-test-job"
    with (
        patch("app.tasks.enqueue_generation", return_value=job),
        patch(
            "app.tasks.ollama_tasks.run_full_pipeline.delay",
            return_value=job,
        ),
    ):
        yield


@pytest.fixture()
def flutter_app():
    app, tmpdir = _make_flutter_app()
    with _no_real_celery():
        yield app
    _close_flutter_app(app, tmpdir)


@pytest.fixture()
def short_token_app():
    """Same site as Test admin: short-lived tokens force a refresh on reload."""
    app, tmpdir = _make_flutter_app(token_seconds=45)
    with _no_real_celery():
        yield app
    _close_flutter_app(app, tmpdir)


def _seed():
    from datetime import datetime, timezone

    from app.models import (
        Idea,
        Instance,
        InstanceAIConfig,
        Membership,
        PromptConfig,
        PromptRun,
        StageAIConfig,
        User,
        UserRole,
    )

    instance = Instance(number=INSTANCE_NUMBER, name=INSTANCE_NAME)
    db.session.add(instance)
    db.session.flush()

    admin = User(email=ADMIN_EMAIL, name="Flutter Admin", role=UserRole.USER)
    admin.set_password(ADMIN_PASSWORD)
    db.session.add(admin)
    db.session.flush()
    # Instance admin, not a global ADMIN: this is the shape that used to lose
    # its `admin_instance_ids` on instance switch and hide the Admin menu.
    db.session.add(
        Membership(user_id=admin.id, instance_id=instance.id, role="INSTANCE_ADMIN")
    )

    for email, name, password, membership_role in (
        (
            LIVE_ADMIN_EMAIL,
            LIVE_ADMIN_NAME,
            LIVE_ADMIN_PASSWORD,
            "INSTANCE_ADMIN",
        ),
        (
            LIVE_USER_EMAIL,
            LIVE_USER_NAME,
            LIVE_USER_PASSWORD,
            "USER",
        ),
    ):
        user = User(email=email, name=name, role=UserRole.USER)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        db.session.add(
            Membership(user_id=user.id, instance_id=instance.id, role=membership_role)
        )

    prompt = PromptConfig(
        title="Seeded prompt",
        prompt_body="Invent a sustainable idea about {{topic}}.",
        interval_minutes=1440,
        model_name="llama3",
        provider="ollama",
        is_active=True,
        instance_id=instance.id,
        created_by_id=admin.id,
    )
    db.session.add(prompt)
    db.session.flush()

    # One provider saved (Editable), one phase configured; the other
    # providers/phases show "Configure".
    db.session.add(
        InstanceAIConfig(
            instance_id=instance.id,
            provider="openai",
            model_allowlist=["gpt-4o-mini"],
            budget_cents=5000,
        )
    )
    db.session.add(
        StageAIConfig(
            instance_id=instance.id,
            stage="SCOPE",
            provider="ollama",
            model_name="llama3",
            temperature=0.4,
        )
    )
    db.session.add_all(
        [
            PromptRun(
                instance_id=instance.id,
                prompt_config_id=prompt.id,
                triggered_by="manual",
                status="SUCCESS",
                provider="ollama",
                model="llama3",
                duration_seconds=8.5,
                created_at=datetime.now(timezone.utc),
            ),
            PromptRun(
                instance_id=instance.id,
                prompt_config_id=prompt.id,
                triggered_by="manual",
                status="FAILED",
                provider="ollama",
                model="llama3",
                error="connection refused",
                created_at=datetime.now(timezone.utc),
            ),
        ]
    )

    for ref, title, status in (
        ("IDEA-9101", "Kelp reforestation marketplace", "SPARK"),
        ("IDEA-9102", "Tidal energy monitoring kit", "SPARK"),
        ("IDEA-9103", "Predator-free sanctuary bookings", "SCOPE"),
    ):
        db.session.add(
            Idea(
                reference_code=ref,
                prompt_title=title,
                raw_content=f"## {title}\n\nSeed idea for {ref}.",
                status=status,
                instance_id=instance.id,
                prompt_config_id=prompt.id,
                created_by_id=admin.id,
            )
        )
    db.session.commit()


@pytest.fixture()
def flutter_server(flutter_app):
    port = _free_port()
    server = make_server("127.0.0.1", port, flutter_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def flutter_page(browser, flutter_server):
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()
    page._page_errors = []
    page.on("pageerror", lambda exc: page._page_errors.append(str(exc)))
    yield page
    context.close()


@pytest.fixture()
def short_token_server(short_token_app):
    port = _free_port()
    server = make_server("127.0.0.1", port, short_token_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def short_token_page(browser, short_token_server):
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()
    page._page_errors = []
    page.on("pageerror", lambda exc: page._page_errors.append(str(exc)))
    yield page
    context.close()


# --------------------------------------------------------------------------
# Semantics helpers
# --------------------------------------------------------------------------


def _enable_semantics(page, timeout=30):
    """Turn on Flutter's accessibility tree and wait until it has content.

    The host element exists from first paint but stays hidden until the
    placeholder is activated, so an early click is lost. Poll until the tree
    reports text.
    """
    import time

    page.wait_for_selector(
        "flt-semantics-placeholder", state="attached", timeout=timeout * 1000
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        page.evaluate(
            "() => { const el = document.querySelector('flt-semantics-placeholder');"
            " if (el) el.click(); }"
        )
        page.wait_for_timeout(500)
        text = _text(page)
        if text.strip():
            return
    raise AssertionError("Flutter semantics tree never became visible")


def _text(page):
    return page.evaluate(
        "() => { const h = document.querySelector('flt-semantics-host');"
        " return h ? h.innerText : ''; }"
    )


def _wait_text(page, needle, timeout=25):
    page.wait_for_function(
        "needle => { const h = document.querySelector('flt-semantics-host');"
        " return !!h && h.innerText.includes(needle); }",
        arg=needle,
        timeout=timeout * 1000,
    )


def _nodes(page):
    return page.evaluate(NODES_JS)


def _labels(page):
    return [n["label"] for n in _nodes(page)]


def _wait_label(page, needle, timeout=25):
    page.wait_for_function(
        "needle => Array.from(document.querySelectorAll('flt-semantics')).some("
        "n => (n.getAttribute('aria-label') || '').includes(needle))",
        arg=needle,
        timeout=timeout * 1000,
    )


def _wait_any(page, needle, timeout=25):
    """Wait until either the semantics text or an aria-label contains it."""
    page.wait_for_function(
        """needle => {
          const host = document.querySelector('flt-semantics-host');
          if (host && host.innerText.includes(needle)) return true;
          return Array.from(document.querySelectorAll('flt-semantics')).some(
            (n) => (n.getAttribute('aria-label') || '').includes(needle));
        }""",
        arg=needle,
        timeout=timeout * 1000,
    )


def _contains(page, needle):
    return needle in _text(page) or any(needle in label for label in _labels(page))


def _scroll_until(page, needle, tries=14, delta=400):
    """Scroll the routed list until the needle is in view.

    Flutter only builds semantics for visible list rows, so content below
    the fold is invisible to the accessibilty tree.
    """
    for _ in range(tries):
        if _contains(page, needle):
            return
        page.mouse.move(700, 500)
        page.mouse.wheel(0, delta)
        page.wait_for_timeout(400)
    raise AssertionError(f"{needle!r} never scrolled into view")


def _scroll_top(page):
    page.mouse.move(700, 400)
    page.mouse.wheel(0, -6000)
    page.wait_for_timeout(500)


def _smallest_node(page, needle):
    """Smallest visible semantics node whose text/label contains needle."""
    candidates = [
        n
        for n in _nodes(page)
        if n["w"] > 0
        and n["h"] > 0
        and needle in f"{n['label']} {n['text']}"
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda n: n["w"] * n["h"])


def _click_node(page, node, settle=500):
    page.mouse.click(node["x"] + node["w"] / 2, node["y"] + node["h"] / 2)
    page.wait_for_timeout(settle)


def _click_text(page, text, timeout=25):
    _wait_text(page, text, timeout=timeout)
    page.get_by_text(text, exact=True).last.click()
    page.wait_for_timeout(600)


def _click_dialog_run(page):
    """Click the confirm button in a Flutter AlertDialog.

    The dialog's own text node also contains "Run" (in its title), so a
    text locator can hit the wrong semantics node. Find the button by its
    role and exact text, then click its centre through the canvas.
    """
    page.wait_for_function(
        """() => Array.from(document.querySelectorAll('flt-semantics')).some((n) =>
             n.getAttribute('role') === 'button' &&
             (n.innerText || '').trim() === 'Run')"""
    )
    run = next(
        n
        for n in _nodes(page)
        if n["role"] == "button" and n["text"].strip() == "Run"
    )
    _click_node(page, run)


def _rows(page):
    """Idea rows: full-width buttons labelled with the idea summary."""
    return [n for n in _nodes(page) if n["role"] == "button" and len(n["label"]) > 40]


def _fill_input(page, locator, value):
    """Type into a Flutter text field.

    `fill` alone is unreliable: Flutter re-creates the semantics <input> for
    obscured fields and the value can be lost before submit (the app then
    reports "Invalid credentials"). Click, clear, type, then verify.
    """
    for _ in range(4):
        locator.click()
        page.wait_for_timeout(150)
        locator.press("Control+A")
        locator.press("Backspace")
        locator.press_sequentially(value, delay=40)
        page.wait_for_timeout(150)
        if locator.input_value() == value:
            return
    raise AssertionError(f"text field kept value {locator.input_value()!r}")


def _login(page, base_url):
    page.goto(
        f"{base_url}/login?instance={INSTANCE_NUMBER}", wait_until="domcontentloaded"
    )
    _enable_semantics(page)
    inputs = page.locator("input")
    _fill_input(page, inputs.nth(0), ADMIN_EMAIL)
    _fill_input(page, inputs.nth(1), ADMIN_PASSWORD)
    _click_text(page, "Sign in")
    # A single-membership user lands on the ideas list directly; a user with
    # several sites gets the picker first.
    try:
        _wait_text(page, "matching ideas", timeout=20)
    except Exception:
        _click_text(page, INSTANCE_NAME)
        _wait_text(page, "matching ideas", timeout=25)


def _login_from_protected_route(page, base_url, email, password):
    """Sign in from a deep link that starts behind the auth gate."""
    page.goto(
        f"{base_url}/ideas?instance={INSTANCE_NUMBER}", wait_until="domcontentloaded"
    )
    _enable_semantics(page)
    inputs = page.locator("input")
    _fill_input(page, inputs.nth(0), email)
    _fill_input(page, inputs.nth(1), password)
    _click_text(page, "Sign in")


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_header_shows_admin_nav_identity_and_site(flutter_page, flutter_server):
    """Requirement: Admin menu + username + "Site 90" in the top header."""
    page = flutter_page
    _login(page, flutter_server)

    text = _text(page)
    assert "Admin" in text, text
    # Instance settings is reached through Admin; a second top-level
    # "Settings" entry was the duplicate the user reported.
    assert "Settings" not in text, text
    assert "Flutter Admin" in text, text

    labels = [n["label"] for n in _nodes(page)]
    assert any(label.startswith(f"Site {INSTANCE_NUMBER}") for label in labels), labels


def _open_admin(page, tile):
    _click_text(page, "Admin")
    _wait_text(page, "Go to")
    _click_text(page, tile)


def test_activity_shows_runs_and_prompt_dashboard_drilldown(
    flutter_page, flutter_server
):
    """Requirement: see what ran/failed, timings, models; drill into a prompt."""
    page = flutter_page
    _login(page, flutter_server)
    _open_admin(page, "Activity")

    _scroll_until(page, "Recent runs")
    text = _text(page)
    labels = " | ".join(_labels(page))
    assert "Seeded prompt" in text or "Seeded prompt" in labels, labels
    assert "connection refused" in text or "connection refused" in labels, labels
    assert "8.5s" in text or "8.5s" in labels, labels
    assert "ollama/llama3" in text or "ollama/llama3" in labels, labels

    _scroll_until(page, "Prompt health Seeded prompt")
    health = [
        n
        for n in _nodes(page)
        if "Prompt health Seeded prompt" in f"{n['label']} {n['text']}"
    ]
    assert health, [n["text"] for n in _nodes(page)][:20]
    _click_node(
        page,
        min(health, key=lambda n: n["w"] * n["h"]),
    )

    _scroll_until(page, "Ideas by state")
    dashboard = _text(page) + " | " + " | ".join(_labels(page))
    assert "Run outcomes" in dashboard, dashboard
    assert "Time by model" in dashboard, dashboard
    assert "SPARK" in dashboard, dashboard

    spark = [
        n
        for n in _nodes(page)
        if n["label"].startswith("SPARK") or n["text"].startswith("SPARK")
    ]
    assert spark, [n["text"] for n in _nodes(page)][:30]
    _click_node(page, min(spark, key=lambda n: n["w"] * n["h"]))
    _wait_text(page, "matching ideas", timeout=25)
    assert "Filtered by" in _text(page)


def test_instance_settings_edits_provider_and_phase_defaults(
    flutter_page, flutter_server, flutter_app
):
    """Requirement: instance admins can edit providers and per-phase AI."""
    page = flutter_page
    _login(page, flutter_server)
    _open_admin(page, "Instance settings")

    _wait_text(page, "AI providers")
    _scroll_until(page, "openai configured")
    labels = " | ".join(_labels(page))
    assert "opencode" in labels or "opencode" in _text(page), labels
    assert "openai" in labels or "openai" in _text(page), labels

    openai_card = [
        n
        for n in _nodes(page)
        if n["role"] == "button" and "openai configured" in n["label"]
    ]
    assert openai_card, [n["label"] for n in _nodes(page)][:30]
    _click_node(page, openai_card[0])
    _wait_any(page, "openai settings")

    inputs = page.locator("input")
    # Dialog fields, in order: key, endpoint, embedding model, ...
    # Model allowlist is now a chip multi-select. Toggle "gpt-4o".
    # Click the "gpt-4o" chip (exact match, not "gpt-4o-mini").
    # Chips render as checkboxes in the accessibility tree.
    gpt_nodes = [
        n for n in _nodes(page)
        if "gpt-4o" in (n["label"] + n["text"]).lower()
    ]
    chip = [
        n for n in gpt_nodes
        if "mini" not in n["label"].lower()
    ]
    assert chip, [n["label"] for n in gpt_nodes]
    _click_node(page, chip[0])
    page.wait_for_timeout(300)
    _click_text(page, "Save")
    page.wait_for_timeout(800)

    from app.models import InstanceAIConfig

    with flutter_app.app_context():
        config = InstanceAIConfig.query.filter_by(provider="openai").first()
        assert sorted(config.model_allowlist or []) == sorted(
            ["gpt-4o-mini", "gpt-4o"]
        )

    _scroll_top(page)
    _click_text(page, "Phase defaults")
    _scroll_until(page, "SPARK inherits")
    spark_card = [
        n
        for n in _nodes(page)
        if n["role"] == "button" and "SPARK inherits" in n["label"]
    ]
    assert spark_card, [n["label"] for n in _nodes(page)][:30]
    _click_node(page, spark_card[0])
    _wait_any(page, "SPARK defaults")

    # Provider dropdown is not an input; the model field is the first one.
    _fill_input(page, page.locator("input").nth(0), "llama3.2")
    _click_text(page, "Save")
    page.wait_for_timeout(800)

    from app.models import StageAIConfig

    with flutter_app.app_context():
        row = StageAIConfig.query.filter_by(stage="SPARK").first()
        assert row is not None
        assert row.model_name == "llama3.2"


def test_admin_can_multi_select_and_bulk_change_status(
    flutter_page, flutter_server, flutter_app
):
    """Requirement: multi-select + bulk state change actually works."""
    page = flutter_page
    _login(page, flutter_server)

    _click_text(page, "Select")
    _wait_text(page, "0 selected")

    rows = [n for n in _rows(page) if "SPARK" in n["label"]]
    assert len(rows) == 2, [n["label"][:60] for n in rows]
    for node in rows:
        _click_node(page, node)
    _wait_text(page, "2 selected")

    _click_text(page, "Change status")
    _click_text(page, "SCOPE")
    _click_text(page, "Confirm")
    _wait_text(page, "Moved 2 ideas to SCOPE", timeout=30)

    # Persisted server-side, not just in the widget tree.
    from app.models import Idea

    with flutter_app.app_context():
        statuses = {
            idea.reference_code: idea.status.value
            for idea in Idea.query.filter(
                Idea.reference_code.in_(["IDEA-9101", "IDEA-9102"])
            ).all()
        }
    assert set(statuses.values()) == {"SCOPE"}, statuses


def test_detail_offers_secondary_actions_and_list_refreshes_on_return(
    flutter_page, flutter_server, flutter_app
):
    """Requirement: start Brief/Design/Build from detail; phase survives back."""
    page = flutter_page
    _login(page, flutter_server)

    # IDEA-9103 is the newest row and is at SCOPE, so Brief (PRD_DOC) is
    # allowed while Design (MAP+) is not.
    page.wait_for_function(
        """ref => Array.from(document.querySelectorAll('flt-semantics')).some((n) =>
             (n.getAttribute('aria-label') || '').includes(ref))""",
        arg="IDEA-9103",
        timeout=25000,
    )
    rows = _rows(page)
    target = next(n for n in rows if "IDEA-9103" in n["label"])
    _click_node(page, target)
    # The section heading itself is not exposed in the semantics tree (it is
    # a bare Text beside an icon button); the first action button is.
    _wait_text(page, "Refine Idea")

    text = _text(page)
    assert "Refine Idea" in text, text
    assert "Brief" in text, text
    assert "Design" not in text, text

    # Change the phase out of band; coming back must reload, not show a
    # stale cached row.
    from app.models import Idea

    with flutter_app.app_context():
        idea = Idea.query.filter_by(reference_code="IDEA-9103").first()
        idea.status = "MAP"
        db.session.commit()

    _click_back(page)
    _wait_text(page, "matching ideas", timeout=25)
    page.wait_for_function(
        """ref => Array.from(document.querySelectorAll('flt-semantics')).some((n) => {
             const label = n.getAttribute('aria-label') || '';
             return label.includes(ref) && label.includes('MAP');
           })""",
        arg="IDEA-9103",
        timeout=25000,
    )


def _click_back(page):
    nodes = [n for n in _nodes(page) if n["label"] == "Back"]
    if nodes:
        _click_node(page, nodes[0])
        return
    # Flutter exposes the IconButton without an aria-label here (the tooltip
    # text shows up as innerText only), so fall back to the header's leading
    # 40x40 button at the top-left of the AppBar.
    leading = [
        n
        for n in _nodes(page)
        if n["role"] == "button" and n["x"] < 60 and n["y"] < 60 and n["w"] <= 60
    ]
    assert leading, "no back button in header"
    _click_node(page, leading[0])


def test_expired_token_restore_keeps_site_admin_actions(
    short_token_page, short_token_server, short_token_app
):
    """BUG.052/053/060/061: refresh must keep the Site 90 instance claim.

    The Test admin shape is deliberate: role USER with an INSTANCE_ADMIN
    membership. A refresh without `instance_id` produces an unscoped token,
    and every admin/action endpoint then rejects that user.
    """
    page = short_token_page
    _login(page, short_token_server)

    # Let the access token expire, then restore the session from storage.
    # The first /me call must trigger a refresh before the app paints.
    page.wait_for_timeout(47_000)
    page.reload(wait_until="domcontentloaded")
    _enable_semantics(page)
    _wait_text(page, "matching ideas", timeout=30)
    assert "Failed to load" not in _text(page)

    # Admin menu was the reported 403.
    _click_text(page, "Admin")
    _wait_text(page, "Go to", timeout=30)
    assert "Failed to load" not in _text(page)

    # Bulk status change also depended on the scoped claim.
    _click_text(page, "Ideas")
    _wait_text(page, "matching ideas", timeout=30)
    _click_text(page, "Select")
    _wait_text(page, "0 selected")
    rows = [n for n in _rows(page) if "SPARK" in n["label"]]
    assert len(rows) == 2, [n["label"][:60] for n in rows]
    for node in rows:
        _click_node(page, node)
    _click_text(page, "Change status")
    _click_text(page, "SCOPE")
    _click_text(page, "Confirm")
    _wait_text(page, "Moved 2 ideas to SCOPE", timeout=30)

    # Secondary actions must still be visible and runnable.
    page.wait_for_function(
        """ref => Array.from(document.querySelectorAll('flt-semantics')).some((n) =>
             (n.getAttribute('aria-label') || '').includes(ref))""",
        arg="IDEA-9103",
        timeout=25000,
    )
    target = next(n for n in _rows(page) if "IDEA-9103" in n["label"])
    _click_node(page, target)
    _wait_text(page, "Refine Idea", timeout=25)
    detail_text = _text(page)
    assert "Brief" in detail_text, detail_text
    assert "Actions unavailable" not in detail_text, detail_text

    _click_text(page, "Refine Idea")
    _wait_any(page, "Run Refine Idea?")
    _click_dialog_run(page)
    _wait_text(page, "Refine Idea started.", timeout=25)

    # run-full is admin-only and used the same instance-scoped check.
    _click_text(page, "Run full pipeline")
    _wait_any(page, "Run full pipeline?")
    _click_dialog_run(page)
    _wait_text(page, "Full pipeline queued.", timeout=25)

    text = _text(page)
    assert "Admin access required" not in text, text

    from app.models import Idea

    with short_token_app.app_context():
        statuses = {
            idea.reference_code: idea.status.value
            for idea in Idea.query.filter(
                Idea.reference_code.in_(["IDEA-9101", "IDEA-9102"])
            ).all()
        }
    assert set(statuses.values()) == {"SCOPE"}, statuses


def test_pipeline_status_survives_navigation_and_refresh(
    flutter_page, flutter_server, flutter_app
):
    """REQ.033 / REQ.034: shell status is persistent, not a passing snackbar."""
    from datetime import datetime, timezone

    from app.extensions import db
    from app.models import Idea, Instance, PromptRun, PromptRunStatus, Release, User

    with flutter_app.app_context():
        instance = Instance.query.filter_by(number=INSTANCE_NUMBER).one()
        admin = User.query.filter_by(email=ADMIN_EMAIL).one()
        parent = Idea(
            reference_code="IDEA-9500",
            prompt_title="Status test parent",
            raw_content="Parent for a release pipeline.",
            status="SCALE",
            instance_id=instance.id,
            created_by_id=admin.id,
        )
        db.session.add(parent)
        db.session.flush()
        run = PromptRun(
            idea_id=parent.id,
            instance_id=instance.id,
            action_type="FULL_PIPELINE",
            status=PromptRunStatus.RUNNING,
            triggered_by="manual",
            created_at=datetime.now(timezone.utc),
        )
        release = Release(
            parent_idea_id=parent.id,
            instance_id=instance.id,
            name="Release Status 1.1",
            created_by_id=admin.id,
            pipeline_status="running",
            pipeline_phase="design",
            pipeline_started_at=datetime.now(timezone.utc),
            pipeline_state={
                "children": {
                    "11111111-1111-4111-8111-111111111111": {
                        "reference_code": "IDEA-9501",
                        "prd": "done",
                        "design": "done",
                    },
                    "22222222-2222-4222-8222-222222222222": {
                        "reference_code": "IDEA-9502",
                        "prd": "done",
                        "design": "pending",
                    },
                }
            },
        )
        db.session.add_all([run, release])
        db.session.commit()
        parent_id = str(parent.id)
        release_id = str(release.id)

    page = flutter_page
    _login(page, flutter_server)
    _wait_text(page, "Full pipeline running — IDEA-9500", timeout=30)
    _wait_text(
        page,
        "Release pipeline running — Release Status 1.1 · Design (1/2)",
        timeout=30,
    )

    # Navigation, then a browser refresh: both must keep the same banner
    # because the status comes from the server, not widget-local state.
    page.goto(
        f"{flutter_server}/prompts?instance={INSTANCE_NUMBER}",
        wait_until="domcontentloaded",
    )
    _enable_semantics(page)
    _wait_text(page, "Full pipeline running — IDEA-9500", timeout=30)

    page.reload(wait_until="domcontentloaded")
    _enable_semantics(page)
    _wait_text(page, "Release pipeline running — Release Status 1.1", timeout=30)

    # The Scale card itself shows the persisted release phase and a Stop
    # action while the pipeline is active.
    page.goto(
        f"{flutter_server}/ideas?instance={INSTANCE_NUMBER}&idea={parent_id}",
        wait_until="domcontentloaded",
    )
    _enable_semantics(page)
    _wait_any(page, "Scale", timeout=25)
    _click_node(page, _smallest_node(page, "Scale"))
    _wait_any(page, "Running · Design", timeout=25)
    assert "Stop" in _text(page)

    with flutter_app.app_context():
        finished = db.session.get(Release, release_id)
        finished.pipeline_status = "done"
        finished.pipeline_phase = "done"
        db.session.commit()

    page.reload(wait_until="domcontentloaded")
    _enable_semantics(page)
    _wait_any(page, "Scale", timeout=25)
    _click_node(page, _smallest_node(page, "Scale"))
    _wait_any(page, "Done", timeout=25)
    assert not page._page_errors, page._page_errors


@pytest.mark.parametrize(
    "email,password,display_name,is_instance_admin",
    [
        (LIVE_ADMIN_EMAIL, LIVE_ADMIN_PASSWORD, LIVE_ADMIN_NAME, True),
        (LIVE_USER_EMAIL, LIVE_USER_PASSWORD, LIVE_USER_NAME, False),
    ],
)
def test_login_from_deep_link_stays_signed_in(
    flutter_page, flutter_server, email, password, display_name, is_instance_admin
):
    """A successful login from /ideas must not bounce back to the login form.

    The auth gate used to cache the first (anonymous) token read, so signing
    in from a protected deep link kept showing LoginPage. Both Site 90 user
    shapes are covered because the bounce affected either account.
    """
    page = flutter_page
    _login_from_protected_route(page, flutter_server, email, password)

    _wait_text(page, "matching ideas", timeout=30)
    text = _text(page)
    assert "Sign in" not in text, text
    assert "Create an account" not in text, text
    assert display_name in text, text
    assert ("Admin" in text) is is_instance_admin, text
    assert not page._page_errors, page._page_errors
