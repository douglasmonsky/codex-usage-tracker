"""Local dashboard server with lazy context API."""

from __future__ import annotations

import json
import sqlite3
import threading
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from codex_usage_tracker.core.i18n import normalize_language
from codex_usage_tracker.core.paths import (
    DEFAULT_RATE_CARD_PATH,
)
from codex_usage_tracker.dashboard.api import (
    render_dashboard_html,
)
from codex_usage_tracker.server import context as server_context
from codex_usage_tracker.server import usage_refresh as server_usage_refresh
from codex_usage_tracker.server import utils as server_utils
from codex_usage_tracker.server.allowance import (
    handle_allowance_diagnostics_request,
    handle_allowance_export_request,
    handle_allowance_history_request,
)
from codex_usage_tracker.server.call_detail import (
    handle_call_detail_request,
)
from codex_usage_tracker.server.call_lists import (
    handle_calls_request,
    handle_thread_calls_request,
)
from codex_usage_tracker.server.context_settings import (
    ContextApiState,
    context_settings_payload,
)
from codex_usage_tracker.server.dashboard_shell import dashboard_shell_payload
from codex_usage_tracker.server.diagnostic_routes import DiagnosticRouteMixin
from codex_usage_tracker.server.live_queries import live_query_params
from codex_usage_tracker.server.live_rows import annotate_live_rows, query_live_call_rows
from codex_usage_tracker.server.open_investigator import (
    OpenInvestigatorRequestError,
    open_investigator_payload,
)
from codex_usage_tracker.server.recommendations import handle_recommendations_request
from codex_usage_tracker.server.reports import handle_reports_pack_request
from codex_usage_tracker.server.request_guards import (
    has_valid_api_token,
    request_origin_allowed,
)
from codex_usage_tracker.server.responses import (
    send_error_response,
    send_exception_response,
    send_html_response,
    send_json_response,
)
from codex_usage_tracker.server.routes import (
    GET_DIAGNOSTIC_FACT_ROUTES,
    GET_ROUTE_METHODS,
    POST_ROUTE_METHODS,
    is_dashboard_shell_path,
)
from codex_usage_tracker.server.status import handle_status_request
from codex_usage_tracker.server.summary import handle_summary_request
from codex_usage_tracker.server.threads import handle_threads_request

_first = server_utils.first_query_value
_matches_live_derived_filters = server_utils.matches_live_derived_filters
_parse_api_limit = server_utils.parse_api_limit
_parse_api_offset = server_utils.parse_api_offset
_parse_bool = server_utils.parse_bool_query_value
_parse_limit = server_utils.parse_dashboard_limit
_parse_offset = server_utils.parse_dashboard_offset
_parse_optional_float = server_utils.parse_optional_float
_parse_report_limit = server_utils.parse_report_limit
_safe_int = server_utils.safe_int
_truthy = server_utils.truthy_query_value
_url_host = server_utils.url_host
_validate_context_api_mode = server_utils.validate_context_api_mode
_validate_loopback_host = server_utils.validate_loopback_host


_DASHBOARD_ASSET_MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}
_REACT_DASHBOARD_PATH = "/react-dashboard.html"
_REACT_DASHBOARD_INDEX_PATH = "/codex-usage-tracker-assets/react/index.html"


def _optional_int_query(params: dict[str, list[str]], key: str) -> int | None:
    value = _first(params.get(key))
    return None if value is None else _safe_int(value)


