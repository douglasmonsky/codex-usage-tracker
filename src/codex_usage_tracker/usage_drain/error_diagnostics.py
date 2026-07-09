"""Prediction error diagnostics for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain.types import UsageDeltaSpan
from codex_usage_tracker.usage_drain.utils import (
    minute_bucket,
    number,
    numeric_bucket,
    parse_timestamp,
    reset_phase_bucket,
    reset_remaining_minutes,
    rounded,
    span_reset_timestamp,
    span_window_minutes,
    value_stddev,
    window_elapsed_fraction,
)


def span_error_metadata(span: UsageDeltaSpan) -> dict[str, Any]:
    start_dt = parse_timestamp(span.start_event_timestamp)
    reset_minutes = _span_reset_remaining_minutes(span, start_dt)
    elapsed_fraction = _span_window_elapsed_fraction(span, reset_minutes)
    return {
        "date": start_dt.date().isoformat() if start_dt else "missing",
        "day_of_week": str(start_dt.weekday()) if start_dt else "missing",
        "hour_bucket": f"{start_dt.hour:02d}" if start_dt else "missing",
        "reset_phase": reset_phase_bucket(elapsed_fraction),
        "baseline_used_bucket": numeric_bucket(
            span.baseline_used_percent, width=5.0, max_value=100.0, suffix="pct"
        ),
        "window_elapsed_bucket": reset_phase_bucket(elapsed_fraction),
        "reset_remaining_bucket": minute_bucket(reset_minutes),
        "rate_limit_plan_type": span.rate_limit_plan_type or "missing",
        "rate_limit_limit_id": span.rate_limit_limit_id or "missing",
        "usage_window_source": span.usage_window_source or "missing",
    }


def _span_reset_remaining_minutes(span: UsageDeltaSpan, start_dt: Any) -> float:
    remaining_minutes = reset_remaining_minutes(start_dt, span_reset_timestamp(span))
    return remaining_minutes or 0.0


def _span_window_elapsed_fraction(span: UsageDeltaSpan, reset_minutes: float) -> float:
    window_minutes = span_window_minutes(span)
    elapsed_minutes = max(window_minutes - reset_minutes, 0.0)
    return window_elapsed_fraction(elapsed_minutes, window_minutes)


def prediction_error_diagnostics(rows: list[dict[str, Any]], model_name: str) -> dict[str, Any]:
    errors = prediction_error_rows(rows, model_name)
    if not errors:
        return empty_prediction_error_diagnostics()
    return prediction_error_summary(errors)


def prediction_error_rows(rows: list[dict[str, Any]], model_name: str) -> list[dict[str, Any]]:
    return [_prediction_error_row(row, model_name) for row in rows]


def _prediction_error_row(row: dict[str, Any], model_name: str) -> dict[str, Any]:
    predictions = row.get("predictions", {})
    predicted = number(predictions.get(model_name))
    actual = number(row.get("actual"))
    previous_actual = number(row.get("previous_actual"))
    error = predicted - actual
    return {
        "index": int(row["index"]),
        "actual": actual,
        "predicted": predicted,
        "previous_actual": previous_actual,
        "error": error,
        "abs_error": abs(error),
        "metadata": row.get("metadata", {}),
    }


def empty_prediction_error_diagnostics() -> dict[str, Any]:
    return {
        "n": 0,
        "exact_match_share": None,
        "within_quarter_point_share": None,
        "within_one_point_share": None,
        "large_error_share": None,
        "top_transition_errors": [],
        "top_error_dates": [],
        "error_by_day_of_week": [],
        "error_by_hour": [],
        "error_by_reset_phase": [],
        "error_by_one_percent_streak": [],
        "error_by_same_delta_streak": [],
        "largest_errors": [],
    }


def prediction_error_summary(errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(errors),
        "exact_match_share": prediction_error_share(errors, exact_error=0.0),
        "within_quarter_point_share": prediction_error_share(errors, max_error=0.25),
        "within_one_point_share": prediction_error_share(errors, max_error=1.0),
        "large_error_share": prediction_error_share(errors, min_error=5.0),
        "top_transition_errors": top_transition_errors(errors),
        "top_error_dates": top_error_groups(errors, "date"),
        "error_by_day_of_week": top_error_groups(errors, "day_of_week"),
        "error_by_hour": top_error_groups(errors, "hour_bucket"),
        "error_by_reset_phase": top_error_groups(errors, "reset_phase"),
        "error_by_one_percent_streak": top_error_groups(errors, "one_percent_streak_bucket"),
        "error_by_same_delta_streak": top_error_groups(errors, "same_delta_streak_bucket"),
        "largest_errors": largest_prediction_errors(errors),
    }


def prediction_error_share(
    errors: list[dict[str, Any]],
    *,
    exact_error: float | None = None,
    min_error: float | None = None,
    max_error: float | None = None,
) -> float | None:
    if not errors:
        return None
    matching = 0
    for item in errors:
        abs_error = item["abs_error"]
        matches_exact = exact_error is None or abs_error == exact_error
        above_min = min_error is None or abs_error >= min_error
        below_max = max_error is None or abs_error <= max_error
        if matches_exact and above_min and below_max:
            matching += 1
    return rounded(matching / len(errors))


def top_transition_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for item in errors:
        key = (round(item["previous_actual"], 6), round(item["actual"], 6))
        grouped.setdefault(key, []).append(item)
    rows = [
        {
            "previous_delta_percent": previous,
            "actual_delta_percent": actual,
            "count": len(items),
            "mean_abs_error": rounded(sum(item["abs_error"] for item in items) / len(items)),
            "max_abs_error": rounded(max(item["abs_error"] for item in items)),
        }
        for (previous, actual), items in grouped.items()
    ]
    rows.sort(
        key=lambda row: (
            -number(row["mean_abs_error"]),
            -int(number(row.get("count"))),
        )
    )
    return rows[:10]


def top_error_groups(errors: list[dict[str, Any]], field_name: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in errors:
        metadata = item.get("metadata", {})
        key = str(metadata.get(field_name) or "missing")
        grouped.setdefault(key, []).append(item)
    rows = [
        {
            field_name: key,
            "count": len(items),
            "mean_abs_error": rounded(sum(item["abs_error"] for item in items) / len(items)),
            "max_abs_error": rounded(max(item["abs_error"] for item in items)),
        }
        for key, items in grouped.items()
    ]
    rows.sort(
        key=lambda row: (
            -number(row["mean_abs_error"]),
            -int(number(row.get("count"))),
        )
    )
    return rows[:10]


def largest_prediction_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(errors, key=lambda item: item["abs_error"], reverse=True)[:10]
    return [
        {
            "index": item["index"],
            "date": item["metadata"].get("date"),
            "hour_bucket": item["metadata"].get("hour_bucket"),
            "day_of_week": item["metadata"].get("day_of_week"),
            "reset_phase": item["metadata"].get("reset_phase"),
            "previous_delta_percent": rounded(item["previous_actual"]),
            "actual_delta_percent": rounded(item["actual"]),
            "predicted_delta_percent": rounded(item["predicted"]),
            "abs_error": rounded(item["abs_error"]),
        }
        for item in rows
    ]


def value_distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "n": 0,
            "mean": None,
            "stddev": None,
            "min": None,
            "max": None,
        }
    mean = sum(values) / len(values)
    return {
        "n": len(values),
        "mean": rounded(mean),
        "stddev": rounded(value_stddev(values)),
        "min": rounded(min(values)),
        "max": rounded(max(values)),
    }
