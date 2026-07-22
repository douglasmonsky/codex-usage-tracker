"""Local dashboard server with lazy context API."""

from __future__ import annotations

import threading
import webbrowser
from http import HTTPStatus
from http.server import HTTPServer
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from codex_usage_tracker.core.i18n import normalize_language
from codex_usage_tracker.core.paths import DEFAULT_RATE_CARD_PATH
from codex_usage_tracker.server import allowance, allowance_v2, compression_routes
from codex_usage_tracker.server import context as server_context
from codex_usage_tracker.server import usage_refresh as server_usage_refresh
from codex_usage_tracker.server.analysis_jobs import AnalysisJobRegistry
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
from codex_usage_tracker.server.dashboard_pages import (
    _REACT_DASHBOARD_PATH,
    DashboardPageMixin,
)
from codex_usage_tracker.server.dedupe import DedupeRouteMixin
from codex_usage_tracker.server.diagnostic_routes import DiagnosticRouteMixin
from codex_usage_tracker.server.http_v2 import HttpV2RouteMixin
from codex_usage_tracker.server.investigations import (
    InvestigationKind,
    handle_investigation_request,
)
from codex_usage_tracker.server.live_queries import live_query_params
from codex_usage_tracker.server.live_rows import annotate_live_rows, query_live_call_rows
from codex_usage_tracker.server.open_investigator import (
    OpenInvestigatorRequestError,
    open_investigator_payload,
)
from codex_usage_tracker.server.query_cache import AggregateQueryCache
from codex_usage_tracker.server.recommendations import handle_recommendations_request
from codex_usage_tracker.server.reports import handle_reports_pack_request
from codex_usage_tracker.server.request_guards import (
    HeaderLookup,
    has_valid_api_token,
    request_origin_allowed,
)
from codex_usage_tracker.server.responses import (
    send_error_response,
    send_exception_response,
    send_json_response,
)
from codex_usage_tracker.server.routes import (
    GET_DIAGNOSTIC_FACT_ROUTES,
    get_route_method,
    is_dashboard_shell_path,
    post_route_method,
)
from codex_usage_tracker.server.status import handle_readiness_request, handle_status_request
from codex_usage_tracker.server.summary import handle_summary_request
from codex_usage_tracker.server.threads import handle_threads_request


