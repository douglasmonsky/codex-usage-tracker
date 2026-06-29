from codex_usage_tracker.usage_drain_state_diagnostics import (
    state_ambiguous_group_record,
)


def test_state_ambiguous_group_record_preserves_summary_contract() -> None:
    rows = [
        {"actual": 1.0, "metadata": {"date": "2026-06-02"}},
        {"actual": 2.0, "metadata": {"date": "2026-06-03"}},
        {"actual": 1.0, "metadata": {"date": "2026-06-01"}},
    ]

    record = state_ambiguous_group_record(
        ("previous:1", "same:long"),
        rows,
        signature=("previous_delta_bucket", "same_delta_streak_bucket", "missing"),
        mode_value=1.0,
    )

    assert record["state"] == {
        "previous_delta_bucket": "previous:1",
        "same_delta_streak_bucket": "same:long",
        "missing": "missing",
    }
    assert record["n"] == 3
    assert record["actual_values"] == [
        {"delta_percent": 1.0, "count": 2, "share": 0.666667},
        {"delta_percent": 2.0, "count": 1, "share": 0.333333},
    ]
    assert record["mode_delta_percent"] == 1.0
    assert record["mode_share"] == 0.666667
    assert record["oracle_mae"] == 0.333333
    assert record["total_abs_error"] == 1.0
    assert record["first_date"] == "2026-06-01"
    assert record["last_date"] == "2026-06-03"
