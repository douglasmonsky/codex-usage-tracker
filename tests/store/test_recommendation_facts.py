from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.pricing.allowance import annotate_rows_with_allowance
from codex_usage_tracker.pricing.costing import annotate_rows_with_efficiency
from codex_usage_tracker.recommendation_engine.api import refresh_usage_index
from codex_usage_tracker.recommendation_engine.materialization import (
    backfill_recommendation_facts,
    sync_recommendation_facts,
)
from codex_usage_tracker.reports.recommendations import (
    annotate_rows_with_recommendations,
)
from codex_usage_tracker.store.api import (
    query_dashboard_events,
    upsert_usage_events,
)
from codex_usage_tracker.store.connection import connect
from tests.store_dashboard_helpers import _entry, _make_codex_home, _token_event, _usage_event


def test_materialized_recommendation_facts_match_legacy_annotations(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        replace(
            _usage_event(
                record_id="edge-unpriced",
                session_id="session-edge",
                thread_key="thread:edge",
                event_timestamp="2026-07-13T12:00:00Z",
                cumulative_total_tokens=900_000,
            ),
            model="synthetic-unpriced-model",
            input_tokens=250_000,
            cached_input_tokens=1_000,
            output_tokens=50,
            reasoning_output_tokens=40_000,
            total_tokens=250_050,
        ),
        replace(
            _usage_event(
                record_id="edge-archived",
                session_id="session-archived",
                thread_key="thread:archived",
                event_timestamp="2026-07-12T12:00:00Z",
                cumulative_total_tokens=1_000,
            ),
            is_archived=1,
            model="synthetic-unpriced-model",
        ),
    ]

    upsert_usage_events(events, db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(
            conn,
            record_ids=(event.record_id for event in events),
        )

    legacy_rows = query_dashboard_events(db_path=db_path, limit=0)
    legacy_rows = annotate_rows_with_allowance(annotate_rows_with_efficiency(legacy_rows))
    expected = {row["record_id"]: row for row in annotate_rows_with_recommendations(legacy_rows)}
    with connect(db_path) as conn:
        facts = conn.execute(
            """
            SELECT * FROM recommendation_facts ORDER BY record_id
            """
        ).fetchall()

    assert {str(row["record_id"]) for row in facts} == set(expected)
    for fact in facts:
        legacy = expected[str(fact["record_id"])]
        recommendations = json.loads(str(fact["recommendations_json"]))
        assert recommendations == legacy["action_recommendations"]
        assert fact["primary_recommendation_key"] == legacy["primary_signal"]
        assert (
            json.loads(str(fact["secondary_recommendation_keys_json"]))
            == legacy["secondary_signals"]
        )
        assert fact["recommendation_score"] == legacy["recommendation_score"]
        assert fact["recommended_action_key"] == legacy["recommended_action_key"]


def test_append_sync_does_not_rebuild_historical_recommendation_facts(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    source_path = next((codex_home / "sessions").glob("**/*.jsonl"))
    with connect(db_path) as conn:
        initial_count = int(conn.execute("SELECT COUNT(*) FROM recommendation_facts").fetchone()[0])
        conn.executescript(
            """
            CREATE TABLE protected_recommendation_facts (
                record_id TEXT PRIMARY KEY
            );
            INSERT INTO protected_recommendation_facts
            SELECT record_id FROM recommendation_facts;
            CREATE TRIGGER protect_historical_recommendation_fact
            BEFORE DELETE ON recommendation_facts
            WHEN OLD.record_id IN (SELECT record_id FROM protected_recommendation_facts)
            BEGIN
                SELECT RAISE(ABORT, 'historical recommendation fact was rebuilt');
            END;
            """
        )

    with source_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                _entry(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "APPENDED FACT"}],
                    },
                )
            )
            + "\n"
        )
        handle.write(json.dumps(_token_event(8_000, 400)) + "\n")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with connect(db_path) as conn:
        final_count = int(conn.execute("SELECT COUNT(*) FROM recommendation_facts").fetchone()[0])
    assert final_count == initial_count + 1


def test_recommendation_fact_backfill_is_idempotent_and_db_only(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = _usage_event(
        record_id="backfill",
        session_id="session",
        thread_key="thread:session",
        event_timestamp="2026-07-13T12:00:00Z",
        cumulative_total_tokens=1_000,
    )
    upsert_usage_events([event], db_path=db_path)

    with connect(db_path) as conn:
        conn.execute("DELETE FROM recommendation_facts")
        first_count = backfill_recommendation_facts(conn)
        first = _fact_snapshot(conn)
        second_count = backfill_recommendation_facts(conn)
        second = _fact_snapshot(conn)

    assert first_count == 1
    assert second_count == 1
    assert first == second


def test_source_replacement_removes_orphaned_recommendation_facts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    source_path = tmp_path / "synthetic-source.jsonl"
    event = replace(
        _usage_event(
            record_id="removed",
            session_id="session",
            thread_key="thread:session",
            event_timestamp="2026-07-13T12:00:00Z",
            cumulative_total_tokens=1_000,
        ),
        source_file=str(source_path),
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id])

    upsert_usage_events([], db_path=db_path, replace_source_files=[source_path])
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[])

    with connect(db_path) as conn:
        fact_count = int(conn.execute("SELECT COUNT(*) FROM recommendation_facts").fetchone()[0])
        state_count = int(
            conn.execute(
                "SELECT record_count FROM recommendation_fact_state WHERE singleton = 1"
            ).fetchone()[0]
        )
    assert fact_count == 0
    assert state_count == 0


def test_threshold_changes_update_recommendation_config_fingerprint(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    thresholds_path = tmp_path / "thresholds.json"
    event = replace(
        _usage_event(
            record_id="threshold",
            session_id="session",
            thread_key="thread:session",
            event_timestamp="2026-07-13T12:00:00Z",
            cumulative_total_tokens=900_000,
        ),
        model="synthetic-unpriced-model",
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id])
    with connect(db_path) as conn:
        initial = conn.execute(
            "SELECT config_fingerprint FROM recommendation_fact_state WHERE singleton = 1"
        ).fetchone()

    thresholds_path.write_text(
        json.dumps({"large_cumulative_tokens": 2_000_000}),
        encoding="utf-8",
    )
    with connect(db_path) as conn:
        backfill_recommendation_facts(conn, thresholds_path=thresholds_path)
        changed = conn.execute(
            "SELECT config_fingerprint FROM recommendation_fact_state WHERE singleton = 1"
        ).fetchone()

    assert initial is not None
    assert changed is not None
    assert changed[0] != initial[0]


def _fact_snapshot(conn) -> list[tuple[object, ...]]:
    return [
        tuple(row)
        for row in conn.execute(
            """
            SELECT
                record_id,
                primary_recommendation_key,
                secondary_recommendation_keys_json,
                recommendation_score,
                recommended_action_key,
                recommendations_json,
                facts_version,
                algorithm_version,
                config_fingerprint
            FROM recommendation_facts
            ORDER BY record_id
            """
        )
    ]
