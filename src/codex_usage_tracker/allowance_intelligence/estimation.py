"""Prior-only, reset-aware weekly allowance reconstruction and forecasts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from statistics import median
from typing import Any

MODEL_VERSION = "reset-aware-v2"


def build_weekly_estimation(
    cycles: list[dict[str, Any]], intervals: list[dict[str, Any]], *, now: Any
) -> dict[str, Any]:
    """Estimate weekly use without allowing an observation to train itself.

    Completed quality-approved cycles are the calibration unit: a dense cycle therefore
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
        (
            str(c["cycle_id"]),
            _at(c.get("last_observed_at")),
            cycle_capacity[str(c["cycle_id"])][0],
            cycle_capacity[str(c["cycle_id"])][1],
        )
        for c in cycles
        if _completed_quality(c) and str(c.get("cycle_id")) in cycle_capacity
    ]
    reconstructions, missing, eligible = _walk_forward(rows, completed)
    final_capacities = [value for _, _, value, _ in completed]
    capacity = _weighted_median(
        [
            (value, _recency_weight(base_weight, finished, now))
            for _, finished, value, base_weight in completed
        ]
    )
    capacity_available = len(final_capacities) >= 2 and capacity is not None
    validation = _validation(reconstructions)
    capacity_status = "validated" if capacity_available and validation["status"] == "validated" else "descriptive"
    current = _current_estimate(cycles, rows, capacity if capacity_available else None)
    scenarios = _pace_scenarios(rows, cycles, now, validation["pace_residual_quantiles"])
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


