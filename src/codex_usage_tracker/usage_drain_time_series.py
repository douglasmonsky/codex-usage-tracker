"""Bounded time-series helpers for usage-drain dashboard reports."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sqrt
from typing import Any

from codex_usage_tracker.usage_drain_model import UsageDeltaSpan

MAX_VISIBLE_USAGE_POINTS = 240
WEEKLY_USAGE_WINDOW_MINUTES = 10080


def usage_time_series(
    rows: list[dict[str, Any]],
    spans: list[UsageDeltaSpan],
) -> dict[str, Any]:
    """Build bounded, aggregate-only chart data from indexed usage rows."""

    return {
        "visible_usage": visible_usage_time_series(rows),
        "usage_drain_spans": usage_drain_span_series(spans),
        "weekly_credit_projection": weekly_credit_projection(rows),
        "notes": [
            "Visible usage lines use sampled indexed rows and may include flat stretches where the visible percentage did not change.",
            "Weekly credit projection uses the secondary 10,080-minute usage counter when present.",
            "Projection intervals are descriptive 95% intervals from within-window span dispersion, not official allowance guarantees.",
        ],
    }


def visible_usage_time_series(rows: list[dict[str, Any]]) -> dict[str, Any]:
    points = []
    for index, row in enumerate(sorted(rows, key=_chronological_key), start=1):
        if _is_alternate_codex_limit(row.get("rate_limit_limit_id")):
            continue
        five_hour = _number_or_none(row.get("rate_limit_primary_used_percent"))
        weekly = _valid_weekly_used_percent(row)
        if five_hour is None and weekly is None:
            continue
        points.append(
            {
                "call_index": index,
                "timestamp": row.get("event_timestamp"),
                "five_hour_used_percent": _rounded(five_hour),
                "weekly_used_percent": _rounded(weekly),
            }
        )
    return {
        "unit": "visible_used_percent",
        "series": ["five_hour_used_percent", "weekly_used_percent"],
        "points": _sample_curve_points(points, max_points=MAX_VISIBLE_USAGE_POINTS),
        "source_fields": {
            "five_hour_used_percent": "rate_limit_primary_used_percent",
            "weekly_used_percent": "rate_limit_secondary_used_percent",
        },
    }


def usage_drain_span_series(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    points = [
        {
            "span_index": index,
            "timestamp": span.end_event_timestamp,
            "delta_usage_percent": _rounded(span.delta_usage_percent),
            "standard_usage_credits": _rounded(span.standard_usage_credits),
            "credits_per_visible_percent": _rounded(
                span.standard_usage_credits / span.delta_usage_percent
                if span.delta_usage_percent > 0
                else None
            ),
        }
        for index, span in enumerate(spans, start=1)
        if span.delta_usage_percent > 0
    ]
    return {
        "unit": "positive_visible_delta_percent",
        "points": _sample_curve_points(points, max_points=MAX_VISIBLE_USAGE_POINTS),
    }


def weekly_credit_projection(rows: list[dict[str, Any]]) -> dict[str, Any]:
    spans = _weekly_usage_delta_spans(rows)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        key = str(span.get("week_key") or span.get("reset_key") or "unknown")
        grouped.setdefault(key, []).append(span)
    raw_points = [
        _weekly_projection_point(key, grouped[key])
        for key in sorted(grouped, key=lambda item: _weekly_group_sort_key(grouped[item]))
    ]
    points: list[dict[str, Any]] = [point for point in raw_points if point is not None]
    return {
        "unit": "projected_standard_usage_credits_per_full_week",
        "window_minutes": WEEKLY_USAGE_WINDOW_MINUTES,
        "span_count": len(spans),
        "point_count": len(points),
        "points": points,
        "trend": _weekly_projection_trend(points),
        "confidence_method": (
            "For each weekly reset window, estimate full-week credits as "
            "observed standard credits divided by observed weekly visible percent "
            "and multiplied by 100. Confidence bars use 1.96 times the standard "
            "error of per-span full-week estimates inside that reset window."
        ),
    }


def _weekly_usage_delta_spans(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=_chronological_key)
    spans: list[dict[str, Any]] = []
    baseline_percent: float | None = None
    baseline_bucket: tuple[Any, ...] | None = None
    pending_rows: list[dict[str, Any]] = []
    for row in sorted_rows:
        if _is_alternate_codex_limit(row.get("rate_limit_limit_id")):
            continue
        used_percent = _valid_weekly_used_percent(row)
        resets_at = _number_or_none(row.get("rate_limit_secondary_resets_at"))
        if used_percent is None:
            continue
        bucket = (
            row.get("rate_limit_plan_type"),
            row.get("rate_limit_limit_id"),
            _weekly_window_key(
                resets_at,
                row.get("rate_limit_plan_type"),
                row.get("rate_limit_limit_id"),
            ),
        )
        if baseline_percent is None:
            baseline_percent = used_percent
            baseline_bucket = bucket
            pending_rows = []
            continue
        if bucket != baseline_bucket:
            baseline_percent = used_percent
            baseline_bucket = bucket
            pending_rows = []
            continue
        pending_rows.append(row)
        if used_percent <= baseline_percent:
            continue
        credits = sum(max(_number(item.get("usage_credits")), 0.0) for item in pending_rows)
        delta = used_percent - baseline_percent
        spans.append(
            {
                "start_event_timestamp": pending_rows[0].get("event_timestamp"),
                "end_event_timestamp": pending_rows[-1].get("event_timestamp"),
                "baseline_used_percent": baseline_percent,
                "end_used_percent": used_percent,
                "delta_usage_percent": delta,
                "standard_usage_credits": credits,
                "row_count": len(pending_rows),
                "week_key": _weekly_window_key(
                    resets_at,
                    row.get("rate_limit_plan_type"),
                    row.get("rate_limit_limit_id"),
                ),
                "reset_key": _reset_key(resets_at),
                "reset_timestamp": _timestamp_from_epoch(resets_at),
                "rate_limit_plan_type": row.get("rate_limit_plan_type"),
                "rate_limit_limit_id": row.get("rate_limit_limit_id"),
            }
        )
        baseline_percent = used_percent
        pending_rows = []
    return spans


def _weekly_projection_point(
    key: str,
    spans: list[dict[str, Any]],
) -> dict[str, Any] | None:
    usable = [span for span in spans if _number(span.get("delta_usage_percent")) > 0]
    if not usable:
        return None
    observed_delta = sum(_number(span.get("delta_usage_percent")) for span in usable)
    observed_credits = sum(_number(span.get("standard_usage_credits")) for span in usable)
    if observed_delta <= 0:
        return None
    estimates = [
        _number(span.get("standard_usage_credits"))
        / _number(span.get("delta_usage_percent"))
        * 100.0
        for span in usable
        if _number(span.get("delta_usage_percent")) > 0
    ]
    projection = observed_credits / observed_delta * 100.0
    stddev = _sample_stddev(estimates)
    standard_error = (
        stddev / sqrt(len(estimates)) if stddev is not None and len(estimates) > 1 else None
    )
    ci_half_width = 1.96 * standard_error if standard_error is not None else None
    start = min(str(span.get("start_event_timestamp") or "") for span in usable)
    end = max(str(span.get("end_event_timestamp") or "") for span in usable)
    return {
        "week_key": key,
        "label": _week_label(usable[0], key),
        "start_event_timestamp": start,
        "end_event_timestamp": end,
        "span_count": len(usable),
        "call_count": int(sum(_number(span.get("row_count")) for span in usable)),
        "observed_usage_delta_percent": _rounded(observed_delta),
        "observed_standard_usage_credits": _rounded(observed_credits),
        "projected_weekly_credits": _rounded(projection),
        "ci_low": _rounded(max(projection - ci_half_width, 0.0) if ci_half_width is not None else None),
        "ci_high": _rounded(projection + ci_half_width if ci_half_width is not None else None),
        "confidence": _projection_confidence(len(usable), observed_delta),
        "rate_limit_plan_type": usable[-1].get("rate_limit_plan_type"),
    }


def _weekly_projection_trend(points: list[dict[str, Any]]) -> dict[str, Any]:
    trend_points, basis = _trend_points_for_latest_plan(points)
    values = [_number(point.get("projected_weekly_credits")) for point in trend_points]
    if basis.startswith("insufficient") or len(values) < 3:
        return {
            "point_count": len(values),
            "basis": basis,
            "slope_credits_per_week": None,
            "direction": "insufficient_data",
            "first_projected_weekly_credits": _rounded(values[0]) if values else None,
            "latest_projected_weekly_credits": _rounded(values[-1]) if values else None,
            "change_from_first_credits": None,
            "change_from_first_pct": None,
            "rate_limit_plan_type": trend_points[0].get("rate_limit_plan_type") if trend_points else None,
        }
    xs = list(range(len(values)))
    x_mean = _mean([float(value) for value in xs])
    y_mean = _mean(values)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = (
        sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=False))
        / denominator
        if denominator
        else 0.0
    )
    change = values[-1] - values[0]
    return {
        "point_count": len(values),
        "basis": basis,
        "slope_credits_per_week": _rounded(slope),
        "direction": "up" if slope > 0 else "down" if slope < 0 else "flat",
        "first_projected_weekly_credits": _rounded(values[0]),
        "latest_projected_weekly_credits": _rounded(values[-1]),
        "change_from_first_credits": _rounded(change),
        "change_from_first_pct": _rounded(change / values[0] if values[0] else None),
        "rate_limit_plan_type": trend_points[-1].get("rate_limit_plan_type") if trend_points else None,
    }


def _trend_points_for_latest_plan(points: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    latest_plan = next(
        (point.get("rate_limit_plan_type") for point in reversed(points) if point.get("rate_limit_plan_type")),
        None,
    )
    if latest_plan is not None:
        plan_points = [point for point in points if point.get("rate_limit_plan_type") == latest_plan]
        confident = [point for point in plan_points if point.get("confidence") in {"medium", "high"}]
        if len(confident) >= 3:
            return confident, "latest_plan_medium_high_confidence"
        if len(plan_points) >= 3:
            return plan_points, "latest_plan_all_points"
        return plan_points, "latest_plan_insufficient_same_plan_windows"
    return points, "insufficient_known_plan_windows"


def _valid_weekly_used_percent(row: dict[str, Any]) -> float | None:
    used_percent = _number_or_none(row.get("rate_limit_secondary_used_percent"))
    window_minutes = _number_or_none(row.get("rate_limit_secondary_window_minutes"))
    resets_at = _number_or_none(row.get("rate_limit_secondary_resets_at"))
    if used_percent is None or window_minutes != WEEKLY_USAGE_WINDOW_MINUTES:
        return None
    if not _row_in_usage_window(row, resets_at, window_minutes):
        return None
    return used_percent


def _sample_curve_points(
    points: list[dict[str, Any]],
    *,
    max_points: int,
) -> list[dict[str, Any]]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    last_index = len(points) - 1
    selected_indexes = {
        round(index * last_index / (max_points - 1)) for index in range(max_points)
    }
    return [points[index] for index in sorted(selected_indexes)]


def _chronological_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(row.get("event_timestamp") or ""),
        int(_number(row.get("cumulative_total_tokens"))),
        str(row.get("record_id") or ""),
    )


def _sample_stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean_value = _mean(values)
    variance = sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)
    return variance**0.5


def _projection_confidence(span_count: int, observed_delta_percent: float) -> str:
    if span_count >= 20 and observed_delta_percent >= 30:
        return "high"
    if span_count >= 8 and observed_delta_percent >= 10:
        return "medium"
    return "low"


def _weekly_group_sort_key(spans: list[dict[str, Any]]) -> str:
    if not spans:
        return ""
    return str(spans[0].get("start_event_timestamp") or "")


def _week_label(span: dict[str, Any], fallback: str) -> str:
    timestamp = str(span.get("reset_timestamp") or span.get("end_event_timestamp") or "")
    dt = _parse_datetime(timestamp)
    if dt is None:
        return fallback
    return dt.strftime("Reset %b %d")


def _weekly_window_key(
    resets_at: float | None,
    plan_type: object,
    limit_id: object,
) -> str:
    reset_day = "unknown"
    timestamp = _timestamp_from_epoch(resets_at)
    dt = _parse_datetime(timestamp)
    if dt is not None:
        reset_day = dt.date().isoformat()
    elif resets_at is not None:
        reset_day = str(int(resets_at))
    return f"{plan_type or 'unknown'}:{limit_id or 'unknown'}:{reset_day}"


def _row_in_usage_window(
    row: dict[str, Any],
    resets_at: float | None,
    window_minutes: float | None,
) -> bool:
    """Reject repaired/stale allowance snapshots outside their reset window."""

    if resets_at is None or window_minutes is None:
        return False
    event_dt = _parse_datetime(row.get("event_timestamp"))
    if event_dt is None:
        return False
    reset_dt = datetime.fromtimestamp(resets_at, tz=timezone.utc)
    window = timedelta(minutes=window_minutes)
    tolerance = timedelta(minutes=30)
    return reset_dt - window - tolerance <= event_dt <= reset_dt + tolerance


def _reset_key(value: float | None) -> str:
    if value is None:
        return "unknown"
    return str(int(value))


def _timestamp_from_epoch(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_alternate_codex_limit(limit_id: object) -> bool:
    return isinstance(limit_id, str) and limit_id.startswith("codex_") and limit_id != "codex"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _rounded(value: object) -> float | None:
    if value is None or value == "":
        return None
    if not isinstance(value, int | float | str):
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _number_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    if not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
