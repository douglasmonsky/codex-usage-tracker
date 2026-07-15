from datetime import datetime, timezone

from codex_usage_tracker.allowance_intelligence.cycles import (
    derive_allowance_cycles,
    observed_plan_type,
    select_allowance_cohort,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_observed_plan_type_is_explicit_and_conservative():
    assert observed_plan_type([{"plan_type": "pro"}, {"plan_type": "PRO"}]) == "pro"
    assert observed_plan_type([{"plan_type": "Pro Lite"}, {"plan_type": "pro-lite"}]) == "prolite"
    assert observed_plan_type([{"plan_type": None}, {"plan_type": "prolite"}]) == "prolite"
    assert observed_plan_type([{"plan_type": "pro"}, {"plan_type": "prolite"}]) == "mixed"
    assert observed_plan_type([{"plan_type": None}]) == "unknown"


def _row(name, used, reset, when, **extra):
    return {
        "observation_id": name,
        "record_id": name,
        "event_timestamp": when,
        "window_kind": "weekly",
        "window_key": "primary",
        "limit_id": "codex",
        "used_percent": used,
        "resets_at": reset,
        "cumulative_total_tokens": extra.pop("tokens", 1),
        **extra,
    }


def test_reset_jitter_coalesces_and_intervals_do_not_cross_reset():
    rows = [
        _row("one", 10, 2_000_000_000, "2025-12-31T23:58:00Z"),
        _row("two", 12, 2_000_000_030, "2025-12-31T23:59:00Z", tokens=2),
        _row("three", 1, 2_000_001_000, "2026-01-01T00:00:00Z", tokens=3),
    ]
    cycles, intervals = derive_allowance_cycles(rows, now=NOW)
    assert len(cycles) == 2
    assert cycles[0].reset_at == 2_000_000_015
    assert all(interval.cycle_id == cycles[0].cycle_id for interval in intervals)


def test_interleaved_reset_observations_coalesce_by_reset_identity():
    rows = [
        _row("first-a", 10, 2_000_000_000, "2025-12-31T23:56:00Z"),
        _row("first-b", 1, 2_000_001_000, "2025-12-31T23:57:00Z", tokens=2),
        _row("second-a", 12, 2_000_000_000, "2025-12-31T23:58:00Z", tokens=3),
        _row("second-b", 3, 2_000_001_000, "2025-12-31T23:59:00Z", tokens=4),
    ]

    cycles, intervals = derive_allowance_cycles(rows, now=NOW)

    assert len(cycles) == 2
    assert {
        cycle.reset_at: [row["observation_id"] for row in cycle.observations]
        for cycle in cycles
    } == {
        2_000_000_000: ["first-a", "second-a"],
        2_000_001_000: ["first-b", "second-b"],
    }
    assert len(intervals) == 2
    assert all(interval.start["resets_at"] == interval.end["resets_at"] for interval in intervals)


def test_weekly_decrease_is_censored_but_five_hour_rolling_decrease_is_not():
    weekly = [
        _row("one", 20, 2_000_000_000, "2025-12-31T23:58:00Z"),
        _row("two", 10, 2_000_000_000, "2025-12-31T23:59:00Z"),
    ]
    _, intervals = derive_allowance_cycles(weekly, now=NOW)
    assert intervals[0].censor_reason == "weekly_reversal"
    for row in weekly:
        row["window_kind"] = "five_hour"
    _, intervals = derive_allowance_cycles(weekly, now=NOW)
    assert intervals == []


def test_conflicts_and_archive_scopes_never_join():
    rows = [
        _row("one", 10, 2_000_000_000, "2025-12-31T23:58:00Z"),
        _row("two", 12, 2_000_000_000, "2025-12-31T23:58:00Z"),
        _row("archive", 20, 2_000_000_000, "2025-12-31T23:59:00Z", is_archived=1),
    ]
    cycles, intervals = derive_allowance_cycles(rows, now=NOW)
    assert cycles[0].status == "ambiguous"
    assert all(not cycle.cohort.is_archived for cycle in cycles)
    assert all(not interval.start.get("is_archived", False) for interval in intervals)


def test_constant_zero_alternate_does_not_replace_fresh_codex():
    rows = [_row("normal", 10, 2_000_000_000, "2025-12-31T23:59:00Z")]
    rows += [
        _row(str(i), 0, 2_000_000_000, "2025-12-31T23:59:00Z", limit_id="alternate")
        for i in range(3)
    ]
    assert select_allowance_cohort(rows, now=NOW).key == "codex"


def test_stale_normal_requires_per_cycle_alternate_evidence():
    rows = [_row("normal", 10, 1, "2025-12-31T00:00:00Z")]
    rows += [
        _row(f"alt-{index}", float(index), reset, "2025-12-31T23:59:00Z", limit_id="alternate")
        for index, reset in enumerate((2_000_000_000, 2_000_000_000, 2_000_000_100, 2_000_000_100))
    ]
    assert select_allowance_cohort(rows, now=NOW) is None
    rows = [
        _row(f"zero-{index}", 0, 2_000_000_000, "2025-12-31T23:59:00Z", limit_id="alternate")
        for index in range(3)
    ]
    assert select_allowance_cohort(rows, now=NOW) is None


def test_existing_reset_identity_and_missing_metadata_are_conservative():
    rows = [
        _row("one", 10, 2_000_000_030, "2025-12-31T23:58:00Z"),
        _row("two", 12, 2_000_000_030, "2025-12-31T23:59:00Z", tokens=2),
    ]
    cycles, _ = derive_allowance_cycles(rows, now=NOW, existing_reset_epochs=[2_000_000_000])
    assert cycles[0].reset_at == 2_000_000_000
    for row in rows:
        row["resets_at"] = None
    cycles, intervals = derive_allowance_cycles(rows, now=NOW)
    assert cycles[0].status == "ambiguous"
    assert intervals[0].censor_reason == "missing_reset_metadata"
    assert not intervals[0].eligible_for_interpolation


def test_existing_epochs_are_scoped_by_archive_window_and_cohort():
    rows = [_row("one", 10, 2_000_000_030, "2025-12-31T23:58:00Z")]
    cycles, _ = derive_allowance_cycles(
        rows,
        now=NOW,
        existing_reset_epochs={(True, "weekly", "primary", "codex"): [2_000_000_000]},
    )
    assert cycles[0].reset_at == 2_000_000_030


def test_weekly_cycle_states_come_from_reset_chronology():
    rows = [
        _row("past", 20, 1_767_225_000, "2025-12-31T22:00:00Z"),
        _row("open", 2, 2_000_000_000, "2025-12-31T23:59:00Z"),
    ]
    cycles, _ = derive_allowance_cycles(rows, now=NOW)
    assert [cycle.status for cycle in cycles] == ["completed", "open"]
