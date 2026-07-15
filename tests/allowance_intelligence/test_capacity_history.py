from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from codex_usage_tracker.allowance_intelligence.capacity_history import (
    build_capacity_history,
    load_capacity_cycles,
)
from codex_usage_tracker.store.schema import init_db

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def _cycles(
    values: list[float], *, plan_types: list[str] | None = None
) -> list[dict[str, object]]:
    return [
        {
            "cycle_id": f"cycle-{index}",
            "last_observed_at": (NOW + timedelta(days=index)).isoformat(),
            "credits_per_percent": value,
            "status": "completed",
            "quality_grade": "high",
            "price_coverage": 1.0,
            "conflict_count": 0,
            "plan_type": plan_types[index] if plan_types else "pro",
        }
        for index, value in enumerate(values)
    ]


def test_capacity_history_gives_each_completed_cycle_one_vote() -> None:
    history = build_capacity_history(
        _cycles([100.0, 120.0, 900.0, 110.0]),
        granularity="cycle",
        trailing_window=8,
    )

    assert [row["credits_per_percent"] for row in history["points"]] == [
        100.0,
        120.0,
        900.0,
        110.0,
    ]
    assert history["points"][-1]["rolling_median"] == 115.0
    assert history["eligible_cycle_count"] == 4
    assert history["plan_types"] == ["pro"]


def test_capacity_history_calculates_trailing_statistics_within_each_plan_type() -> None:
    history = build_capacity_history(
        _cycles(
            [100.0, 10.0, 110.0, 20.0, 120.0, 30.0, 130.0, 40.0],
            plan_types=["pro", "prolite", "pro", "prolite", "pro", "prolite", "pro", "prolite"],
        ),
        granularity="cycle",
    )

    assert history["plan_types"] == ["pro", "prolite"]
    assert history["points"][-2]["rolling_median"] == 115.0
    assert history["points"][-1]["rolling_median"] == 25.0
    assert [row["plan_type"] for row in history["points"]] == [
        "pro",
        "prolite",
        "pro",
        "prolite",
        "pro",
        "prolite",
        "pro",
        "prolite",
    ]


def test_capacity_history_discloses_tukey_outliers_without_dropping_them() -> None:
    history = build_capacity_history(
        _cycles([90.0, 95.0, 100.0, 105.0, 1_000.0]),
        granularity="cycle",
    )

    assert len(history["points"]) == 5
    assert history["clipped_point_count"] == 1
    assert history["robust_domain"]["mode"] == "tukey_1_5_iqr"
    assert history["robust_domain"]["max"] == 120.0


def test_capacity_history_excludes_cycles_that_cannot_support_capacity() -> None:
    cycles = _cycles([100.0, 110.0, 120.0, 130.0])
    cycles[0]["status"] = "open"
    cycles[1]["quality_grade"] = "low"
    cycles[2]["price_coverage"] = 0.94
    cycles[3]["conflict_count"] = 1

    history = build_capacity_history(cycles, granularity="cycle")

    assert history["points"] == []
    assert history["eligible_cycle_count"] == 0


def test_load_capacity_cycles_returns_one_aggregate_ratio_per_cycle() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    connection.execute(
        """INSERT INTO allowance_cycles
        (cycle_id,window_kind,window_key,cohort_key,is_archived,last_observed_at,
         quality_grade,status,cycle_state,price_coverage,conflict_count,plan_type,
         source_revision,model_version)
        VALUES ('cycle-1','weekly','primary','codex',0,?,'high','completed',
                'completed',1.0,0,'pro','revision-1','reset-aware-v2')""",
        (NOW.isoformat(),),
    )
    for index, (movement, credits) in enumerate(((2.0, 200.0), (3.0, 450.0))):
        connection.execute(
            """INSERT INTO allowance_intervals
            (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,
             visible_percent_delta,estimated_credits,point_kind,
             eligible_for_change_detection,source_revision,model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"interval-{index}",
                "cycle-1",
                "weekly",
                "primary",
                "codex",
                0,
                movement,
                credits,
                "positive",
                1,
                "revision-1",
                "reset-aware-v2",
            ),
        )

    rows = load_capacity_cycles(
        connection,
        source_revision="revision-1",
        archive_scope="active",
        window_kind="weekly",
        cohort_key="codex",
    )

    assert len(rows) == 1
    assert rows[0]["credits_per_percent"] == 130.0
    assert rows[0]["plan_type"] == "pro"
