"""Local dashboard server with lazy context API."""

from __future__ import annotations

import json
import sqlite3
import threading
import webbrowser
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from codex_usage_tracker.context import DEFAULT_CONTEXT_CHARS, load_call_context
from codex_usage_tracker.dashboard import dashboard_payload, generate_dashboard
from codex_usage_tracker.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.store import refresh_usage_index


def serve_dashboard(
    db_path: Path,
    output_path: Path = DEFAULT_DASHBOARD_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    limit: int = 5000,
    since: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    context_chars: int = DEFAULT_CONTEXT_CHARS,
    open_browser: bool = False,
    codex_home: Path = DEFAULT_CODEX_HOME,
    include_archived: bool = False,
) -> None:
    """Generate and serve the dashboard plus a localhost-only context endpoint."""

    _validate_loopback_host(host)
    output = generate_dashboard(
        db_path=db_path,
        output_path=output_path,
        limit=limit,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        since=since,
    )
    handler = partial(
        _UsageDashboardHandler,
        directory=str(output.parent),
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        limit=limit,
        since=since,
        codex_home=codex_home,
        include_archived=include_archived,
        dashboard_name=output.name,
        context_chars=context_chars,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{_url_host(host)}:{port}/{output.name}"
    print(f"Serving Codex usage dashboard at {url}")
    print("Aggregate rows refresh through /api/usage; raw context is loaded only through /api/context after a row action.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server.")
    finally:
        server.server_close()


class _UsageDashboardHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: object,
        db_path: Path,
        pricing_path: Path,
        allowance_path: Path,
        limit: int,
        since: str | None,
        codex_home: Path,
        include_archived: bool,
        dashboard_name: str,
        context_chars: int,
        refresh_lock: threading.Lock,
        **kwargs: object,
    ) -> None:
        self._db_path = db_path
        self._pricing_path = pricing_path
        self._allowance_path = allowance_path
        self._limit = limit
        self._since = since
        self._codex_home = codex_home
        self._include_archived = include_archived
        self._dashboard_name = dashboard_name
        self._context_chars = context_chars
        self._refresh_lock = refresh_lock
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if parsed.path == "/api/context":
            self._handle_context(parsed.query)
            return
        if parsed.path == "/api/usage":
            self._handle_usage(parsed.query)
            return
        if parsed.path == "/":
            self.path = f"/{self._dashboard_name}"
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'",
        )
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        if self.path.startswith("/api/usage"):
            return
        super().log_message(format, *args)

    def _handle_context(self, query: str) -> None:
        params = parse_qs(query)
        record_id = _first(params.get("record_id"))
        if not record_id:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "record_id is required"},
            )
            return
        include_tool_output = _truthy(_first(params.get("include_tool_output")))
        try:
            payload = load_call_context(
                record_id=record_id,
                db_path=self._db_path,
                max_chars=self._context_chars,
                include_tool_output=include_tool_output,
            )
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while loading context: {exc}"},
            )
            return
        except ValueError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except FileNotFoundError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except OSError as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Could not read source log: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_usage(self, query: str) -> None:
        params = parse_qs(query)
        limit = _parse_limit(_first(params.get("limit")), self._limit)
        refresh_result = None
        try:
            if _truthy(_first(params.get("refresh"))):
                with self._refresh_lock:
                    result = refresh_usage_index(
                        codex_home=self._codex_home,
                        db_path=self._db_path,
                        include_archived=self._include_archived,
                    )
                refresh_result = {
                    "scanned_files": result.scanned_files,
                    "parsed_events": result.parsed_events,
                    "skipped_events": result.skipped_events,
                    "inserted_or_updated_events": result.inserted_or_updated_events,
                    "db_path": result.db_path,
                    "parser_diagnostics": result.parser_diagnostics,
                }
            payload = dashboard_payload(
                db_path=self._db_path,
                limit=limit,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                since=self._since,
            )
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading usage data: {exc}"},
            )
            return
        except OSError as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Could not read aggregate dashboard data: {exc}"},
            )
            return
        payload["refreshed_at"] = _utc_now()
        payload["refresh_result"] = refresh_result
        self._send_json(HTTPStatus.OK, payload)

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _first(values: list[str] | None) -> str | None:
    return values[0] if values else None


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _parse_limit(value: str | None, default: int | None) -> int | None:
    if value is None or value == "":
        return default
    if value.lower() == "all":
        return None
    try:
        limit = int(value)
    except ValueError:
        return default
    if limit <= 0:
        return None
    return limit


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_loopback_host(host: str) -> None:
    if host == "localhost":
        return
    try:
        address = ip_address(host)
    except ValueError as exc:
        raise ValueError(
            "serve-dashboard --host must be localhost, 127.0.0.1, or ::1"
        ) from exc
    if not address.is_loopback:
        raise ValueError("serve-dashboard refuses to expose raw context off localhost")


def _url_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host
