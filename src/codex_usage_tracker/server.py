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
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs, urlparse

from codex_usage_tracker.allowance import annotate_rows_with_allowance, load_allowance_config
from codex_usage_tracker.call_origin import ensure_call_origin
from codex_usage_tracker.context import (
    CONTEXT_MODE_QUICK,
    CONTEXT_MODES,
    DEFAULT_CONTEXT_CHARS,
    DEFAULT_CONTEXT_ENTRIES,
    load_call_context,
)
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
    query_thread_summaries,
    query_usage_api_event_count,
    query_usage_api_events,
    query_usage_record,
    query_usage_status,
    refresh_metadata,
    refresh_usage_index,
)
from codex_usage_tracker.threads import annotate_thread_attachments


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
        if parsed.path == "/api/usage":
            self._handle_usage(parsed.query)
            return
        if parsed.path == "/":
            self.path = f"/{self._dashboard_name}"
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
        try:
            counts = query_usage_status(
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
        parser_diagnostics = {
            key.removeprefix("parser_"): _safe_int(value)
            for key, value in metadata.items()
            if key.startswith("parser_") and _safe_int(value)
        }
        self._send_json(
            HTTPStatus.OK,
            {
                "schema": "codex-usage-tracker-status-v1",
                "payload_schema": "codex-usage-tracker-live-api-v1",
                "latest_refresh_at": metadata.get("latest_refresh_at"),
                "include_archived": include_archived,
                "row_counts": counts,
                "max_event_timestamp": counts.get("max_event_timestamp"),
                "parser_adapter": metadata.get("parser_adapter"),
                "parser_diagnostics": parser_diagnostics,
            },
        )

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
            rows = self._annotate_live_rows([row])
        except sqlite3.Error as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Database error while reading call: {exc}"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "schema": "codex-usage-tracker-call-v1",
                "record": rows[0],
                "previous_record_id": row.get("previous_record_id"),
                "next_record_id": row.get("next_record_id"),
                "raw_context_included": False,
            },
        )

    def _handle_threads(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = _parse_api_limit(_first(params.get("limit")), 100)
            offset = _parse_api_offset(_first(params.get("offset")))
            include_archived = _parse_bool(_first(params.get("include_archived")), self._include_archived)
            sort = _first(params.get("sort")) or "tokens"
            direction = _first(params.get("direction")) or "desc"
            rows = query_thread_summaries(
                db_path=self._db_path,
                limit=limit,
                offset=offset,
                search=_first(params.get("q")) or _first(params.get("search")),
                include_archived=include_archived,
                sort=sort,
                direction=direction,
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
        self._send_json(
            HTTPStatus.OK,
            {
                "schema": "codex-usage-tracker-threads-v1",
                "rows": rows,
                "row_count": len(rows),
                "limit": limit,
                "offset": offset,
                "include_archived": include_archived,
                "raw_context_included": False,
            },
        )

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
        rows = self._annotate_live_rows(rows)
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

    def _annotate_live_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                refresh_started = perf_counter()
                with self._refresh_lock:
                    result = refresh_usage_index(
                        codex_home=self._codex_home,
                        db_path=self._db_path,
                        include_archived=include_archived,
                    )
                refresh_ms = _elapsed_ms(refresh_started)
                refresh_result = {
                    "scanned_files": result.scanned_files,
                    "parsed_events": result.parsed_events,
                    "skipped_events": result.skipped_events,
                    "inserted_or_updated_events": result.inserted_or_updated_events,
                    "db_path": result.db_path,
                    "parser_diagnostics": result.parser_diagnostics,
                    "include_archived": include_archived,
                }
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


def _parse_api_limit(value: str | None, default: int) -> int | None:
    if value is None or value == "":
        return default
    if value.lower() == "all":
        return None
    try:
        limit = int(value)
    except ValueError as exc:
        raise ValueError("limit must be a positive integer or all") from exc
    if limit <= 0:
        raise ValueError("limit must be a positive integer or all")
    return min(limit, 10_000)


def _parse_report_limit(value: str | None, default: int) -> int:
    limit = _parse_api_limit(value, default)
    return 10_000 if limit is None else limit


def _parse_api_offset(value: str | None) -> int:
    if value is None or value == "":
        return 0
    try:
        offset = int(value)
    except ValueError as exc:
        raise ValueError("offset must be a non-negative integer") from exc
    if offset < 0:
        raise ValueError("offset must be a non-negative integer")
    return offset


def _parse_optional_float(value: str | None, name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _optional_filter(
    value: str | None,
    allowed: tuple[str, ...],
    name: str,
) -> str | None:
    if value is None or value == "":
        return None
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return value


def _matches_live_derived_filters(
    row: dict[str, Any],
    *,
    pricing_status: str | None,
    credit_confidence: str | None,
) -> bool:
    if pricing_status == "priced" and not row.get("pricing_model"):
        return False
    if pricing_status == "estimated" and not row.get("pricing_estimated"):
        return False
    if pricing_status == "unpriced" and row.get("pricing_model"):
        return False
    return not (credit_confidence and row.get("usage_credit_confidence") != credit_confidence)


def _has_more(limit: int | None, offset: int, row_count: int, total_matched: int) -> bool:
    return limit is not None and offset + row_count < total_matched


def _next_offset(
    limit: int | None,
    offset: int,
    row_count: int,
    total_matched: int,
) -> int | None:
    return offset + row_count if _has_more(limit, offset, row_count, total_matched) else None


def _parse_context_limit(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    if value.lower() == "all":
        return 0
    try:
        limit = int(value)
    except ValueError:
        return default
    return max(limit, 0)


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _json_response_body(payload: dict[str, object]) -> bytes:
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return json.dumps(payload, ensure_ascii=True).encode("utf-8")

    previous_size: int | None = None
    while True:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        current_size = len(body)
        if current_size == previous_size:
            return body
        diagnostics["json_bytes"] = current_size
        previous_size = current_size


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
