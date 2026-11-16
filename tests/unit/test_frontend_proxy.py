"""Unit tests for the static-file + /api reverse-proxy helper.

``frontend_proxy`` runs as a standalone script for supervised builds, so it
never gets imported by the Flask app and had zero coverage. These tests drive
the handler with stubbed sockets and a patched ``urlopen`` so no real port is
bound and no backend is required.
"""

import io
import urllib.error
from email.message import Message
from unittest.mock import MagicMock, patch

import pytest

from app.services import frontend_proxy


class _StubHandler(frontend_proxy.ProxyHandler):
    """A ProxyHandler with fake socket, headers and response recording."""

    def __init__(
        self,
        backend="http://127.0.0.1:8000/",
        path="/api/v1/ideas",
        command="GET",
        headers=None,
        body=b"",
    ):
        self.backend = backend.rstrip("/")
        self.path = path
        self.command = command
        self.headers = headers or {}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.sent = []

    def send_response(self, code, message=None):
        self.sent.append(("status", code, message))

    def send_header(self, key, value):
        self.sent.append(("header", key, value))

    def end_headers(self):
        self.sent.append(("end",))

    def send_error(self, code, message=None):
        self.sent.append(("error", code, message))


class _FakeResponse:
    def __init__(self, status=200, reason="OK", headers=None, data=b"{}"):
        self.status = status
        self.reason = reason
        self.headers = headers or Message()
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


class TestPathRouting:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/api/v1/ideas", True),
            ("/api", True),
            ("/api?x=1", True),
            ("/health", True),
            ("/ready", True),
            ("/docs", True),
            ("/openapi.json", True),
            ("/", False),
            ("/assets/app.js", False),
            ("/healthz", False),
        ],
    )
    def test_is_backend_path(self, path, expected):
        handler = _StubHandler(path=path)
        assert handler._is_backend_path() is expected

    def test_backend_target_joins_path(self):
        handler = _StubHandler(backend="http://b:1/", path="/api/x")
        assert handler._backend_target() == "http://b:1/api/x"


class TestProxy:
    def test_successful_get_forwards_body_and_headers(self):
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["Connection"] = "keep-alive"
        handler = _StubHandler(path="/api/x", headers={"X-Test": "1"})
        with patch(
            "app.services.frontend_proxy.urllib.request.urlopen",
            return_value=_FakeResponse(headers=headers, data=b'{"ok": true}'),
        ) as opened:
            handler._proxy()

        req = opened.call_args.args[0]
        assert req.full_url == "http://127.0.0.1:8000/api/x"
        assert ("status", 200, "OK") in handler.sent
        assert ("header", "Content-Type", "application/json") in handler.sent
        # Hop-by-hop headers are stripped from the response.
        assert not any(entry[:2] == ("header", "Connection") for entry in handler.sent)
        assert handler.wfile.getvalue() == b'{"ok": true}'

    def test_head_does_not_write_body(self):
        handler = _StubHandler(command="HEAD")
        with patch(
            "app.services.frontend_proxy.urllib.request.urlopen",
            return_value=_FakeResponse(data=b"ignored"),
        ):
            handler._proxy()
        assert handler.wfile.getvalue() == b""
        assert ("header", "Content-Length", "7") in handler.sent

    def test_post_forwards_request_body(self):
        handler = _StubHandler(
            command="POST",
            headers={"Content-Length": "4", "Content-Type": "text/plain"},
            body=b"ping",
        )
        with patch(
            "app.services.frontend_proxy.urllib.request.urlopen",
            return_value=_FakeResponse(),
        ) as opened:
            handler._proxy()
        req = opened.call_args.args[0]
        assert req.data == b"ping"
        assert req.get_method() == "POST"
        # Original Content-Length is dropped, a correct one is added back.
        assert req.headers["Content-length"] == "4"

    def test_http_error_is_relayed(self):
        error_headers = Message()
        error_headers["Content-Type"] = "application/json"
        error = urllib.error.HTTPError(
            "http://127.0.0.1:8000/api/x",
            404,
            "Not Found",
            error_headers,
            io.BytesIO(b'{"error": "missing"}'),
        )
        handler = _StubHandler()
        with patch(
            "app.services.frontend_proxy.urllib.request.urlopen",
            side_effect=error,
        ):
            handler._proxy()
        assert ("status", 404, "Not Found") in handler.sent
        assert handler.wfile.getvalue() == b'{"error": "missing"}'

    def test_http_error_head_does_not_write_body(self):
        error = urllib.error.HTTPError(
            "http://127.0.0.1:8000/api/x",
            500,
            "Server Error",
            Message(),
            io.BytesIO(b"boom"),
        )
        handler = _StubHandler(command="HEAD")
        with patch(
            "app.services.frontend_proxy.urllib.request.urlopen",
            side_effect=error,
        ):
            handler._proxy()
        assert handler.wfile.getvalue() == b""

    def test_unexpected_error_returns_502(self):
        handler = _StubHandler()
        with patch(
            "app.services.frontend_proxy.urllib.request.urlopen",
            side_effect=ValueError("connection refused"),
        ):
            handler._proxy()
        assert ("error", 502, "Bad gateway") in handler.sent

    def test_closed_socket_is_not_written_on_error(self):
        handler = _StubHandler()
        handler.wfile.close()
        with patch(
            "app.services.frontend_proxy.urllib.request.urlopen",
            side_effect=ValueError("boom"),
        ):
            handler._proxy()
        assert ("error", 502, "Bad gateway") not in handler.sent


