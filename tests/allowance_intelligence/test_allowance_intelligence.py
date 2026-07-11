from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.allowance_intelligence import (
    build_allowance_analysis,
    build_allowance_export_report,
)
from codex_usage_tracker.store.api import (
    query_allowance_observations,
    upsert_usage_events,
)
from tests.store_dashboard_helpers import _usage_event


def test_allowance_observations_normalize_primary_and_secondary_windows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id="rec-1",
                session_id="session-1",
                thread_key="thread:allowance",
                event_timestamp="2026-06-01T00:00:00Z",
                cumulative_total_tokens=100,
                rate_limit_plan_type="pro",
                rate_limit_limit_id="codex",
                rate_limit_primary_used_percent=35.0,
                rate_limit_primary_window_minutes=10080,
                rate_limit_primary_resets_at=1000,
                rate_limit_secondary_used_percent=12.0,
                rate_limit_secondary_window_minutes=300,
                rate_limit_secondary_resets_at=2000,
            )
        ],
        db_path=db_path,
    )

    rows = query_allowance_observations(db_path=db_path, limit=None)

    assert [row["window_kind"] for row in rows] == ["weekly", "five_hour"]
    assert rows[0]["remaining_percent"] == 65.0
    assert rows[1]["remaining_percent"] == 88.0


def test_weekly_stable_allowance_does_not_flag_regime_change() -> None:
    analysis = build_allowance_analysis(
        [
            _analysis_row("r0", 10.0, 0.0),
            _analysis_row("r1", 11.0, 100.0),
            _analysis_row("r2", 12.0, 100.0),
            _analysis_row("r3", 13.0, 100.0),
            _analysis_row("r4", 14.0, 100.0),
        ]
    )

    assert analysis["summary"]["primary_evidence_grade"] == "no_change_detected"
    assert analysis["summary"]["candidate_change_count"] == 0


def test_weekly_capacity_drop_with_thin_baseline_is_not_promoted() -> None:
    analysis = build_allowance_analysis(
        [
            _analysis_row("r0", 10.0, 0.0),
            _analysis_row("r1", 11.0, 100.0),
            _analysis_row("r2", 12.0, 100.0),
            _analysis_row("r3", 13.0, 50.0),
            _analysis_row("r4", 14.0, 50.0),
            _analysis_row("r5", 15.0, 50.0),
        ]
    )

    assert analysis["summary"]["primary_evidence_grade"] == "no_change_detected"
    assert analysis["summary"]["candidate_change_count"] == 0
    assert analysis["change_candidates"] == []


def test_weekly_capacity_drop_flags_strong_local_evidence_after_baseline() -> None:
    rows = [_analysis_row("r0", 10.0, 0.0)]
    rows.extend(_analysis_row(f"r{index}", 10.0 + index, 100.0) for index in range(1, 7))
    rows.extend(_analysis_row(f"r{index}", 10.0 + index, 50.0) for index in range(7, 10))

    analysis = build_allowance_analysis(rows)

    assert analysis["summary"]["primary_evidence_grade"] == "strong_local_evidence"
    assert analysis["summary"]["candidate_change_count"] == 1
    candidate = analysis["change_candidates"][0]
    assert candidate["previous_span_count"] == 6
    assert candidate["capacity_ratio"] == 0.5
    assert candidate["recent_span_count"] == 3
    assert candidate["statistical_evidence"]["method"] == "exact_permutation_mean_shift"
    assert candidate["statistical_evidence"]["effect_size_cliffs_delta"] == -1.0
    assert candidate["statistical_evidence"]["signal"] == "directionally_consistent_small_sample"
    assert candidate["statistical_evidence"][
        "median_confidence_interval_before_95"
    ]["available"]
    assert not candidate["statistical_evidence"][
        "median_confidence_interval_after_95"
    ]["available"]
    assert not analysis["summary"]["research_readiness"]["ready_for_public_claim"]