def _walk_forward(
    rows: list[dict[str, Any]], completed: list[tuple[str, str, float, float]]
) -> tuple[list[dict[str, Any]], int, int]:
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
        prior = [
            (value, _recency_weight(base_weight, finished, ended))
            for prior_id, finished, value, base_weight in completed
            if prior_id != cycle_id and finished < ended
        ]
        cap = _weighted_median(prior)
        start, end = _number(row.get("start_used_percent")), _number(row.get("end_used_percent"))
        observed_delta = end - start if start is not None and end is not None else None
        explained = credits / cap if cap else None
        # Only interpolate inside an interval when the producer supplied a
        # canonical cumulative-credit sample.  Endpoint-only evidence must not
        # invent a timing path.
        cumulative = _number(row.get("cumulative_credits"))
        estimated = (
            start + explained * cumulative / credits
            if start is not None and explained is not None and cumulative is not None
            else None
        )
        output.append({
            "cycle_id": cycle_id, "observed_at": row.get("end_observed_at"),
            "interval_hours": _interval_hours(row),
            "prior_capacity_credits_per_percent": _round(cap),
            "estimated_used_percent": _round(estimated),
            "representation": "interpolated" if estimated is not None else "endpoint_observed_only",
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
    pace_residuals = [
        correction / hours
        for row in training
        if (correction := _number(row.get("anchor_correction"))) is not None
        and (hours := _number(row.get("interval_hours"))) is not None
        and hours > 0
    ]
    pace_quantiles = {
        "p10": _quantile(pace_residuals, .10),
        "p50": _quantile(pace_residuals, .50),
        "p90": _quantile(pace_residuals, .90),
    }
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
        "pace_residual_quantiles": pace_quantiles,
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
        deltas = [
            value
            for row in prior
            if (value := _number(row.get("observed_delta"))) is not None
        ]
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
    quality_cycles = [c for c in cycles if _quality(c)]
    if capacity is None or not quality_cycles:
        return {"used_percent": None, "clipped": False, "reason": "insufficient_prior_capacity"}
    latest = max(quality_cycles, key=lambda c: _at(c.get("last_observed_at")))
    at, used, cycle_id = _at(latest.get("last_observed_at")), _number(latest.get("latest_used_percent")), str(latest.get("cycle_id"))
    post_all = [
        r
        for r in rows
        if str(r.get("cycle_id")) == cycle_id
        and _at(r.get("end_observed_at")) > at
    ]
    if any(r.get("point_kind") != "positive" or r.get("censor_reason") for r in post_all):
        return {"used_percent": None, "clipped": False, "reason": "post_observation_boundary"}
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


def _pace_scenarios(
    rows: list[dict[str, Any]],
    cycles: list[dict[str, Any]],
    now: Any,
    residuals: dict[str, float],
) -> dict[str, Any]:
    if not rows:
        return {"status": "observed_only", "reason": "insufficient_recent_pace_samples", "if_current_pace_continues": None, "sample_count": 0, "unit": "percent_per_hour"}
    latest = max(cycles, key=lambda c: _at(c.get("last_observed_at"))) if cycles else None
    latest_id = latest.get("cycle_id") if latest else None
    prior = [c for c in cycles if c.get("cycle_id") != latest_id and _completed_quality(c)]
    comparable = max(prior, key=lambda c: _at(c.get("last_observed_at"))) if prior else None
    pace_rows = [
        row
        for row in rows
        if row.get("point_kind") == "positive"
        and not row.get("censor_reason")
        and _number(row.get("visible_percent_delta")) is not None
    ]
    groups = {
        "recent_6h": [r for r in pace_rows if _age(r, now) <= 6],
        "trailing_24h": [r for r in pace_rows if _age(r, now) <= 24],
        "current_cycle": [r for r in pace_rows if r.get("cycle_id") == latest_id],
        "comparable_prior_cycle": [
            r
            for r in pace_rows
            if comparable and r.get("cycle_id") == comparable.get("cycle_id")
        ],
    }
    windows = {
        name: {
            **_pace_window(items),
            **(
                {"cycle_id": str(comparable.get("cycle_id"))}
                if name == "comparable_prior_cycle" and comparable
                else {}
            ),
        }
        for name, items in groups.items()
    }
    values = [float(item["value"]) for item in windows.values() if item["value"] is not None]
    sample_count = sum(_interval_hours(row) is not None for row in pace_rows)
    if len(values) < 4:
        return {"status": "observed_only", "reason": "insufficient_recent_pace_samples", "if_current_pace_continues": None, "contributing_windows": windows, "sample_count": sample_count, "unit": "percent_per_hour"}
    center, spread = median(values), [v - median(values) for v in values]
    return {"status": "conditional", "reason": None, "if_current_pace_continues": _round(center), "contributing_windows": windows, "sample_count": sample_count, "unit": "percent_per_hour", "low": _round(center + _quantile(spread, .10) + residuals["p10"]), "high": _round(center + _quantile(spread, .90) + residuals["p90"])}


def _cycle_capacities(
    rows: list[dict[str, Any]], cycles: dict[str, dict[str, Any]]
) -> dict[str, tuple[float, float]]:
    result = {}
    for cycle_id, cycle in cycles.items():
        if not _completed_quality(cycle):
            continue
        selected = [r for r in rows if str(r.get("cycle_id")) == cycle_id and _eligible(r) and (_number(r.get("price_coverage")) or 0) > 0]
        credits, delta = sum(_number(r.get("estimated_credits")) or 0 for r in selected), sum(max(0, _number(r.get("visible_percent_delta")) or 0) for r in selected)
        if credits > 0 and delta > 0:
            support = sum(
                (_number(row.get("price_coverage")) or 0) * _interval_quality(row)
                for row in selected
            ) / len(selected)
            quality = 1.0 if cycle.get("quality_grade") == "high" else 0.6
            result[cycle_id] = (credits / delta, min(1.0, quality * support))
    return result


def _total_ratio(
    rows: list[dict[str, Any]], completed: list[tuple[str, str, float, float]]
) -> float | None:
    ids = {cycle_id for cycle_id, _, _, _ in completed}
    selected = [r for r in rows if str(r.get("cycle_id")) in ids and _eligible(r) and (_number(r.get("price_coverage")) or 0) > 0]
    credits, delta = sum(_number(r.get("estimated_credits")) or 0 for r in selected), sum(max(0, _number(r.get("visible_percent_delta")) or 0) for r in selected)
    return credits / delta if delta else None


def _quality(row: dict[str, Any]) -> bool:
    return row.get("quality_grade") in {"high", "medium"} and row.get("status") in {"open", "completed"}
def _completed_quality(row: dict[str, Any]) -> bool:
    return _quality(row) and row.get("status") == "completed"
def _eligible(row: dict[str, Any]) -> bool: return bool(row.get("eligible_for_calibration")) and row.get("point_kind") == "positive"
def _interval_quality(row: dict[str, Any]) -> float:
    confidence = _number(row.get("confidence"))
    return min(1.0, max(0.0, confidence)) if confidence is not None else 1.0
def _recency_weight(base_weight: float, observed_at: str, reference: Any) -> float:
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    reference_at = (
        reference
        if isinstance(reference, datetime)
        else datetime.fromisoformat(_at(reference).replace("Z", "+00:00"))
    )
    age_days = max(0.0, (reference_at - observed).total_seconds() / 86400)
    return base_weight / (1.0 + age_days / 28.0)
def _number(value: Any) -> float | None: return float(value) if isinstance(value, int | float) else None
def _round(value: float | None) -> float | None: return round(value, 6) if value is not None else None
def _at(value: Any) -> str: return str(value or "")
def _weighted_median(values: list[tuple[float, float]]) -> float | None:
    weighted = sorted((value, max(0.0, weight)) for value, weight in values if weight > 0)
    if not weighted:
        return None
    threshold = sum(weight for _, weight in weighted) / 2
    cumulative = 0.0
    for value, weight in weighted:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return weighted[-1][0]
def _pace_rate(rows: list[dict[str, Any]]) -> tuple[float | None, int]:
    valid = [
        (delta, hours)
        for row in rows
        if (delta := _number(row.get("visible_percent_delta"))) is not None
        and (hours := _interval_hours(row)) is not None
        and hours > 0
    ]
    total_hours = sum(hours for _, hours in valid)
    return (
        (sum(delta for delta, _ in valid) / total_hours if total_hours > 0 else None),
        len(valid),
    )
def _pace_window(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    value, sample_count = _pace_rate(rows)
    return {"value": _round(value), "sample_count": sample_count}
def _interval_hours(row: dict[str, Any]) -> float | None:
    start, end = _at(row.get("start_observed_at")), _at(row.get("end_observed_at"))
    if not start or not end:
        return None
    seconds = (
        datetime.fromisoformat(end.replace("Z", "+00:00"))
        - datetime.fromisoformat(start.replace("Z", "+00:00"))
    ).total_seconds()
    return seconds / 3600 if seconds > 0 else None
def _iqr(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    ordered = sorted(values)
    return median(ordered[len(ordered) // 2 :]) - median(ordered[: (len(ordered) + 1) // 2])
def _quantile(values: Sequence[float | None], p: float) -> float:
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
