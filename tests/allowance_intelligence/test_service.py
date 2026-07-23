from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from codex_usage_tracker.allowance_intelligence.service import (
    build_allowance_evidence,
    build_allowance_series,
    build_allowance_status,
)
from codex_usage_tracker.store.schema import init_db

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


@pytest.fixture
def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO allowance_source_state VALUES (1, 1, 'r1', 2, '2026-07-15T11:58:00+00:00', 'reset-aware-v2', '2026-07-15T12:00:00+00:00')")
    conn.executemany(
        """INSERT INTO allowance_cycles (cycle_id,window_kind,window_key,cohort_key,is_archived,reset_at,first_observed_at,last_observed_at,latest_used_percent,observation_count,canonical_observation_count,canonical_tokens,price_coverage,quality_grade,status,cycle_state,source_revision,model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [("week", "weekly", "primary", "codex", 0, 1784145600, "2026-07-15T10:00:00+00:00", "2026-07-15T11:58:00+00:00", 40, 2, 2, 100, 0.8, "high", "open", "open", "r1", "reset-aware-v2"), ("five", "five_hour", "secondary", "codex", 0, 1784116800, "2026-07-15T11:57:00+00:00", "2026-07-15T11:58:00+00:00", 10, 2, 2, 50, None, "high", "open", "open", "r1", "reset-aware-v2")],
    )
    conn.execute("INSERT INTO allowance_intervals (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,end_observed_at,end_used_percent,point_kind,source_revision,model_version) VALUES ('i1','week','weekly','primary','codex',0,'2026-07-15T11:58:00+00:00',40,'positive','r1','reset-aware-v2')")
    return conn


def test_status_schema_freshness_and_matching_revision_are_compact(connection: sqlite3.Connection) -> None:
    connection.execute("UPDATE allowance_cycles SET plan_type = 'pro' WHERE cycle_id = 'week'")
    payload = build_allowance_status(connection, now=NOW, privacy_mode="strict")
    assert payload["schema"] == "codex-usage-tracker-allowance-status-v2"
    assert payload["weekly"]["freshness"] == "fresh"
    assert payload["weekly"]["plan_type"] == "pro"
    assert payload["five_hour"]["freshness"] == "fresh"
    assert payload["next"]["poll_after_seconds"] == 30
    assert build_allowance_status(connection, now=NOW, since_revision="r1") == {
        "schema": payload["schema"],
        "revision": "r1",
        "changed": False,
        "quality": {"canonical": True, "copied_rows_excluded": 0},
        "next": {"action": "poll_status", "poll_after_seconds": 60},
    }


def test_status_exposes_versioned_weekly_estimation_without_changing_observations(
    connection: sqlite3.Connection,
) -> None:
    payload = build_allowance_status(connection, now=NOW)
    assert payload["weekly"]["used_percent"] == 40
    assert payload["estimation"]["model_version"] == "reset-aware-v2"
    assert payload["estimation"]["window_kind"] == "weekly"
    assert payload["estimation"]["forecast"]["used_percent"] is None


def test_status_can_skip_historical_estimation_for_first_paint(
    connection: sqlite3.Connection,
) -> None:
    payload = build_allowance_status(connection, now=NOW, include_estimation=False)

    assert payload["weekly"]["used_percent"] == 40
    assert "estimation" not in payload


def test_status_omits_historical_reconstructions_from_polling_payload(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        "UPDATE allowance_intervals SET eligible_for_calibration = 1, "
        "estimated_credits = 4, price_coverage = 1, start_used_percent = 39 "
        "WHERE interval_id = 'i1'"
    )
    payload = build_allowance_status(connection, now=NOW)

    assert payload["estimation"]["reconstructions"] == []


def test_copied_row_diagnostic_respects_archive_scope(connection: sqlite3.Connection) -> None:
    values = (
        "duplicate", "session", "2026-07-15T11:00:00+00:00", "/synthetic/log.jsonl",
        1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 1,
    )
    sql = """INSERT INTO usage_events (
        record_id, session_id, event_timestamp, source_file, line_number,
        input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens,
        total_tokens, cumulative_input_tokens, cumulative_cached_input_tokens,
        cumulative_output_tokens, cumulative_reasoning_output_tokens,
        cumulative_total_tokens, uncached_input_tokens, cache_ratio,
        reasoning_output_ratio, context_window_percent, is_duplicate, is_archived
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    connection.execute(sql, (*values, 0))
    connection.execute(sql, ("archived-duplicate", *values[1:], 1))

    assert build_allowance_status(connection, now=NOW)["quality"]["copied_rows_excluded"] == 1
    assert build_allowance_status(connection, now=NOW, include_archived=True)["quality"]["copied_rows_excluded"] == 2


def test_status_aging_and_reset_make_observation_stale(connection: sqlite3.Connection) -> None:
    assert build_allowance_status(connection, now=datetime(2026, 7, 15, 17, tzinfo=timezone.utc))["weekly"]["freshness"] == "aging"
    assert build_allowance_status(connection, now=datetime(2026, 7, 15, 18, 1, tzinfo=timezone.utc))["weekly"]["freshness"] == "stale"
    connection.execute("UPDATE allowance_cycles SET reset_at = 1 WHERE cycle_id = 'week'")
    assert build_allowance_status(connection, now=NOW)["weekly"]["freshness"] == "stale"


def test_series_presets_validation_and_evidence_privacy(connection: sqlite3.Connection) -> None:
    connection.execute("UPDATE allowance_cycles SET plan_type = 'pro' WHERE cycle_id = 'week'")
    series = build_allowance_series(connection, now=NOW, range_preset="24h", granularity="hour")
    assert series["schema"] == "codex-usage-tracker-allowance-series-v2"
    assert [point["kind"] for point in series["points"]] == ["observed"]
    assert series["cycles"][0]["cycle_id"] == "week"
    assert series["cycles"][0]["plan_type"] == "pro"
    with pytest.raises(ValueError):
        build_allowance_series(connection, now=NOW, range_preset="bad")
    evidence = build_allowance_evidence(connection, privacy_mode="strict")
    assert evidence["schema"] == "codex-usage-tracker-allowance-evidence-v2"
    assert "end_record_id" not in evidence["rows"][0]
    normal_evidence = build_allowance_evidence(connection, privacy_mode="normal")
    assert normal_evidence["provenance"] == "local_aggregate"
    assert "start_record_id" not in normal_evidence["rows"][0]
    assert "end_record_id" not in normal_evidence["rows"][0]


def test_weekly_series_returns_chronological_capacity_history(
    connection: sqlite3.Connection,
) -> None:
    _insert_completed_capacity_cycles(connection, [100.0, 120.0, 900.0, 110.0])

    series = build_allowance_series(
        connection,
        now=NOW,
        range_preset="all",
        granularity="cycle",
    )

    history = series["capacity_history"]
    assert history["unit"] == "credits_per_percent"
    assert [row["credits_per_percent"] for row in history["points"]] == [
        100.0,
        120.0,
        900.0,
        110.0,
    ]
    assert history["points"] == sorted(
        history["points"], key=lambda row: row["completed_at"]
    )
    assert history["plan_types"] == ["pro"]
    assert {row["plan_type"] for row in history["points"]} == {"pro"}
    assert history["clipped_point_count"] == 1


def test_five_hour_series_refuses_weekly_capacity_math(
    connection: sqlite3.Connection,
) -> None:
    series = build_allowance_series(
        connection,
        now=NOW,
        range_preset="24h",
        window_kind="five_hour",
    )

    assert series["capacity_history"] == {
        "status": "unsupported_window_model",
        "unit": "credits_per_percent",
        "points": [],
    }


def test_evidence_skips_nonmeaningful_rows_without_skipping_later_transition(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        "INSERT INTO allowance_intervals (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,end_observed_at,point_kind,source_revision) VALUES ('baseline','week','weekly','primary','codex',0,'2026-07-15T11:59:00+00:00','baseline','r1')"
    )
    evidence = build_allowance_evidence(connection, limit=1, privacy_mode="local")
    assert [row["point_kind"] for row in evidence["rows"]] == ["positive"]


def test_strict_evidence_has_no_stable_local_identifiers(connection: sqlite3.Connection) -> None:
    evidence = build_allowance_evidence(connection, privacy_mode="strict")
    forbidden = {"interval_id", "cycle_id", "cohort_key", "source_revision", "record_id", "session_id", "observation_id", "source_id"}
    assert not (forbidden & set(evidence["rows"][0]))
    assert evidence["revision"] == "r1"


def test_status_cohort_diagnostics_and_reset_series_break(connection: sqlite3.Connection) -> None:
    connection.execute(
        "UPDATE allowance_cycles SET status = 'ambiguous', cycle_state = 'ambiguous', "
        "conflict_count = 0 WHERE cycle_id = 'week'"
    )
    connection.execute(
        """INSERT INTO allowance_cycles (cycle_id,window_kind,window_key,cohort_key,is_archived,reset_at,first_observed_at,last_observed_at,latest_used_percent,observation_count,canonical_observation_count,canonical_tokens,status,cycle_state,source_revision) VALUES ('week-2','weekly','primary','alternate',0,1784232000,'2026-07-15T11:00:00+00:00','2026-07-15T11:59:00+00:00',5,1,1,1,'open','open','r1')"""
    )
    status = build_allowance_status(connection, now=NOW)
    assert status["data_state"] == "partial"
    assert status["cohorts"]["selected"]
    assert status["cohorts"]["alternates"]
    series = build_allowance_series(connection, now=NOW, range_preset="24h")
    assert "reset" in [point["kind"] for point in series["points"]]


def test_normal_codex_primary_is_selected_independently_per_window(
    connection: sqlite3.Connection,
) -> None:
    status = build_allowance_status(connection, now=NOW)
    assert status["cohorts"]["selected"]["weekly"]["id"] == "codex"
    assert status["cohorts"]["selected"]["five_hour"]["id"] == "codex"
    assert not any(
        cohort["id"] == "codex" and cohort["window_kind"] == "five_hour"
        for cohort in status["cohorts"]["alternates"]
    )


def test_stale_weekly_normal_keeps_primary_and_reports_reconciliation(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("UPDATE allowance_cycles SET reset_at = 1 WHERE cycle_id = 'week'")
    connection.execute(
        """INSERT INTO allowance_cycles (cycle_id,window_kind,window_key,cohort_key,is_archived,reset_at,first_observed_at,last_observed_at,latest_used_percent,observation_count,canonical_observation_count,canonical_tokens,status,cycle_state,source_revision) VALUES ('weekly-alt','weekly','primary','alternate',0,1784232000,'2026-07-15T11:00:00+00:00','2026-07-15T11:59:00+00:00',5,3,3,1,'open','open','r1')"""
    )
    _insert_alternate_observations(connection, [0, 1, 2])
    status = build_allowance_status(connection, now=NOW)
    assert status["cohorts"]["selected"]["weekly"]["id"] == "codex"
    assert status["data_state"] == "partial"
    assert status["cohorts"]["reconciliation"]


def test_older_selected_normal_cycle_is_not_an_alternate(connection: sqlite3.Connection) -> None:
    connection.execute(
        """INSERT INTO allowance_cycles (cycle_id,window_kind,window_key,cohort_key,is_archived,reset_at,first_observed_at,last_observed_at,latest_used_percent,observation_count,canonical_observation_count,canonical_tokens,status,cycle_state,source_revision) VALUES ('week-old','weekly','primary','codex',0,1784000000,'2026-07-14T10:00:00+00:00','2026-07-14T11:00:00+00:00',5,3,3,1,'completed','completed','r1')"""
    )
    status = build_allowance_status(connection, now=NOW)
    assert not any(
        cohort["id"] == "codex" and cohort["window_kind"] == "weekly"
        for cohort in status["cohorts"]["alternates"]
    )


def test_constant_zero_alternate_observations_are_not_eligible(connection: sqlite3.Connection) -> None:
    connection.execute("UPDATE allowance_cycles SET reset_at = 1 WHERE cycle_id = 'week'")
    connection.execute(
        """INSERT INTO allowance_cycles (cycle_id,window_kind,window_key,cohort_key,is_archived,reset_at,first_observed_at,last_observed_at,latest_used_percent,observation_count,canonical_observation_count,canonical_tokens,status,cycle_state,source_revision) VALUES ('weekly-flat','weekly','primary','flat',0,1784232000,'2026-07-15T11:00:00+00:00','2026-07-15T11:59:00+00:00',0,3,3,1,'open','open','r1')"""
    )
    _insert_alternate_observations(connection, [0, 0, 0], cohort="flat")
    assert not build_allowance_status(connection, now=NOW)["cohorts"]["reconciliation"]


def _insert_alternate_observations(
    connection: sqlite3.Connection, values: list[float], cohort: str = "alternate"
) -> None:
    connection.executemany(
        """INSERT INTO allowance_observations (observation_id,record_id,session_id,event_timestamp,line_number,source,window_key,window_kind,used_percent,resets_at,limit_id,is_archived) VALUES (?,?,?,?,?,?,?,?,?,?,?,0)""",
        [
            (f"{cohort}-{index}", f"record-{cohort}-{index}", "session", f"2026-07-15T11:{50 + index:02d}:00+00:00", index, "test", "primary", "weekly", value, 1784232000, cohort)
            for index, value in enumerate(values)
        ],
    )


def _insert_completed_capacity_cycles(
    connection: sqlite3.Connection, values: list[float]
) -> None:
    for index, value in enumerate(values, 1):
        cycle_id = f"completed-{index}"
        observed_at = f"2026-06-{index:02d}T12:00:00+00:00"
        connection.execute(
            """INSERT INTO allowance_cycles
            (cycle_id,window_kind,window_key,cohort_key,plan_type,is_archived,
             first_observed_at,last_observed_at,quality_grade,status,cycle_state,
             price_coverage,conflict_count,source_revision,model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cycle_id,
                "weekly",
                "primary",
                "codex",
                "pro",
                0,
                observed_at,
                observed_at,
                "high",
                "completed",
                "completed",
                1.0,
                0,
                "r1",
                "reset-aware-v2",
            ),
        )
        connection.execute(
            """INSERT INTO allowance_intervals
            (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,
             start_observed_at,end_observed_at,visible_percent_delta,
             estimated_credits,price_coverage,point_kind,
             eligible_for_change_detection,source_revision,model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"completed-interval-{index}",
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
                "positive",
                1,
                "r1",
                "reset-aware-v2",
            ),
        )


@pytest.mark.parametrize("start_at,end_at", [("not-a-date", "2026-07-15T12:00:00+00:00"), ("2026-07-15T10:00:00", "2026-07-15T12:00:00+00:00"), ("2026-07-15T13:00:00+00:00", "2026-07-15T12:00:00+00:00")])
def test_series_custom_range_requires_aware_ordered_timestamps(connection: sqlite3.Connection, start_at: str, end_at: str) -> None:
    with pytest.raises(ValueError):
        build_allowance_series(connection, now=NOW, range_preset="custom", start_at=start_at, end_at=end_at)
