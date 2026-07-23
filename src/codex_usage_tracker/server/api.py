"""Local dashboard server with lazy context API."""

from __future__ import annotations

import secrets
import threading
import webbrowser
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from codex_usage_tracker.context.api import DEFAULT_CONTEXT_CHARS
from codex_usage_tracker.core.i18n import normalize_language
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.dashboard.api import (
    generate_dashboard,
)
from codex_usage_tracker.interfaces.http.v2 import ApplicationHttpV2Services, HttpV2Facade
from codex_usage_tracker.server import compression_routes
from codex_usage_tracker.server import utils as server_utils
from codex_usage_tracker.server.analysis_jobs import AnalysisJobRegistry
from codex_usage_tracker.server.context_settings import (
    ContextApiState,
)
from codex_usage_tracker.server.handler import _UsageDashboardHandler
from codex_usage_tracker.server.query_cache import AggregateQueryCache
from codex_usage_tracker.server.usage_refresh import RefreshJobRegistry

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
    refresh_on_start: bool = False,
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
    refresh_jobs = RefreshJobRegistry()
    refresh_lock = threading.Lock()
    analysis_jobs = AnalysisJobRegistry()
    compression_jobs = compression_routes.CompressionJobRegistry()
    query_cache = AggregateQueryCache()
    allowance_query_cache = AggregateQueryCache(
        max_entries=4,
        max_payload_bytes=8 * 1_024 * 1_024,
    )
    http_v2_facade = HttpV2Facade(
        ApplicationHttpV2Services(
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            thresholds_path=thresholds_path,
            projects_path=projects_path,
            codex_home=codex_home,
        )
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
        refresh_lock=refresh_lock,
        refresh_jobs=refresh_jobs,
        analysis_jobs=analysis_jobs,
        compression_jobs=compression_jobs,
        query_cache=query_cache,
        allowance_query_cache=allowance_query_cache,
        http_v2_facade=http_v2_facade,
    )
    server = ThreadingHTTPServer((host, port), handler)
    legacy_url = f"http://{_url_host(host)}:{port}/{output.name}"
    dashboard_url = f"http://{_url_host(host)}:{port}/react-dashboard.html"
    if selected_language == "zh-Hans":
        print(f"Codex 用量仪表盘正在运行：{dashboard_url}")
        print(f"旧版仪表盘备用入口：{legacy_url}")
        context_mode = "已启用，可按记录显式加载" if context_api_enabled else "已禁用，可稍后在仪表盘中启用"
        print("聚合记录通过带服务器专用令牌的 /api/usage 接口刷新。")
        print(f"原始上下文 API {context_mode}；仪表盘 HTML 中不会嵌入上下文。")
    else:
        print(f"Serving Codex usage dashboard at {dashboard_url}")
        print(f"Legacy dashboard fallback remains available at {legacy_url}")
        context_mode = (
            "enabled for explicit row actions"
            if context_api_enabled
            else "disabled until enabled from the dashboard"
        )
        print("Aggregate rows refresh through /api/usage with a per-server token.")
        print(f"Raw context API is {context_mode}; context is never embedded in the dashboard HTML.")
    if refresh_on_start:
        refresh_job = refresh_jobs.start_refresh(
            codex_home=codex_home,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            thresholds_path=thresholds_path,
            include_archived=include_archived,
            aggregate_only=False,
            refresh_lock=refresh_lock,
        )
        job_id = refresh_job["job_id"]
        if selected_language == "zh-Hans":
            print(f"后台刷新已开始：{job_id}")
        else:
            print(f"Background refresh started: {job_id}")
    if open_browser:
        webbrowser.open(dashboard_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止仪表盘服务器。" if selected_language == "zh-Hans" else "\nStopping dashboard server.")
    finally:
        server.server_close()
