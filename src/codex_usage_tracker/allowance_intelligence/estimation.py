"""Prior-only, reset-aware weekly allowance reconstruction and forecasts."""

from __future__ import annotations

from statistics import median
from typing import Any

MODEL_VERSION = "reset-aware-v2"


def build_weekly_estimation(
    cycles: list[dict[str, Any]], intervals: list[dict[str, Any]], *, now: Any
) -> dict[str, Any]:
    """Build deterministic estimates using evidence available before each interval.

    Cycles, rather than individual intervals, are the independence unit.  This
    deliberately returns descriptive results until two completed quality cycles
    exist; no current or future observation is allowed into an older estimate.
    """
    as_of = now.isoformat()
    weekly_cycles = sorted(
        (
            row
            for row in cycles
            if row.get("window_kind") == "weekly"
            and str(row.get("last_observed_at") or "") <= as_of
        ),
        key=lambda row: (str(row.get("last_observed_at") or ""), str(row.get("cycle_id") or "")),
    )
    cycle_by_id = {str(row.get("cycle_id")): row for row in weekly_cycles}
    weekly_intervals = sorted(
        (
            row
            for row in intervals
            if row.get("window_kind") == "weekly" and str(row.get("end_observed_at") or "") <= as_of
        ),
        key=lambda row: (str(row.get("end_observed_at") or ""), str(row.get("cycle_id") or "")),
    )
    capacity_by_cycle = _capacity_by_cycle(weekly_intervals, cycle_by_id)
    reconstructions: list[dict[str, Any]] = []
    completed: list[tuple[str, float]] = []
    missing_pricing = 0
    eligible_intervals = 0
    priced_intervals = 0

    for interval in weekly_intervals:
        if not _eligible(interval):
            continue
        eligible_intervals += 1
        credits = _number(interval.get("estimated_credits"))
        coverage = _number(interval.get("price_coverage"))
        if credits is None or coverage is None or coverage <= 0:
            missing_pricing += 1
            continue
        priced_intervals += 1
        cycle_id = str(interval.get("cycle_id"))
        prior = [value for prior_id, value in completed if prior_id != cycle_id]
        prior_capacity = _weighted_median(prior)
        start = _number(interval.get("start_used_percent"))
        end = _number(interval.get("end_used_percent"))
        observed_delta = (end - start) if start is not None and end is not None else None
        cumulative = _cumulative_credits(
            weekly_intervals, cycle_id, str(interval.get("end_observed_at") or "")
        )
        explained = credits / prior_capacity if prior_capacity and prior_capacity > 0 else None
        estimated = (
            start + explained * cumulative / credits
            if start is not None and explained is not None and credits > 0
            else None
        )
        reconstructions.append(
            {
                "cycle_id": cycle_id,
                "observed_at": interval.get("end_observed_at"),
                "prior_capacity_credits_per_percent": _round(prior_capacity),
                "estimated_used_percent": _round(estimated),
                "observed_delta": _round(observed_delta),
                "anchor_correction": _round(observed_delta - explained)
                if observed_delta is not None and explained is not None
                else None,
            }
        )
        cycle_capacity = capacity_by_cycle.get(cycle_id)
        if cycle_capacity is not None and cycle_id not in {item[0] for item in completed}:
            # A completed cycle can contribute once, after its last eligible interval.
            is_last = str(interval.get("end_observed_at") or "") == _last_interval_at(
                weekly_intervals, cycle_id
            )
            if is_last and _completed_quality_cycle(cycle_by_id.get(cycle_id, {})):
                completed.append((cycle_id, cycle_capacity))

    capacities = [value for _, value in completed]
    capacity = _weighted_median(capacities)
    completed_count = len(completed)
    preliminary_status = "validated" if completed_count >= 2 else "descriptive"
    coverage = priced_intervals / eligible_intervals if eligible_intervals else 0.0
    capacity_payload = {
        "status": preliminary_status,
        "credits_per_percent": _round(capacity),
        "total_ratio_credits_per_percent": _round(_total_ratio(capacity_by_cycle, completed)),
        "robust_median_credits_per_percent": _round(median(capacities)) if capacities else None,
        "iqr_credits_per_percent": _round(_iqr(capacities)),
        "completed_cycle_count": completed_count,
        "eligible_interval_count": eligible_intervals,
        "price_coverage": _round(coverage),
        "unexplained_movement_share": _round(_unexplained_share(reconstructions)),
        "prior_only_errors": _prior_errors(reconstructions),
        "cycle_weight_cap": 1.0,
    }
    current = reconstructions[-1] if reconstructions else None
    validation = _validation(reconstructions, preliminary_status)
    capacity_status = "validated" if validation["status"] == "validated" else "descriptive"
    capacity_payload["status"] = capacity_status
    weekly_estimate = _weekly_estimate(current, capacity_status)
    forecast = _forecast(weekly_estimate, capacity_status, completed_count, validation)
    return {
        "model_version": MODEL_VERSION,
        "window_kind": "weekly",
        "capacity": capacity_payload,
        "coverage_gaps": {
            "missing_pricing_interval_count": missing_pricing,
            "eligible_interval_count": eligible_intervals,
        },
        "reconstructions": reconstructions,
        "weekly_estimate": weekly_estimate,
        "forecast": forecast,
        "validation": validation,
        "pace_scenarios": _pace_scenarios(weekly_intervals, now),
    }


