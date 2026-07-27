"""Loopback-only stdlib HTTP server for the kernel API."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ...application import KernelApplication, build_application
from .app import MAX_BODY_BYTES, HttpApp, HttpResponse


def create_server(
    application: KernelApplication | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("kernel HTTP server must bind to loopback")
    adapter = HttpApp(application or build_application())

    class Handler(BaseHTTPRequestHandler):
        server_version = "CodexUsageKernel/0.26"

        def do_GET(self) -> None:  # noqa: N802
            self._handle()

        def do_POST(self) -> None:  # noqa: N802
            self._handle()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            del format, args
            return

        def _handle(self) -> None:
            try:
                length = _content_length(self.headers.get("Content-Length"))
            except ValueError:
                self._write(HttpResponse(400, "text/plain", b"invalid request\n"))
                return
            if length > MAX_BODY_BYTES:
                self._write(HttpResponse(413, "text/plain", b"request too large\n"))
                return
            body = self.rfile.read(length) if length else b""
            response = adapter.handle(
                self.command,
                self.path,
                body=body,
                headers={key: value for key, value in self.headers.items()},
            )
            self._write(response)

        def _write(self, response: HttpResponse) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            for key, value in response.headers:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response.body)

    return ThreadingHTTPServer((host, port), Handler)


def _content_length(value: str | None) -> int:
    if value is None:
        return 0
    if not value.isascii() or not value.isdigit():
        raise ValueError("Content-Length is invalid")
    return int(value)
