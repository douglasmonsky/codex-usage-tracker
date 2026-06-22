from __future__ import annotations

import csv
from pathlib import Path

from codex_usage_tracker.usage_drain_model import (
    FastProxyAnnotation,
    UsageDeltaSpan,
    build_usage_delta_spans,
    documented_fast_credit_multiplier,
    fit_predictive_usage_drain_models,
    fit_usage_drain_proxy,
    load_fast_proxy_annotations,
    summarize_usage_drain_model,
)


def _row(
    record_id: str,
    timestamp: str,
    used: float | None,
    credits: float,
    *,
    model: str = "gpt-5.5",
    window_minutes: int = 300,
    resets_at: int = 1000,
    secondary_used: float | None = None,
    secondary_window_minutes: int | None = 10080,
    secondary_resets_at: int | None = 2000,
    uncached_input_tokens: int = 0,
    cached_input_tokens: int = 0,
    reasoning_output_tokens: int = 0,
    nonreasoning_output_tokens: int = 0,
) -> dict[str, object]:
    output_tokens = reasoning_output_tokens + nonreasoning_output_tokens
    input_tokens = uncached_input_tokens + cached_input_tokens
    return {
        "record_id": record_id,
        "event_timestamp": timestamp,
        "rate_limit_plan_type": "plus",
        "rate_limit_limit_id": "codex",
        "rate_limit_primary_used_percent": used,
        "rate_limit_primary_window_minutes": window_minutes,
        "rate_limit_primary_resets_at": resets_at,
        "rate_limit_secondary_used_percent": secondary_used,
        "rate_limit_secondary_window_minutes": secondary_window_minutes,
        "rate_limit_secondary_resets_at": secondary_resets_at,
        "usage_credits": credits,
        "model": model,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": uncached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def test_build_usage_delta_spans_includes_zero_change_calls_then_censors_resets() -> None:
    rows = [
        _row("a", "2026-06-01T00:00:00Z", 10.0, 99.0),
        _row("b", "2026-06-01T00:01:00Z", 10.0, 2.0),
        _row("c", "2026-06-01T00:02:00Z", 12.0, 3.0),
        _row("d", "2026-06-01T00:03:00Z", 12.0, 1.0),
        _row("e", "2026-06-01T00:04:00Z", 5.0, 1.0),
        _row("f", "2026-06-01T00:05:00Z", 6.0, 4.0),
        _row("g", "2026-06-01T00:06:00Z", 7.0, 4.0, resets_at=2000),
    ]
    proxies = {
        "b": FastProxyAnnotation(label="strong_proxy", timing_confidence="medium"),
        "c": FastProxyAnnotation(label="strong_proxy", timing_confidence="medium"),
        "f": FastProxyAnnotation(label="not_fast_proxy", timing_confidence="low"),
    }

    spans, stats = build_usage_delta_spans(rows, fast_proxy_annotations=proxies)

    assert stats["positive_usage_spans"] == 2
    assert stats["censored_or_reset_pending_segments"] == 1
    assert [span.row_count for span in spans] == [2, 1]
    assert spans[0].delta_usage_percent == 2.0
    assert spans[0].candidate_standard_credits["strong_only"] == 5.0
    assert spans[0].documented_fast_weighted_credits["strong_only"] == 12.5
    assert spans[1].non_candidate_standard_credits["strong_only"] == 4.0

    summary = summarize_usage_drain_model(rows, fast_proxy_annotations=proxies)
    assert summary["delta_regimes"]["all_spans"]["spans"] == 2
    assert summary["delta_regimes"]["all_spans"]["top_delta_values"][0] == {
        "delta_percent": 1.0,
        "count": 1,
        "share": 0.5,
    }
    walk_forward = summary["walk_forward_prediction"]["scopes"]["all_after_first"]
    assert walk_forward["actual"]["n"] == 1
    assert walk_forward["models"]["constant_one_percent"]["mae"] == 0.0
    assert walk_forward["models"]["previous_delta"]["mae"] == 1.0
    previous_error = walk_forward["error_diagnostics"]["previous_delta"]
    assert previous_error["exact_match_share"] == 0.0
    assert previous_error["top_transition_errors"][0] == {
        "previous_delta_percent": 2.0,
        "actual_delta_percent": 1.0,
        "count": 1,
        "mean_abs_error": 1.0,
        "max_abs_error": 1.0,
    }
    assert previous_error["largest_errors"][0]["date"] == "2026-06-01"


def test_build_usage_delta_spans_prefers_five_hour_window_when_secondary() -> None:
    rows = [
        _row(
            "a",
            "2026-06-01T00:00:00Z",
            50.0,
            1.0,
            window_minutes=10080,
            secondary_used=10.0,
            secondary_window_minutes=300,
            secondary_resets_at=1500,
        ),
        _row(
            "b",
            "2026-06-01T00:01:00Z",
            50.0,
            2.0,
            window_minutes=10080,
            secondary_used=12.0,
            secondary_window_minutes=300,
            secondary_resets_at=1500,
        ),
    ]

    spans, stats = build_usage_delta_spans(rows)

    assert stats["five_hour_usage_window_rows"] == 2
    assert stats["fallback_usage_window_rows"] == 0
    assert len(spans) == 1
    assert spans[0].usage_window_source == "secondary"
    assert spans[0].usage_window_minutes == 300
    assert spans[0].delta_usage_percent == 2.0


def test_regime_streaks_expose_one_percent_runs_and_breaks() -> None:
    rows = [
        _row("base", "2026-06-01T00:00:00Z", 0.0, 0.0),
        _row("a", "2026-06-01T00:01:00Z", 1.0, 1.0),
        _row("b", "2026-06-01T00:02:00Z", 2.0, 1.0),
        _row("c", "2026-06-01T00:03:00Z", 3.0, 1.0),
        _row("d", "2026-06-01T00:04:00Z", 4.0, 1.0),
        _row("e", "2026-06-01T00:05:00Z", 6.0, 2.0),
        _row("f", "2026-06-01T00:06:00Z", 7.0, 1.0),
    ]

    summary = summarize_usage_drain_model(rows)

    streaks = summary["regime_streaks"]
    one_percent_runs = streaks["one_percent_runs"]
    assert one_percent_runs["count"] == 2
    assert one_percent_runs["max_span_count"] == 4
    assert one_percent_runs["current_streak"] == 1
    assert one_percent_runs["top_runs"][0]["span_count"] == 4
    assert streaks["breaks_after_long_one_percent_runs"][0] == {
        "preceding_start_index": 0,
        "preceding_end_index": 3,
        "preceding_span_count": 4,
        "break_index": 4,
        "break_delta_percent": 2.0,
        "break_timestamp": "2026-06-01T00:05:00Z",
        "break_date": "2026-06-01",
    }
    walk_forward = summary["walk_forward_prediction"]["scopes"]["all_after_first"]
    assert walk_forward["models"]["hybrid_streak_regime"]["mae"] < 0.5
    assert "error_by_one_percent_streak" in walk_forward["error_diagnostics"][
        "hybrid_streak_regime"
    ]
    assert "one_percent_regime_grace" in walk_forward["models"]
    assert summary["span_correlations"]["delta_usage_percent"]["n"] == 6
    assert (
        summary["span_correlations"]["one_percent_span_capacity"][
            "standard_usage_credits"
        ]["n"]
        == 5
    )
    calibration = summary["walk_forward_prediction"]["one_percent_grace_calibration"]
    assert calibration["default_config"] == {
        "streak_threshold": 10,
        "grace_spans": 1,
        "max_break_delta_percent": 2.0,
    }


def test_one_percent_regime_grace_ignores_one_small_break() -> None:
    rows = [_row("base", "2026-06-01T00:00:00Z", 0.0, 0.0)]
    used = 0.0
    for index in range(11):
        used += 1.0
        rows.append(
            _row(
                f"one-{index}",
                f"2026-06-01T00:{index + 1:02d}:00Z",
                used,
                1.0,
            )
        )
    used += 2.0
    rows.append(_row("break", "2026-06-01T00:12:00Z", used, 2.0))
    used += 1.0
    rows.append(_row("resume", "2026-06-01T00:13:00Z", used, 1.0))

    summary = summarize_usage_drain_model(rows)

    walk_forward = summary["walk_forward_prediction"]["scopes"]["all_after_first"]
    previous = walk_forward["models"]["previous_delta"]
    grace = walk_forward["models"]["one_percent_regime_grace"]
    assert grace["mae"] < previous["mae"]
    calibration = summary["walk_forward_prediction"]["one_percent_grace_calibration"]
    assert calibration["scopes"]["all_after_first"]["best_by_mae"]["mae"] <= grace["mae"]


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
        if model["name"]
        == "capacity_same_span_shape_interactions__time_ordered_80_20"
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
    component_regression = capacity["token_component_regression"]["variants"][
        "unweighted"
    ]["capacity_credits"]["no_intercept"]["all"]
    assert component_regression["r2"] == 1.0
    assert component_regression["mae"] == 0.0
    coefficient = _coefficients_by_feature(component_regression["coefficients"])[
        "uncached_input_tokens"
    ]
    assert coefficient is not None
    assert abs(coefficient - 125.0) < 0.00001


def test_token_component_regression_recovers_rate_card_and_fast_weighting() -> None:
    rows = [_row("base", "2026-06-01T00:00:00Z", 0.0, 0.0)]
    proxies: dict[str, FastProxyAnnotation] = {}
    used = 0.0
    component_rows = [
        (1_000_000, 0, 0, 0, False),
        (0, 1_000_000, 0, 0, False),
        (0, 0, 100_000, 0, True),
        (0, 0, 0, 100_000, False),
        (500_000, 250_000, 10_000, 20_000, True),
        (250_000, 750_000, 20_000, 5_000, False),
        (750_000, 100_000, 5_000, 30_000, True),
        (125_000, 875_000, 15_000, 10_000, False),
    ]
    for index, (
        uncached,
        cached,
        reasoning,
        nonreasoning,
        is_fast,
    ) in enumerate(component_rows):
        used += 1.0 + (index % 3)
        record_id = f"component-{index}"
        if is_fast:
            proxies[record_id] = FastProxyAnnotation(
                label="possible_proxy",
                timing_confidence="medium",
            )
        rows.append(
            _row(
                record_id,
                f"2026-06-01T00:{index + 1:02d}:00Z",
                used,
                _component_credits(
                    uncached=uncached,
                    cached=cached,
                    reasoning=reasoning,
                    nonreasoning=nonreasoning,
                ),
                uncached_input_tokens=uncached,
                cached_input_tokens=cached,
                reasoning_output_tokens=reasoning,
                nonreasoning_output_tokens=nonreasoning,
            )
        )

    summary = summarize_usage_drain_model(rows, fast_proxy_annotations=proxies)

    regression = summary["token_component_regression"]
    unweighted = regression["variants"]["unweighted"]["credit_accounting"][
        "no_intercept"
    ]["all"]
    weighted = regression["variants"]["high_medium_fast_weighted"]["credit_accounting"][
        "no_intercept"
    ]["all"]
    assert unweighted["r2"] == 1.0
    assert weighted["r2"] == 1.0
    assert weighted["mae"] == 0.0
    assert regression["variants"]["high_medium_fast_weighted"]["candidate_rows"] == 3
    assert _coefficients_by_feature(unweighted["coefficients"]) == {
        "uncached_input_tokens": 125.0,
        "cached_input_tokens": 12.5,
        "reasoning_output_tokens": 750.0,
        "nonreasoning_output_tokens": 750.0,
    }


def _component_credits(
    *,
    uncached: int,
    cached: int,
    reasoning: int,
    nonreasoning: int,
) -> float:
    return (
        (uncached * 125.0)
        + (cached * 12.5)
        + ((reasoning + nonreasoning) * 750.0)
    ) / 1_000_000.0


def _coefficients_by_feature(rows: list[dict[str, object]]) -> dict[str, float | None]:
    return {str(row["feature"]): row["coefficient"] for row in rows}


def test_fit_usage_drain_proxy_recovers_documented_multiplier() -> None:
    rows = [
        _row("baseline", "2026-06-01T00:00:00Z", 0.0, 0.0),
        _row("normal", "2026-06-01T00:01:00Z", 10.0, 10.0),
        _row("base2", "2026-06-01T00:02:00Z", 10.0, 0.0),
        _row("fast", "2026-06-01T00:03:00Z", 35.0, 10.0),
        _row("base3", "2026-06-01T00:04:00Z", 35.0, 0.0),
        _row("mixed-normal", "2026-06-01T00:05:00Z", 35.0, 10.0),
        _row("mixed-fast", "2026-06-01T00:06:00Z", 70.0, 10.0),
    ]
    proxies = {
        "fast": FastProxyAnnotation(label="strong_proxy", timing_confidence="medium"),
        "mixed-fast": FastProxyAnnotation(label="strong_proxy", timing_confidence="medium"),
    }
    spans, _stats = build_usage_delta_spans(rows, fast_proxy_annotations=proxies)

    result = fit_usage_drain_proxy(spans, "strong_only")

    assert result.implied_candidate_multiplier == 2.5
    assert result.documented_weighted_candidate_multiplier == 2.5
    assert result.best_grid_multiplier_by_r2 == 2.5


def test_load_fast_proxy_annotations_and_documented_model_multipliers(tmp_path: Path) -> None:
    proxy_path = tmp_path / "proxy.csv"
    with proxy_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["record_id", "fast_proxy_label", "timing_confidence", "fast_proxy_score"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "abc",
                "fast_proxy_label": "possible_proxy",
                "timing_confidence": "medium",
                "fast_proxy_score": "4",
            }
        )

    annotations = load_fast_proxy_annotations(proxy_path)

    assert annotations["abc"].is_candidate
    assert annotations["abc"].is_high_or_medium
    assert annotations["abc"].score == 4.0
    assert documented_fast_credit_multiplier("gpt-5.5") == 2.5
    assert documented_fast_credit_multiplier("gpt-5.4") == 2.0
    assert documented_fast_credit_multiplier("gpt-5.3-codex") is None


