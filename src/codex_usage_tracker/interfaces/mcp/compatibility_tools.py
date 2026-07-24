"""Explicit legacy handlers retained by the full MCP profile."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from importlib import import_module

COMPATIBILITY_TOOL_NAMES = (
    "subagent_usage",
    "refresh_usage_index",
    "usage_refresh_start",
    "usage_refresh_status",
    "usage_doctor",
    "usage_summary",
    "usage_dedupe_diagnostics",
    "usage_calls",
    "usage_call_detail",
    "usage_threads",
    "usage_report_pack",
    "usage_dashboard_recommendations",
    "usage_allowance_history",
    "usage_allowance_diagnostics",
    "usage_allowance_export",
    "usage_allowance_status",
    "usage_allowance_series",
    "usage_allowance_evidence",
    "usage_allowance_analysis",
    "usage_allowance_analysis_status",
    "usage_compression_start",
    "usage_compression_status",
    "usage_compression_profile",
    "usage_compression_candidates",
    "usage_compression_candidate_detail",
    "usage_compression_simulate",
    "usage_recommendations",
    "session_usage",
    "usage_call_context",
    "most_expensive_usage_calls",
    "usage_pricing_coverage",
    "usage_source_coverage",
    "usage_content_search",
    "usage_thread_trace",
    "usage_repetition_scan",
    "usage_command_loop_scan",
    "usage_file_churn_scan",
    "usage_repeated_file_rediscovery",
    "usage_shell_churn",
    "usage_large_low_output_calls",
    "usage_suggest_investigations",
    "usage_investigate",
    "usage_action_brief",
    "usage_test_hypotheses",
    "usage_context_bloat_scan",
    "usage_investigation_walk",
    "usage_local_evidence_export",
    "generate_usage_dashboard",
    "export_usage_csv",
    "init_usage_pricing_config",
    "update_usage_pricing_config",
    "init_usage_allowance_config",
)

# These explicit local operations have no one-call aggregate core equivalent.
ADVANCED_TOOL_NAMES = frozenset(
    {
        "usage_dedupe_diagnostics",
        "usage_allowance_export",
        "usage_call_context",
        "usage_content_search",
        "usage_thread_trace",
        "usage_local_evidence_export",
        "export_usage_csv",
    }
)

OVERLAPPING_CORE_TOOL_NAMES = ("usage_status", "usage_query")

_MODULE_TOOL_NAMES = (
    ("codex_usage_tracker.interfaces.mcp.mcp_subagents", ("subagent_usage",)),
    (
        "codex_usage_tracker.interfaces.mcp.mcp_server_tools",
        (
            "refresh_usage_index",
            "usage_refresh_start",
            "usage_refresh_status",
            "usage_doctor",
            "usage_summary",
            "session_usage",
            "usage_call_context",
            "most_expensive_usage_calls",
        ),
    ),
    (
        "codex_usage_tracker.interfaces.mcp.mcp_dashboard",
        (
            "usage_status",
            "usage_dedupe_diagnostics",
            "usage_calls",
            "usage_call_detail",
            "usage_threads",
            "usage_report_pack",
            "usage_dashboard_recommendations",
        ),
    ),
    (
        "codex_usage_tracker.interfaces.mcp.mcp_local_operations",
        (
            "generate_usage_dashboard",
            "export_usage_csv",
            "init_usage_pricing_config",
            "update_usage_pricing_config",
            "init_usage_allowance_config",
        ),
    ),
    (
        "codex_usage_tracker.interfaces.mcp.mcp_allowance",
        (
            "usage_allowance_history",
            "usage_allowance_diagnostics",
            "usage_allowance_export",
            "usage_allowance_status",
            "usage_allowance_series",
            "usage_allowance_evidence",
            "usage_allowance_analysis",
            "usage_allowance_analysis_status",
        ),
    ),
    (
        "codex_usage_tracker.interfaces.mcp.mcp_compression",
        (
            "usage_compression_start",
            "usage_compression_status",
            "usage_compression_profile",
            "usage_compression_candidates",
            "usage_compression_candidate_detail",
            "usage_compression_simulate",
        ),
    ),
    (
        "codex_usage_tracker.interfaces.mcp.mcp_discovery",
        (
            "usage_query",
            "usage_recommendations",
            "usage_pricing_coverage",
            "usage_source_coverage",
            "usage_content_search",
            "usage_thread_trace",
            "usage_repetition_scan",
            "usage_command_loop_scan",
            "usage_file_churn_scan",
            "usage_repeated_file_rediscovery",
            "usage_shell_churn",
            "usage_large_low_output_calls",
        ),
    ),
    (
        "codex_usage_tracker.interfaces.mcp.mcp_investigations",
        (
            "usage_suggest_investigations",
            "usage_investigate",
            "usage_action_brief",
            "usage_test_hypotheses",
            "usage_context_bloat_scan",
            "usage_investigation_walk",
            "usage_local_evidence_export",
        ),
    ),
)


@lru_cache(maxsize=1)
def compatibility_handlers() -> dict[str, Callable[..., object]]:
    """Resolve every full-profile legacy handler without decorator registration."""
    handlers: dict[str, Callable[..., object]] = {}
    for module_name, names in _MODULE_TOOL_NAMES:
        module = import_module(module_name)
        for name in names:
            handler = getattr(module, name, None)
            if not callable(handler):
                raise LookupError(f"missing compatibility handler: {name}")
            handlers[name] = handler

    expected = set(COMPATIBILITY_TOOL_NAMES) | set(OVERLAPPING_CORE_TOOL_NAMES)
    if set(handlers) != expected:
        missing = sorted(expected - set(handlers))
        extra = sorted(set(handlers) - expected)
        raise LookupError(
            f"invalid compatibility handler catalog: missing={missing}, extra={extra}"
        )
    return handlers


def compatibility_handler(name: str) -> Callable[..., object]:
    """Return one exact legacy callable with its original signature."""
    try:
        return compatibility_handlers()[name]
    except KeyError as exc:
        raise LookupError(f"unknown compatibility handler: {name}") from exc
