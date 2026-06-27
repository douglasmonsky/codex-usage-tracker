"""Feature-row construction for usage-drain modeling."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from codex_usage_tracker.usage_drain_types import EFFORT_LEVELS, UsageDeltaSpan
from codex_usage_tracker.usage_drain_utils import (
    dominant_label,
    minute_bucket,
    numeric_bucket,
    parse_timestamp,
    reset_phase_bucket,
    reset_remaining_minutes,
    second_bucket,
    span_wall_time_seconds,
)


def span_feature_row(span: UsageDeltaSpan, *, proxy: str) -> dict[str, Any]:
    start_dt = parse_timestamp(span.start_event_timestamp)
    date_label = start_dt.date().isoformat() if start_dt else "missing"
    day_index = start_dt.weekday() if start_dt else -1
    hour_value = (
        start_dt.hour + (start_dt.minute / 60.0) + (start_dt.second / 3600.0)
        if start_dt
        else 0.0
    )
    hour_bucket = f"{start_dt.hour:02d}" if start_dt else "missing"
    standard = span.standard_usage_credits
    candidate = span.candidate_standard_credits.get(proxy, 0.0)
    non_candidate = span.non_candidate_standard_credits.get(proxy, 0.0)
    documented = span.documented_fast_weighted_credits.get(proxy, standard)
    input_tokens = span.token_totals.get("input_tokens", 0.0)
    cached_tokens = span.token_totals.get("cached_input_tokens", 0.0)
    output_tokens = span.token_totals.get("output_tokens", 0.0)
    reasoning_tokens = span.token_totals.get("reasoning_output_tokens", 0.0)
    total_tokens = span.token_totals.get("total_tokens", 0.0)
    duration = span.timing_totals.get("call_duration_seconds", 0.0)
    wall_time_seconds = span_wall_time_seconds(span)
    turn_count = span.turn_count if span.turn_count > 0 else min(span.row_count, 1)
    max_calls_in_turn = span.max_calls_in_turn if span.max_calls_in_turn > 0 else (
        span.row_count if span.row_count > 0 else 0
    )
    same_turn_share = max_calls_in_turn / span.row_count if span.row_count else 0.0
    window_minutes = (
        span.usage_window_minutes
        if span.usage_window_minutes is not None
        else span.rate_limit_primary_window_minutes or 0.0
    )
    reset_timestamp = (
        span.usage_window_resets_at
        if span.usage_window_resets_at is not None
        else span.rate_limit_primary_resets_at
    )
    remaining_minutes = reset_remaining_minutes(start_dt, reset_timestamp)
    reset_minutes = remaining_minutes or 0.0
    window_elapsed_minutes = (
        max(window_minutes - reset_minutes, 0.0) if window_minutes > 0 else 0.0
    )
    window_elapsed_fraction = (
        min(max(window_elapsed_minutes / window_minutes, 0.0), 1.0)
        if window_minutes > 0
        else 0.0
    )
    day_of_week = str(day_index) if day_index >= 0 else "missing"
    baseline_used_bucket = numeric_bucket(
        span.baseline_used_percent, width=5.0, max_value=100.0, suffix="pct"
    )
    window_elapsed_bucket = reset_phase_bucket(window_elapsed_fraction)
    reset_remaining_bucket = minute_bucket(reset_minutes)
    row_count_bucket = numeric_bucket(
        float(span.row_count), width=5.0, max_value=50.0, suffix="calls"
    )
    call_duration_bucket = second_bucket(duration)
    span_wall_time_bucket = second_bucket(wall_time_seconds)
    effort_total = sum(span.effort_counts.values())
    dominant_effort = dominant_label(span.effort_counts, default="missing")
    dominant_effort_count = span.effort_counts.get(dominant_effort, 0)
    effort_purity = dominant_effort_count / effort_total if effort_total else 0.0
    effort_shares = {
        effort: span.effort_counts.get(effort, 0) / effort_total
        if effort_total
        else 0.0
        for effort in EFFORT_LEVELS
    }
    return {
        "target": span.delta_usage_percent,
        "start_event_timestamp": span.start_event_timestamp,
        "standard_usage_credits": standard,
        "log_standard_usage_credits": math.log1p(max(standard, 0.0)),
        "row_count": float(span.row_count),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "uncached_input_tokens": span.token_totals.get("uncached_input_tokens", 0.0),
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "cache_ratio": cached_tokens / input_tokens if input_tokens else 0.0,
        "output_token_share": output_tokens / total_tokens if total_tokens else 0.0,
        "reasoning_output_share": reasoning_tokens / output_tokens if output_tokens else 0.0,
        "mean_usage_credits_per_call": standard / span.row_count if span.row_count else 0.0,
        "turn_count": float(turn_count),
        "log_turn_count": math.log1p(max(turn_count, 0)),
        "multi_call_turn_count": float(span.multi_call_turn_count),
        "max_calls_in_turn": float(max_calls_in_turn),
        "same_turn_share": same_turn_share,
        "calls_per_turn": span.row_count / turn_count if turn_count else 0.0,
        "credits_per_turn": standard / turn_count if turn_count else 0.0,
        "tokens_per_turn": total_tokens / turn_count if turn_count else 0.0,
        "input_tokens_per_turn": input_tokens / turn_count if turn_count else 0.0,
        "output_tokens_per_turn": output_tokens / turn_count if turn_count else 0.0,
        "credits_per_call": standard / span.row_count if span.row_count else 0.0,
        "tokens_per_call": total_tokens / span.row_count if span.row_count else 0.0,
        "candidate_standard_credits": candidate,
        "non_candidate_standard_credits": non_candidate,
        "candidate_credit_share": candidate / standard if standard else 0.0,
        "documented_fast_weighted_credits": documented,
        "documented_fast_extra_credits": max(documented - standard, 0.0),
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
        "baseline_used_percent": span.baseline_used_percent,
        "rate_limit_primary_window_minutes": span.rate_limit_primary_window_minutes or 0.0,
        "usage_window_minutes": window_minutes,
        "usage_window_source": span.usage_window_source or "missing",
        "reset_remaining_minutes": reset_minutes,
        "window_elapsed_minutes": window_elapsed_minutes,
        "window_elapsed_fraction": window_elapsed_fraction,
        "baseline_used_bucket": baseline_used_bucket,
        "window_elapsed_bucket": window_elapsed_bucket,
        "reset_remaining_bucket": reset_remaining_bucket,
        "baseline_used_x_window_elapsed_bucket": (
            f"{baseline_used_bucket}__{window_elapsed_bucket}"
        ),
        "hour_x_window_elapsed_bucket": f"{hour_bucket}__{window_elapsed_bucket}",
        "day_x_hour_bucket": f"{day_of_week}__{hour_bucket}",
        "days_since_first_span": 0.0,
        "hour_sin": math.sin(2 * math.pi * hour_value / 24.0),
        "hour_cos": math.cos(2 * math.pi * hour_value / 24.0),
        "day_of_week_sin": math.sin(2 * math.pi * day_index / 7.0) if day_index >= 0 else 0.0,
        "day_of_week_cos": math.cos(2 * math.pi * day_index / 7.0) if day_index >= 0 else 0.0,
        "is_weekend": 1.0 if day_index in {5, 6} else 0.0,
        "call_duration_seconds": duration,
        "mean_call_duration_seconds": duration / span.row_count if span.row_count else 0.0,
        "previous_call_delta_seconds": span.timing_totals.get("previous_call_delta_seconds", 0.0),
        "span_wall_time_seconds": wall_time_seconds,
        "span_wall_time_minutes": wall_time_seconds / 60.0,
        "mean_span_wall_time_seconds_per_call": (
            wall_time_seconds / span.row_count if span.row_count else 0.0
        ),
        "row_count_bucket": row_count_bucket,
        "call_duration_bucket": call_duration_bucket,
        "span_wall_time_bucket": span_wall_time_bucket,
        "row_count_x_call_duration_bucket": (
            f"{row_count_bucket}__{call_duration_bucket}"
        ),
        "row_count_x_span_wall_time_bucket": (
            f"{row_count_bucket}__{span_wall_time_bucket}"
        ),
        "call_duration_x_span_wall_time_bucket": (
            f"{call_duration_bucket}__{span_wall_time_bucket}"
        ),
        "hour_x_row_count_bucket": f"{hour_bucket}__{row_count_bucket}",
        "baseline_used_x_row_count_bucket": (
            f"{baseline_used_bucket}__{row_count_bucket}"
        ),
        "date": date_label,
        "day_of_week": day_of_week,
        "hour_bucket": hour_bucket,
        "rate_limit_plan_type": span.rate_limit_plan_type or "missing",
        "rate_limit_limit_id": span.rate_limit_limit_id or "missing",
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
            row["days_since_first_span"] = max(
                (parsed.date() - first_date.date()).days, 0
            )
