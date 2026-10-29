"""Self-contained TLS wiring (Phase E/1).

The container serves HTTPS itself when TLS_CERT_FILE + TLS_KEY_FILE are
set. That must also flip HTTPS enforcement, HSTS and Secure cookies on.
Defaults must stay plain HTTP so existing deployments are unaffected.
"""

import os
import stat

from app import create_app
from app.config import TestingConfig


class TlsTestingConfig(TestingConfig):
    TLS_CERT_FILE = "/certs/server.crt"
    TLS_KEY_FILE = "/certs/server.key"


def test_defaults_stay_http():
    app = create_app("testing")
    assert app.config["FORCE_HTTPS"] is False
    assert app.config["JWT_COOKIE_SECURE"] is False


def test_tls_files_imply_https_and_secure_cookies():
    app = create_app(TlsTestingConfig)
    assert app.config["FORCE_HTTPS"] is True
    assert app.config["JWT_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_SECURE"] is True


def test_hsts_header_when_https_enforced():
    app = create_app(TlsTestingConfig)
    response = app.test_client().get("/login", base_url="https://localhost")
    assert response.headers.get("Strict-Transport-Security")


def test_http_redirects_when_https_enforced():
    app = create_app(TlsTestingConfig)
    response = app.test_client().get("/login", base_url="http://localhost")
    assert response.status_code in (301, 302, 308)
    assert response.headers["Location"].startswith("https://")


def test_proxy_fix_only_when_opted_in():
    from werkzeug.middleware.proxy_fix import ProxyFix

    app = create_app("testing")
    assert not isinstance(app.wsgi_app, ProxyFix)

    class ProxiedConfig(TestingConfig):
        TRUST_PROXY_HEADERS = True

    proxied = create_app(ProxiedConfig)
    assert isinstance(proxied.wsgi_app, ProxyFix)


def test_entrypoint_is_executable_and_passes_through():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "docker-entrypoint.sh")
    path = os.path.abspath(path)
    mode = os.stat(path).st_mode
    assert mode & stat.S_IXUSR
    # No TLS env -> the provided command runs unchanged.
    env = dict(os.environ)
    env.pop("TLS_CERT_FILE", None)
    env.pop("TLS_KEY_FILE", None)
    import subprocess

    result = subprocess.run(
        ["sh", path, "echo", "ok"], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
