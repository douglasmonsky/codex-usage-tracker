"""Feature-row construction for usage-drain modeling."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from codex_usage_tracker.usage_drain.types import EFFORT_LEVELS, UsageDeltaSpan
from codex_usage_tracker.usage_drain.utils import (
    dominant_label,
    minute_bucket,
    numeric_bucket,
    parse_timestamp,
    reset_phase_bucket,
    reset_remaining_minutes,
    second_bucket,
    span_reset_timestamp,
    span_wall_time_seconds,
    span_window_minutes,
    window_elapsed_fraction,
    window_elapsed_minutes,
)


def span_feature_row(span: UsageDeltaSpan, *, proxy: str) -> dict[str, Any]:
    """Build one model feature row for a visible usage-drain span."""
    start_dt, time_features = _span_time_features(span)
    credit_features = _span_credit_features(span, proxy=proxy)
    turn_features = _span_turn_features(span, credit_features)
    effort_features = _span_effort_features(span)
    window_features = _span_window_features(span, start_dt, time_features)
    timing_features = _span_timing_features(span, time_features, window_features)
    return {
        "target": span.delta_usage_percent,
        "start_event_timestamp": span.start_event_timestamp,
        **credit_features,
        **turn_features,
        **effort_features,
        **window_features,
        **time_features,
        **timing_features,
        "date": time_features["date"],
        "day_of_week": time_features["day_of_week"],
        "hour_bucket": time_features["hour_bucket"],
        "rate_limit_plan_type": span.rate_limit_plan_type or "missing",
        "rate_limit_limit_id": span.rate_limit_limit_id or "missing",
    }


def _span_time_features(span: UsageDeltaSpan) -> tuple[datetime | None, dict[str, Any]]:
    start_dt = parse_timestamp(span.start_event_timestamp)
    date_label = start_dt.date().isoformat() if start_dt else "missing"
    day_index = _span_day_index(start_dt)
    hour_value = _span_hour_value(start_dt)
    hour_bucket = f"{start_dt.hour:02d}" if start_dt else "missing"
    day_of_week = str(day_index) if day_index >= 0 else "missing"
    return start_dt, {
        "date": date_label,
        "day_of_week": day_of_week,
        "hour_bucket": hour_bucket,
        "hour_sin": _cyclic_sin(hour_value, period=24.0),
        "hour_cos": _cyclic_cos(hour_value, period=24.0),
        "day_of_week_sin": _day_cyclic_sin(day_index),
        "day_of_week_cos": _day_cyclic_cos(day_index),
        "is_weekend": 1.0 if day_index in {5, 6} else 0.0,
    }


def _span_day_index(start_dt: datetime | None) -> int:
    return start_dt.weekday() if start_dt else -1


def _span_hour_value(start_dt: datetime | None) -> float:
    if not start_dt:
        return 0.0
    return start_dt.hour + (start_dt.minute / 60.0) + (start_dt.second / 3600.0)


def _cyclic_sin(value: float, *, period: float) -> float:
    return math.sin(2 * math.pi * value / period)


def _cyclic_cos(value: float, *, period: float) -> float:
    return math.cos(2 * math.pi * value / period)


def _day_cyclic_sin(day_index: int) -> float:
    return _cyclic_sin(float(day_index), period=7.0) if day_index >= 0 else 0.0


def _day_cyclic_cos(day_index: int) -> float:
    return _cyclic_cos(float(day_index), period=7.0) if day_index >= 0 else 0.0


def _span_credit_features(span: UsageDeltaSpan, *, proxy: str) -> dict[str, Any]:
    standard = span.standard_usage_credits
    candidate = span.candidate_standard_credits.get(proxy, 0.0)
    non_candidate = span.non_candidate_standard_credits.get(proxy, 0.0)
    documented = span.documented_fast_weighted_credits.get(proxy, standard)
    input_tokens = span.token_totals.get("input_tokens", 0.0)
    cached_tokens = span.token_totals.get("cached_input_tokens", 0.0)
    output_tokens = span.token_totals.get("output_tokens", 0.0)
    reasoning_tokens = span.token_totals.get("reasoning_output_tokens", 0.0)
    total_tokens = span.token_totals.get("total_tokens", 0.0)
    return {
        "standard_usage_credits": standard,
        "log_standard_usage_credits": math.log1p(max(standard, 0.0)),
        "row_count": float(span.row_count),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "uncached_input_tokens": span.token_totals.get("uncached_input_tokens", 0.0),
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "cache_ratio": _safe_div(cached_tokens, input_tokens),
        "output_token_share": _safe_div(output_tokens, total_tokens),
        "reasoning_output_share": _safe_div(reasoning_tokens, output_tokens),
        "mean_usage_credits_per_call": _safe_div(standard, span.row_count),
        "credits_per_call": _safe_div(standard, span.row_count),
        "tokens_per_call": _safe_div(total_tokens, span.row_count),
        "candidate_standard_credits": candidate,
        "non_candidate_standard_credits": non_candidate,
        "candidate_credit_share": _safe_div(candidate, standard),
        "documented_fast_weighted_credits": documented,
        "documented_fast_extra_credits": max(documented - standard, 0.0),
    }


def _span_turn_features(span: UsageDeltaSpan, credit_features: dict[str, Any]) -> dict[str, Any]:
    standard = float(credit_features["standard_usage_credits"])
    total_tokens = float(credit_features["total_tokens"])
    input_tokens = float(credit_features["input_tokens"])
    output_tokens = float(credit_features["output_tokens"])
    turn_count = _span_turn_count(span)
    max_calls_in_turn = _span_max_calls_in_turn(span)
    same_turn_share = _safe_div(max_calls_in_turn, span.row_count)
    return {
        "turn_count": float(turn_count),
        "log_turn_count": math.log1p(max(turn_count, 0)),
        "multi_call_turn_count": float(span.multi_call_turn_count),
        "max_calls_in_turn": float(max_calls_in_turn),
        "same_turn_share": same_turn_share,
        "calls_per_turn": _safe_div(span.row_count, turn_count),
        "credits_per_turn": _safe_div(standard, turn_count),
        "tokens_per_turn": _safe_div(total_tokens, turn_count),
        "input_tokens_per_turn": _safe_div(input_tokens, turn_count),
        "output_tokens_per_turn": _safe_div(output_tokens, turn_count),
    }


def _span_turn_count(span: UsageDeltaSpan) -> int:
    return span.turn_count if span.turn_count > 0 else min(span.row_count, 1)


def _span_max_calls_in_turn(span: UsageDeltaSpan) -> int:
    if span.max_calls_in_turn > 0:
        return span.max_calls_in_turn
    return span.row_count if span.row_count > 0 else 0


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _span_effort_features(span: UsageDeltaSpan) -> dict[str, Any]:
    effort_total = sum(span.effort_counts.values())
    dominant_effort = dominant_label(span.effort_counts, default="missing")
    dominant_effort_count = span.effort_counts.get(dominant_effort, 0)
    effort_purity = dominant_effort_count / effort_total if effort_total else 0.0
    effort_shares = {
        effort: span.effort_counts.get(effort, 0) / effort_total if effort_total else 0.0
        for effort in EFFORT_LEVELS
    }
    return {
        "dominant_effort": dominant_effort,
        "effort_mix": "pure" if effort_purity >= 1.0 else "mixed",
        "effort_purity": effort_purity,
        "effort_low_share": effort_shares["low"],
        "effort_medium_share": effort_shares["medium"],
        "effort_high_share": effort_shares["high"],
        "effort_xhigh_share": effort_shares["xhigh"],
        "effort_missing_share": effort_shares["missing"],
        "effort_other_share": effort_shares["other"],
        "effort_non_xhigh_share": 1.0 - effort_shares["xhigh"],
    }


def _span_window_features(
    span: UsageDeltaSpan,
    start_dt: datetime | None,
    time_features: dict[str, Any],
) -> dict[str, Any]:
    window_minutes = span_window_minutes(span)
    reset_timestamp = span_reset_timestamp(span)
    remaining_minutes = reset_remaining_minutes(start_dt, reset_timestamp)
    reset_minutes = remaining_minutes or 0.0
    elapsed_minutes = window_elapsed_minutes(window_minutes, reset_minutes)
    elapsed_fraction = window_elapsed_fraction(elapsed_minutes, window_minutes)
    baseline_used_bucket = numeric_bucket(
        span.baseline_used_percent, width=5.0, max_value=100.0, suffix="pct"
    )
    window_elapsed_bucket = reset_phase_bucket(elapsed_fraction)
    reset_remaining_bucket = minute_bucket(reset_minutes)
    hour_bucket = str(time_features["hour_bucket"])
    day_of_week = str(time_features["day_of_week"])
    return {
        "baseline_used_percent": span.baseline_used_percent,
        "rate_limit_primary_window_minutes": span.rate_limit_primary_window_minutes or 0.0,
        "usage_window_minutes": window_minutes,
        "usage_window_source": span.usage_window_source or "missing",
        "reset_remaining_minutes": reset_minutes,
        "window_elapsed_minutes": elapsed_minutes,
        "window_elapsed_fraction": elapsed_fraction,
        "baseline_used_bucket": baseline_used_bucket,
        "window_elapsed_bucket": window_elapsed_bucket,
        "reset_remaining_bucket": reset_remaining_bucket,
        "baseline_used_x_window_elapsed_bucket": (
            f"{baseline_used_bucket}__{window_elapsed_bucket}"
        ),
        "hour_x_window_elapsed_bucket": f"{hour_bucket}__{window_elapsed_bucket}",
        "day_x_hour_bucket": f"{day_of_week}__{hour_bucket}",
        "days_since_first_span": 0.0,
    }


def _span_timing_features(
    span: UsageDeltaSpan,
    time_features: dict[str, Any],
    window_features: dict[str, Any],
) -> dict[str, Any]:
    duration = span.timing_totals.get("call_duration_seconds", 0.0)
    wall_time_seconds = span_wall_time_seconds(span)
    row_count_bucket = numeric_bucket(
        float(span.row_count), width=5.0, max_value=50.0, suffix="calls"
    )
    call_duration_bucket = second_bucket(duration)
    span_wall_time_bucket = second_bucket(wall_time_seconds)
    hour_bucket = time_features["hour_bucket"]
    baseline_used_bucket = window_features["baseline_used_bucket"]
    return {
        "call_duration_seconds": duration,
        "mean_call_duration_seconds": _safe_div(duration, span.row_count),
        "previous_call_delta_seconds": span.timing_totals.get("previous_call_delta_seconds", 0.0),
        "span_wall_time_seconds": wall_time_seconds,
        "span_wall_time_minutes": wall_time_seconds / 60.0,
        "mean_span_wall_time_seconds_per_call": _safe_div(wall_time_seconds, span.row_count),
        "row_count_bucket": row_count_bucket,
        "call_duration_bucket": call_duration_bucket,
        "span_wall_time_bucket": span_wall_time_bucket,
        "row_count_x_call_duration_bucket": f"{row_count_bucket}__{call_duration_bucket}",
        "row_count_x_span_wall_time_bucket": f"{row_count_bucket}__{span_wall_time_bucket}",
        "call_duration_x_span_wall_time_bucket": (
            f"{call_duration_bucket}__{span_wall_time_bucket}"
        ),
        "hour_x_row_count_bucket": f"{hour_bucket}__{row_count_bucket}",
        "baseline_used_x_row_count_bucket": f"{baseline_used_bucket}__{row_count_bucket}",
    }


def add_days_since_first_span(rows: list[dict[str, Any]]) -> None:
    first_date: datetime | None = None
    for row in rows:
        parsed = parse_timestamp(str(row.get("date") or ""))
        if parsed is None:
            parsed = parse_timestamp(str(row.get("start_event_timestamp") or ""))
        if parsed is not None and first_date is None:
            first_date = parsed
        if parsed is None or first_date is None:
            row["days_since_first_span"] = 0.0
        else:
            row["days_since_first_span"] = max((parsed.date() - first_date.date()).days, 0)
