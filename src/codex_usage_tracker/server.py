"""Local dashboard server with lazy context API."""

from __future__ import annotations

import hmac
import json
import secrets
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
from codex_usage_tracker.i18n import normalize_language
from codex_usage_tracker.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.store import refresh_usage_index


class _ContextApiState:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled


def serve_dashboard(
    db_path: Path,
    output_path: Path = DEFAULT_DASHBOARD_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    limit: int = 5000,
    since: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    context_chars: int = DEFAULT_CONTEXT_CHARS,
    open_browser: bool = False,
    codex_home: Path = DEFAULT_CODEX_HOME,
    include_archived: bool = False,
    context_api: str = "explicit",
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    privacy_mode: str = "normal",
    language: str | None = None,
) -> None:
    """Generate and serve the dashboard plus a localhost-only context endpoint."""

    _validate_loopback_host(host)
    _validate_context_api_mode(context_api)
    api_token = secrets.token_urlsafe(32)
    context_api_enabled = context_api != "disabled"
    selected_language = normalize_language(language)
    context_api_state = _ContextApiState(context_api_enabled)
    output = generate_dashboard(
        db_path=db_path,
        output_path=output_path,
        limit=limit,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        since=since,
        api_token=api_token,
        context_api_enabled=context_api_enabled,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
        privacy_mode=privacy_mode,
        include_archived=include_archived,
        language=selected_language,
    )
    handler = partial(
        _UsageDashboardHandler,
        directory=str(output.parent),
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
        privacy_mode=privacy_mode,
        limit=limit,
        since=since,
        codex_home=codex_home,
        include_archived=include_archived,
        dashboard_name=output.name,
        context_chars=context_chars,
        api_token=api_token,
        context_api_state=context_api_state,
        language=selected_language,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{_url_host(host)}:{port}/{output.name}"
    print(f"Serving Codex usage dashboard at {url}")
    context_mode = (
        "enabled for explicit row actions"
        if context_api_enabled
        else "disabled until enabled from the dashboard"
    )
    print("Aggregate rows refresh through /api/usage with a per-server token.")
    print(f"Raw context API is {context_mode}; context is never embedded in the dashboard HTML.")
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
        thresholds_path: Path,
        projects_path: Path,
        limit: int,
        since: str | None,
        codex_home: Path,
        include_archived: bool,
        dashboard_name: str,
        context_chars: int,
        api_token: str,
        refresh_lock: threading.Lock,
        context_api_enabled: bool = False,
        context_api_state: _ContextApiState | None = None,
        privacy_mode: str = "normal",
        rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
        language: str = "en",
        **kwargs: object,
    ) -> None:
        self._db_path = db_path
        self._pricing_path = pricing_path
        self._allowance_path = allowance_path
        self._rate_card_path = rate_card_path
        self._thresholds_path = thresholds_path
        self._projects_path = projects_path
        self._privacy_mode = privacy_mode
        self._language = normalize_language(language)
        self._limit = limit
        self._since = since
        self._codex_home = codex_home
        self._include_archived = include_archived
        self._dashboard_name = dashboard_name
        self._context_chars = context_chars
        self._api_token = api_token
        self._context_api_state = context_api_state or _ContextApiState(context_api_enabled)
        self._refresh_lock = refresh_lock
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if not self._request_origin_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Request host or origin is not allowed"})
            return
        if parsed.path == "/api/context":
            self._handle_context(parsed.query)
            return
        if parsed.path == "/api/context-settings":
            self._handle_context_settings(parsed.query)
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
            "default-src 'self'; script-src 'self'; "
            "style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'",
        )
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        if self.path.startswith("/api/usage"):
            return
        super().log_message(format, *args)

    def _handle_context(self, query: str) -> None:
        params = parse_qs(query)
        if not self._context_api_state.enabled:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {
                    "error": "Context loading is disabled for this dashboard server.",
                    "context_api_enabled": False,
                    "can_enable_context_api": True,
                },
            )
            return
        if not self._has_valid_api_token(params):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Valid API token is required"})
            return
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

    def _handle_context_settings(self, query: str) -> None:
        params = parse_qs(query)
        if not self._has_valid_api_token(params):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Valid API token is required"})
            return
        enabled = _parse_bool(_first(params.get("enabled")), True)
        self._context_api_state.set_enabled(enabled)
        self._send_json(
            HTTPStatus.OK,
            {
                "schema": "codex-usage-tracker-context-settings-v1",
                "context_api_enabled": self._context_api_state.enabled,
                "raw_context_persisted": False,
            },
        )

    def _handle_usage(self, query: str) -> None:
        params = parse_qs(query)
        limit = _parse_limit(_first(params.get("limit")), self._limit)
        offset = _parse_offset(_first(params.get("offset")))
        include_archived = _parse_bool(_first(params.get("include_archived")), self._include_archived)
        language = normalize_language(_first(params.get("lang")) or self._language)
        refresh_result = None
        try:
            if _truthy(_first(params.get("refresh"))):
                if not self._has_valid_api_token(params):
                    self._send_json(
                        HTTPStatus.FORBIDDEN,
                        {"error": "Valid API token is required for refresh"},
                    )
                    return
                with self._refresh_lock:
                    result = refresh_usage_index(
                        codex_home=self._codex_home,
                        db_path=self._db_path,
                        include_archived=include_archived,
                    )
                refresh_result = {
                    "scanned_files": result.scanned_files,
                    "parsed_events": result.parsed_events,
                    "skipped_events": result.skipped_events,
                    "inserted_or_updated_events": result.inserted_or_updated_events,
                    "db_path": result.db_path,
                    "parser_diagnostics": result.parser_diagnostics,
                    "include_archived": include_archived,
                }
            payload = dashboard_payload(
                db_path=self._db_path,
                limit=limit,
                offset=offset,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                rate_card_path=self._rate_card_path,
                thresholds_path=self._thresholds_path,
                projects_path=self._projects_path,
                privacy_mode=self._privacy_mode,
                since=self._since,
                api_token=self._api_token,
                context_api_enabled=self._context_api_state.enabled,
                include_archived=include_archived,
                language=language,
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

    def _request_origin_allowed(self) -> bool:
        if not _allowed_loopback_host(_host_header_name(self.headers.get("Host"))):
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"}:
            return False
        if not _allowed_loopback_host(parsed.hostname):
            return False
        return parsed.port is None or parsed.port == self.server.server_port

    def _has_valid_api_token(self, params: dict[str, list[str]]) -> bool:
        provided = self.headers.get("X-Codex-Usage-Token") or _first(params.get("api_token")) or ""
        return hmac.compare_digest(str(provided), self._api_token)

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


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


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


def _parse_offset(value: str | None) -> int:
    if value is None or value == "":
        return 0
    try:
        offset = int(value)
    except ValueError:
        return 0
    return max(offset, 0)


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


def _validate_context_api_mode(mode: str) -> None:
    if mode not in {"explicit", "disabled"}:
        raise ValueError("--context-api must be explicit or disabled")


def _allowed_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _host_header_name(value: str | None) -> str | None:
    if not value:
        return None
    host = value.strip()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end > 0 else None
    return host.split(":", 1)[0]


def _url_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host
