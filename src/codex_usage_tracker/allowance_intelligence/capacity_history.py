"""Aggregate weekly capacity history over completed allowance cycles."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

_GRANULARITIES = {"cycle", "week", "month"}


def build_capacity_history(
    cycles: list[dict[str, Any]],
    *,
    granularity: str,
    trailing_window: int = 8,
    regime_boundaries: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build robust chronological capacity summaries with one vote per cycle."""
    if granularity not in _GRANULARITIES:
        raise ValueError("granularity must be cycle, week, or month")
    if trailing_window < 4:
        raise ValueError("trailing_window must be at least 4")
    eligible = sorted(
        (_normalized_cycle(row) for row in cycles if _eligible_cycle(row)),
        key=lambda row: (str(row["completed_at"]), str(row["cycle_id"])),
    )
    points = _rolling_points(eligible, trailing_window=trailing_window)
    domain = _tukey_domain(points)
    return {
        "status": "ready" if points else "insufficient_completed_cycles",
        "unit": "credits_per_percent",
        "points": points,
        "buckets": list(points) if granularity == "cycle" else [],
        "robust_domain": domain,
        "clipped_point_count": _clipped_count(points, domain),
        "eligible_cycle_count": len(points),
        "plan_types": sorted({str(point["plan_type"]) for point in points}),
        "trailing_window_cycles": trailing_window,
        "regime_boundary_count": len(regime_boundaries),
    }


def load_capacity_cycles(
    connection: sqlite3.Connection,
    *,
    source_revision: str,
    archive_scope: str,
    window_kind: str,
    cohort_key: str,
    start_at: str | None = None,
    end_at: str | None = None,
) -> list[dict[str, Any]]:
    """Return one aggregate capacity ratio per allowance cycle."""
    if archive_scope not in {"active", "all"}:
        raise ValueError("archive_scope must be active or all")
    cycle_conditions = [
        "source_revision = ?",
        "window_kind = ?",
        "cohort_key = ?",
    ]
    cycle_parameters: list[object] = [source_revision, window_kind, cohort_key]
    if archive_scope == "active":
        cycle_conditions.append("is_archived = 0")
    if start_at is not None:
        cycle_conditions.append("last_observed_at >= ?")
        cycle_parameters.append(start_at)
    if end_at is not None:
        cycle_conditions.append("last_observed_at <= ?")
        cycle_parameters.append(end_at)
    cycles = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM allowance_cycles WHERE "
            + " AND ".join(cycle_conditions)
            + " ORDER BY last_observed_at, cycle_id",
            cycle_parameters,
        )
    ]
    interval_conditions = [
        "source_revision = ?",
        "window_kind = ?",
        "cohort_key = ?",
        "eligible_for_change_detection = 1",
        "point_kind = 'positive'",
    ]
    interval_parameters: list[object] = [source_revision, window_kind, cohort_key]
    if archive_scope == "active":
        interval_conditions.append("is_archived = 0")
    ratios = {
        str(row["cycle_id"]): float(row["credits"]) / float(row["movement"])
        for row in connection.execute(
            "SELECT cycle_id, SUM(estimated_credits) AS credits, "
            "SUM(visible_percent_delta) AS movement FROM allowance_intervals WHERE "
            + " AND ".join(interval_conditions)
            + " GROUP BY cycle_id HAVING credits > 0 AND movement > 0",
            interval_parameters,
        )
    }
    for cycle in cycles:
        cycle["credits_per_percent"] = ratios.get(str(cycle["cycle_id"]))
    return cycles


def _eligible_cycle(row: Mapping[str, Any]) -> bool:
    value = row.get("credits_per_percent")
    coverage = row.get("price_coverage")
    return bool(
        row.get("status") == "completed"
        and row.get("quality_grade") in {"high", "medium"}
        and isinstance(coverage, int | float)
        and float(coverage) >= 0.95
        and int(row.get("conflict_count") or 0) == 0
        and isinstance(value, int | float)
        and math.isfinite(float(value))
        and float(value) > 0
    )


def _normalized_cycle(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "cycle_id": str(row["cycle_id"]),
        "completed_at": str(row.get("last_observed_at") or ""),
        "credits_per_percent": round(float(row["credits_per_percent"]), 6),
        "quality_grade": str(row.get("quality_grade") or "unknown"),
        "price_coverage": round(float(row.get("price_coverage") or 0), 6),
        "plan_type": str(row.get("plan_type") or "unknown"),
        "regime_id": None,
    }


def _rolling_points(
    cycles: list[dict[str, Any]], *, trailing_window: int
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    plan_history: dict[str, list[dict[str, Any]]] = {}
    for cycle in cycles:
        plan_cycles = plan_history.setdefault(str(cycle["plan_type"]), [])
        plan_cycles.append(cycle)
        start = max(0, len(plan_cycles) - trailing_window)
        values = [
            float(row["credits_per_percent"]) for row in plan_cycles[start:]
        ]
        enough = len(values) >= 4
        points.append(
            {
                **cycle,
                "rolling_median": round(median(values), 6) if enough else None,
                "rolling_q1": round(_quantile(values, 0.25), 6) if enough else None,
                "rolling_q3": round(_quantile(values, 0.75), 6) if enough else None,
            }
        )
    return points


def _tukey_domain(points: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["credits_per_percent"]) for row in points]
    if not values:
        return {"mode": "tukey_1_5_iqr", "min": None, "max": None}
    q1, q3 = _quantile(values, 0.25), _quantile(values, 0.75)
    spread = q3 - q1
    return {
        "mode": "tukey_1_5_iqr",
        "min": round(max(0.0, q1 - (1.5 * spread)), 6),
        "max": round(q3 + (1.5 * spread), 6),
    }


def _clipped_count(points: list[dict[str, Any]], domain: Mapping[str, Any]) -> int:
    lower, upper = domain.get("min"), domain.get("max")
    if lower is None or upper is None:
        return 0
    return sum(
        not float(lower) <= float(row["credits_per_percent"]) <= float(upper)
        for row in points
    )


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires at least one value")
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)
