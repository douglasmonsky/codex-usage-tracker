"""Capacity-model specification helpers for usage-drain modeling."""

from __future__ import annotations

from codex_usage_tracker.usage_drain_types import PredictiveModelSpec
from codex_usage_tracker.usage_drain_utils import format_bucket_number


def capacity_model_specs() -> list[tuple[PredictiveModelSpec, str]]:
    start_context = (
        "baseline_used_percent",
        "usage_window_minutes",
        "reset_remaining_minutes",
        "window_elapsed_minutes",
        "window_elapsed_fraction",
        "days_since_first_span",
        "hour_sin",
        "hour_cos",
        "day_of_week_sin",
        "day_of_week_cos",
        "is_weekend",
    )
    history_context = (
        *start_context,
        "previous_capacity_credits",
        "rolling3_capacity_credits",
        "rolling10_capacity_credits",
        "rolling10_capacity_median",
        "rolling10_capacity_stddev",
        "same_hour_rolling10_capacity_credits",
        "same_hour_seen_count",
        "same_day_of_week_rolling10_capacity_credits",
        "same_day_of_week_seen_count",
        "ewma_capacity_credits",
    )
    time_categories = (
        "rate_limit_plan_type",
        "rate_limit_limit_id",
        "usage_window_source",
        "day_of_week",
    )
    date_categories = (*time_categories, "date", "hour_bucket")
    state_bucket_categories = (
        *time_categories,
        "hour_bucket",
        "baseline_used_bucket",
        "window_elapsed_bucket",
        "reset_remaining_bucket",
    )
    state_interaction_categories = (
        *state_bucket_categories,
        "baseline_used_x_window_elapsed_bucket",
        "hour_x_window_elapsed_bucket",
        "day_x_hour_bucket",
    )
    same_span_shape = (
        *history_context,
        "row_count",
        "call_duration_seconds",
        "mean_call_duration_seconds",
        "previous_call_delta_seconds",
        "span_wall_time_seconds",
        "span_wall_time_minutes",
        "mean_span_wall_time_seconds_per_call",
    )
    same_span_shape_categories = (
        *state_bucket_categories,
        "row_count_bucket",
        "call_duration_bucket",
        "span_wall_time_bucket",
    )
    same_span_shape_interaction_categories = (
        *same_span_shape_categories,
        "row_count_x_call_duration_bucket",
        "row_count_x_span_wall_time_bucket",
        "call_duration_x_span_wall_time_bucket",
        "hour_x_row_count_bucket",
        "baseline_used_x_row_count_bucket",
    )
    same_span_tokens = (
        *same_span_shape,
        "input_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "cache_ratio",
        "output_token_share",
        "reasoning_output_share",
    )
    specs: list[tuple[PredictiveModelSpec, str]] = [
        (
            PredictiveModelSpec(
                "capacity_start_context",
                start_context,
                time_categories,
            ),
            "causal_start_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_date_hour_context",
                start_context,
                date_categories,
            ),
            "causal_start_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_state_bucket_context",
                start_context,
                state_bucket_categories,
            ),
            "causal_start_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_history_context",
                history_context,
                time_categories,
            ),
            "causal_history_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_history_state_buckets",
                history_context,
                state_bucket_categories,
            ),
            "causal_history_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_history_state_interactions",
                history_context,
                state_interaction_categories,
            ),
            "causal_history_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_same_span_shape",
                same_span_shape,
                time_categories,
            ),
            "explanatory_same_span",
        ),
        (
            PredictiveModelSpec(
                "capacity_same_span_shape_buckets",
                same_span_shape,
                same_span_shape_categories,
            ),
            "explanatory_same_span",
        ),
        (
            PredictiveModelSpec(
                "capacity_same_span_shape_interactions",
                same_span_shape,
                same_span_shape_interaction_categories,
            ),
            "explanatory_same_span",
        ),
        (
            PredictiveModelSpec(
                "capacity_same_span_tokens",
                same_span_tokens,
                time_categories,
            ),
            "explanatory_same_span",
        ),
    ]
    for alpha in (10.0, 30.0, 100.0):
        alpha_label = format_bucket_number(alpha)
        specs.extend(
            [
                (
                    PredictiveModelSpec(
                        f"capacity_history_state_interactions_ridge{alpha_label}",
                        history_context,
                        state_interaction_categories,
                        ridge_alpha=alpha,
                    ),
                    "causal_history_context",
                ),
                (
                    PredictiveModelSpec(
                        f"capacity_same_span_shape_interactions_ridge{alpha_label}",
                        same_span_shape,
                        same_span_shape_interaction_categories,
                        ridge_alpha=alpha,
                    ),
                    "explanatory_same_span",
                ),
            ]
        )
    return specs
