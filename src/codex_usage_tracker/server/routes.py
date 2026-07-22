"""Pure route tables for the local dashboard server."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

GET_ROUTE_METHODS: Mapping[str, str] = MappingProxyType(
    {
        "/api/context": "_handle_context",
        "/api/context-settings": "_handle_context_settings",
        "/api/open-investigator": "_handle_open_investigator",
        "/api/health": "_handle_health",
        "/api/status": "_handle_status",
        "/api/v2/status": "_handle_http_v2",
        "/api/v2/capabilities": "_handle_http_v2",
        "/api/readiness": "_handle_readiness",
        "/api/calls": "_handle_calls",
        "/api/call": "_handle_call",
        "/api/threads": "_handle_threads",
        "/api/thread-calls": "_handle_thread_calls",
        "/api/summary": "_handle_summary",
        "/api/recommendations": "_handle_recommendations",
        "/api/allowance/history": "_handle_allowance_history",
        "/api/allowance/diagnostics": "_handle_allowance_diagnostics",
        "/api/allowance/export": "_handle_allowance_export",
        "/api/allowance/status": "_handle_allowance_status_v2",
        "/api/allowance/series": "_handle_allowance_series_v2",
        "/api/allowance/evidence": "_handle_allowance_evidence_v2",
        "/api/allowance/analysis": "_handle_allowance_analysis_v2",
        "/api/allowance/analysis/jobs": "_handle_allowance_analysis_job_status_v2",
        "/api/reports/pack": "_handle_reports_pack",
        "/api/investigations/agentic": "_handle_investigation_agentic",
        "/api/investigations/repeated-files": ("_handle_investigation_repeated_file_rediscovery"),
        "/api/investigations/shell-churn": "_handle_investigation_shell_churn",
        "/api/investigations/large-low-output": "_handle_investigation_large_low_output",
        "/api/investigations/walk": "_handle_investigation_walk",
        "/api/diagnostics/summary": "_handle_diagnostics_summary",
        "/api/diagnostics/dedupe": "_handle_dedupe_diagnostics",
        "/api/diagnostics/facts": "_handle_diagnostics_facts",
        "/api/diagnostics/fact-calls": "_handle_diagnostics_fact_calls",
        "/api/diagnostics/overview": "_handle_diagnostics_overview",
        "/api/diagnostics/tool-output": "_handle_diagnostics_tool_output",
        "/api/diagnostics/commands": "_handle_diagnostics_commands",
        "/api/diagnostics/git-interactions": "_handle_diagnostics_git_interactions",
        "/api/diagnostics/file-reads": "_handle_diagnostics_file_reads",
        "/api/diagnostics/file-modifications": "_handle_diagnostics_file_modifications",
        "/api/diagnostics/read-productivity": "_handle_diagnostics_read_productivity",
        "/api/diagnostics/concentration": "_handle_diagnostics_concentration",
        "/api/diagnostics/guided-summary": "_handle_diagnostics_guided_summary",
        "/api/diagnostics/usage-drain": "_handle_diagnostics_usage_drain",
        "/api/diagnostics/refresh/status": "_handle_diagnostics_refresh_status",
        "/api/compression/status": "_handle_compression_status",
        "/api/compression/profile": "_handle_compression_profile",
        "/api/usage": "_handle_usage",
        "/api/refresh/start": "_handle_refresh_start",
        "/api/refresh/status": "_handle_refresh_status",
    }
)

GET_DIAGNOSTIC_FACT_ROUTES: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "/api/diagnostics/compactions": MappingProxyType({"fact_type": "compaction"}),
        "/api/diagnostics/tools": MappingProxyType({"fact_group": "tools"}),
    }
)

POST_ROUTE_METHODS: Mapping[str, str] = MappingProxyType(
    {
        "/api/v2/refresh": "_handle_http_v2",
        "/api/v2/analyze": "_handle_http_v2",
        "/api/v2/query": "_handle_http_v2",
        "/api/v2/evidence": "_handle_http_v2",
        "/api/v2/allowance": "_handle_http_v2",
        "/api/compression/start": "_handle_compression_start",
        "/api/allowance/analysis/jobs": "_handle_allowance_analysis_job_start_v2",
        "/api/diagnostics/refresh": "_handle_diagnostics_refresh",
        "/api/diagnostics/overview/refresh": "_handle_diagnostics_overview_refresh",
        "/api/diagnostics/tool-output/refresh": "_handle_diagnostics_tool_output_refresh",
        "/api/diagnostics/commands/refresh": "_handle_diagnostics_commands_refresh",
        "/api/diagnostics/git-interactions/refresh": "_handle_diagnostics_git_interactions_refresh",
        "/api/diagnostics/file-reads/refresh": "_handle_diagnostics_file_reads_refresh",
        "/api/diagnostics/file-modifications/refresh": "_handle_diagnostics_file_modifications_refresh",
        "/api/diagnostics/read-productivity/refresh": "_handle_diagnostics_read_productivity_refresh",
        "/api/diagnostics/concentration/refresh": "_handle_diagnostics_concentration_refresh",
        "/api/diagnostics/guided-summary/refresh": "_handle_diagnostics_guided_summary_refresh",
        "/api/diagnostics/usage-drain/refresh": "_handle_diagnostics_usage_drain_refresh",
    }
)

GET_DYNAMIC_ROUTE_METHODS: Mapping[str, str] = MappingProxyType(
    {"/api/v2/jobs/{job_id}": "_handle_http_v2"}
)


def get_route_method(path: str) -> str | None:
    """Return the GET handler for one exact or bounded dynamic API path."""
    exact = GET_ROUTE_METHODS.get(path)
    if exact is not None:
        return exact
    if path.startswith("/api/v2/jobs/") and path != "/api/v2/jobs/":
        return GET_DYNAMIC_ROUTE_METHODS["/api/v2/jobs/{job_id}"]
    if path.startswith("/api/v2/"):
        return "_handle_http_v2"
    return None


def post_route_method(path: str) -> str | None:
    """Return the POST handler, including JSON errors for unknown v2 paths."""
    return POST_ROUTE_METHODS.get(path) or (
        "_handle_http_v2" if path.startswith("/api/v2/") else None
    )


def is_dashboard_shell_path(path: str, dashboard_name: str) -> bool:
    """Return whether a path should render the dashboard shell."""
    return path in {"/", f"/{dashboard_name}"}
