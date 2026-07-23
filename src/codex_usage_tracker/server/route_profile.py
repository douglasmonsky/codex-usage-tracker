"""Types and constructor for dashboard route execution metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RouteMethod = Literal["GET", "POST"]
RouteWorkload = Literal["interactive", "bounded_report", "heavy_analysis"]
RouteExecution = Literal["synchronous", "async_start", "poll"]
RouteExposure = Literal["stable", "compatibility", "developer"]


@dataclass(frozen=True)
class DashboardRouteProfile:
    """Describe the execution and persistence behavior of one API route."""

    method: RouteMethod
    path: str
    handler: str
    owner: str
    workload: RouteWorkload
    scope_behavior: str
    result_bound: str
    cache_behavior: str
    may_scan_all_history: bool
    execution: RouteExecution
    exposure: RouteExposure = "compatibility"
    input_limit_bytes: int | None = None
    output_limit_bytes: int | None = None


def profile(
    method: RouteMethod,
    path: str,
    handler: str,
    owner: str,
    workload: RouteWorkload,
    scope_behavior: str,
    result_bound: str,
    cache_behavior: str,
    *,
    may_scan_all_history: bool = False,
    execution: RouteExecution = "synchronous",
    exposure: RouteExposure = "compatibility",
    input_limit_bytes: int | None = None,
    output_limit_bytes: int | None = None,
) -> DashboardRouteProfile:
    """Build one immutable route profile."""
    return DashboardRouteProfile(
        method=method,
        path=path,
        handler=handler,
        owner=owner,
        workload=workload,
        scope_behavior=scope_behavior,
        result_bound=result_bound,
        cache_behavior=cache_behavior,
        may_scan_all_history=may_scan_all_history,
        execution=execution,
        exposure=exposure,
        input_limit_bytes=input_limit_bytes,
        output_limit_bytes=output_limit_bytes,
    )
