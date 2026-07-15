"""Prior-only, reset-aware weekly allowance reconstruction and forecasts."""

from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any

MODEL_VERSION = "reset-aware-v2"


def build_weekly_estimation(
    cycles: list[dict[str, Any]], intervals: list[dict[str, Any]], *, now: Any
) -> dict[str, Any]:
    """Estimate weekly use without allowing an observation to train itself.

    Completed accepted cycles are the calibration unit: a dense cycle therefore
    has exactly one vote.  Every reconstructed interval sees only cycles that
    completed strictly before the interval ended.
    """
    as_of = now.isoformat()
    cycles = sorted(
        [c for c in cycles if c.get("window_kind") == "weekly" and _at(c.get("last_observed_at")) <= as_of],
        key=lambda c: (_at(c.get("last_observed_at")), str(c.get("cycle_id"))),
    )
    rows = sorted(
        [r for r in intervals if r.get("window_kind") == "weekly" and _at(r.get("end_observed_at")) <= as_of],
        key=lambda r: (_at(r.get("end_observed_at")), str(r.get("interval_id") or "")),
    )
    by_id = {str(c.get("cycle_id")): c for c in cycles}
    cycle_capacity = _cycle_capacities(rows, by_id)
    completed = [
        (str(c["cycle_id"]), _at(c.get("last_observed_at")), cycle_capacity[str(c["cycle_id"])])
        for c in cycles
        if _completed_quality(c) and str(c.get("cycle_id")) in cycle_capacity
    ]
    reconstructions, missing, eligible = _walk_forward(rows, completed)
    final_capacities = [value for _, _, value in completed]
    capacity = _weighted_median(final_capacities)
    capacity_available = len(final_capacities) >= 2 and capacity is not None
    validation = _validation(reconstructions)
    capacity_status = "validated" if capacity_available and validation["status"] == "validated" else "descriptive"
    current = _current_estimate(cycles, rows, capacity if capacity_available else None)
    scenarios = _pace_scenarios(rows, cycles, now, validation["residual_quantiles"])
    return {
        "model_version": MODEL_VERSION,
        "window_kind": "weekly",
        "capacity": {
            "status": capacity_status,
            "credits_per_percent": _round(capacity),
            "total_ratio_credits_per_percent": _round(_total_ratio(rows, completed)),
            "robust_median_credits_per_percent": _round(median(final_capacities)) if final_capacities else None,
            "iqr_credits_per_percent": _round(_iqr(final_capacities)),
            "completed_cycle_count": len(final_capacities),
            "eligible_interval_count": eligible,
            "price_coverage": _round((eligible - missing) / eligible) if eligible else 0.0,
            "unexplained_movement_share": _round(_unexplained_share(reconstructions)),
            "prior_only_errors": _error_summary(reconstructions),
            "cycle_weight_cap": 1.0,
        },
        "coverage_gaps": {"missing_pricing_interval_count": missing, "eligible_interval_count": eligible},
        "reconstructions": reconstructions,
        "weekly_estimate": current,
        "forecast": _forecast(current, capacity_status, validation),
        "validation": validation,
        "pace_scenarios": scenarios,
    }


def _walk_forward(rows: list[dict[str, Any]], completed: list[tuple[str, str, float]]) -> tuple[list[dict[str, Any]], int, int]:
    output: list[dict[str, Any]] = []
    missing = eligible = 0
    for row in rows:
        if not _eligible(row):
            continue
        eligible += 1
        credits, coverage = _number(row.get("estimated_credits")), _number(row.get("price_coverage"))
        if credits is None or credits <= 0 or coverage is None or coverage <= 0:
            missing += 1
            continue
        ended, cycle_id = _at(row.get("end_observed_at")), str(row.get("cycle_id"))
        prior = [value for prior_id, finished, value in completed if prior_id != cycle_id and finished < ended]
        cap = _weighted_median(prior)
        start, end = _number(row.get("start_used_percent")), _number(row.get("end_used_percent"))
        observed_delta = end - start if start is not None and end is not None else None
        explained = credits / cap if cap else None
        output.append({
            "cycle_id": cycle_id, "observed_at": row.get("end_observed_at"),
            "prior_capacity_credits_per_percent": _round(cap),
            "estimated_used_percent": _round(start + explained) if start is not None and explained is not None else None,
            "observed_delta": _round(observed_delta), "predicted_delta": _round(explained),
            "anchor_correction": _round(observed_delta - explained) if observed_delta is not None and explained is not None else None,
        })
    return output, missing, eligible


