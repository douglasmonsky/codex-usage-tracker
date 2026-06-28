"""Local dashboard server with lazy context API."""

from __future__ import annotations

import secrets
import sqlite3
import threading
import webbrowser
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from codex_usage_tracker import server_utils
from codex_usage_tracker.context import DEFAULT_CONTEXT_CHARS
from codex_usage_tracker.dashboard import (
    generate_dashboard,
    render_dashboard_html,
)
from codex_usage_tracker.diagnostic_snapshots import (
    build_diagnostic_commands_report,
    build_diagnostic_concentration_report,
    build_diagnostic_file_modifications_report,
    build_diagnostic_file_reads_report,
    build_diagnostic_git_interactions_report,
    build_diagnostic_overview_report,
    build_diagnostic_read_productivity_report,
    build_diagnostic_tool_output_report,
)
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
from codex_usage_tracker.server_call_detail import (
    MissingRecordIdError,
    UsageRecordNotFoundError,
    call_detail_payload,
)
from codex_usage_tracker.server_call_lists import (
    MissingThreadKeyError,
    calls_payload,
    thread_calls_payload,
)
from codex_usage_tracker.server_context import ContextRequestError, context_payload
from codex_usage_tracker.server_context_settings import (
    ContextApiState,
    context_settings_payload,
)
from codex_usage_tracker.server_dashboard_shell import dashboard_shell_payload
from codex_usage_tracker.server_diagnostic_facts import (
    diagnostic_fact_calls_payload,
    diagnostics_facts_payload,
    diagnostics_summary_payload,
)
from codex_usage_tracker.server_diagnostic_snapshots import (
    diagnostic_refresh_payload,
    diagnostic_snapshot_payload,
    usage_drain_snapshot_payload,
)
from codex_usage_tracker.server_live_queries import live_query_params
from codex_usage_tracker.server_live_rows import annotate_live_rows, query_live_call_rows
from codex_usage_tracker.server_open_investigator import (
    OpenInvestigatorRequestError,
    open_investigator_payload,
)
from codex_usage_tracker.server_recommendations import recommendations_payload
from codex_usage_tracker.server_request_guards import (
    has_valid_api_token,
    request_origin_allowed,
)
from codex_usage_tracker.server_responses import send_html_response, send_json_response
from codex_usage_tracker.server_routes import (
    GET_DIAGNOSTIC_FACT_ROUTES,
    GET_ROUTE_METHODS,
    POST_ROUTE_METHODS,
    is_dashboard_shell_path,
)
from codex_usage_tracker.server_status import status_payload
from codex_usage_tracker.server_summary import summary_payload
from codex_usage_tracker.server_threads import threads_payload
from codex_usage_tracker.server_usage_refresh import UsageRefreshAuthError, usage_payload

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