def test_predictive_models_compare_control_families_on_holdout() -> None:
    spans: list[UsageDeltaSpan] = []
    for index in range(70):
        credit = float(1 + (index % 7))
        day_index = index % 7
        weekend_boost = 2.0 if day_index in {5, 6} else 0.0
        delta = 0.75 * credit + weekend_boost
        spans.append(
            UsageDeltaSpan(
                start_event_timestamp=f"2026-06-{1 + (index % 14):02d}T{index % 24:02d}:00:00Z",
                end_event_timestamp=f"2026-06-{1 + (index % 14):02d}T{index % 24:02d}:01:00Z",
                baseline_used_percent=10.0,
                end_used_percent=10.0 + delta,
                delta_usage_percent=delta,
                row_count=1,
                standard_usage_credits=credit,
                non_candidate_standard_credits={"all_candidates": credit},
                candidate_standard_credits={"all_candidates": 0.0},
                documented_fast_weighted_credits={"all_candidates": credit},
                candidate_row_counts={"all_candidates": 0},
                token_totals={
                    "input_tokens": credit * 100,
                    "cached_input_tokens": credit * 20,
                    "uncached_input_tokens": credit * 80,
                    "output_tokens": credit * 10,
                    "reasoning_output_tokens": credit * 2,
                    "total_tokens": credit * 110,
                },
                rate_limit_plan_type="pro",
                rate_limit_limit_id="codex",
            )
        )

    results = fit_predictive_usage_drain_models(spans)
    by_name = {result["name"]: result for result in results}

    assert by_name["baseline_train_mean__interleaved_every_5th"]["holdout"]["r2"] < 0.1
    assert by_name["time_controls__interleaved_every_5th"]["holdout"]["r2"] > 0.9
    assert by_name["time_controls__interleaved_every_5th"]["holdout"]["mae"] < 0.2