def _validation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [r for r in rows if r.get("anchor_correction") is not None]
    # A genuine later holdout; its residuals never define its own bands.
    holdout_n = max(1, len(evaluated) // 3) if evaluated else 0
    training, holdout = evaluated[:-holdout_n] if holdout_n else [], evaluated[-holdout_n:] if holdout_n else []
    residuals = [_number(r["anchor_correction"]) for r in training]
    quantiles = {"p10": _quantile(residuals, .10), "p50": _quantile(residuals, .50), "p90": _quantile(residuals, .90)}
    coverage = {str(level): _coverage(holdout, residuals, level) for level in (50, 80, 95)}
    errors = [abs(_number(r["anchor_correction"]) or 0) for r in holdout]
    baselines = _baselines(evaluated, len(training))
    mae = sum(errors) / len(errors) if errors else None
    beats = bool(mae is not None and all(item["mean_absolute_error"] is not None and mae < item["mean_absolute_error"] for item in baselines.values()))
    adequate = all((coverage[str(level)] or 0) >= .5 for level in (50, 80, 95))
    validated = len(training) >= 3 and len(holdout) >= 1 and beats and adequate
    return {
        "status": "validated" if validated else "descriptive", "sample_size": len(evaluated),
        "evaluation_horizon": "time_ordered_holdout", "calibration_window": "strictly_earlier_completed_cycles",
        "median_absolute_error": _round(median(errors)) if errors else None, "mean_absolute_error": _round(mae),
        "rmse": _round((sum(e * e for e in errors) / len(errors)) ** .5) if errors else None,
        "residual_quantiles": quantiles, "interval_coverage": coverage,
        "segmented_errors": {"weekly": {"mean_absolute_error": _round(mae), "sample_size": len(errors)}},
        "baselines": baselines,
        "holdout": {"sample_size": len(holdout), "residual_quantiles": quantiles, "interval_coverage": coverage},
    }


def _baselines(rows: list[dict[str, Any]], start: int) -> dict[str, dict[str, float | int | None]]:
    values: dict[str, list[float]] = {key: [] for key in ("unchanged_counter", "previous_interval", "recent_observed_pace", "previous_cycle_pace")}
    for index in range(start, len(rows)):
        target, prior = rows[index], rows[:index]
        actual = _number(target.get("observed_delta"))
        if actual is None or not prior:
            continue
        deltas = [_number(r.get("observed_delta")) for r in prior if _number(r.get("observed_delta")) is not None]
        previous = _number(prior[-1].get("observed_delta"))
        prior_cycle = [r for r in prior if r["cycle_id"] != target["cycle_id"]]
        cycle_delta = _number(prior_cycle[-1].get("observed_delta")) if prior_cycle else None
        forecasts = {"unchanged_counter": 0.0, "previous_interval": previous,
                     "recent_observed_pace": median(deltas) if deltas else None,
                     "previous_cycle_pace": cycle_delta}
        for key, prediction in forecasts.items():
            if prediction is not None:
                values[key].append(abs(actual - prediction))
    return {key: {"mean_absolute_error": _round(sum(v) / len(v)) if v else None, "sample_size": len(v)} for key, v in values.items()}


def _current_estimate(cycles: list[dict[str, Any]], rows: list[dict[str, Any]], capacity: float | None) -> dict[str, Any]:
    accepted = [c for c in cycles if _quality(c)]
    if capacity is None or not accepted:
        return {"used_percent": None, "clipped": False, "reason": "insufficient_prior_capacity"}
    latest = max(accepted, key=lambda c: _at(c.get("last_observed_at")))
    at, used, cycle_id = _at(latest.get("last_observed_at")), _number(latest.get("latest_used_percent")), str(latest.get("cycle_id"))
    post_all = [
        r
        for r in rows
        if str(r.get("cycle_id")) == cycle_id
        and _at(r.get("end_observed_at")) > at
        and r.get("point_kind") == "positive"
    ]
    post = [
        r
        for r in post_all
        if _eligible(r)
        and (_number(r.get("price_coverage")) or 0) > 0
        and _number(r.get("estimated_credits")) is not None
    ]
    if used is None or len(post) != len(post_all) or any(
        (_number(r.get("estimated_credits")) or 0) <= 0 for r in post
    ):
        return {"used_percent": None, "clipped": False, "reason": "missing_post_observation_coverage"}
    credits = sum(_number(r.get("estimated_credits")) or 0 for r in post)
    raw = used + credits / capacity
    clipped = min(100.0, max(0.0, raw))
    return {"used_percent": _round(clipped), "clipped": clipped != raw, "reason": None,
            "observed_at": latest.get("last_observed_at"), "post_observation_credits": _round(credits)}


def _forecast(estimate: dict[str, Any], status: str, validation: dict[str, Any]) -> dict[str, Any]:
    if status != "validated" or estimate.get("used_percent") is None:
        return {"used_percent": None, "reason": "insufficient_prior_cycle_evidence", "quantiles": None}
    center, q = float(estimate["used_percent"]), validation["residual_quantiles"]
    return {"used_percent": center, "reason": None, "sample_size": validation["holdout"]["sample_size"],
            "quantiles": {key: _round(min(100, max(0, center + q[key]))) for key in q}}


def _pace_scenarios(rows: list[dict[str, Any]], cycles: list[dict[str, Any]], now: Any, residuals: dict[str, float]) -> dict[str, Any]:
    if not rows:
        return {"status": "observed_only", "reason": "insufficient_recent_pace_samples", "if_current_pace_continues": None, "sample_count": 0}
    latest_id = max(cycles, key=lambda c: _at(c.get("last_observed_at"))).get("cycle_id") if cycles else None
    groups = {"recent_6h": [r for r in rows if _age(r, now) <= 6], "trailing_24h": [r for r in rows if _age(r, now) <= 24], "current_cycle": [r for r in rows if r.get("cycle_id") == latest_id], "comparable_prior_cycle": [r for r in rows if r.get("cycle_id") != latest_id]}
    windows = {name: _median_delta(items) for name, items in groups.items()}
    values = [v for v in windows.values() if v is not None]
    if len(values) < 4:
        return {"status": "observed_only", "reason": "insufficient_recent_pace_samples", "if_current_pace_continues": None, "contributing_windows": windows, "sample_count": len(values)}
    center, spread = median(values), [v - median(values) for v in values]
    return {"status": "conditional", "reason": None, "if_current_pace_continues": _round(center), "contributing_windows": windows, "sample_count": len(values), "low": _round(center + _quantile(spread, .10) + residuals["p10"]), "high": _round(center + _quantile(spread, .90) + residuals["p90"])}


def _cycle_capacities(rows: list[dict[str, Any]], cycles: dict[str, dict[str, Any]]) -> dict[str, float]:
    result = {}
    for cycle_id, cycle in cycles.items():
        if not _completed_quality(cycle):
            continue
        selected = [r for r in rows if str(r.get("cycle_id")) == cycle_id and _eligible(r) and (_number(r.get("price_coverage")) or 0) > 0]
        credits, delta = sum(_number(r.get("estimated_credits")) or 0 for r in selected), sum(max(0, _number(r.get("visible_percent_delta")) or 0) for r in selected)
        if credits > 0 and delta > 0:
            result[cycle_id] = credits / delta
    return result


def _total_ratio(rows: list[dict[str, Any]], completed: list[tuple[str, str, float]]) -> float | None:
    ids = {cycle_id for cycle_id, _, _ in completed}
    selected = [r for r in rows if str(r.get("cycle_id")) in ids and _eligible(r) and (_number(r.get("price_coverage")) or 0) > 0]
    credits, delta = sum(_number(r.get("estimated_credits")) or 0 for r in selected), sum(max(0, _number(r.get("visible_percent_delta")) or 0) for r in selected)
    return credits / delta if delta else None


def _quality(row: dict[str, Any]) -> bool: return row.get("quality_grade") in {"high", "medium"} and row.get("cycle_state") == "accepted"
def _completed_quality(row: dict[str, Any]) -> bool: return _quality(row) and row.get("status") == "completed"
def _eligible(row: dict[str, Any]) -> bool: return bool(row.get("eligible_for_calibration")) and row.get("point_kind") == "positive"
def _number(value: Any) -> float | None: return float(value) if isinstance(value, int | float) else None
def _round(value: float | None) -> float | None: return round(value, 6) if value is not None else None
def _at(value: Any) -> str: return str(value or "")
def _weighted_median(values: list[float]) -> float | None: return median(values) if values else None
def _median_delta(rows: list[dict[str, Any]]) -> float | None:
    values = [_number(r.get("visible_percent_delta")) for r in rows]
    return median([v for v in values if v is not None]) if any(v is not None for v in values) else None
def _iqr(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    ordered = sorted(values)
    return median(ordered[len(ordered) // 2 :]) - median(ordered[: (len(ordered) + 1) // 2])
def _quantile(values: list[float | None], p: float) -> float:
    ordered = sorted(v for v in values if v is not None)
    return ordered[min(len(ordered)-1, int(p*(len(ordered)-1)))] if ordered else 0.0
def _coverage(rows: list[dict[str, Any]], residuals: list[float | None], level: int) -> float | None:
    if not rows or not residuals:
        return None
    lower, upper = _quantile(residuals, (1-level/100)/2), _quantile(residuals, 1-(1-level/100)/2)
    return _round(sum(lower <= (_number(r["anchor_correction"]) or 0) <= upper for r in rows) / len(rows))
def _error_summary(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    values = [abs(_number(r["anchor_correction"]) or 0) for r in rows if r.get("anchor_correction") is not None]
    return {"sample_size": len(values), "median_absolute_error": _round(median(values)) if values else None}
def _unexplained_share(rows: list[dict[str, Any]]) -> float | None:
    numer = sum(abs(_number(r["anchor_correction"]) or 0) for r in rows if r.get("anchor_correction") is not None)
    denom = sum(abs(_number(r["observed_delta"]) or 0) for r in rows if r.get("anchor_correction") is not None)
    return numer / denom if denom else None
def _age(row: dict[str, Any], now: Any) -> float:
    return max(0, (now - datetime.fromisoformat(_at(row.get("end_observed_at")).replace("Z", "+00:00"))).total_seconds()/3600)
