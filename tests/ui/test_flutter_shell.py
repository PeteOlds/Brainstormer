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

NODES_JS = """
() => Array.from(document.querySelectorAll('flt-semantics')).map((n) => {
  const r = n.getBoundingClientRect();
  return {
    role: n.getAttribute('role'),
    label: n.getAttribute('aria-label') || '',
    x: Math.round(r.x), y: Math.round(r.y),
    w: Math.round(r.width), h: Math.round(r.height),
  };
})
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def flutter_app():
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

    app = create_app(LiveConfig, init_celery_app=False)
    with app.app_context():
        db.create_all()
        _seed()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    shutil.rmtree(tmpdir, ignore_errors=True)


def _seed():
    from app.models import Idea, Instance, Membership, User, UserRole

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


def _click_node(page, node, settle=500):
    page.mouse.click(node["x"] + node["w"] / 2, node["y"] + node["h"] / 2)
    page.wait_for_timeout(settle)


def _click_text(page, text, timeout=25):
    _wait_text(page, text, timeout=timeout)
    page.get_by_text(text, exact=True).last.click()
    page.wait_for_timeout(600)


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


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_header_shows_admin_nav_identity_and_site(flutter_page, flutter_server):
    """Requirement: Admin menu + username + "Site 90" in the top header."""
    page = flutter_page
    _login(page, flutter_server)

    text = _text(page)
    assert "Admin" in text, text
    assert "Settings" in text, text
    assert "Flutter Admin" in text, text

    labels = [n["label"] for n in _nodes(page)]
    assert any(label.startswith(f"Site {INSTANCE_NUMBER}") for label in labels), labels


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
