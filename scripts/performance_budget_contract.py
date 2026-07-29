"""Versioned absolute-budget contract for the synthetic performance suite."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

PERFORMANCE_BUDGET_CONTRACT_VERSION = (
    "codex-usage-tracker.ci-performance-budgets.v1"
)

PERFORMANCE_BUDGETS_MS: Mapping[str, float] = MappingProxyType(
    {
        "active_writer_max_ms": 150.0,
        "active_writer_p95_ms": 50.0,
        "allowance_read_p95_ms": 550.0,
        "common_query_p95_ms": 500.0,
        "comparison_query_p95_ms": 1_000.0,
        "concentration_query_p95_ms": 1_000.0,
        "curated_agent_templates_p95_ms": 500.0,
        "daily_query_p95_ms": 500.0,
        "guidance_p95_ms": 5.0,
        "initial_writer_p95_ms": 2_000.0,
        "query_p95_ms": 500.0,
        "rollup_rebuild_elapsed_ms": 5_500.0,
        "status_p95_ms": 50.0,
        "timeline_first_page_p95_ms": 500.0,
        "tool_impact_p95_ms": 500.0,
        "top_thread_costs_p95_ms": 100.0,
        "top_threads_p95_ms": 1_000.0,
    }
)


def require_budget(metric: str, budget: float) -> None:
    """Reject missing, extra, or silently changed performance budgets."""

    expected = PERFORMANCE_BUDGETS_MS.get(metric)
    if expected is None:
        raise ValueError(f"unknown performance budget metric: {metric}")
    if budget != expected:
        raise ValueError(
            f"performance budget for {metric} must be {expected:.6f} ms"
        )
