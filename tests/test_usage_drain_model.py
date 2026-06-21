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
) -> dict[str, object]:
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
    same_bucket_mode = by_name[
        "same_bucket_rolling10_mode_delta__time_ordered_80_20"
    ]["holdout"]
    train_mean = by_name["baseline_train_mean__time_ordered_80_20"]["holdout"]
    assert persistence["mae"] == 0.0
    assert rolling_mode["mae"] == 0.0
    assert same_bucket_mode["mae"] == 0.0
    assert persistence["mae"] < train_mean["mae"]