def _quality_cycle(row: dict[str, Any]) -> bool:
    return row.get("quality_grade") in {"high", "medium"} and row.get("cycle_state") == "accepted"


def _completed_quality_cycle(row: dict[str, Any]) -> bool:
    return _quality_cycle(row) and row.get("status") == "completed"


def _eligible(row: dict[str, Any]) -> bool:
    return bool(row.get("eligible_for_calibration")) and row.get("point_kind") == "positive"


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _weighted_median(values: list[float]) -> float | None:
    return median(values) if values else None


def _iqr(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    ordered = sorted(values)
    return median(ordered[len(ordered) // 2 :]) - median(ordered[: (len(ordered) + 1) // 2])


def _capacity_by_cycle(
    intervals: list[dict[str, Any]], cycles: dict[str, dict[str, Any]]
) -> dict[str, float]:
    result: dict[str, float] = {}
    for cycle_id, cycle in cycles.items():
        if not _quality_cycle(cycle):
            continue
        rows = [row for row in intervals if str(row.get("cycle_id")) == cycle_id and _eligible(row)]
        credits = sum(
            value
            for row in rows
            if (value := _number(row.get("estimated_credits"))) is not None
            and (_number(row.get("price_coverage")) or 0) > 0
        )
        delta = sum(max(0.0, _number(row.get("visible_percent_delta")) or 0.0) for row in rows)
        if credits > 0 and delta > 0:
            result[cycle_id] = credits / delta
    return result


def _cumulative_credits(intervals: list[dict[str, Any]], cycle_id: str, ended: str) -> float:
    return sum(
        _number(row.get("estimated_credits")) or 0.0
        for row in intervals
        if str(row.get("cycle_id")) == cycle_id and str(row.get("end_observed_at") or "") <= ended
    )


def _last_interval_at(intervals: list[dict[str, Any]], cycle_id: str) -> str:
    return max(
        (
            str(row.get("end_observed_at") or "")
            for row in intervals
            if str(row.get("cycle_id")) == cycle_id
        ),
        default="",
    )


def _total_ratio(by_cycle: dict[str, float], completed: list[tuple[str, float]]) -> float | None:
    # Capacities are already cycle totals; equal cycle weights cap dense cycles.
    values = [by_cycle[key] for key, _ in completed]
    return sum(values) / len(values) if values else None


def _unexplained_share(rows: list[dict[str, Any]]) -> float | None:
    corrections = [
        abs(_number(row.get("anchor_correction")) or 0.0)
        for row in rows
        if row.get("anchor_correction") is not None
    ]
    observed = [
        abs(_number(row.get("estimated_used_percent")) or 0.0)
        for row in rows
        if row.get("anchor_correction") is not None
    ]
    return sum(corrections) / sum(observed) if observed and sum(observed) else None


def _prior_errors(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    errors = [
        abs(_number(row.get("anchor_correction")) or 0.0)
        for row in rows
        if row.get("anchor_correction") is not None
    ]
    return {
        "sample_size": len(errors),
        "median_absolute_error": _round(median(errors)) if errors else None,
    }


def _weekly_estimate(row: dict[str, Any] | None, status: str) -> dict[str, Any]:
    if status != "validated" or row is None or row.get("estimated_used_percent") is None:
        return {"used_percent": None, "clipped": False, "reason": "insufficient_prior_capacity"}
    raw = float(row["estimated_used_percent"])
    clipped = min(100.0, max(0.0, raw))
    return {"used_percent": _round(clipped), "clipped": clipped != raw, "reason": None}


def _forecast(
    estimate: dict[str, Any], status: str, count: int, validation: dict[str, Any]
) -> dict[str, Any]:
    if status != "validated" or estimate["used_percent"] is None:
        return {
            "used_percent": None,
            "reason": "insufficient_prior_cycle_evidence",
            "quantiles": None,
        }
    residuals = validation["residual_quantiles"]
    center = float(estimate["used_percent"])
    return {
        "used_percent": estimate["used_percent"],
        "reason": None,
        "quantiles": {
            "p10": _round(min(100, max(0, center + residuals["p10"]))),
            "p50": _round(min(100, max(0, center + residuals["p50"]))),
            "p90": _round(min(100, max(0, center + residuals["p90"]))),
        },
        "sample_size": count,
    }


def _validation(rows: list[dict[str, Any]], status: str) -> dict[str, Any]:
    residuals = [
        _number(row.get("anchor_correction"))
        for row in rows
        if row.get("anchor_correction") is not None
    ]
    absolute = [abs(value) for value in residuals if value is not None]
    quantiles = {
        "p10": _quantile(residuals, 0.1),
        "p50": _quantile(residuals, 0.5),
        "p90": _quantile(residuals, 0.9),
    }
    coverage = {
        str(level): _round(
            sum(
                abs(value) <= _quantile([abs(item) for item in residuals], level / 100)
                for value in residuals
            )
            / len(residuals)
        )
        if residuals
        else None
        for level in (50, 80, 95)
    }
    mae = sum(absolute) / len(absolute) if absolute else None
    baseline_errors = {
        "unchanged_counter": [_number(row.get("observed_delta")) or 0.0 for row in rows],
        "previous_interval": [
            abs(
                (_number(row.get("observed_delta")) or 0.0)
                - (_number(rows[index - 1].get("observed_delta")) or 0.0)
            )
            for index, row in enumerate(rows)
            if index
        ],
        "recent_observed_pace": [
            abs(
                (_number(row.get("observed_delta")) or 0.0)
                - median([_number(item.get("observed_delta")) or 0.0 for item in rows[:index]])
            )
            for index, row in enumerate(rows)
            if index
        ],
        "previous_cycle_pace": [
            abs(
                (_number(row.get("observed_delta")) or 0.0)
                - (_number(rows[index - 1].get("observed_delta")) or 0.0)
            )
            for index, row in enumerate(rows)
            if index
        ],
    }
    baselines = {
        key: {
            "mean_absolute_error": _round(sum(values) / len(values)) if values else None,
            "sample_size": len(values),
        }
        for key, values in baseline_errors.items()
    }
    beats = mae is not None and all(
        item["mean_absolute_error"] is None or mae <= item["mean_absolute_error"]
        for item in baselines.values()
    )
    validated = (
        status == "validated" and len(residuals) >= 3 and beats and (coverage["80"] or 0) >= 0.5
    )
    return {
        "status": "validated" if validated else "descriptive",
        "sample_size": len(residuals),
        "evaluation_horizon": "walk_forward",
        "calibration_window": "prior_completed_cycles",
        "median_absolute_error": _round(median(absolute)) if absolute else None,
        "mean_absolute_error": _round(mae),
        "rmse": _round((sum(error * error for error in absolute) / len(absolute)) ** 0.5)
        if absolute
        else None,
        "residual_quantiles": quantiles,
        "interval_coverage": coverage,
        "segmented_errors": {
            "weekly": {"mean_absolute_error": _round(mae), "sample_size": len(absolute)}
        },
        "baselines": baselines,
    }


def _quantile(values: list[float | None], probability: float) -> float:
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int(probability * (len(ordered) - 1)))]


def _pace_scenarios(intervals: list[dict[str, Any]], now: Any) -> dict[str, Any]:
    def rate(rows: list[dict[str, Any]]) -> float | None:
        values = [_number(row.get("visible_percent_delta")) for row in rows]
        numeric = [value for value in values if value is not None]
        return median(numeric) if numeric else None

    recent6 = [row for row in intervals if _age_hours(row, now) <= 6]
    recent24 = [row for row in intervals if _age_hours(row, now) <= 24]
    current_id = str(intervals[-1].get("cycle_id")) if intervals else ""
    current = [row for row in intervals if str(row.get("cycle_id")) == current_id]
    prior = [row for row in intervals if str(row.get("cycle_id")) != current_id]
    windows = {
        "recent_6h": rate(recent6),
        "trailing_24h": rate(recent24),
        "current_cycle": rate(current),
        "comparable_prior_cycle": rate(prior),
    }
    values = [value for value in windows.values() if value is not None]
    if len(values) < 4:
        return {
            "status": "observed_only",
            "reason": "insufficient_recent_pace_samples",
            "if_current_pace_continues": None,
            "contributing_windows": [key for key, value in windows.items() if value is not None],
            "sample_count": len(values),
        }
    center = median(values)
    return {
        "status": "conditional",
        "reason": None,
        "if_current_pace_continues": _round(center),
        "low": _round(_quantile(values, 0.1)),
        "high": _round(_quantile(values, 0.9)),
        "contributing_windows": windows,
        "sample_count": len(values),
    }


def _age_hours(row: dict[str, Any], now: Any) -> float:
    from datetime import datetime

    return max(
        0,
        (
            now - datetime.fromisoformat(str(row.get("end_observed_at")).replace("Z", "+00:00"))
        ).total_seconds()
        / 3600,
    )