class _UsageDashboardHandler(DiagnosticRouteMixin, SimpleHTTPRequestHandler):
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
        refresh_jobs: server_usage_refresh.RefreshJobRegistry | None = None,
        dashboard_path: Path | None = None,
        context_api_enabled: bool = False,
        context_api_state: ContextApiState | None = None,
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
        self._dashboard_path = (
            Path(dashboard_path)
            if dashboard_path is not None
            else Path(str(kwargs.get("directory", "."))) / dashboard_name
        )
        self._context_chars = context_chars
        self._api_token = api_token
        self._context_api_state = context_api_state or ContextApiState(context_api_enabled)
        self._refresh_lock = refresh_lock
        self._refresh_jobs = refresh_jobs or server_usage_refresh.RefreshJobRegistry()
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if not self._request_origin_allowed():
            self._send_error(
                HTTPStatus.FORBIDDEN,
                "Request host or origin is not allowed",
            )
            return
        route_method = GET_ROUTE_METHODS.get(parsed.path)
        if route_method is not None:
            getattr(self, route_method)(parsed.query)
            return
        fact_filters = GET_DIAGNOSTIC_FACT_ROUTES.get(parsed.path)
        if fact_filters is not None:
            self._handle_diagnostics_facts(parsed.query, **fact_filters)
            return
        if self._is_investigator_dashboard_request(parsed.path, parsed.query):
            self._handle_investigator_dashboard(parsed.query)
            return
        if is_dashboard_shell_path(parsed.path, self._dashboard_name):
            self._handle_dashboard_shell(parsed.query)
            return
        if parsed.path == _REACT_DASHBOARD_PATH:
            self._handle_react_dashboard(parsed.query)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if not self._request_origin_allowed():
            self._send_error(
                HTTPStatus.FORBIDDEN,
                "Request host or origin is not allowed",
            )
            return
        route_method = POST_ROUTE_METHODS.get(parsed.path)
        if route_method is not None:
            getattr(self, route_method)(parsed.query)
            return
        self._send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

    def end_headers(self) -> None:
        if self._is_dashboard_html_request():
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'",
        )
        super().end_headers()

    def guess_type(self, path: str) -> str:
        forced_type = _DASHBOARD_ASSET_MIME_TYPES.get(Path(path).suffix.lower())
        if forced_type is not None:
            return forced_type
        return super().guess_type(path)

    def _is_dashboard_html_request(self) -> bool:
        path = urlparse(self.path).path
        return path in {"/", f"/{self._dashboard_name}", _REACT_DASHBOARD_PATH} or bool(
            getattr(self, "_serving_react_dashboard", False),
        )

    def _handle_react_dashboard(self, query: str) -> None:
        payload = self._dashboard_shell_payload(query)
        if payload is None:
            return
        payload["pricing_snapshot_warning"] = ""
        index_path = Path(self.translate_path(_REACT_DASHBOARD_INDEX_PATH))
        try:
            html = index_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._send_exception("Could not read React dashboard shell", exc)
            return
        html = self._cache_bust_react_asset_urls(html)
        usage_data = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
        usage_script = f'<script id="usage-data" type="application/json">{usage_data}</script>'
        if '<div id="root"></div>' in html:
            html = html.replace(
                '<div id="root"></div>', f'<div id="root"></div>\n    {usage_script}', 1
            )
        elif "</head>" in html:
            html = html.replace("</head>", f"  {usage_script}\n</head>", 1)
        else:
            html = f"{html}\n{usage_script}"
        original_path = self.path
        self._serving_react_dashboard = True
        try:
            self._send_html(html.encode("utf-8"))
        finally:
            self.path = original_path
            self._serving_react_dashboard = False

    def _cache_bust_react_asset_urls(self, html: str) -> str:
        for asset_url in (
            "/codex-usage-tracker-assets/react/assets/dashboard-react.js",
            "/codex-usage-tracker-assets/react/assets/index.css",
        ):
            version = self._react_asset_version(asset_url)
            if not version:
                continue
            html = html.replace(f'{asset_url}"', f'{asset_url}?v={version}"')
            html = html.replace(f"{asset_url}'", f"{asset_url}?v={version}'")
        return html

    def _react_asset_version(self, asset_url: str) -> str:
        asset_path = Path(self.translate_path(asset_url))
        try:
            stat = asset_path.stat()
        except OSError:
            return ""
        return f"{stat.st_mtime_ns:x}-{stat.st_size:x}"

    def _is_investigator_dashboard_request(self, path: str, query: str) -> bool:
        if path != f"/{self._dashboard_name}":
            return False
        params = parse_qs(query)
        return _first(params.get("view")) == "call" and bool(_first(params.get("record")))

    def _handle_investigator_dashboard(self, query: str) -> None:
        payload = self._dashboard_shell_payload(query)
        if payload is None:
            return
        payload["investigator_boot"] = True
        payload["pricing_snapshot_warning"] = ""
        body = render_dashboard_html(
            payload,
            output_path=self._dashboard_path,
            guide_href="codex-usage-tracker-guide/dashboard-guide.html",
            body_attrs={
                "data-active-view": "call",
                "data-investigator-boot": "true",
                "data-dashboard-shell": "true",
            },
        ).encode("utf-8")
        self._send_html(body)

    def _handle_dashboard_shell(self, query: str) -> None:
        payload = self._dashboard_shell_payload(query)
        if payload is None:
            return
        payload["pricing_snapshot_warning"] = ""
        body = render_dashboard_html(
            payload,
            output_path=self._dashboard_path,
            guide_href="codex-usage-tracker-guide/dashboard-guide.html",
            body_attrs={"data-dashboard-shell": "true"},
        ).encode("utf-8")
        self._send_html(body)

    def _dashboard_shell_payload(self, query: str) -> dict[str, object] | None:
        try:
            return dashboard_shell_payload(
                query,
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                rate_card_path=self._rate_card_path,
                thresholds_path=self._thresholds_path,
                projects_path=self._projects_path,
                privacy_mode=self._privacy_mode,
                since=self._since,
                api_token=self._api_token,
                context_api_enabled=self._context_api_state.enabled,
                include_archived_default=self._include_archived,
                language_default=self._language,
                limit_default=self._limit,
            )
        except sqlite3.Error as exc:
            self._send_exception("Database error while preparing dashboard shell", exc)
            return None
        except OSError as exc:
            self._send_exception("Could not prepare dashboard shell", exc)
            return None

    def _send_html(self, body: bytes) -> None:
        send_html_response(self, body)

    def log_message(self, format: str, *args: object) -> None:
        if self.path.startswith("/api/usage"):
            return
        super().log_message(format, *args)

    def _handle_context(self, query: str) -> None:
        server_context.handle_context_request(
            query,
            db_path=self._db_path,
            default_context_chars=self._context_chars,
            context_api_enabled=self._context_api_state.enabled,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_context_settings(self, query: str) -> None:
        params = parse_qs(query)
        if not self._has_valid_api_token(params):
            self._send_error(HTTPStatus.FORBIDDEN, "Valid API token required")
            return
        payload = context_settings_payload(query, context_api_state=self._context_api_state)
        self._send_json(HTTPStatus.OK, payload)

    def _handle_open_investigator(self, query: str) -> None:
        params = parse_qs(query)
        if not self._has_valid_api_token(params):
            self._send_error(HTTPStatus.FORBIDDEN, "Valid API token required")
            return
        try:
            payload = open_investigator_payload(
                query,
                request_host=self.headers.get("Host"),
                server_port=self.server.server_port,
                dashboard_name=self._dashboard_name,
                open_new_tab=webbrowser.open_new_tab,
            )
        except OpenInvestigatorRequestError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_status(self, query: str) -> None:
        handle_status_request(
            query,
            db_path=self._db_path,
            include_archived_default=self._include_archived,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_calls(self, query: str) -> None:
        handle_calls_request(
            query,
            live_query_params=self._live_query_params,
            live_call_rows=self._live_call_rows,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_call(self, query: str) -> None:
        handle_call_detail_request(
            query,
            db_path=self._db_path,
            annotate_rows=self._annotate_live_rows,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_threads(self, query: str) -> None:
        handle_threads_request(
            query,
            db_path=self._db_path,
            include_archived_default=self._include_archived,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_thread_calls(self, query: str) -> None:
        handle_thread_calls_request(
            query,
            live_query_params=self._live_query_params,
            live_call_rows=self._live_call_rows,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_summary(self, query: str) -> None:
        handle_summary_request(
            query,
            db_path=self._db_path,
            pricing_path=self._pricing_path,
            projects_path=self._projects_path,
            privacy_mode=self._privacy_mode,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_recommendations(self, query: str) -> None:
        handle_recommendations_request(
            query,
            db_path=self._db_path,
            pricing_path=self._pricing_path,
            allowance_path=self._allowance_path,
            projects_path=self._projects_path,
            privacy_mode=self._privacy_mode,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_allowance_history(self, query: str) -> None:
        handle_allowance_history_request(
            query,
            db_path=self._db_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            include_archived_default=self._include_archived,
            privacy_mode=self._privacy_mode,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_allowance_diagnostics(self, query: str) -> None:
        handle_allowance_diagnostics_request(
            query,
            db_path=self._db_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            include_archived_default=self._include_archived,
            privacy_mode=self._privacy_mode,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_allowance_export(self, query: str) -> None:
        handle_allowance_export_request(
            query,
            db_path=self._db_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            include_archived_default=self._include_archived,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_reports_pack(self, query: str) -> None:
        handle_reports_pack_request(
            query,
            live_query_params=self._live_query_params,
            live_call_rows=self._live_call_rows,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _live_query_params(
        self,
        params: dict[str, list[str]],
        *,
        thread_key: str | None = None,
    ) -> dict[str, Any]:
        return live_query_params(
            params,
            include_archived_default=self._include_archived,
            thread_key=thread_key,
        )

    def _live_call_rows(
        self,
        *,
        query_params: dict[str, Any],
        pricing_status: str | None,
        credit_confidence: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        return query_live_call_rows(
            db_path=self._db_path,
            query_params=query_params,
            pricing_status=pricing_status,
            credit_confidence=credit_confidence,
            pricing_path=self._pricing_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            thresholds_path=self._thresholds_path,
            projects_path=self._projects_path,
            privacy_mode=self._privacy_mode,
        )

    def _annotate_live_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return annotate_live_rows(
            rows,
            pricing_path=self._pricing_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            thresholds_path=self._thresholds_path,
            projects_path=self._projects_path,
            privacy_mode=self._privacy_mode,
        )

    def _handle_refresh_start(self, query: str) -> None:
        server_usage_refresh.handle_refresh_job_start_request(
            query,
            codex_home=self._codex_home,
            db_path=self._db_path,
            include_archived_default=self._include_archived,
            refresh_lock=self._refresh_lock,
            refresh_jobs=self._refresh_jobs,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_json=self._send_json,
        )

    def _handle_refresh_status(self, query: str) -> None:
        server_usage_refresh.handle_refresh_job_status_request(
            query,
            refresh_jobs=self._refresh_jobs,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_json=self._send_json,
        )

    def _handle_usage(self, query: str) -> None:
        server_usage_refresh.handle_usage_request(
            query,
            db_path=self._db_path,
            pricing_path=self._pricing_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            thresholds_path=self._thresholds_path,
            projects_path=self._projects_path,
            privacy_mode=self._privacy_mode,
            since=self._since,
            api_token=self._api_token,
            context_api_enabled=self._context_api_state.enabled,
            include_archived_default=self._include_archived,
            language_default=self._language,
            limit_default=self._limit,
            codex_home=self._codex_home,
            refresh_lock=self._refresh_lock,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _request_origin_allowed(self) -> bool:
        return request_origin_allowed(self.headers, self.server.server_port)

    def _has_valid_api_token(self, params: dict[str, list[str]]) -> bool:
        return has_valid_api_token(self.headers, params, self._api_token)

    def _send_error(
        self,
        status: HTTPStatus,
        message: str,
        **extra: object,
    ) -> None:
        send_error_response(self, status, message, **extra)

    def _send_exception(self, prefix: str, exc: BaseException) -> None:
        send_exception_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, prefix, exc)

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        send_json_response(self, status, payload)
