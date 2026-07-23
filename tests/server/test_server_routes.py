from __future__ import annotations

from codex_usage_tracker.server.routes import (
    GET_DIAGNOSTIC_FACT_ROUTES,
    GET_DYNAMIC_ROUTE_METHODS,
    GET_ROUTE_METHODS,
    POST_ROUTE_METHODS,
    get_route_method,
    is_dashboard_shell_path,
    is_deprecated_http_v1_path,
)


def test_server_route_tables_cover_dashboard_api_paths() -> None:
    assert GET_ROUTE_METHODS["/api/context"] == "_handle_context"
    assert GET_ROUTE_METHODS["/api/diagnostics/usage-drain"] == ("_handle_diagnostics_usage_drain")
    assert GET_ROUTE_METHODS["/api/diagnostics/dedupe"] == "_handle_dedupe_diagnostics"
    assert GET_ROUTE_METHODS["/api/allowance/history"] == "_handle_allowance_history"
    assert GET_ROUTE_METHODS["/api/allowance/diagnostics"] == ("_handle_allowance_diagnostics")
    assert GET_ROUTE_METHODS["/api/allowance/export"] == "_handle_allowance_export"
    assert GET_ROUTE_METHODS["/api/allowance/status"] == "_handle_allowance_status_v2"
    assert GET_ROUTE_METHODS["/api/allowance/series"] == "_handle_allowance_series_v2"
    assert GET_ROUTE_METHODS["/api/allowance/evidence"] == "_handle_allowance_evidence_v2"
    assert GET_ROUTE_METHODS["/api/allowance/analysis"] == "_handle_allowance_analysis_v2"
    assert GET_ROUTE_METHODS["/api/allowance/analysis/jobs"] == (
        "_handle_allowance_analysis_job_status_v2"
    )
    assert POST_ROUTE_METHODS["/api/allowance/analysis/jobs"] == (
        "_handle_allowance_analysis_job_start_v2"
    )
    assert POST_ROUTE_METHODS["/api/v2/evidence"] == "_handle_http_v2"
    assert GET_ROUTE_METHODS["/api/investigations/agentic"] == "_handle_investigation_agentic"
    assert GET_ROUTE_METHODS["/api/investigations/repeated-files"] == (
        "_handle_investigation_repeated_file_rediscovery"
    )
    assert GET_ROUTE_METHODS["/api/investigations/shell-churn"] == (
        "_handle_investigation_shell_churn"
    )
    assert GET_ROUTE_METHODS["/api/investigations/large-low-output"] == (
        "_handle_investigation_large_low_output"
    )
    assert GET_ROUTE_METHODS["/api/investigations/walk"] == "_handle_investigation_walk"
    assert GET_ROUTE_METHODS["/api/usage"] == "_handle_usage"
    assert GET_DIAGNOSTIC_FACT_ROUTES == {
        "/api/diagnostics/compactions": {"fact_type": "compaction"},
        "/api/diagnostics/tools": {"fact_group": "tools"},
    }


def test_server_route_tables_cover_stable_http_v2_paths() -> None:
    assert GET_ROUTE_METHODS["/api/v2/status"] == "_handle_http_v2"
    assert GET_ROUTE_METHODS["/api/v2/capabilities"] == "_handle_http_v2"
    assert GET_DYNAMIC_ROUTE_METHODS["/api/v2/jobs/{job_id}"] == "_handle_http_v2"
    assert get_route_method("/api/v2/jobs/job_123") == "_handle_http_v2"
    assert get_route_method("/api/v2/jobs/") == "_handle_http_v2"
    assert {
        path for path, handler in POST_ROUTE_METHODS.items() if handler == "_handle_http_v2"
    } == {
        "/api/v2/refresh",
        "/api/v2/analyze",
        "/api/v2/query",
        "/api/v2/evidence",
        "/api/v2/allowance",
    }


def test_server_route_tables_cover_diagnostic_refresh_paths() -> None:
    assert GET_ROUTE_METHODS["/api/diagnostics/refresh/status"] == (
        "_handle_diagnostics_refresh_status"
    )
    assert POST_ROUTE_METHODS["/api/diagnostics/refresh"] == "_handle_diagnostics_refresh"
    assert POST_ROUTE_METHODS["/api/diagnostics/commands/refresh"] == (
        "_handle_diagnostics_commands_refresh"
    )
    assert POST_ROUTE_METHODS["/api/diagnostics/usage-drain/refresh"] == (
        "_handle_diagnostics_usage_drain_refresh"
    )


def test_server_route_tables_cover_compression_lab_paths() -> None:
    assert GET_ROUTE_METHODS["/api/compression/status"] == "_handle_compression_status"
    assert GET_ROUTE_METHODS["/api/compression/profile"] == "_handle_compression_profile"
    assert POST_ROUTE_METHODS["/api/compression/start"] == "_handle_compression_start"


def test_dashboard_shell_path_matches_root_and_generated_dashboard_name() -> None:
    assert is_dashboard_shell_path("/", "dashboard.html")
    assert is_dashboard_shell_path("/dashboard.html", "dashboard.html")
    assert not is_dashboard_shell_path("/api/usage", "dashboard.html")


def test_only_unversioned_api_routes_receive_v1_deprecation_metadata() -> None:
    assert is_deprecated_http_v1_path("/api/usage")
    assert is_deprecated_http_v1_path("/api/calls")
    assert not is_deprecated_http_v1_path("/api/v2/query")
    assert not is_deprecated_http_v1_path("/react-dashboard.html")
