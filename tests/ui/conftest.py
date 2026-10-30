"""Browser (Playwright) test harness.

These tests run against a real HTTP server in a background thread, with a
file-backed SQLite database so the server thread and the test process see
the same rows. They are opt-in:

    pytest -m ui          # run them
    pytest                # skips them (keeps the default suite ~4 min)

Nothing here touches Redis, Ollama or the network: Celery is eager and
Alpine is served locally. Tailwind/Chart.js come from CDNs and will fail
to load offline, which is why console *resource* errors are reported but
only JavaScript exceptions (`pageerror`) fail a test.
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

ADMIN_EMAIL = "ui-admin@example.com"
ADMIN_PASSWORD = "admin123"
USER_EMAIL = "ui-user@example.com"
USER_PASSWORD = "user123"
INSTANCE_NUMBER = 90


def pytest_collection_modifyitems(config, items):
    """Skip UI tests unless `-m ui` (or another marker expr) was passed."""
    if "ui" in (config.option.markexpr or ""):
        return
    skip = pytest.mark.skip(reason="UI tests: run with `pytest -m ui`")
    for item in items:
        if "ui" in item.keywords:
            item.add_marker(skip)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def live_app():
    """Fresh app + file-backed DB per test (mutation isolation)."""
    tmpdir = tempfile.mkdtemp(prefix="brainstormer-ui-")
    db_path = os.path.join(tmpdir, "ui.db")

    class LiveConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        # The dev server is threaded: one connection shared across threads
        # (StaticPool) corrupts state and hangs requests. A real pool with
        # a busy timeout is the only safe option for a live test server.
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {"check_same_thread": False, "timeout": 30},
        }
        RATELIMIT_ENABLED = False
        # Production allows both: the UI authenticates API calls with the
        # Authorization header, but admin *pages* are plain navigation and
        # carry the login cookie. TestingConfig is headers-only, which
        # would 401 every /admin/* page in the browser.
        JWT_TOKEN_LOCATION = ["headers", "cookies"]
        # The browser UI authenticates with the HttpOnly cookies and echoes
        # the CSRF cookie in X-CSRF-TOKEN, exactly like production.
        JWT_COOKIE_CSRF_PROTECT = True
        JWT_COOKIE_SECURE = False
        LEGACY_WEB_ENABLED = True
        FORCE_HTTPS = False

    app = create_app(LiveConfig, init_celery_app=True)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture()
def live_server(live_app):
    """Serve the app on a free port; yield the base URL."""
    port = _free_port()
    server = make_server("127.0.0.1", port, live_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def seeded(live_app):
    """Deterministic world: one instance, an admin, a member, and ideas."""
    from app.models import Idea, Instance, Membership, User, UserRole

    with live_app.app_context():
        instance = Instance.query.filter_by(number=INSTANCE_NUMBER).first()
        if instance is None:
            instance = Instance(number=INSTANCE_NUMBER, name="UI Test Instance")
            db.session.add(instance)
            db.session.flush()

        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        if admin is None:
            admin = User(email=ADMIN_EMAIL, name="UI Admin", role=UserRole.ADMIN)
            admin.set_password(ADMIN_PASSWORD)
            db.session.add(admin)

        member = User.query.filter_by(email=USER_EMAIL).first()
        if member is None:
            member = User(email=USER_EMAIL, name="UI Member", role=UserRole.USER)
            member.set_password(USER_PASSWORD)
            db.session.add(member)
        db.session.flush()

        for user, role in ((admin, "INSTANCE_ADMIN"), (member, "USER")):
            exists = Membership.query.filter_by(
                user_id=user.id, instance_id=instance.id
            ).first()
            if exists is None:
                db.session.add(
                    Membership(
                        user_id=user.id, instance_id=instance.id, role=role
                    )
                )
        db.session.commit()

        seeds = [
            ("IDEA-9001", "Remote team onboarding kit", "SPARK"),
            ("IDEA-9002", "Local produce subscription boxes", "SCOPE"),
            ("IDEA-9003", "Workshop booking marketplace", "MAP"),
            ("IDEA-9004", "Compliance document assistant", "SHIP"),
            ("IDEA-9005", "Field service scheduling app", "SCALE"),
        ]
        for ref, title, status in seeds:
            if Idea.query.filter_by(reference_code=ref).first() is None:
                db.session.add(
                    Idea(
                        reference_code=ref,
                        prompt_title=title,
                        raw_content=f"## {title}\n\nA test idea for {ref}.",
                        status=status,
                        instance_id=instance.id,
                        created_by_id=admin.id,
                    )
                )

        # Stored-XSS probe: idea content is rendered with x-html, so any
        # markup an idea carries is executable in every viewer's browser.
        if Idea.query.filter_by(reference_code="IDEA-9006").first() is None:
            db.session.add(
                Idea(
                    reference_code="IDEA-9006",
                    prompt_title="XSS probe",
                    raw_content=(
                        "Payload "
                        '<img src=x onerror="window.__xss=1"> '
                        "<script>window.__xss=2</script> "
                        "[link](javascript:window.__xss=3)"
                    ),
                    status="SPARK",
                    instance_id=instance.id,
                    created_by_id=admin.id,
                )
            )
        db.session.commit()

        from app.models import PromptConfig

        if PromptConfig.query.filter_by(title="UI Seed Prompt").first() is None:
            db.session.add(
                PromptConfig(
                    title="UI Seed Prompt",
                    prompt_body="Generate an idea about {{topic}}",
                    interval_minutes=60,
                    model_name="llama3:8b",
                    is_active=True,
                    created_by_id=admin.id,
                    instance_id=instance.id,
                )
            )
            db.session.commit()

        from app.models import Idea as IdeaModel

        idea_ids = {
            row.reference_code: str(row.id)
            for row in IdeaModel.query.filter(
                IdeaModel.reference_code.in_(
                    [ref for ref, _t, _s in seeds] + ["IDEA-9006"]
                )
            ).all()
        }

        return {
            "instance_id": str(instance.id),
            "instance_number": instance.number,
            "admin_id": str(admin.id),
            "member_id": str(member.id),
            "ideas": [ref for ref, _t, _s in seeds],
            "idea_ids": idea_ids,
        }


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        instance = playwright.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture()
def context(browser, live_server):
    """Context that refuses to leave the test origin.

    Tailwind and Chart.js are loaded from CDNs. Offline (CI, sandboxes)
    those requests hang until the navigation timeout, so they are aborted
    here instead. Alpine is served from /static and still works, which is
    what the tests actually exercise.
    """
    ctx = browser.new_context(ignore_https_errors=True)

    # The CDN <script> tags are aborted below, so the inline
    # `tailwind.config = {...}` in base.html would throw. Stub the globals
    # before any page script runs; Alpine is local and unaffected.
    ctx.add_init_script("window.tailwind = window.tailwind || { config: {} };")

    def _only_local(route):
        if route.request.url.startswith(live_server):
            route.continue_()
        else:
            route.abort()

    ctx.route("**/*", _only_local)
    yield ctx
    ctx.close()


def goto(page, url, **kwargs):
    """Navigate without waiting for CDN resources that never arrive."""
    kwargs.setdefault("wait_until", "domcontentloaded")
    return page.goto(url, **kwargs)


@pytest.fixture()
def page(context, live_server, seeded):
    """A page with console/pageerror capture attached."""
    page = context.new_page()
    page._page_errors = []
    page._console_errors = []
    page.on("pageerror", lambda exc: page._page_errors.append(str(exc)))
    page.on(
        "console",
        lambda msg: (
            page._console_errors.append(msg.text) if msg.type == "error" else None
        ),
    )
    yield page


def login(page, base_url, email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
    """Log in through the real login form and land on /ideas."""
    goto(page, f"{base_url}/login?instance={INSTANCE_NUMBER}")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submit-btn")
    page.wait_for_url("**/ideas", timeout=15000)
    return page


@pytest.fixture()
def admin_page(page, live_server):
    login(page, live_server)
    return page


@pytest.fixture()
def member_page(page, live_server):
    login(page, live_server, USER_EMAIL, USER_PASSWORD)
    return page


def assert_no_page_errors(page):
    """Fail on JavaScript exceptions (the 'blank page' class of bug)."""
    assert page._page_errors == [], f"JS errors: {page._page_errors}"


def _write_self_signed_cert(directory: str) -> tuple[str, str]:
    """Throwaway cert for the TLS server (SAN: 127.0.0.1 + localhost)."""
    import datetime as dt

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1))
        .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = os.path.join(directory, "server.crt")
    key_path = os.path.join(directory, "server.key")
    with open(cert_path, "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as fh:
        fh.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    return cert_path, key_path


@pytest.fixture()
def tls_server():
    """Serve the app over HTTPS with a self-signed cert.

    Proves the deployment path: cert files present -> HTTPS served, HSTS
    set, and Secure cookies used.
    """
    tmpdir = tempfile.mkdtemp(prefix="brainstormer-tls-")
    cert_path, key_path = _write_self_signed_cert(tmpdir)
    db_path = os.path.join(tmpdir, "tls.db")

    class TlsConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {"check_same_thread": False, "timeout": 30},
        }
        TLS_CERT_FILE = cert_path
        TLS_KEY_FILE = key_path
        RATELIMIT_ENABLED = False
        JWT_TOKEN_LOCATION = ["headers", "cookies"]
        JWT_COOKIE_CSRF_PROTECT = True

    app = create_app(TlsConfig, init_celery_app=True)
    with app.app_context():
        db.create_all()
        from app.models import User

        admin = User(email=ADMIN_EMAIL, role="ADMIN")
        admin.set_password(ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()

    port = _free_port()
    server = make_server(
        "127.0.0.1", port, app, threaded=True, ssl_context=(cert_path, key_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{port}", app
    finally:
        server.shutdown()
        thread.join(timeout=5)
        with app.app_context():
            db.session.remove()
        shutil.rmtree(tmpdir, ignore_errors=True)
