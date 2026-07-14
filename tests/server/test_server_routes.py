from __future__ import annotations

from codex_usage_tracker.server.routes import (
    GET_DIAGNOSTIC_FACT_ROUTES,
    GET_ROUTE_METHODS,
    POST_ROUTE_METHODS,
    is_dashboard_shell_path,
)


def test_server_route_tables_cover_dashboard_api_paths() -> None:
    assert GET_ROUTE_METHODS["/api/context"] == "_handle_context"
    assert GET_ROUTE_METHODS["/api/diagnostics/usage-drain"] == ("_handle_diagnostics_usage_drain")
    assert GET_ROUTE_METHODS["/api/allowance/history"] == "_handle_allowance_history"
    assert GET_ROUTE_METHODS["/api/allowance/diagnostics"] == ("_handle_allowance_diagnostics")
    assert GET_ROUTE_METHODS["/api/allowance/export"] == "_handle_allowance_export"
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


def test_dashboard_shell_path_matches_root_and_generated_dashboard_name() -> None:
    assert is_dashboard_shell_path("/", "dashboard.html")
    assert is_dashboard_shell_path("/dashboard.html", "dashboard.html")
    assert not is_dashboard_shell_path("/api/usage", "dashboard.html")