def test_larger_consistent_weekly_shift_is_public_claim_ready() -> None:
    rows = [_analysis_row("r0", 10.0, 0.0)]
    rows.extend(_analysis_row(f"r{index}", 10.0 + index, 100.0) for index in range(1, 7))
    rows.extend(_analysis_row(f"r{index}", 10.0 + index, 50.0) for index in range(7, 13))

    analysis = build_allowance_analysis(rows)

    candidate = analysis["change_candidates"][0]
    statistical_evidence = candidate["statistical_evidence"]
    assert candidate["previous_span_count"] == 6
    assert candidate["recent_span_count"] == 6
    assert statistical_evidence["signal"] == "strong_nonparametric_shift"
    assert statistical_evidence["p_value_one_sided"] <= 0.05
    assert statistical_evidence["median_confidence_interval_before_95"] == {
        "method": "exact_binomial_order_statistic",
        "confidence_level": 0.95,
        "sample_size": 6,
        "available": True,
        "low": 100.0,
        "high": 100.0,
        "achieved_coverage": 0.96875,
    }
    assert statistical_evidence["median_confidence_interval_after_95"] == {
        "method": "exact_binomial_order_statistic",
        "confidence_level": 0.95,
        "sample_size": 6,
        "available": True,
        "low": 50.0,
        "high": 50.0,
        "achieved_coverage": 0.96875,
    }
    assert analysis["summary"]["research_readiness"]["ready_for_public_claim"]


def test_five_hour_shift_is_downgraded_as_counter_noise() -> None:
    analysis = build_allowance_analysis(
        [
            _analysis_row("r0", 10.0, 0.0, window_kind="five_hour"),
            _analysis_row("r1", 11.0, 100.0, window_kind="five_hour"),
            _analysis_row("r2", 12.0, 100.0, window_kind="five_hour"),
            _analysis_row("r3", 13.0, 50.0, window_kind="five_hour"),
            _analysis_row("r4", 14.0, 50.0, window_kind="five_hour"),
        ]
    )

    assert analysis["summary"]["primary_evidence_grade"] == "counter_noise_likely"
    assert analysis["summary"]["candidate_change_count"] == 0


def test_strict_export_omits_local_identifiers(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id="secret-record",
                session_id="secret-session",
                thread_key="thread:private",
                event_timestamp="2026-06-01T00:00:00Z",
                cumulative_total_tokens=100,
                rate_limit_plan_type="pro",
                rate_limit_limit_id="codex",
                rate_limit_primary_used_percent=10.0,
                rate_limit_primary_window_minutes=10080,
                rate_limit_primary_resets_at=1000,
            ),
            _usage_event(
                record_id="secret-record-2",
                session_id="secret-session",
                thread_key="thread:private",
                event_timestamp="2026-06-01T00:01:00Z",
                cumulative_total_tokens=200,
                rate_limit_plan_type="pro",
                rate_limit_limit_id="codex",
                rate_limit_primary_used_percent=11.0,
                rate_limit_primary_window_minutes=10080,
                rate_limit_primary_resets_at=1000,
            ),
        ],
        db_path=db_path,
    )

    payload = build_allowance_export_report(db_path=db_path).payload
    encoded = json.dumps(payload)

    assert payload["schema"] == "codex-usage-tracker-allowance-evidence-export-v1"
    assert payload["privacy_mode"] == "strict"
    assert "secret-record" not in encoded
    assert "secret-session" not in encoded
    assert "/tmp/synthetic" not in encoded
    assert "thread:private" not in encoded


def _analysis_row(
    record_id: str,
    used_percent: float,
    usage_credits: float,
    *,
    window_kind: str = "weekly",
) -> dict[str, object]:
    row_index = int("".join(character for character in record_id if character.isdigit()) or "0")
    return {
        "record_id": record_id,
        "event_timestamp": f"2026-06-01T00:{row_index:02d}:00Z",
        "window_key": "primary",
        "window_kind": window_kind,
        "window_minutes": 10080 if window_kind == "weekly" else 300,
        "used_percent": used_percent,
        "plan_type": "pro",
        "limit_id": "codex",
        "usage_credits": usage_credits,
        "usage_credit_confidence": "exact",
        "cumulative_total_tokens": row_index * 100,
    }
