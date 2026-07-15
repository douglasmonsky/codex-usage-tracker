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
        [("week", "weekly", "primary", "codex", 0, 1784145600, "2026-07-15T10:00:00+00:00", "2026-07-15T11:58:00+00:00", 40, 2, 2, 100, 0.8, "high", "accepted", "accepted", "r1", "reset-aware-v2"), ("five", "five_hour", "secondary", "codex", 0, 1784116800, "2026-07-15T11:57:00+00:00", "2026-07-15T11:58:00+00:00", 10, 2, 2, 50, None, "high", "accepted", "accepted", "r1", "reset-aware-v2")],
    )
    conn.execute("INSERT INTO allowance_intervals (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,end_observed_at,end_used_percent,point_kind,source_revision,model_version) VALUES ('i1','week','weekly','primary','codex',0,'2026-07-15T11:58:00+00:00',40,'positive','r1','reset-aware-v2')")
    return conn


def test_status_schema_freshness_and_matching_revision_are_compact(connection: sqlite3.Connection) -> None:
    payload = build_allowance_status(connection, now=NOW, privacy_mode="strict")
    assert payload["schema"] == "codex-usage-tracker-allowance-status-v2"
    assert payload["weekly"]["freshness"] == "fresh"
    assert payload["five_hour"]["freshness"] == "fresh"
    assert payload["next"]["poll_after_seconds"] == 30
    assert build_allowance_status(connection, now=NOW, since_revision="r1") == {"schema": payload["schema"], "revision": "r1", "changed": False}


def test_status_aging_and_reset_make_observation_stale(connection: sqlite3.Connection) -> None:
    assert build_allowance_status(connection, now=datetime(2026, 7, 15, 17, tzinfo=timezone.utc))["weekly"]["freshness"] == "aging"
    assert build_allowance_status(connection, now=datetime(2026, 7, 15, 18, 1, tzinfo=timezone.utc))["weekly"]["freshness"] == "stale"
    connection.execute("UPDATE allowance_cycles SET reset_at = 1 WHERE cycle_id = 'week'")
    assert build_allowance_status(connection, now=NOW)["weekly"]["freshness"] == "stale"


def test_series_presets_validation_and_evidence_privacy(connection: sqlite3.Connection) -> None:
    series = build_allowance_series(connection, now=NOW, range_preset="24h", granularity="hour")
    assert series["schema"] == "codex-usage-tracker-allowance-series-v2"
    assert [point["kind"] for point in series["points"]] == ["observed"]
    assert series["cycles"][0]["cycle_id"] == "week"
    with pytest.raises(ValueError):
        build_allowance_series(connection, now=NOW, range_preset="bad")
    evidence = build_allowance_evidence(connection, privacy_mode="strict")
    assert evidence["schema"] == "codex-usage-tracker-allowance-evidence-v2"
    assert "end_record_id" not in evidence["rows"][0]
