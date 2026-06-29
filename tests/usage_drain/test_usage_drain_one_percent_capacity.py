from __future__ import annotations

from codex_usage_tracker.usage_drain.model import summarize_usage_drain_model


def _row(
    record_id: str,
    timestamp: str,
    used: float | None,
    credits: float,
    *,
    uncached_input_tokens: int = 0,
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "session_id": "session",
        "turn_id": record_id,
        "event_timestamp": timestamp,
        "rate_limit_plan_type": "plus",
        "rate_limit_limit_id": "codex",
        "rate_limit_primary_used_percent": used,
        "rate_limit_primary_window_minutes": 300,
        "rate_limit_primary_resets_at": 1000,
        "rate_limit_secondary_used_percent": None,
        "rate_limit_secondary_window_minutes": 10080,
        "rate_limit_secondary_resets_at": 2000,
        "usage_credits": credits,
        "model": "gpt-5.5",
        "effort": "xhigh",
        "input_tokens": uncached_input_tokens,
        "cached_input_tokens": 0,
        "uncached_input_tokens": uncached_input_tokens,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": uncached_input_tokens,
    }


def test_one_percent_capacity_modeling_reports_tick_capacity_models() -> None:
    rows = [_row("base", "2026-06-01T00:00:00Z", 0.0, 0.0)]
    used = 0.0
    for index in range(24):
        hold_credits = 1.0 + (index % 3)
        rows.append(
            _row(
                f"hold-{index}",
                f"2026-06-01T00:{(index * 2) + 1:02d}:00Z",
                used,
                hold_credits,
                uncached_input_tokens=int(hold_credits * 1_000_000 / 125.0),
            )
        )
        used += 1.0
        tick_credits = 4.0 + (index % 5)
        rows.append(
            _row(
                f"tick-{index}",
                f"2026-06-01T00:{(index * 2) + 2:02d}:00Z",
                used,
                tick_credits,
                uncached_input_tokens=int(tick_credits * 1_000_000 / 125.0),
            )
        )

    summary = summarize_usage_drain_model(rows)

    capacity = summary["one_percent_capacity_modeling"]
    assert capacity["span_count"] == 24
    assert capacity["target"] == "standard_usage_credits"
    assert capacity["target_distribution"]["n"] == 24
    assert capacity["best_by_holdout_mae"] is not None
    assert capacity["best_causal_by_holdout_mae"] is not None
    kinds = {model["kind"] for model in capacity["models"]}
    assert "capacity_causal_baseline" in kinds
    assert "causal_history_context" in kinds
    assert "explanatory_same_span" in kinds
    model_names = {model["name"] for model in capacity["models"]}
    assert "capacity_history_state_buckets__time_ordered_80_20" in model_names
    assert "capacity_history_state_interactions__time_ordered_80_20" in model_names
    assert "capacity_history_state_interactions_ridge100__time_ordered_80_20" in model_names
    assert "capacity_same_span_shape_buckets__time_ordered_80_20" in model_names
    assert "capacity_same_span_shape_interactions__time_ordered_80_20" in model_names
    assert (
        "capacity_same_span_shape_interactions_ridge30__time_ordered_80_20"
        in model_names
    )
    shape_bucket_model = next(
        model
        for model in capacity["models"]
        if model["name"] == "capacity_same_span_shape_interactions__time_ordered_80_20"
    )
    assert "row_count_bucket" in shape_bucket_model["categorical_features"]
    assert "span_wall_time_bucket" in shape_bucket_model["categorical_features"]
    assert "row_count_x_call_duration_bucket" in shape_bucket_model[
        "categorical_features"
    ]
    ridge_model = next(
        model
        for model in capacity["models"]
        if model["name"]
        == "capacity_same_span_shape_interactions_ridge30__time_ordered_80_20"
    )
    assert ridge_model["ridge_alpha"] == 30.0
    diagnostics = ridge_model["holdout_error_diagnostics"]
    assert diagnostics["n"] > 0
    assert "row_count_bucket" in diagnostics["top_error_groups"]


def test_one_percent_capacity_modeling_reports_low_data_shape() -> None:
    rows = [_row("base", "2026-06-01T00:00:00Z", 0.0, 0.0)]
    used = 0.0
    for index in range(3):
        rows.append(
            _row(
                f"hold-{index}",
                f"2026-06-01T00:{(index * 2) + 1:02d}:00Z",
                used,
                1.0,
            )
        )
        used += 1.0
        rows.append(
            _row(
                f"tick-{index}",
                f"2026-06-01T00:{(index * 2) + 2:02d}:00Z",
                used,
                2.0,
            )
        )

    capacity = summarize_usage_drain_model(rows)["one_percent_capacity_modeling"]

    assert capacity["span_count"] == 3
    assert capacity["splits"] == ["time_ordered_80_20", "interleaved_every_5th"]
    assert capacity["best_by_holdout_mae"] is None
    assert capacity["best_causal_by_holdout_mae"] is None
    assert capacity["models"] == []