class _UsageDashboardHandler(
    compression_routes.CompressionRouteMixin,
    DiagnosticRouteMixin,
    DedupeRouteMixin,
    HttpV2RouteMixin,
    DashboardPageMixin,
):
    def __init__(
        self,
        *args: Any,
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
        analysis_jobs: AnalysisJobRegistry | None = None,
        compression_jobs: compression_routes.CompressionJobRegistry | None = None,
        query_cache: AggregateQueryCache | None = None,
        allowance_query_cache: AggregateQueryCache | None = None,
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
        self._analysis_jobs = analysis_jobs or AnalysisJobRegistry()
        self._compression_jobs = compression_jobs or compression_routes.CompressionJobRegistry()
        self._query_cache = query_cache or AggregateQueryCache()
        self._allowance_query_cache = allowance_query_cache or allowance.new_query_cache()
        self._configure_http_v2()
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        self._request_started_at = perf_counter()
        parsed = urlparse(self.path)
        if not self._request_origin_allowed():
            self._send_error(
                HTTPStatus.FORBIDDEN,
                "Request host or origin is not allowed",
            )
            return
        route_method = get_route_method(parsed.path)
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
        self._request_started_at = perf_counter()
        parsed = urlparse(self.path)
        if not self._request_origin_allowed():
            self._send_error(
                HTTPStatus.FORBIDDEN,
                "Request host or origin is not allowed",
            )
            return
        route_method = post_route_method(parsed.path)
        if route_method is not None:
            getattr(self, route_method)(parsed.query)
            return
        self._send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

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
                server_port=cast(HTTPServer, self.server).server_port,
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
            codex_home=self._codex_home,
            db_path=self._db_path,
            pricing_path=self._pricing_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            include_archived_default=self._include_archived,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_readiness(self, query: str) -> None:
        del query
        handle_readiness_request(codex_home=self._codex_home, send_json=self._send_json)

    def _handle_health(self, query: str) -> None:
        del query
        self._send_json(
            HTTPStatus.OK,
            {"schema": "codex-usage-tracker-health-v1", "status": "ok"},
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
            query_cache=self._query_cache,
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
            rate_card_path=self._rate_card_path,
            thresholds_path=self._thresholds_path,
            projects_path=self._projects_path,
            privacy_mode=self._privacy_mode,
            query_cache=self._query_cache,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_allowance_history(self, query: str) -> None:
        self._handle_allowance_report(query, diagnostics=False)

    def _handle_allowance_status_v2(self, query: str) -> None:
        allowance_v2.handle_allowance_status_request(
            query,
            db_path=self._db_path,
            privacy_mode=self._privacy_mode,
            include_archived_default=self._include_archived,
            send_error=self._send_error,
            send_json=self._send_json,
        )

    def _handle_allowance_series_v2(self, query: str) -> None:
        allowance_v2.handle_allowance_series_request(
            query,
            db_path=self._db_path,
            include_archived_default=self._include_archived,
            send_error=self._send_error,
            send_json=self._send_json,
        )

    def _handle_allowance_evidence_v2(self, query: str) -> None:
        allowance_v2.handle_allowance_evidence_request(
            query,
            db_path=self._db_path,
            privacy_mode=self._privacy_mode,
            include_archived_default=self._include_archived,
            send_error=self._send_error,
            send_json=self._send_json,
        )

    def _handle_allowance_analysis_v2(self, query: str) -> None:
        allowance_v2.handle_allowance_analysis_request(
            query,
            db_path=self._db_path,
            include_archived_default=self._include_archived,
            send_error=self._send_error,
            send_json=self._send_json,
        )

    def _handle_allowance_analysis_job_start_v2(self, query: str) -> None:
        allowance_v2.handle_allowance_analysis_job_start_request(
            query,
            db_path=self._db_path,
            registry=self._analysis_jobs,
            include_archived_default=self._include_archived,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_json=self._send_json,
        )

    def _handle_allowance_analysis_job_status_v2(self, query: str) -> None:
        allowance_v2.handle_allowance_analysis_job_status_request(
            query,
            registry=self._analysis_jobs,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_json=self._send_json,
        )

    def _handle_allowance_diagnostics(self, query: str) -> None:
        self._handle_allowance_report(query, diagnostics=True)

    def _handle_allowance_report(self, query: str, *, diagnostics: bool) -> None:
        handler = (
            allowance.handle_allowance_diagnostics_request
            if diagnostics
            else allowance.handle_allowance_history_request
        )
        handler(
            query,
            db_path=self._db_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            include_archived_default=self._include_archived,
            privacy_mode=self._privacy_mode,
            query_cache=self._allowance_query_cache,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_allowance_export(self, query: str) -> None:
        allowance.handle_allowance_export_request(
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

    def _handle_investigation_agentic(self, query: str) -> None:
        self._handle_investigation("agentic", query)

    def _handle_investigation_repeated_file_rediscovery(self, query: str) -> None:
        self._handle_investigation("repeated-file-rediscovery", query)

    def _handle_investigation_shell_churn(self, query: str) -> None:
        self._handle_investigation("shell-churn", query)

    def _handle_investigation_large_low_output(self, query: str) -> None:
        self._handle_investigation("large-low-output", query)

    def _handle_investigation_walk(self, query: str) -> None:
        self._handle_investigation("walk", query)

    def _handle_investigation(self, kind: InvestigationKind, query: str) -> None:
        handle_investigation_request(
            kind,
            query,
            db_path=self._db_path,
            pricing_path=self._pricing_path,
            allowance_path=self._allowance_path,
            projects_path=self._projects_path,
            include_archived_default=self._include_archived,
            privacy_mode=self._privacy_mode,
            query_cache=self._query_cache,
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
            pricing_path=self._pricing_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            thresholds_path=self._thresholds_path,
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
        server = cast(HTTPServer, self.server)
        return request_origin_allowed(cast(HeaderLookup, self.headers), server.server_port)

    def _has_valid_api_token(self, params: dict[str, list[str]]) -> bool:
        return has_valid_api_token(cast(HeaderLookup, self.headers), params, self._api_token)

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