def _optional_int_query(params: dict[str, list[str]], key: str) -> int | None:
    value = _first(params.get(key))
    return None if value is None else _safe_int(value)


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
    context_api_state = ContextApiState(context_api_enabled)
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
        include_rows=False,
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
        dashboard_path=output,
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
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if not self._request_origin_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Request host or origin is not allowed"})
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
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if not self._request_origin_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Request host or origin is not allowed"})
            return
        route_method = POST_ROUTE_METHODS.get(parsed.path)
        if route_method is not None:
            getattr(self, route_method)(parsed.query)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown API endpoint"})

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
        return path in {"/", f"/{self._dashboard_name}"}

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
            )
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while preparing dashboard shell: {exc}"},
            )
            return None
        except OSError as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Could not prepare dashboard shell: {exc}"},
            )
            return None

    def _send_html(self, body: bytes) -> None:
        send_html_response(self, body)

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
                    "error": "Context loading disabled for dashboard server.",
                    "context_api_enabled": False,
                    "can_enable_context_api": True,
                },
            )
            return
        if not self._has_valid_api_token(params):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Valid API token required"})
            return
        try:
            payload = context_payload(
                query,
                db_path=self._db_path,
                default_context_chars=self._context_chars,
            )
        except ContextRequestError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
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
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Valid API token required"})
            return
        payload = context_settings_payload(query, context_api_state=self._context_api_state)
        self._send_json(HTTPStatus.OK, payload)
    def _handle_open_investigator(self, query: str) -> None:
        params = parse_qs(query)
        if not self._has_valid_api_token(params):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Valid API token required"})
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
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._send_json(HTTPStatus.OK, payload)
    def _handle_status(self, query: str) -> None:
        try:
            payload = status_payload(
                query,
                db_path=self._db_path,
                include_archived_default=self._include_archived,
            )
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading status: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_calls(self, query: str) -> None:
        try:
            payload = calls_payload(
                query,
                live_query_params=self._live_query_params,
                live_call_rows=self._live_call_rows,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading calls: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_call(self, query: str) -> None:
        try:
            payload = call_detail_payload(
                query,
                db_path=self._db_path,
                annotate_rows=self._annotate_live_rows,
            )
        except MissingRecordIdError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except UsageRecordNotFoundError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading call: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_threads(self, query: str) -> None:
        try:
            payload = threads_payload(
                query,
                db_path=self._db_path,
                include_archived_default=self._include_archived,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading threads: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_thread_calls(self, query: str) -> None:
        try:
            payload = thread_calls_payload(
                query,
                live_query_params=self._live_query_params,
                live_call_rows=self._live_call_rows,
            )
        except MissingThreadKeyError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading thread calls: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_summary(self, query: str) -> None:
        try:
            payload = summary_payload(
                query,
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                projects_path=self._projects_path,
                privacy_mode=self._privacy_mode,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading summary: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_recommendations(self, query: str) -> None:
        try:
            payload = recommendations_payload(
                query,
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                projects_path=self._projects_path,
                privacy_mode=self._privacy_mode,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading recommendations: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_diagnostics_summary(self, query: str) -> None:
        try:
            payload = diagnostics_summary_payload(
                query,
                db_path=self._db_path,
                include_archived_default=self._include_archived,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading diagnostics: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_diagnostics_facts(
        self,
        query: str,
        *,
        fact_type: str | None = None,
        fact_group: str | None = None,
    ) -> None:
        try:
            payload = diagnostics_facts_payload(
                query,
                db_path=self._db_path,
                include_archived_default=self._include_archived,
                request_path=urlparse(self.path).path,
                fact_type=fact_type,
                fact_group=fact_group,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading diagnostics: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_diagnostics_fact_calls(self, query: str) -> None:
        try:
            payload = diagnostic_fact_calls_payload(
                query,
                db_path=self._db_path,
                include_archived_default=self._include_archived,
                privacy_mode=self._privacy_mode,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading diagnostic calls: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_diagnostics_overview(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_overview_report,
            refresh=False,
            label="diagnostic overview",
        )

    def _handle_diagnostics_refresh(self, query: str) -> None:
        params = parse_qs(query)
        if not self._has_valid_api_token(params):
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "Valid API token is required for diagnostic refresh"},
            )
            return
        try:
            payload = diagnostic_refresh_payload(
                query,
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                rate_card_path=self._rate_card_path,
                include_archived_default=self._include_archived,
                refresh_lock=self._refresh_lock,
            )
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while refreshing diagnostics: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)
    def _handle_diagnostics_overview_refresh(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_overview_report,
            refresh=True,
            label="diagnostic overview",
        )

    def _handle_diagnostics_tool_output(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_tool_output_report,
            refresh=False,
            label="diagnostic tool output",
        )

    def _handle_diagnostics_tool_output_refresh(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_tool_output_report,
            refresh=True,
            label="diagnostic tool output",
        )

    def _handle_diagnostics_commands(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_commands_report,
            refresh=False,
            label="diagnostic commands",
        )

    def _handle_diagnostics_commands_refresh(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_commands_report,
            refresh=True,
            label="diagnostic commands",
        )

    def _handle_diagnostics_git_interactions(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_git_interactions_report,
            refresh=False,
            label="diagnostic git interactions",
        )

    def _handle_diagnostics_git_interactions_refresh(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_git_interactions_report,
            refresh=True,
            label="diagnostic git interactions",
        )

    def _handle_diagnostics_file_reads(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_file_reads_report,
            refresh=False,
            label="diagnostic file reads",
        )

    def _handle_diagnostics_file_reads_refresh(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_file_reads_report,
            refresh=True,
            label="diagnostic file reads",
        )

    def _handle_diagnostics_file_modifications(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_file_modifications_report,
            refresh=False,
            label="diagnostic file modifications",
        )

    def _handle_diagnostics_file_modifications_refresh(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_file_modifications_report,
            refresh=True,
            label="diagnostic file modifications",
        )

    def _handle_diagnostics_read_productivity(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_read_productivity_report,
            refresh=False,
            label="diagnostic read productivity",
        )

    def _handle_diagnostics_read_productivity_refresh(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_read_productivity_report,
            refresh=True,
            label="diagnostic read productivity",
        )

    def _handle_diagnostics_concentration(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_concentration_report,
            refresh=False,
            label="diagnostic concentration",
        )

    def _handle_diagnostics_concentration_refresh(self, query: str) -> None:
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_diagnostic_concentration_report,
            refresh=True,
            label="diagnostic concentration",
        )

    def _handle_diagnostics_usage_drain(self, query: str) -> None:
        self._handle_diagnostic_usage_drain_snapshot(
            query,
            refresh=False,
        )

    def _handle_diagnostics_usage_drain_refresh(self, query: str) -> None:
        self._handle_diagnostic_usage_drain_snapshot(
            query,
            refresh=True,
        )

    def _handle_diagnostic_usage_drain_snapshot(
        self,
        query: str,
        *,
        refresh: bool,
    ) -> None:
        params = parse_qs(query)
        if refresh and not self._has_valid_api_token(params):
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "Valid API token is required for diagnostic refresh"},
            )
            return
        include_archived = _parse_bool(
            _first(params.get("include_archived")),
            self._include_archived,
        )
        try:
            payload = usage_drain_snapshot_payload(
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                rate_card_path=self._rate_card_path,
                include_archived=include_archived,
                refresh=refresh,
                refresh_lock=self._refresh_lock,
            )
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading diagnostic usage drain: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

    def _handle_diagnostic_snapshot(
        self,
        query: str,
        *,
        build_report: Any,
        refresh: bool,
        label: str,
    ) -> None:
        params = parse_qs(query)
        if refresh and not self._has_valid_api_token(params):
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "Valid API token is required for diagnostic refresh"},
            )
            return
        include_archived = _parse_bool(
            _first(params.get("include_archived")),
            self._include_archived,
        )
        try:
            payload = diagnostic_snapshot_payload(
                db_path=self._db_path,
                include_archived=include_archived,
                refresh=refresh,
                refresh_lock=self._refresh_lock,
                build_report=build_report,
            )
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading {label}: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, payload)

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

    def _handle_usage(self, query: str) -> None:
        params = parse_qs(query)
        try:
            payload = usage_payload(
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
                refresh_allowed=self._has_valid_api_token(params),
            )
        except UsageRefreshAuthError as exc:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
            return
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
        self._send_json(HTTPStatus.OK, payload)
    def _request_origin_allowed(self) -> bool:
        return request_origin_allowed(self.headers, self.server.server_port)

    def _has_valid_api_token(self, params: dict[str, list[str]]) -> bool:
        return has_valid_api_token(self.headers, params, self._api_token)

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        send_json_response(self, status, payload)
