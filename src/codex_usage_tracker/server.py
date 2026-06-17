"""Local dashboard server with lazy context API."""

from __future__ import annotations

import hmac
import secrets
import sqlite3
import threading
import webbrowser
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs, urlparse

from codex_usage_tracker import server_utils
from codex_usage_tracker.allowance import annotate_rows_with_allowance, load_allowance_config
from codex_usage_tracker.api_payloads import refresh_result_payload
from codex_usage_tracker.call_origin import ensure_call_origin
from codex_usage_tracker.context import (
    CONTEXT_MODE_QUICK,
    CONTEXT_MODES,
    DEFAULT_CONTEXT_CHARS,
    DEFAULT_CONTEXT_ENTRIES,
    load_call_context,
)
from codex_usage_tracker.dashboard import (
    dashboard_payload,
    generate_dashboard,
    render_dashboard_html,
)
from codex_usage_tracker.dashboard_diagnostics import dashboard_parser_diagnostics
from codex_usage_tracker.i18n import normalize_language
from codex_usage_tracker.lifecycle_recommendations import (
    lifecycle_recommendations_payload,
    query_lifecycle_recommendations,
)
from codex_usage_tracker.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.pricing import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    load_project_config,
)
from codex_usage_tracker.recommendations import (
    annotate_rows_with_recommendations,
    load_threshold_config,
)
from codex_usage_tracker.reports import (
    QUERY_CREDIT_CONFIDENCE_CHOICES,
    QUERY_PRICING_STATUS_CHOICES,
    build_recommendations_report,
    build_summary_report,
)
from codex_usage_tracker.store import (
    query_latest_observed_usage,
    query_thread_model_buckets,
    query_thread_summaries,
    query_thread_summary_count,
    query_thread_usage_impact_summaries,
    query_usage_api_event_count,
    query_usage_api_events,
    query_usage_record,
    query_usage_status,
    refresh_metadata,
    refresh_usage_index,
)
from codex_usage_tracker.store_context_epochs import (
    context_epochs_payload,
    query_context_epochs,
)
from codex_usage_tracker.store_task_receipts import (
    query_task_receipts,
    task_receipts_payload,
)
from codex_usage_tracker.store_work_sessions import (
    query_thread_work_session,
    query_thread_work_sessions,
    sessions_payload,
    work_session_payload,
)
from codex_usage_tracker.threads import annotate_thread_attachments
from codex_usage_tracker.usage_impact_cache import UsageImpactCache
from codex_usage_tracker.usage_impact_store import (
    query_usage_impact_rows,
    usage_impact_payload,
)

_allowed_loopback_host = server_utils.allowed_loopback_host
_elapsed_ms = server_utils.elapsed_ms
_first = server_utils.first_query_value
_has_more = server_utils.has_more_rows
_host_header_name = server_utils.host_header_name
_json_response_body = server_utils.json_response_body
_matches_live_derived_filters = server_utils.matches_live_derived_filters
_next_offset = server_utils.next_row_offset
_optional_filter = server_utils.optional_choice_filter
_parse_api_limit = server_utils.parse_api_limit
_parse_api_limit_allow_zero = server_utils.parse_api_limit_allow_zero
_parse_api_offset = server_utils.parse_api_offset
_parse_bool = server_utils.parse_bool_query_value
_parse_context_limit = server_utils.parse_context_limit
_parse_limit = server_utils.parse_dashboard_limit
_parse_offset = server_utils.parse_dashboard_offset
_parse_optional_float = server_utils.parse_optional_float
_parse_report_limit = server_utils.parse_report_limit
_truthy = server_utils.truthy_query_value
_url_host = server_utils.url_host
_utc_now = server_utils.utc_now
_validate_context_api_mode = server_utils.validate_context_api_mode
_validate_loopback_host = server_utils.validate_loopback_host


def _refresh_result_invalidates_usage_impact(result: object) -> bool:
    if bool(getattr(result, "skipped_downstream_work", False)):
        return False
    return any(
        int(getattr(result, field, 0) or 0) > 0
        for field in (
            "inserted_records",
            "deleted_records",
            "full_reparse_source_files",
            "inserted_or_updated_events",
        )
    )


def _sum_optional_number(values: Any) -> float | None:
    total = 0.0
    found = False
    for value in values:
        if isinstance(value, int | float):
            total += float(value)
            found = True
    return total if found else None


def _thread_summary_label(
    values: list[object],
    noun: str,
    *,
    excluded_primary: set[str] | None = None,
) -> str:
    labels = sorted({str(value) for value in values if value})
    if not labels:
        return "Unknown"
    if len(labels) == 1:
        return labels[0]
    excluded = excluded_primary or set()
    primary_candidates = [label for label in labels if label not in excluded and label != "Unknown"]
    primary = primary_candidates[0] if primary_candidates else labels[0]
    return f"{primary} +{len(labels) - 1} {noun}"


