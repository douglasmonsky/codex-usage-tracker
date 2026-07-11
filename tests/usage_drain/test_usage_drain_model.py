from __future__ import annotations

import csv
from pathlib import Path

from codex_usage_tracker.usage_drain.model import (
    FastProxyAnnotation,
    UsageDeltaSpan,
    build_usage_delta_spans,
    documented_fast_credit_multiplier,
    fit_predictive_usage_drain_models,
    fit_usage_drain_proxy,
    load_fast_proxy_annotations,
    summarize_usage_drain_model,
)
from tests.usage_drain.model_test_helpers import (
    coefficients_by_feature as _coefficients_by_feature,
)
from tests.usage_drain.model_test_helpers import (
    component_credits as _component_credits,
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
    effort: str | None = "xhigh",
    session_id: str = "session",
    turn_id: str | None = None,
    rate_limit_limit_id: str = "codex",
) -> dict[str, object]:
    output_tokens = reasoning_output_tokens + nonreasoning_output_tokens
    input_tokens = uncached_input_tokens + cached_input_tokens
    return {
        "record_id": record_id,
        "session_id": session_id,
        "turn_id": turn_id if turn_id is not None else record_id,
        "event_timestamp": timestamp,
        "rate_limit_plan_type": "plus",
        "rate_limit_limit_id": rate_limit_limit_id,
        "rate_limit_primary_used_percent": used,
        "rate_limit_primary_window_minutes": window_minutes,
        "rate_limit_primary_resets_at": resets_at,
        "rate_limit_secondary_used_percent": secondary_used,
        "rate_limit_secondary_window_minutes": secondary_window_minutes,
        "rate_limit_secondary_resets_at": secondary_resets_at,
        "usage_credits": credits,
        "model": model,
        "effort": effort,
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
        _row("b", "2026-06-01T00:01:00Z", 10.0, 2.0, turn_id="turn-1"),
        _row("c", "2026-06-01T00:02:00Z", 12.0, 3.0, turn_id="turn-1"),
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
    assert spans[0].effort_counts == {"xhigh": 2}
    assert spans[0].turn_count == 1
    assert spans[0].max_calls_in_turn == 2
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


def test_alternate_codex_limit_rows_count_as_work_but_not_boundaries() -> None:
    rows = [
        _row("a", "2026-06-01T00:00:00Z", 10.0, 1.0),
        _row(
            "bengal",
            "2026-06-01T00:01:00Z",
            0.0,
            5.0,
            rate_limit_limit_id="codex_bengalfox",
        ),
        _row("hold", "2026-06-01T00:02:00Z", 10.0, 2.0),
        _row("close", "2026-06-01T00:03:00Z", 11.0, 3.0),
    ]

    spans, stats = build_usage_delta_spans(rows)

    assert stats["alternate_codex_limit_rows_ignored_for_boundaries"] == 1
    assert stats["rows_without_usage_snapshot"] == 1
    assert stats["positive_usage_spans"] == 1
    assert stats["censored_or_reset_pending_segments"] == 0
    assert len(spans) == 1
    assert spans[0].row_count == 3
    assert spans[0].standard_usage_credits == 10.0
    assert spans[0].rate_limit_limit_id == "codex"


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
    assert (
        "error_by_one_percent_streak" in walk_forward["error_diagnostics"]["hybrid_streak_regime"]
    )
    assert "one_percent_regime_grace" in walk_forward["models"]
    assert summary["span_correlations"]["delta_usage_percent"]["n"] == 6
    assert (
        summary["span_correlations"]["one_percent_span_capacity"]["standard_usage_credits"]["n"]
        == 5
    )
    calibration = summary["walk_forward_prediction"]["one_percent_grace_calibration"]
    assert calibration["default_config"] == {
        "streak_threshold": 10,
        "grace_spans": 1,
        "max_break_delta_percent": 2.0,
    }
    segments = summary["piecewise_regime_segments"]
    assert segments["segment_count"] == 3
    assert segments["latest_segment"]["label"] == "stable_one_percent"
    assert segments["latest_segment"]["span_count"] == 1
    assert segments["longest_segments"][0]["label"] == "stable_one_percent"
    assert segments["longest_segments"][0]["span_count"] == 4
    assert "stable_one_percent" in segments["by_label"]
    adaptation = segments["adaptation_by_position"]
    assert adaptation["position_buckets"] == [
        "first_span",
        "second_span",
        "third_span",
        "fourth_fifth_span",
        "sixth_plus_span",
    ]
    assert adaptation["all_segments"]["first_span"]["prediction_rows"] == 2
    assert adaptation["by_label"]["stable_one_percent"]["first_span"]["prediction_rows"] == 1
    boundaries = segments["boundary_diagnostics"]
    assert boundaries["n"] == 5
    assert boundaries["boundary_count"] == 2
    assert boundaries["boundary_rate"] == 0.4
    assert boundaries["transition_counts"] == [
        {
            "transition": "small_blip->stable_one_percent",
            "count": 1,
            "share": 0.5,
        },
        {
            "transition": "stable_one_percent->small_blip",
            "count": 1,
            "share": 0.5,
        },
    ]
    assert "previous_segment_position_bucket" in boundaries["context_fields"]
    assert "previous_segment_wall_time_bucket" in boundaries["context_fields"]
    assert boundaries["by_context"]["previous_segment_position_bucket"][0] == {
        "previous_segment_position_bucket": "fourth_fifth_span",
        "n": 1,
        "boundary_count": 1,
        "non_boundary_count": 0,
        "boundary_rate": 1.0,
    }
    assert boundaries["by_previous_label"][0] == {
        "previous_label": "small_blip",
        "n": 1,
        "boundary_count": 1,
        "non_boundary_count": 0,
        "boundary_rate": 1.0,
    }
    assert boundaries["after_long_one_percent_run"]["boundary_count"] == 0


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
    boundaries = summary["piecewise_regime_segments"]["boundary_diagnostics"]
    assert boundaries["after_long_one_percent_run"] == {
        "n": 2,
        "boundary_count": 1,
        "non_boundary_count": 1,
        "boundary_rate": 0.5,
    }
    latest = boundaries["latest_boundaries"][0]
    assert latest["previous_segment_position_bucket"] == "first_span"
    assert latest["previous_segment_position"] == 1


def test_boundary_walk_forward_risk_learns_segment_age_pattern() -> None:
    rows = [_row("base", "2026-06-01T00:00:00Z", 0.0, 0.0)]
    used = 0.0
    index = 0
    for _repeat in range(16):
        for delta in (1.0, 1.0, 2.0):
            index += 1
            used += delta
            rows.append(
                _row(
                    f"span-{index}",
                    f"2026-06-01T00:{index:02d}:00Z",
                    used,
                    1.0,
                )
            )

    summary = summarize_usage_drain_model(rows)

    risk = summary["piecewise_regime_segments"]["boundary_diagnostics"]["walk_forward_risk"]
    scope = risk["scopes"]["all_after_10"]
    assert scope["boundary_count"] > 0
    prior = scope["models"]["overall_prior_rate"]
    segment_age = scope["models"]["segment_age_risk"]
    label_segment_age = scope["models"]["label_segment_age_risk"]
    assert segment_age["average_precision"] > prior["average_precision"]
    assert label_segment_age["brier"] == 0.0
    assert label_segment_age["auc"] == 1.0
    diagnostics = scope["risk_detail_diagnostics"]["label_segment_age_risk"]
    assert diagnostics["matched_state_share"] == 1.0
    assert diagnostics["top_signatures"][0]["signature"] == (
        "previous_label,previous_segment_position_bucket"
    )

    delta_prediction = summary["piecewise_regime_segments"]["boundary_diagnostics"][
        "walk_forward_delta_prediction"
    ]
    delta_scope = delta_prediction["scopes"]["all_after_10"]
    previous_delta = delta_scope["models"]["previous_delta"]
    label_segment_age_mode = delta_scope["models"]["label_segment_age_mode"]
    boundary_conditioned = delta_scope["models"]["boundary_conditioned_label_segment_age_mode"]
    adaptive_mae_gate = delta_scope["models"]["adaptive_mae_gate_label_segment_age_mode"]
    adaptive_rmse_gate = delta_scope["models"]["adaptive_rmse_gate_label_segment_age_mode"]
    boundary_conditioned_weighted = delta_scope["models"]["risk_weighted_boundary_conditioned_mode"]
    assert label_segment_age_mode["mae"] == 0.0
    assert label_segment_age_mode["rmse"] == 0.0
    assert label_segment_age_mode["mae"] < previous_delta["mae"]
    assert boundary_conditioned_weighted["mae"] == 0.0
    assert boundary_conditioned_weighted["rmse"] == 0.0
    assert boundary_conditioned["mae"] >= boundary_conditioned_weighted["mae"]
    assert adaptive_mae_gate["mae"] == 0.0
    assert adaptive_rmse_gate["rmse"] == 0.0
    delta_diagnostics = delta_scope["prediction_detail_diagnostics"]["label_segment_age_mode"]
    assert delta_diagnostics["matched_state_share"] == 1.0
    assert delta_diagnostics["top_signatures"][0]["signature"] == (
        "previous_label,previous_segment_position_bucket"
    )
    boundary_conditioned_diagnostics = delta_scope["prediction_detail_diagnostics"][
        "boundary_conditioned_label_segment_age_mode"
    ]
    assert boundary_conditioned_diagnostics["matched_state_share"] > 0.0
    ambiguity = summary["walk_forward_prediction"]["state_ambiguity"]["scopes"]["all_after_10"][
        "signatures"
    ]
    assert ambiguity["previous_delta"]["ambiguous_group_count"] == 1
    assert ambiguity["previous_delta"]["ambiguous_row_share"] > 0.0
    assert ambiguity["history_state"]["ambiguous_group_count"] == 0
    assert ambiguity["history_state"]["repeated_oracle_mode_metrics"]["mae"] == 0.0
    adaptive_diagnostics = delta_scope["risk_gate_diagnostics"][
        "adaptive_mae_gate_label_segment_age_mode"
    ]
    assert adaptive_diagnostics["override_share"] > 0.0
    assert adaptive_diagnostics["mean_threshold"] == 0.55
    previous_delta_residuals = delta_scope["residual_diagnostics"]["previous_delta"]
    boundary_errors = previous_delta_residuals["top_error_groups"]["boundary_state"]
    assert boundary_errors[0]["boundary_state"] == "boundary"
    assert boundary_errors[0]["share_abs_error"] == 1.0
    assert previous_delta_residuals["largest_errors"][0]["boundary_state"] == "boundary"


def test_boundary_delta_risk_gate_keeps_previous_delta_for_stable_regime() -> None:
    rows = [_row("base", "2026-06-01T00:00:00Z", 0.0, 0.0)]
    used = 0.0
    for index, delta in enumerate(([8.0] * 18) + ([9.0] * 18), start=1):
        used += delta
        hour, minute = divmod(index, 60)
        rows.append(
            _row(
                f"span-{index}",
                f"2026-06-01T{hour:02d}:{minute:02d}:00Z",
                used,
                1.0,
            )
        )

    summary = summarize_usage_drain_model(rows)

    delta_scope = summary["piecewise_regime_segments"]["boundary_diagnostics"][
        "walk_forward_delta_prediction"
    ]["scopes"]["all_after_10"]
    previous_delta = delta_scope["models"]["previous_delta"]
    label_segment_age_mode = delta_scope["models"]["label_segment_age_mode"]
    gated = delta_scope["models"]["risk_gated_label_segment_age_mode"]
    weighted = delta_scope["models"]["risk_weighted_label_segment_age_mode"]
    adaptive_mae_gate = delta_scope["models"]["adaptive_mae_gate_label_segment_age_mode"]
    assert gated["mae"] == previous_delta["mae"]
    assert gated["mae"] < label_segment_age_mode["mae"]
    assert weighted["mae"] <= label_segment_age_mode["mae"]
    assert adaptive_mae_gate["mae"] == previous_delta["mae"]
    gate_diagnostics = delta_scope["risk_gate_diagnostics"]["risk_gated_label_segment_age_mode"]
    assert gate_diagnostics["override_share"] == 0.0
    assert gate_diagnostics["source_counts"][0]["source"] == "risk_gate_previous_delta"
    adaptive_diagnostics = delta_scope["risk_gate_diagnostics"][
        "adaptive_mae_gate_label_segment_age_mode"
    ]
    assert adaptive_diagnostics["override_share"] == 0.0
    assert adaptive_diagnostics["source_counts"][0]["source"] == "adaptive_risk_gate_previous_delta"
    previous_delta_residuals = delta_scope["residual_diagnostics"]["previous_delta"]
    boundary_errors = previous_delta_residuals["top_error_groups"]["boundary_state"]
    assert boundary_errors[0]["boundary_state"] == "same_label"
    assert boundary_errors[0]["share_abs_error"] == 1.0
    assert previous_delta_residuals["largest_errors"][0]["boundary_state"] == "same_label"


def test_empirical_state_bucket_predictor_learns_prior_transitions() -> None:
    rows = [_row("base", "2026-06-01T00:00:00Z", 0.0, 0.0)]
    used = 0.0
    for day in range(20):
        for hour, delta in ((0, 1.0), (12, 4.0)):
            used += delta
            rows.append(
                _row(
                    f"span-{day}-{hour}",
                    f"2026-06-{day + 1:02d}T{hour:02d}:00:00Z",
                    used,
                    1.0,
                )
            )

    summary = summarize_usage_drain_model(rows)

    walk_forward = summary["walk_forward_prediction"]["scopes"]["all_after_10"]
    previous = walk_forward["models"]["previous_delta"]
    empirical = walk_forward["models"]["empirical_history_state_mode"]
    adaptive_gate = walk_forward["models"]["adaptive_mae_transition_gate_history_state_mode"]
    assert empirical["mae"] < previous["mae"]
    assert adaptive_gate["mae"] == empirical["mae"]
    assert adaptive_gate["r2"] == empirical["r2"]
    assert (
        walk_forward["state_bucket_diagnostics"]["empirical_history_state_mode"][
            "matched_state_share"
        ]
        > 0.0
    )
    assert "empirical_calendar_state_mode" in walk_forward["models"]
    transition = summary["walk_forward_prediction"]["transition_risk"]["scopes"]["all_after_10"][
        "non_one_percent_delta"
    ]
    assert transition["positive_rate"] > 0.0
    assert (
        transition["models"]["history_state_risk"]["brier"]
        < transition["models"]["overall_prior_rate"]["brier"]
    )
    assert (
        transition["models"]["history_state_risk"]["average_precision"]
        > transition["models"]["overall_prior_rate"]["average_precision"]
    )
    gate = walk_forward["transition_gate_diagnostics"][
        "adaptive_mae_transition_gate_history_state_mode"
    ]
    assert gate["override_share"] == 1.0
    assert gate["mean_threshold"] == 0.0


def test_allowance_breakpoint_analysis_detects_capacity_denominator_change() -> None:
    rows = [_row("base", "2026-06-01T00:00:00Z", 0.0, 0.0)]
    used = 0.0
    index = 0
    for capacity_per_percent in (10.0, 40.0):
        for repeat in range(30):
            index += 1
            delta = 1.0 + float(repeat % 3)
            used += delta
            hour, minute = divmod(index, 60)
            rows.append(
                _row(
                    f"capacity-{index}",
                    f"2026-06-01T{hour:02d}:{minute:02d}:00Z",
                    used,
                    delta * capacity_per_percent,
                )
            )

    summary = summarize_usage_drain_model(rows)

    analysis = summary["allowance_breakpoint_analysis"]
    assert analysis["span_count"] == 60
    assert analysis["piecewise_sse_reduction_share"] == 1.0
    split = analysis["best_single_break"]
    assert split["split_index"] == 30
    assert split["left_mean_credits_per_percent"] == 10.0
    assert split["right_mean_credits_per_percent"] == 40.0
    assert analysis["global_credit_to_delta_fit"]["metrics"]["r2"] < 1.0
    segments = analysis["segments"]
    assert len(segments) == 2
    assert segments[0]["credits_per_visible_percent"]["mean"] == 10.0
    assert segments[1]["credits_per_visible_percent"]["mean"] == 40.0
    assert segments[0]["credit_to_delta_fit"]["metrics"]["r2"] == 1.0
    assert segments[1]["credit_to_delta_fit"]["metrics"]["r2"] == 1.0
    piecewise = analysis["piecewise_credit_to_delta_fit"]["models"]
    assert (
        piecewise["global_no_intercept_credit_slope"]["metrics"]["r2"]
        == analysis["global_credit_to_delta_fit"]["metrics"]["r2"]
    )
    assert piecewise["piecewise_mean_capacity_denominator"]["metrics"]["r2"] == 1.0
    assert piecewise["piecewise_ceiling_mean_capacity_denominator"]["metrics"]["r2"] == 1.0
    assert piecewise["piecewise_leave_one_out_capacity_denominator"]["metrics"]["r2"] == 1.0
    assert piecewise["piecewise_no_intercept_credit_slope"]["metrics"]["r2"] == 1.0
    assert piecewise["piecewise_ceiling_no_intercept_credit_slope"]["metrics"]["r2"] == 1.0
    online = analysis["online_capacity_credit_to_delta_fit"]
    assert online["prediction_rows"] == 59
    previous = online["models"]["previous_capacity_denominator"]
    assert previous["metrics"]["mae"] == 0.050847
    breakpoint_diagnostics = previous["known_breakpoint_diagnostics"]
    assert breakpoint_diagnostics["known_breakpoint_row_count"] == 1
    assert breakpoint_diagnostics["known_breakpoint_abs_error_share"] == 1.0
    assert breakpoint_diagnostics["non_breakpoint_mae"] == 0.0


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
    unweighted = regression["variants"]["unweighted"]["credit_accounting"]["no_intercept"]["all"]
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
    raw_rows = [_row("baseline", "2026-06-01T00:00:00Z", 0.0, 0.0)]
    used = 0.0
    for index in range(70):
        credit = float(1 + (index % 7))
        day_index = index % 7
        weekend_boost = 2.0 if day_index in {5, 6} else 0.0
        delta = 0.75 * credit + weekend_boost
        timestamp = f"2026-06-{1 + (index % 14):02d}T{index % 24:02d}:00:00Z"
        spans.append(
            UsageDeltaSpan(
                start_event_timestamp=timestamp,
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
        used += delta
        raw_rows.append(
            _row(
                f"delta-{index}",
                timestamp,
                used,
                credit,
                uncached_input_tokens=int(credit * 100),
                cached_input_tokens=int(credit * 20),
                reasoning_output_tokens=int(credit * 2),
                nonreasoning_output_tokens=int(credit * 8),
            )
        )

    results = fit_predictive_usage_drain_models(spans)
    by_name = {result["name"]: result for result in results}

    assert by_name["baseline_train_mean__interleaved_every_5th"]["holdout"]["r2"] < 0.1
    assert "turn_batching__interleaved_every_5th" in by_name
    assert "effort_controls__interleaved_every_5th" in by_name
    assert "online_capacity_controls__interleaved_every_5th" in by_name
    assert by_name["time_controls__interleaved_every_5th"]["holdout"]["r2"] > 0.9
    assert by_name["time_controls__interleaved_every_5th"]["holdout"]["mae"] < 0.2

    summary = summarize_usage_drain_model(raw_rows)
    attribution = summary["predictive_modeling"]["feature_family_attribution"]["sequences"]
    rows = attribution["cost_and_time_controls"]["interleaved_every_5th"]
    by_family = {row["family"]: row for row in rows}
    assert "cyclic time" in by_family
    assert by_family["cyclic time"]["mae_improvement_vs_previous"] > 0.0
    assert "history/regime" in {
        row["family"] for row in attribution["history_regime_controls"]["interleaved_every_5th"]
    }


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
    same_bucket_mode = by_name["same_bucket_rolling10_mode_delta__time_ordered_80_20"]["holdout"]
    train_mean = by_name["baseline_train_mean__time_ordered_80_20"]["holdout"]
    assert persistence["mae"] == 0.0
    assert rolling_mode["mae"] == 0.0
    assert hybrid["mae"] == 0.0
    assert same_bucket_mode["mae"] == 0.0
    assert persistence["mae"] < train_mean["mae"]
