"""Tiny static-file server with an /api reverse proxy.

Used by the supervised runner so a generated build's frontend can be
opened on this machine without a separate nginx/container.  Static files
are served from ``--root``; requests under ``/api`` (and a handful of
backend metadata paths) are forwarded to ``--backend``.
"""

import argparse
import http.server
import socketserver
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, backend="", **kwargs):
        self.backend = backend.rstrip("/")
        super().__init__(*args, **kwargs)

    def _backend_target(self):
        return self.backend + self.path

    def _proxy(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else None
        target = self._backend_target()
        headers = {}
        for key, value in self.headers.items():
            if key.lower() not in {
                "host",
                "connection",
                "content-length",
                "transfer-encoding",
                "accept-encoding",
            }:
                headers[key] = value
        if body is not None:
            headers["Content-Length"] = str(len(body))
        request = urllib.request.Request(
            target, data=body, headers=headers, method=self.command
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                self.send_response(response.status, response.reason)
                for key, value in response.headers.items():
                    if key.lower() not in {
                        "transfer-encoding",
                        "connection",
                        "content-length",
                    }:
                        self.send_header(key, value)
                data = response.read()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
        except urllib.error.HTTPError as exc:
            data = exc.read()
            self.send_response(exc.code, exc.reason)
            for key, value in exc.headers.items():
                if key.lower() not in {
                    "transfer-encoding",
                    "connection",
                    "content-length",
                }:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except Exception:
            if not self.wfile.closed:
                self.send_error(502, "Bad gateway")

    def _is_backend_path(self):
        path = self.path.split("?", 1)[0]
        return path.startswith("/api") or path in {
            "/health",
            "/ready",
            "/docs",
            "/openapi.json",
        }

    def do_GET(self):
        if self._is_backend_path():
            self._proxy()
        else:
            super().do_GET()

    def do_HEAD(self):
        if self._is_backend_path():
            self._proxy()
        else:
            super().do_HEAD()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_PATCH(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--backend", required=True)
    args = parser.parse_args()

    handler = lambda *handler_args, **handler_kwargs: ProxyHandler(
        *handler_args, directory=args.root, backend=args.backend, **handler_kwargs
    )
    httpd = socketserver.ThreadingTCPServer(("0.0.0.0", args.port), handler)
    httpd.allow_reuse_address = True
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