def _split_distinct_csv(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return sorted({part.strip() for part in value.split(",") if part.strip()})


def _single_or_mixed(value: object) -> str | None:
    parts = _split_distinct_csv(value)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "mixed"


def _usage_window_label(minutes: object) -> str | None:
    if not isinstance(minutes, int | float):
        return None
    value = int(minutes)
    if value == 300:
        return "5h"
    if value == 10080:
        return "Weekly"
    if value % 1440 == 0:
        return f"{value // 1440}d"
    if value % 60 == 0:
        return f"{value // 60}h"
    return f"{value}m"


def _usage_impact_sort_value(row: dict[str, Any]) -> float:
    impact = row.get("usage_impact")
    if not isinstance(impact, dict):
        return float("-inf")
    secondary = impact.get("secondary")
    if not isinstance(secondary, dict):
        return float("-inf")
    value = secondary.get("estimate_percent")
    return float(value) if isinstance(value, int | float) else float("-inf")


def _thread_usage_impact_by_thread(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, bool]]:
    """Build per-thread usage-impact summaries from persisted per-call estimates."""

    by_thread: dict[str, dict[str, Any]] = {}
    pending_by_thread: dict[str, bool] = {}
    for row in rows:
        thread_key = str(row.get("thread_key") or "")
        window_type = str(row.get("window_type") or "")
        if not thread_key or window_type not in {"primary", "secondary"}:
            continue
        pending_count = int(row.get("pending_row_count") or 0)
        pending_by_thread[thread_key] = pending_by_thread.get(thread_key, False) or pending_count > 0
        if int(row.get("estimate_row_count") or 0) <= 0:
            continue
        by_thread.setdefault(thread_key, {"primary": None, "secondary": None})
        by_thread[thread_key][window_type] = {
            "schema": "codex-usage-tracker-usage-impact-estimate-v1",
            "label": _usage_window_label(row.get("observed_window_minutes")),
            "window_minutes": row.get("observed_window_minutes"),
            "estimate_percent": row.get("estimated_usage_percent"),
            "lower_percent": row.get("lower_percent"),
            "upper_percent": row.get("upper_percent"),
            "observed_delta_percent": row.get("delta_used_percent"),
            "interval_call_count": row.get("estimate_row_count"),
            "basis": _single_or_mixed(row.get("bases")),
            "source": _single_or_mixed(row.get("sources")),
            "resets_at": row.get("observed_resets_at"),
            "confidence": _single_or_mixed(row.get("confidences")),
            "status": _single_or_mixed(row.get("statuses")),
        }
    return by_thread, pending_by_thread


