from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from codex_usage_tracker.allowance_intelligence import analysis
from codex_usage_tracker.store.schema import init_db

NOW = datetime(2026, 6, 12, tzinfo=timezone.utc)


def _connection(values: list[float] | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    connection.execute(
        "INSERT INTO allowance_source_state VALUES "
        "(1,1,'revision-1',12,'2026-06-12T00:00:00+00:00','reset-aware-v2',"
        "'2026-06-12T00:00:00+00:00')"
    )
    for index, value in enumerate(values or [10, 9, 11, 10, 30, 29, 31, 30]):
        cycle_id = f"cycle-{index:02d}"
        observed_at = f"2026-06-{index + 1:02d}T00:00:00+00:00"
        connection.execute(
            """INSERT INTO allowance_cycles
            (cycle_id,window_kind,window_key,cohort_key,is_archived,reset_at,
             first_observed_at,last_observed_at,quality_grade,status,cycle_state,
             price_coverage,conflict_count,source_revision,model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cycle_id,
                "weekly",
                "primary",
                "codex",
                0,
                1_800_000_000 + index,
                observed_at,
                observed_at,
                "high",
                "completed",
                "completed",
                1.0,
                0,
                "revision-1",
                "reset-aware-v2",
            ),
        )
        connection.execute(
            """INSERT INTO allowance_intervals
            (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,
             start_observed_at,end_observed_at,visible_percent_delta,estimated_credits,
             price_coverage,confidence,point_kind,eligible_for_change_detection,
             source_revision,model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"interval-{index:02d}",
                cycle_id,
                "weekly",
                "primary",
                "codex",
                0,
                observed_at,
                observed_at,
                10.0,
                value * 10,
                1.0,
                1.0,
                "positive",
                1,
                "revision-1",
                "reset-aware-v2",
            ),
        )
    return connection


def test_identical_semantic_key_reuses_persisted_snapshot(monkeypatch) -> None:
    connection = _connection()
    assert analysis.read_allowance_analysis(
        connection,
        rate_card_revision="rate-card-1",
        parameters={"min_cycles_per_regime": 4, "permutation_count": 499},
    ) is None
    calls = 0
    real_detect = analysis.detect_cycle_changes

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_detect(*args, **kwargs)

    monkeypatch.setattr(analysis, "detect_cycle_changes", counted)
    request = {
        "rate_card_revision": "rate-card-1",
        "archive_scope": "active",
        "window_kind": "weekly",
        "cohort_key": "codex",
        "forecast_horizon": 1,
        "parameters": {"min_cycles_per_regime": 4, "permutation_count": 499},
        "now": NOW,
    }
    first = analysis.build_allowance_analysis(connection, **request)
    second = analysis.build_allowance_analysis(connection, **request)
    assert first == second
    assert analysis.read_allowance_analysis(
        connection,
        rate_card_revision="rate-card-1",
        parameters={"min_cycles_per_regime": 4, "permutation_count": 499},
    ) == first
    assert calls == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM allowance_analysis_snapshots"
    ).fetchone()[0] == 1
    assert first["source_revision"] == "revision-1"
    assert first["rate_card_revision"] == "rate-card-1"
    assert first["generated_at"] == NOW.isoformat()
    assert first["data_as_of"] == NOW.isoformat()


def test_rate_card_or_parameters_change_the_snapshot_key() -> None:
    connection = _connection()
    first = analysis.build_allowance_analysis(
        connection,
        rate_card_revision="rate-card-1",
        parameters={"min_cycles_per_regime": 4, "permutation_count": 199},
        now=NOW,
    )
    second = analysis.build_allowance_analysis(
        connection,
        rate_card_revision="rate-card-2",
        parameters={"min_cycles_per_regime": 4, "permutation_count": 199},
        now=NOW,
    )
    third = analysis.build_allowance_analysis(
        connection,
        rate_card_revision="rate-card-2",
        parameters={"min_cycles_per_regime": 4, "permutation_count": 299},
        now=NOW,
    )
    assert len({first["snapshot_id"], second["snapshot_id"], third["snapshot_id"]}) == 3
    assert connection.execute(
        "SELECT COUNT(*) FROM allowance_analysis_snapshots"
    ).fetchone()[0] == 3


@pytest.mark.parametrize(
    "parameters",
    [
        {"min_cycles_per_regime": 1},
        {"permutation_count": 98},
        {"permutation_count": 100_001},
        {"familywise_alpha": 0},
        {"familywise_alpha": 1},
        {"unknown": 1},
    ],
)
def test_analysis_parameters_are_bounded(
    parameters: dict[str, int | float],
) -> None:
    with pytest.raises(ValueError):
        analysis.read_allowance_analysis(
            _connection(),
            rate_card_revision="rate-card-1",
            parameters=parameters,
        )


def test_analysis_persists_multiple_boundaries_and_regimes() -> None:
    connection = _connection(([300.0] * 8) + ([100.0] * 8) + ([220.0] * 8))

    result = analysis.build_allowance_analysis(
        connection,
        rate_card_revision="rate-card-1",
        parameters={"min_cycles_per_regime": 4, "permutation_count": 499},
        now=NOW,
    )
    persisted = analysis.read_allowance_analysis(
        connection,
        rate_card_revision="rate-card-1",
        parameters={"min_cycles_per_regime": 4, "permutation_count": 499},
    )

    assert len(result["boundaries"]) == 2
    assert len(result["regimes"]) == 3
    assert persisted is not None
    assert persisted["boundaries"] == result["boundaries"]
    assert result["selected_boundary"] is None
