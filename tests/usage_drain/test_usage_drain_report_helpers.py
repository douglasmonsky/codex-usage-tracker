from __future__ import annotations

from codex_usage_tracker.usage_drain.reports import _best_allowance_split


def test_best_allowance_split_selects_the_strongest_capacity_change() -> None:
    rows = [
        {
            "credits_per_visible_percent": 10.0 if index < 15 else 40.0,
            "start_event_timestamp": f"start-{index:02d}",
            "end_event_timestamp": f"end-{index:02d}",
        }
        for index in range(30)
    ]

    split = _best_allowance_split(rows)

    assert split is not None
    assert split["split_index"] == 15
    assert split["left_mean_credits_per_percent"] == 10.0
    assert split["right_mean_credits_per_percent"] == 40.0