def _thread_summary_computed_sort_key(row: dict[str, Any], sort: str) -> tuple[float, str]:
    if sort == "usage_impact":
        return _usage_impact_sort_value(row), str(row.get("latest_event_timestamp") or "")
    numeric_value = {
        "cost": row.get("estimated_cost_usd"),
        "usage": row.get("usage_credits"),
    }.get(sort)
    sortable = float(numeric_value) if isinstance(numeric_value, int | float) else float("-inf")
    return sortable, str(row.get("latest_event_timestamp") or "")


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
    usage_impact_cache = UsageImpactCache(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
    )
    usage_impact_cache.warm_async(include_archived=include_archived)
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
        usage_impact_cache=usage_impact_cache,
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
        context_api_state: _ContextApiState | None = None,
        usage_impact_cache: UsageImpactCache | None = None,
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
        self._context_api_state = context_api_state or _ContextApiState(context_api_enabled)
        self._refresh_lock = refresh_lock
        self._usage_impact_cache = usage_impact_cache or UsageImpactCache(
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
        )
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
        if parsed.path == "/api/open-investigator":
            self._handle_open_investigator(parsed.query)
            return
        if parsed.path == "/api/status":
            self._handle_status(parsed.query)
            return
        if parsed.path == "/api/calls":
            self._handle_calls(parsed.query)
            return
        if parsed.path == "/api/call":
            self._handle_call(parsed.query)
            return
        if parsed.path == "/api/usage-impact":
            self._handle_usage_impact(parsed.query)
            return
        if parsed.path == "/api/task-receipts":
            self._handle_task_receipts(parsed.query)
            return
        if parsed.path == "/api/sessions":
            self._handle_sessions(parsed.query)
            return
        if parsed.path == "/api/session":
            self._handle_work_session(parsed.query)
            return
        if parsed.path == "/api/context-epochs":
            self._handle_context_epochs(parsed.query)
            return
        if parsed.path == "/api/threads":
            self._handle_threads(parsed.query)
            return
        if parsed.path == "/api/thread-calls":
            self._handle_thread_calls(parsed.query)
            return
        if parsed.path == "/api/summary":
            self._handle_summary(parsed.query)
            return
        if parsed.path == "/api/recommendations":
            self._handle_recommendations(parsed.query)
            return
        if parsed.path == "/api/lifecycle-recommendations":
            self._handle_lifecycle_recommendations(parsed.query)
            return
        if parsed.path == "/api/usage":
            self._handle_usage(parsed.query)
            return
        if self._is_investigator_dashboard_request(parsed.path, parsed.query):
            self._handle_investigator_dashboard(parsed.query)
            return
        if parsed.path in {"/", f"/{self._dashboard_name}"}:
            self._handle_dashboard_shell(parsed.query)
            return
        super().do_GET()

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
        params = parse_qs(query)
        include_archived = self._include_archived
        history_scope = _first(params.get("history"))
        if history_scope == "all":
            include_archived = True
        elif history_scope == "active":
            include_archived = False
        include_archived = _parse_bool(
            _first(params.get("include_archived")),
            include_archived,
        )
        language = normalize_language(_first(params.get("lang")) or self._language)
        try:
            return dashboard_payload(
                db_path=self._db_path,
                limit=0,
                offset=0,
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
                include_rows=False,
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
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

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
        include_compaction_history = _truthy(_first(params.get("include_compaction_history")))
        diagnostics = _parse_bool(_first(params.get("diagnostics")), False)
        context_mode = (_first(params.get("mode")) or CONTEXT_MODE_QUICK).strip().lower()
        if context_mode not in CONTEXT_MODES:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "mode must be one of: " + ", ".join(sorted(CONTEXT_MODES)),
                },
            )
            return
        max_chars = _parse_context_limit(_first(params.get("max_chars")), self._context_chars)
        max_entries = _parse_context_limit(
            _first(params.get("max_entries")), DEFAULT_CONTEXT_ENTRIES
        )
        try:
            payload = load_call_context(
                record_id=record_id,
                db_path=self._db_path,
                max_chars=max_chars,
                max_entries=max_entries,
                include_tool_output=include_tool_output,
                include_compaction_history=include_compaction_history,
                diagnostics=diagnostics,
                mode=context_mode,
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

    def _handle_open_investigator(self, query: str) -> None:
        params = parse_qs(query)
        if not self._has_valid_api_token(params):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Valid API token is required"})
            return
        target = _first(params.get("url"))
        if not target:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "url is required"})
            return
        parsed_target = urlparse(target)
        if parsed_target.scheme:
            if parsed_target.scheme not in {"http", "https"}:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Only dashboard URLs can be opened"})
                return
            if not _allowed_loopback_host(parsed_target.hostname):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Only loopback dashboard URLs can be opened"})
                return
            if parsed_target.port not in {None, self.server.server_port}:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Dashboard URL port is not allowed"})
                return
        if parsed_target.path != f"/{self._dashboard_name}":
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Only dashboard investigator URLs can be opened"})
            return
        target_params = parse_qs(parsed_target.query)
        if _first(target_params.get("view")) != "call" or not _first(target_params.get("record")):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Investigator URL must include view=call and record"})
            return
        host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_port}"
        safe_url = f"http://{host}{parsed_target.path}"
        if parsed_target.query:
            safe_url = f"{safe_url}?{parsed_target.query}"
        if parsed_target.fragment:
            safe_url = f"{safe_url}#{parsed_target.fragment}"
        opened = webbrowser.open_new_tab(safe_url)
        self._send_json(
            HTTPStatus.OK,
            {
                "schema": "codex-usage-tracker-open-investigator-v1",
                "opened": bool(opened),
                "url": safe_url,
            },
        )

    def _handle_status(self, query: str) -> None:
        params = parse_qs(query)
        include_archived = _parse_bool(_first(params.get("include_archived")), self._include_archived)
        refresh_result: dict[str, object] | None = None
        refresh_ms: float | None = None
        try:
            if _truthy(_first(params.get("refresh"))):
                if not self._has_valid_api_token(params):
                    self._send_json(
                        HTTPStatus.FORBIDDEN,
                        {"error": "Valid API token is required for refresh"},
                    )
                    return
                refresh_result, refresh_ms = self._refresh_usage_index(include_archived)
            counts = query_usage_status(
                db_path=self._db_path,
                include_archived=include_archived,
            )
            observed_usage = query_latest_observed_usage(
                db_path=self._db_path,
                include_archived=include_archived,
            )
            metadata = refresh_metadata(self._db_path)
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading status: {exc}"},
            )
            return
        parser_diagnostics = dashboard_parser_diagnostics(metadata)
        payload: dict[str, object] = {
            "schema": "codex-usage-tracker-status-v1",
            "payload_schema": "codex-usage-tracker-live-api-v1",
            "latest_refresh_at": metadata.get("latest_refresh_at"),
            "include_archived": include_archived,
            "row_counts": counts,
            "max_event_timestamp": counts.get("max_event_timestamp"),
            "observed_usage": observed_usage,
            "parser_adapter": metadata.get("parser_adapter"),
            "parser_diagnostics": parser_diagnostics,
        }
        if refresh_result is not None:
            payload["refresh_result"] = refresh_result
            payload["refresh_ms"] = refresh_ms
        self._send_json(HTTPStatus.OK, payload)

    def _handle_calls(self, query: str) -> None:
        params = parse_qs(query)
        try:
            query_params = self._live_query_params(params)
            pricing_status = _optional_filter(
                _first(params.get("pricing_status")),
                QUERY_PRICING_STATUS_CHOICES,
                "pricing_status",
            )
            credit_confidence = _optional_filter(
                _first(params.get("credit_confidence")),
                QUERY_CREDIT_CONFIDENCE_CHOICES,
                "credit_confidence",
            )
            rows, total_matched = self._live_call_rows(
                query_params=query_params,
                pricing_status=pricing_status,
                credit_confidence=credit_confidence,
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
        self._send_json(
            HTTPStatus.OK,
            {
                "schema": "codex-usage-tracker-calls-v1",
                "rows": rows,
                "row_count": len(rows),
                "total_matched_rows": total_matched,
                "usage_impact_pending": any(row.get("usage_impact_pending") for row in rows),
                "limit": query_params["limit"],
                "offset": query_params["offset"],
                "has_more": _has_more(query_params["limit"], query_params["offset"], len(rows), total_matched),
                "next_offset": _next_offset(query_params["limit"], query_params["offset"], len(rows), total_matched),
                "filters": {
                    **query_params["filters"],
                    "pricing_status": pricing_status,
                    "credit_confidence": credit_confidence,
                },
                "raw_context_included": False,
            },
        )

    def _handle_call(self, query: str) -> None:
        params = parse_qs(query)
        record_id = _first(params.get("record_id")) or _first(params.get("record"))
        if not record_id:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "record_id is required"})
            return
        try:
            row = query_usage_record(db_path=self._db_path, record_id=record_id)
            if row is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"No usage record found: {record_id}"})
                return
            adjacent_raw_rows = [
                query_usage_record(db_path=self._db_path, record_id=adjacent_id)
                for adjacent_id in (row.get("previous_record_id"), row.get("next_record_id"))
                if adjacent_id
            ]
            rows_by_id = {
                candidate["record_id"]: candidate
                for candidate in self._annotate_live_rows(
                    [candidate for candidate in [row, *adjacent_raw_rows] if candidate],
                    include_archived=self._include_archived,
                )
                if candidate.get("record_id")
            }
            selected_row = rows_by_id.get(record_id, row)
            usage_impact_rows = query_usage_impact_rows(
                db_path=self._db_path,
                record_id=record_id,
                limit=0,
            )
            task_receipt_rows = query_task_receipts(
                db_path=self._db_path,
                record_id=record_id,
                limit=0,
                sort="category",
                direction="asc",
            )
            lifecycle_rows, lifecycle_total = query_lifecycle_recommendations(
                db_path=self._db_path,
                record_id=record_id,
                limit=3,
            )
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading call: {exc}"},
            )
            return
        previous_record = rows_by_id.get(str(row.get("previous_record_id") or ""))
        next_record = rows_by_id.get(str(row.get("next_record_id") or ""))
        self._send_json(
            HTTPStatus.OK,
            {
                "schema": "codex-usage-tracker-call-v1",
                "record": selected_row,
                "previous_record": previous_record,
                "next_record": next_record,
                "adjacent_records": [
                    candidate
                    for candidate in (previous_record, selected_row, next_record)
                    if candidate
                ],
                "previous_record_id": row.get("previous_record_id"),
                "next_record_id": row.get("next_record_id"),
                "usage_impact": usage_impact_payload(
                    usage_impact_rows,
                    record_id=record_id,
                    limit=None,
                ),
                "task_receipts": task_receipts_payload(
                    task_receipt_rows,
                    record_id=record_id,
                    limit=None,
                ),
                "lifecycle_recommendations": lifecycle_recommendations_payload(
                    lifecycle_rows,
                    filters={"record_id": record_id},
                    limit=3,
                    total_matched_rows=lifecycle_total,
                ),
                "raw_context_included": False,
            },
        )

    def _handle_usage_impact(self, query: str) -> None:
        params = parse_qs(query)
        record_id = _first(params.get("record_id")) or _first(params.get("record"))
        limit = _parse_api_limit(_first(params.get("limit")), 100)
        offset = _parse_api_offset(_first(params.get("offset")))
        window_type = _first(params.get("window_type"))
        try:
            rows = query_usage_impact_rows(
                db_path=self._db_path,
                record_id=record_id,
                limit=limit,
                offset=offset,
                window_type=window_type,
            )
            if not rows:
                self._usage_impact_cache.warm_async(include_archived=self._include_archived)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading usage impact: {exc}"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            usage_impact_payload(
                rows,
                record_id=record_id,
                limit=limit,
            ),
        )

    def _handle_task_receipts(self, query: str) -> None:
        params = parse_qs(query)
        record_id = _first(params.get("record_id")) or _first(params.get("record"))
        limit = _parse_api_limit_allow_zero(_first(params.get("limit")), 100)
        offset = _parse_api_offset(_first(params.get("offset")))
        try:
            rows = query_task_receipts(
                db_path=self._db_path,
                record_id=record_id,
                thread_key=_first(params.get("thread_key")) or _first(params.get("thread")),
                work_session_id=_first(params.get("work_session_id")) or _first(params.get("session")),
                context_epoch_id=_first(params.get("context_epoch_id")) or _first(params.get("epoch")),
                category=_first(params.get("category")),
                limit=limit,
                offset=offset,
                sort=_first(params.get("sort")) or "latest",
                direction=_first(params.get("direction")) or "desc",
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading task receipts: {exc}"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            task_receipts_payload(
                rows,
                record_id=record_id,
                limit=limit,
                offset=offset,
            ),
        )

    def _handle_lifecycle_recommendations(self, query: str) -> None:
        params = parse_qs(query)
        record_id = _first(params.get("record_id")) or _first(params.get("record"))
        limit = _parse_api_limit_allow_zero(_first(params.get("limit")), 100)
        offset = _parse_api_offset(_first(params.get("offset")))
        filters = {
            "record_id": record_id,
            "thread_key": _first(params.get("thread_key")) or _first(params.get("thread")),
            "work_session_id": _first(params.get("work_session_id")) or _first(params.get("session")),
            "context_epoch_id": _first(params.get("context_epoch_id")) or _first(params.get("epoch")),
            "scope": _first(params.get("scope")),
        }
        try:
            rows, total = query_lifecycle_recommendations(
                db_path=self._db_path,
                record_id=record_id,
                thread_key=filters["thread_key"],
                work_session_id=filters["work_session_id"],
                context_epoch_id=filters["context_epoch_id"],
                scope=filters["scope"],
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading lifecycle recommendations: {exc}"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            lifecycle_recommendations_payload(
                rows,
                filters=filters,
                limit=limit,
                offset=offset,
                total_matched_rows=total,
            ),
        )

    def _handle_sessions(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = _parse_api_limit(_first(params.get("limit")), 100)
            offset = _parse_api_offset(_first(params.get("offset")))
            include_archived = _parse_bool(_first(params.get("include_archived")), self._include_archived)
            rows = query_thread_work_sessions(
                db_path=self._db_path,
                limit=limit,
                offset=offset,
                search=_first(params.get("q")) or _first(params.get("search")),
                thread_key=_first(params.get("thread_key")) or _first(params.get("thread")),
                include_archived=include_archived,
                sort=_first(params.get("sort")) or "uncached",
                direction=_first(params.get("direction")) or "desc",
                cold_resumes_only=_truthy(_first(params.get("cold_resumes_only"))),
                high_uncached_only=_truthy(_first(params.get("high_uncached_only"))),
                needs_handoff_only=_truthy(_first(params.get("needs_handoff_only"))),
                recent_only=_truthy(_first(params.get("recent_only"))),
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading sessions: {exc}"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            sessions_payload(
                rows,
                limit=limit,
                offset=offset,
                include_archived=include_archived,
            ),
        )

    def _handle_work_session(self, query: str) -> None:
        params = parse_qs(query)
        work_session_id = _first(params.get("work_session_id")) or _first(params.get("id"))
        thread_key = _first(params.get("thread_key")) or _first(params.get("thread"))
        raw_index = _first(params.get("session_index"))
        session_index: int | None = None
        if raw_index is not None and raw_index != "":
            try:
                session_index = int(raw_index)
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "session_index must be an integer"})
                return
        try:
            row = query_thread_work_session(
                db_path=self._db_path,
                work_session_id=work_session_id,
                thread_key=thread_key,
                session_index=session_index,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading session: {exc}"},
            )
            return
        if row is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "No thread work session found"})
            return
        try:
            context_epochs = query_context_epochs(
                db_path=self._db_path,
                work_session_id=str(row.get("work_session_id") or ""),
                limit=0,
                sort="started",
                direction="asc",
            )
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading session context epochs: {exc}"},
            )
            return
        self._send_json(HTTPStatus.OK, work_session_payload(row, context_epochs=context_epochs))

    def _handle_context_epochs(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = _parse_api_limit_allow_zero(_first(params.get("limit")), 100)
            offset = _parse_api_offset(_first(params.get("offset")))
            work_session_id = _first(params.get("work_session_id")) or _first(params.get("session"))
            thread_key = _first(params.get("thread_key")) or _first(params.get("thread"))
            rows = query_context_epochs(
                db_path=self._db_path,
                work_session_id=work_session_id,
                thread_key=thread_key,
                limit=limit,
                offset=offset,
                sort=_first(params.get("sort")) or "started",
                direction=_first(params.get("direction")) or "asc",
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading context epochs: {exc}"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            context_epochs_payload(
                rows,
                work_session_id=work_session_id,
                limit=limit,
                offset=offset,
            ),
        )

    def _handle_threads(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = _parse_api_limit(_first(params.get("limit")), 100)
            offset = _parse_api_offset(_first(params.get("offset")))
            include_archived = _parse_bool(_first(params.get("include_archived")), self._include_archived)
            sort = _first(params.get("sort")) or "tokens"
            direction = _first(params.get("direction")) or "desc"
            search = _first(params.get("q")) or _first(params.get("search"))
            total_matched = query_thread_summary_count(
                db_path=self._db_path,
                search=search,
                include_archived=include_archived,
            )
            if sort in {"cost", "usage", "usage_impact"}:
                sorted_rows = query_thread_summaries(
                    db_path=self._db_path,
                    limit=None,
                    offset=0,
                    search=search,
                    include_archived=include_archived,
                    sort="time",
                    direction="desc",
                )
                sorted_rows = self._annotate_thread_summary_rows(
                    sorted_rows,
                    include_archived=include_archived,
                )
                reverse = direction.lower() != "asc"
                sorted_rows.sort(
                    key=lambda row: _thread_summary_computed_sort_key(row, sort),
                    reverse=reverse,
                )
                rows = sorted_rows[offset : offset + limit]
            else:
                rows = query_thread_summaries(
                    db_path=self._db_path,
                    limit=limit,
                    offset=offset,
                    search=search,
                    include_archived=include_archived,
                    sort=sort,
                    direction=direction,
                )
                rows = self._annotate_thread_summary_rows(rows, include_archived=include_archived)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading threads: {exc}"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "schema": "codex-usage-tracker-threads-v1",
                "rows": rows,
                "row_count": len(rows),
                "total_matched_rows": total_matched,
                "limit": limit,
                "offset": offset,
                "has_more": _has_more(limit, offset, len(rows), total_matched),
                "next_offset": _next_offset(limit, offset, len(rows), total_matched),
                "include_archived": include_archived,
                "raw_context_included": False,
            },
        )

    def _annotate_thread_summary_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        include_archived: bool,
    ) -> list[dict[str, Any]]:
        if not rows:
            return rows
        thread_keys = [str(row.get("thread_key") or "") for row in rows]
        buckets = query_thread_model_buckets(
            db_path=self._db_path,
            thread_keys=thread_keys,
            include_archived=include_archived,
        )
        pricing = load_pricing_config(self._pricing_path)
        allowance = load_allowance_config(self._allowance_path)
        annotated_buckets = annotate_rows_with_allowance(
            annotate_rows_with_efficiency(buckets, pricing, model_field="model"),
            allowance,
            model_field="model",
        )
        buckets_by_thread: dict[str, list[dict[str, Any]]] = {}
        for bucket in annotated_buckets:
            key = str(bucket.get("thread_key") or "")
            if not key:
                continue
            buckets_by_thread.setdefault(key, []).append(bucket)
        impact_summaries = query_thread_usage_impact_summaries(
            db_path=self._db_path,
            thread_keys=thread_keys,
            include_archived=include_archived,
        )
        usage_impact_by_thread, pending_impact_by_thread = _thread_usage_impact_by_thread(
            impact_summaries
        )
        annotated_rows: list[dict[str, Any]] = []
        for row in rows:
            copy = dict(row)
            key = str(copy.get("thread_key") or "")
            thread_buckets = buckets_by_thread.get(key, [])
            if thread_buckets:
                copy["model_summary"] = _thread_summary_label(
                    [bucket.get("model") for bucket in thread_buckets],
                    "models",
                    excluded_primary={"codex-auto-review"},
                )
                copy["effort_summary"] = _thread_summary_label(
                    [bucket.get("effort") for bucket in thread_buckets],
                    "efforts",
                )
                copy["estimated_cost_usd"] = _sum_optional_number(
                    bucket.get("estimated_cost_usd") for bucket in thread_buckets
                )
                copy["usage_credits"] = _sum_optional_number(
                    bucket.get("usage_credits") for bucket in thread_buckets
                )
            if key in usage_impact_by_thread:
                copy["usage_impact"] = usage_impact_by_thread[key]
            if pending_impact_by_thread.get(key):
                copy["usage_impact_pending"] = True
            annotated_rows.append(copy)
        return annotated_rows

    def _handle_thread_calls(self, query: str) -> None:
        params = parse_qs(query)
        thread_key = _first(params.get("thread_key")) or _first(params.get("thread"))
        if not thread_key:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "thread_key is required"})
            return
        try:
            query_params = self._live_query_params(params, thread_key=thread_key)
            rows, total_matched = self._live_call_rows(
                query_params=query_params,
                pricing_status=None,
                credit_confidence=None,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading thread calls: {exc}"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "schema": "codex-usage-tracker-thread-calls-v1",
                "thread_key": thread_key,
                "rows": rows,
                "row_count": len(rows),
                "total_matched_rows": total_matched,
                "usage_impact_pending": any(row.get("usage_impact_pending") for row in rows),
                "limit": query_params["limit"],
                "offset": query_params["offset"],
                "has_more": _has_more(query_params["limit"], query_params["offset"], len(rows), total_matched),
                "next_offset": _next_offset(query_params["limit"], query_params["offset"], len(rows), total_matched),
                "raw_context_included": False,
            },
        )

    def _handle_summary(self, query: str) -> None:
        params = parse_qs(query)
        try:
            report = build_summary_report(
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                group_by=_first(params.get("group_by")) or "thread",
                limit=_parse_report_limit(_first(params.get("limit")), 20),
                preset=_first(params.get("preset")),
                since=_first(params.get("since")),
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
        payload = report.payload()
        payload["raw_context_included"] = False
        self._send_json(HTTPStatus.OK, payload)

    def _handle_recommendations(self, query: str) -> None:
        params = parse_qs(query)
        try:
            report = build_recommendations_report(
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                projects_path=self._projects_path,
                since=_first(params.get("since")),
                until=_first(params.get("until")),
                model=_first(params.get("model")),
                effort=_first(params.get("effort")),
                thread=_first(params.get("thread")),
                project=_first(params.get("project")),
                min_score=_parse_optional_float(_first(params.get("min_score")), "min_score"),
                limit=_parse_report_limit(_first(params.get("limit")), 20),
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
        payload = dict(report.payload)
        payload["raw_context_included"] = False
        self._send_json(HTTPStatus.OK, payload)

    def _live_query_params(
        self,
        params: dict[str, list[str]],
        *,
        thread_key: str | None = None,
    ) -> dict[str, Any]:
        include_archived = _parse_bool(
            _first(params.get("include_archived")),
            self._include_archived,
        )
        limit = _parse_api_limit(_first(params.get("limit")), 100)
        offset = _parse_api_offset(_first(params.get("offset")))
        return {
            "limit": limit,
            "offset": offset,
            "search": _first(params.get("q")) or _first(params.get("search")),
            "since": _first(params.get("since")),
            "until": _first(params.get("until")),
            "model": _first(params.get("model")),
            "effort": _first(params.get("effort")),
            "thread": _first(params.get("thread")) if thread_key is None else None,
            "thread_key": thread_key,
            "include_archived": include_archived,
            "sort": _first(params.get("sort")) or "time",
            "direction": _first(params.get("direction")) or "desc",
            "filters": {
                "q": _first(params.get("q")) or _first(params.get("search")),
                "since": _first(params.get("since")),
                "until": _first(params.get("until")),
                "model": _first(params.get("model")),
                "effort": _first(params.get("effort")),
                "thread": _first(params.get("thread")) if thread_key is None else None,
                "thread_key": thread_key,
                "include_archived": include_archived,
                "sort": _first(params.get("sort")) or "time",
                "direction": _first(params.get("direction")) or "desc",
            },
        }

    def _live_call_rows(
        self,
        *,
        query_params: dict[str, Any],
        pricing_status: str | None,
        credit_confidence: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        derived_filter = bool(pricing_status or credit_confidence)
        rows = query_usage_api_events(
            db_path=self._db_path,
            limit=None if derived_filter else query_params["limit"],
            offset=0 if derived_filter else query_params["offset"],
            search=query_params["search"],
            since=query_params["since"],
            until=query_params["until"],
            model=query_params["model"],
            effort=query_params["effort"],
            thread=query_params["thread"],
            thread_key=query_params["thread_key"],
            include_archived=query_params["include_archived"],
            sort=query_params["sort"],
            direction=query_params["direction"],
        )
        rows = self._annotate_live_rows(
            rows,
            include_archived=query_params["include_archived"],
        )
        if derived_filter:
            rows = [
                row
                for row in rows
                if _matches_live_derived_filters(
                    row,
                    pricing_status=pricing_status,
                    credit_confidence=credit_confidence,
                )
            ]
            total_matched = len(rows)
            limit = query_params["limit"]
            offset = query_params["offset"]
            rows = rows[offset:] if limit is None else rows[offset : offset + limit]
            return rows, total_matched
        total_matched = query_usage_api_event_count(
            db_path=self._db_path,
            search=query_params["search"],
            since=query_params["since"],
            until=query_params["until"],
            model=query_params["model"],
            effort=query_params["effort"],
            thread=query_params["thread"],
            thread_key=query_params["thread_key"],
            include_archived=query_params["include_archived"],
        )
        return rows, total_matched

    def _annotate_live_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        include_archived: bool,
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        rows = annotate_thread_attachments([ensure_call_origin(row) for row in rows])
        pricing = load_pricing_config(self._pricing_path)
        allowance = load_allowance_config(
            self._allowance_path,
            rate_card_path=self._rate_card_path,
        )
        thresholds = load_threshold_config(self._thresholds_path)
        projects = load_project_config(self._projects_path)
        rows = annotate_rows_with_allowance(
            annotate_rows_with_efficiency(rows, pricing),
            allowance,
        )
        rows = self._usage_impact_cache.copy_usage_impact(
            rows,
            include_archived=include_archived,
            block=False,
            schedule_warm=False,
        )
        rows = annotate_rows_with_recommendations(rows, thresholds)
        rows = annotate_rows_with_project_identity(rows, projects)
        return apply_project_privacy_to_rows(rows, privacy_mode=self._privacy_mode)

    def _handle_usage(self, query: str) -> None:
        params = parse_qs(query)
        limit = _parse_limit(_first(params.get("limit")), self._limit)
        offset = _parse_offset(_first(params.get("offset")))
        include_archived = _parse_bool(_first(params.get("include_archived")), self._include_archived)
        language = normalize_language(_first(params.get("lang")) or self._language)
        diagnostics_enabled = _parse_bool(_first(params.get("diagnostics")), False)
        shell_only = _parse_bool(_first(params.get("shell")), False)
        refresh_result = None
        refresh_ms: float | None = None
        try:
            if _truthy(_first(params.get("refresh"))):
                if not self._has_valid_api_token(params):
                    self._send_json(
                        HTTPStatus.FORBIDDEN,
                        {"error": "Valid API token is required for refresh"},
                    )
                    return
                refresh_result, refresh_ms = self._refresh_usage_index(include_archived)
            payload_started = perf_counter()
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
                include_rows=not shell_only,
                estimate_usage_impact=shell_only,
            )
            if not shell_only:
                rows = payload.get("rows")
                if isinstance(rows, list):
                    rows_with_impact = self._usage_impact_cache.copy_usage_impact(
                        rows,
                        include_archived=include_archived,
                        block=False,
                    )
                    payload["rows"] = rows_with_impact
                    payload["usage_impact_pending"] = any(
                        row.get("usage_impact_pending") for row in rows_with_impact
                    )
            dashboard_payload_ms = _elapsed_ms(payload_started)
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
        if diagnostics_enabled:
            diagnostic_payload: dict[str, object] = {
                "dashboard_payload_ms": dashboard_payload_ms,
                "rows_returned": len(payload.get("rows") or []),
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            }
            if refresh_ms is not None:
                diagnostic_payload["refresh_ms"] = refresh_ms
            payload["diagnostics"] = diagnostic_payload
        self._send_json(HTTPStatus.OK, payload)

    def _refresh_usage_index(self, include_archived: bool) -> tuple[dict[str, object], float]:
        refresh_started = perf_counter()
        with self._refresh_lock:
            result = refresh_usage_index(
                codex_home=self._codex_home,
                db_path=self._db_path,
                include_archived=include_archived,
            )
        if _refresh_result_invalidates_usage_impact(result):
            self._usage_impact_cache.invalidate()
            self._usage_impact_cache.warm_pending_async(include_archived=include_archived)
        payload = refresh_result_payload(
            result,
            schema="codex-usage-tracker-refresh-v1",
        )
        payload.pop("schema", None)
        payload["include_archived"] = include_archived
        return (
            payload,
            _elapsed_ms(refresh_started),
        )

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
        body = _json_response_body(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return
