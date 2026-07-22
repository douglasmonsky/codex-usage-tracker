"""Declarative MCP tool catalog and validation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import cache, lru_cache

from codex_usage_tracker.interfaces.mcp.core_tools import (
    usage_allowance,
    usage_analyze,
    usage_evidence,
    usage_job_status,
    usage_query,
    usage_refresh,
    usage_status,
)
from codex_usage_tracker.interfaces.mcp.models import McpProfile, ToolDataClass, ToolSpec

PROFILE_ORDER: dict[McpProfile, int] = {"core": 0, "full": 1, "developer": 2}

CORE_TOOL_NAMES = (
    "usage_status",
    "usage_refresh",
    "usage_analyze",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
)

_FULL_TOOL_NAMES = (
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

_DEVELOPER_TOOL_NAMES = (
    "usage_dogfood_start",
    "usage_dogfood_status",
    "usage_dogfood_result",
    "usage_visualization_suggest",
    "usage_visualization_render",
)


class ToolCatalogError(ValueError):
    """Raised when tool metadata cannot form a safe ordered catalog."""


class CoreToolNotImplemented(NotImplementedError):
    """Compatibility exception retained for callers importing the old placeholder type."""


_CORE_HANDLERS: dict[str, Callable[..., object]] = {
    "usage_status": usage_status,
    "usage_refresh": usage_refresh,
    "usage_analyze": usage_analyze,
    "usage_query": usage_query,
    "usage_evidence": usage_evidence,
    "usage_allowance": usage_allowance,
    "usage_job_status": usage_job_status,
}


def _release_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as exc:
        raise ToolCatalogError(f"invalid release: {value}") from exc


def validate_tool_specs(specs: Iterable[ToolSpec]) -> None:
    """Validate uniqueness, profile ordering, and deprecation metadata."""
    names: set[str] = set()
    previous_rank = -1
    for spec in specs:
        if spec.name in names:
            raise ToolCatalogError(f"duplicate tool name: {spec.name}")
        names.add(spec.name)

        rank = PROFILE_ORDER.get(spec.minimum_profile)
        if rank is None or rank < previous_rank:
            raise ToolCatalogError(f"invalid minimum-profile order: {spec.name}")
        previous_rank = rank

        if spec.lifecycle != "deprecated":
            continue
        if not spec.replacement:
            raise ToolCatalogError(f"missing replacement: {spec.name}")
        if not spec.deprecated_since or not spec.remove_after:
            raise ToolCatalogError(f"missing deprecation release: {spec.name}")
        if _release_tuple(spec.remove_after) < _release_tuple(spec.deprecated_since):
            raise ToolCatalogError(f"removal release precedes deprecation release: {spec.name}")


def _data_class(name: str) -> ToolDataClass:
    if name == "usage_call_context":
        return "raw_context"
    if any(
        marker in name
        for marker in (
            "content",
            "thread_trace",
            "repetition",
            "command_loop",
            "file_churn",
            "rediscovery",
            "shell_churn",
            "investigat",
            "context_bloat",
            "local_evidence",
            "compression",
        )
    ):
        return "local_index"
    if any(
        marker in name for marker in ("refresh", "doctor", "generate", "export", "init_", "update_")
    ):
        return "administrative"
    return "aggregate"


def _replacement(name: str) -> str:
    if "allowance" in name:
        return "usage_allowance"
    if "refresh" in name:
        return "usage_refresh"
    if name.endswith("status") or name == "usage_doctor":
        return "usage_status"
    if any(marker in name for marker in ("detail", "context", "evidence")):
        return "usage_evidence"
    if any(
        marker in name
        for marker in (
            "recommend",
            "investigat",
            "compression",
            "dogfood",
            "hypoth",
            "scan",
            "brief",
        )
    ):
        return "usage_analyze"
    return "usage_query"


@lru_cache(maxsize=1)
def _legacy_handlers() -> dict[str, Callable[..., object]]:
    from codex_usage_tracker.cli import (
        mcp_allowance,
        mcp_compression,
        mcp_dashboard,
        mcp_discovery,
        mcp_investigations,
        mcp_server,
        mcp_subagents,
        mcp_visualization,
    )

    modules = (
        mcp_server,
        mcp_allowance,
        mcp_compression,
        mcp_dashboard,
        mcp_discovery,
        mcp_investigations,
        mcp_subagents,
        mcp_visualization,
    )
    handlers: dict[str, Callable[..., object]] = {}
    for name in (*_FULL_TOOL_NAMES, *_DEVELOPER_TOOL_NAMES, "usage_status", "usage_query"):
        handler = next((getattr(module, name) for module in modules if hasattr(module, name)), None)
        if not callable(handler):
            raise ToolCatalogError(f"missing existing handler: {name}")
        handlers[name] = handler
    return handlers


@cache
def _lazy_legacy_handler(name: str) -> Callable[..., object]:
    """Return a callable proxy without importing legacy handler modules."""

    def invoke(*args: object, **kwargs: object) -> object:
        return _legacy_handlers()[name](*args, **kwargs)

    invoke.__name__ = name
    return invoke


@lru_cache(maxsize=1)
def tool_specs() -> tuple[ToolSpec, ...]:
    """Return the validated immutable tool catalog in registration order."""
    specs = (
        tuple(
            ToolSpec(
                name=name,
                minimum_profile="core",
                maturity="stable",
                lifecycle="active",
                data_class=(
                    "administrative" if name in {"usage_status", "usage_refresh"} else "aggregate"
                ),
                handler=_CORE_HANDLERS[name],
            )
            for name in CORE_TOOL_NAMES
        )
        + tuple(
            ToolSpec(
                name=name,
                minimum_profile="full",
                maturity="beta",
                lifecycle="deprecated",
                data_class=_data_class(name),
                handler=_lazy_legacy_handler(name),
                replacement=_replacement(name),
                deprecated_since="0.22.0",
                remove_after="0.25.0",
            )
            for name in _FULL_TOOL_NAMES
        )
        + tuple(
            ToolSpec(
                name=name,
                minimum_profile="developer",
                maturity="experimental",
                lifecycle="active",
                data_class=_data_class(name),
                handler=_lazy_legacy_handler(name),
            )
            for name in _DEVELOPER_TOOL_NAMES
        )
    )
    validate_tool_specs(specs)
    return specs


def handler_for_profile(spec: ToolSpec, profile: McpProfile) -> Callable[..., object]:
    """Preserve existing overlapping handlers outside the core-only server."""
    if profile != "core" and (
        spec.minimum_profile != "core" or spec.name in {"usage_status", "usage_query"}
    ):
        return _legacy_handlers()[spec.name]
    return spec.handler