def test_causal_baselines_capture_low_delta_regime_shift() -> None:
    spans: list[UsageDeltaSpan] = []
    for index in range(80):
        delta = 6.0 if index < 50 else 1.0
        spans.append(
            UsageDeltaSpan(
                start_event_timestamp=f"2026-06-{1 + (index // 8):02d}T{index % 24:02d}:00:00Z",
                end_event_timestamp=f"2026-06-{1 + (index // 8):02d}T{index % 24:02d}:01:00Z",
                baseline_used_percent=20.0,
                end_used_percent=20.0 + delta,
                delta_usage_percent=delta,
                row_count=1,
                standard_usage_credits=10.0,
                non_candidate_standard_credits={"all_candidates": 10.0},
                candidate_standard_credits={"all_candidates": 0.0},
                documented_fast_weighted_credits={"all_candidates": 10.0},
                candidate_row_counts={"all_candidates": 0},
                rate_limit_plan_type="pro",
                rate_limit_limit_id="codex",
            )
        )

    results = fit_predictive_usage_drain_models(spans)
    by_name = {result["name"]: result for result in results}

    persistence = by_name["persistence_previous_delta__time_ordered_80_20"]["holdout"]
    rolling_mode = by_name["rolling10_mode_delta__time_ordered_80_20"]["holdout"]
    hybrid = by_name["hybrid_streak_regime__time_ordered_80_20"]["holdout"]
    same_bucket_mode = by_name[
        "same_bucket_rolling10_mode_delta__time_ordered_80_20"
    ]["holdout"]
    train_mean = by_name["baseline_train_mean__time_ordered_80_20"]["holdout"]
    assert persistence["mae"] == 0.0
    assert rolling_mode["mae"] == 0.0
    assert hybrid["mae"] == 0.0
    assert same_bucket_mode["mae"] == 0.0
    assert persistence["mae"] < train_mean["mae"]