class TestVerbDispatch:
    @pytest.mark.parametrize("verb", ["do_POST", "do_PUT", "do_PATCH", "do_DELETE"])
    def test_body_verbs_always_proxy(self, verb):
        handler = _StubHandler(path="/whatever", command=verb[3:])
        with patch.object(handler, "_proxy") as proxy:
            getattr(handler, verb)()
        proxy.assert_called_once_with()

    def test_options_proxies(self):
        handler = _StubHandler(command="OPTIONS")
        with patch.object(handler, "_proxy") as proxy:
            handler.do_OPTIONS()
        proxy.assert_called_once_with()

    def test_get_routes_backend_paths_to_proxy(self):
        handler = _StubHandler(path="/api/x")
        with patch.object(handler, "_proxy") as proxy:
            handler.do_GET()
        proxy.assert_called_once_with()

    def test_get_serves_static_for_other_paths(self):
        handler = _StubHandler(path="/index.html")
        with patch(
            "app.services.frontend_proxy.http.server.SimpleHTTPRequestHandler.do_GET"
        ) as static_get:
            handler.do_GET()
        static_get.assert_called_once_with()

    def test_head_routes_backend_paths_to_proxy(self):
        handler = _StubHandler(path="/health", command="HEAD")
        with patch.object(handler, "_proxy") as proxy:
            handler.do_HEAD()
        proxy.assert_called_once_with()

    def test_head_serves_static_for_other_paths(self):
        handler = _StubHandler(path="/index.html", command="HEAD")
        with patch(
            "app.services.frontend_proxy.http.server.SimpleHTTPRequestHandler.do_HEAD"
        ) as static_head:
            handler.do_HEAD()
        static_head.assert_called_once_with()


class TestMain:
    def test_main_binds_and_closes_on_interrupt(self):
        args = MagicMock(port=9123, root="/tmp/site", backend="http://b")
        server = MagicMock()
        server.serve_forever.side_effect = KeyboardInterrupt

        with (
            patch(
                "app.services.frontend_proxy.argparse.ArgumentParser.parse_args",
                return_value=args,
            ),
            patch(
                "app.services.frontend_proxy.socketserver.ThreadingTCPServer",
                return_value=server,
            ) as server_cls,
        ):
            frontend_proxy.main()

        bind = server_cls.call_args.args[0]
        assert bind == ("0.0.0.0", 9123)
        assert server.allow_reuse_address is True
        server.serve_forever.assert_called_once_with()
        server.server_close.assert_called_once_with()
