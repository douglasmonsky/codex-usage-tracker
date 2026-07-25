from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.recommendation_engine.materialization import (
    sync_recommendation_facts,
)
from codex_usage_tracker.store.api import query_status_context_facts, upsert_usage_events
from codex_usage_tracker.store.connection import connect, connect_read_only
from codex_usage_tracker.store.home_observed_queries import (
    query_home_latest_observed_usage,
)
from codex_usage_tracker.store.home_queries import (
    persist_home_usage_metrics,
    query_home_refresh_metadata,
    query_home_status_counts,
    query_home_usage_metrics,
)
from tests.store_dashboard_helpers import _usage_event


def test_home_reads_return_empty_without_an_index(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.sqlite3"

    assert query_home_refresh_metadata(db_path=db_path) == {}
    assert query_home_usage_metrics(db_path=db_path) is None
    assert query_home_status_counts(db_path=db_path)["canonical_rows"] == 0
    assert query_home_latest_observed_usage(db_path=db_path) == {
        "available": False,
        "windows": [],
        "reconciliation": {
            "recommended": False,
            "reason": None,
            "suggested_action": None,
            "consecutive_alternate_rows": 0,
            "threshold": 3,
            "latest_limit_id": None,
            "latest_plan_type": None,
            "latest_observed_at": None,
            "selected_observed_at": None,
            "selected_limit_id": None,
        },
    }


def test_home_observed_usage_reads_committed_snapshot_while_writer_is_active(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = _usage_event(
        record_id="observed",
        session_id="session",
        thread_key="thread:Observed",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
        rate_limit_plan_type="plus",
        rate_limit_limit_id="codex",
        rate_limit_primary_used_percent=37,
        rate_limit_primary_window_minutes=300,
    )
    upsert_usage_events([event], db_path=db_path)

    writer = sqlite3.connect(db_path)
    try:
        writer.execute("BEGIN IMMEDIATE")
        observed = query_home_latest_observed_usage(db_path=db_path)
    finally:
        writer.rollback()
        writer.close()

    assert observed["available"] is True
    assert observed["record_id"] == event.record_id
    assert observed["windows"][0]["used_percent"] == 37


def test_home_status_counts_use_current_compact_summaries(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    active = _usage_event(
        record_id="active",
        session_id="active-session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    archived = replace(
        _usage_event(
            record_id="archived",
            session_id="archived-session",
            thread_key="thread:Archived",
            event_timestamp="2026-07-22T09:00:00Z",
            cumulative_total_tokens=2_500,
        ),
        is_archived=1,
    )
    upsert_usage_events([active, archived], db_path=db_path)

    counts = query_home_status_counts(db_path=db_path)

    assert counts == {
        "dedupe_enabled": True,
        "fingerprint_version": "usage-fingerprint-v2",
        "total_rows": 2,
        "active_rows": 1,
        "total_max_event_timestamp": archived.event_timestamp,
        "active_max_event_timestamp": active.event_timestamp,
        "physical_rows": 2,
        "canonical_rows": 2,
        "excluded_copied_rows": 0,
        "duplicate_fingerprint_groups": 0,
        "physical_total_tokens": active.total_tokens + archived.total_tokens,
        "canonical_total_tokens": active.total_tokens + archived.total_tokens,
        "excluded_total_tokens": 0,
        "duplicate_reasons": {},
    }


def test_home_status_counts_preserve_dedupe_v1_totals(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    original = _usage_event(
        record_id="original",
        session_id="session",
        thread_key="thread:Original",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    copied = replace(
        original,
        record_id="copied",
        source_file="/tmp/synthetic/copied.jsonl",
        line_number=2,
    )
    upsert_usage_events([original, copied], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[original.record_id])

    counts = query_home_status_counts(db_path=db_path)

    assert counts["physical_rows"] == 2
    assert counts["canonical_rows"] == 1
    assert counts["excluded_copied_rows"] == 1
    assert counts["duplicate_fingerprint_groups"] == 1
    assert counts["physical_total_tokens"] == original.total_tokens * 2
    assert counts["canonical_total_tokens"] == original.total_tokens
    assert counts["excluded_total_tokens"] == original.total_tokens
    assert counts["duplicate_reasons"] == {"copied_usage_fingerprint": 1}


def test_home_usage_metrics_use_current_canonical_materialization(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    active = _usage_event(
        record_id="active",
        session_id="active-session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    archived = replace(
        _usage_event(
            record_id="archived",
            session_id="archived-session",
            thread_key="thread:Archived",
            event_timestamp="2026-07-21T09:00:00Z",
            cumulative_total_tokens=2_500,
        ),
        is_archived=1,
    )
    upsert_usage_events([active, archived], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[active.record_id, archived.record_id])
        conn.execute(
            """
            UPDATE recommendation_facts
            SET estimated_cost_usd = 1.25,
                usage_credits = 3.5
            WHERE record_id = 'active'
            """
        )
        state = conn.execute(
            "SELECT source_generation, record_count "
            "FROM recommendation_fact_state WHERE singleton = 1"
        ).fetchone()
        assert state is not None
        persist_home_usage_metrics(
            conn,
            source_generation=int(state["source_generation"]),
            materialized_calls=int(state["record_count"]),
        )

    metrics = query_home_usage_metrics(db_path=db_path)

    assert metrics is not None
    assert metrics["calls"] == 1
    assert metrics["total_tokens"] == active.total_tokens
    assert metrics["estimated_cost_usd"] == 1.25
    assert metrics["usage_credits"] == 3.5
    assert metrics["pricing_coverage"] == 1.0
    assert metrics["credit_coverage"] == 1.0


@pytest.mark.parametrize("cache_value", [None, "{invalid"])
def test_home_usage_metrics_do_not_repair_cache_during_read(
    tmp_path: Path,
    cache_value: str | None,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = _usage_event(
        record_id="active",
        session_id="session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id])
        if cache_value is None:
            conn.execute("DELETE FROM refresh_meta WHERE key = 'home_usage_metrics_v1'")
        else:
            conn.execute(
                """
                INSERT INTO refresh_meta (key, value)
                VALUES ('home_usage_metrics_v1', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (cache_value,),
            )

    writer = sqlite3.connect(db_path)
    try:
        writer.execute("BEGIN IMMEDIATE")
        metrics = query_home_usage_metrics(db_path=db_path)
    finally:
        writer.rollback()
        writer.close()

    assert metrics is not None
    assert metrics["calls"] == 1
    assert metrics["total_tokens"] == event.total_tokens
    assert metrics["estimated_cost_usd"] == 0.0
    with connect_read_only(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM refresh_meta WHERE key = 'home_usage_metrics_v1'"
        ).fetchone()
    assert (None if row is None else row["value"]) == cache_value


def test_home_usage_metrics_return_none_without_source_state(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = _usage_event(
        record_id="active",
        session_id="session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        conn.execute("DELETE FROM compression_source_state")

    assert query_home_usage_metrics(db_path=db_path) is None


def test_status_context_uses_current_active_home_materialization(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    active = _usage_event(
        record_id="active",
        session_id="active-session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    archived = replace(
        _usage_event(
            record_id="archived",
            session_id="archived-session",
            thread_key="thread:Archived",
            event_timestamp="2026-07-21T09:00:00Z",
            cumulative_total_tokens=2_500,
        ),
        is_archived=1,
    )
    upsert_usage_events([active, archived], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[active.record_id, archived.record_id])
        conn.execute(
            """
            UPDATE recommendation_facts
            SET estimated_cost_usd = 1.25, usage_credits = 3.5
            WHERE record_id = 'active'
            """
        )
        state = conn.execute(
            "SELECT source_generation, record_count "
            "FROM recommendation_fact_state WHERE singleton = 1"
        ).fetchone()
        assert state is not None
        persist_home_usage_metrics(
            conn,
            source_generation=int(state["source_generation"]),
            materialized_calls=int(state["record_count"]),
        )

    facts = query_status_context_facts(
        db_path,
        scope={"history": "active", "filters": {}},
        priced_models={"gpt-5.5"},
        credit_models={"gpt-5.5"},
    )

    assert facts["physical_rows"] == 1
    assert facts["canonical_rows"] == 1
    assert facts["copied_rows_excluded"] == 0
    assert facts["latest_indexed_event_at"] == active.event_timestamp
    assert facts["pricing_coverage"] == 1.0
    assert facts["credit_coverage"] == 1.0
    assert facts["service_tier_coverage"] == 0.0
    assert facts["source_revision"] == "generation:1"


def test_status_context_preserves_token_weighted_coverage(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    priced = replace(
        _usage_event(
            record_id="priced",
            session_id="priced-session",
            thread_key="thread:Priced",
            event_timestamp="2026-07-21T08:00:00Z",
            cumulative_total_tokens=110,
        ),
        service_tier="priority",
    )
    unpriced = replace(
        _usage_event(
            record_id="unpriced",
            session_id="unpriced-session",
            thread_key="thread:Unpriced",
            event_timestamp="2026-07-21T09:00:00Z",
            cumulative_total_tokens=1_110,
        ),
        model="unpriced-model",
        input_tokens=1_000,
        cached_input_tokens=0,
        output_tokens=100,
        reasoning_output_tokens=10,
        total_tokens=1_100,
    )
    upsert_usage_events([priced, unpriced], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(
            conn,
            record_ids=[priced.record_id, unpriced.record_id],
        )
        conn.execute(
            """
            UPDATE recommendation_facts
            SET estimated_cost_usd = 1.0, usage_credits = 1.0
            WHERE record_id = 'priced'
            """
        )
        state = conn.execute(
            "SELECT source_generation, record_count "
            "FROM recommendation_fact_state WHERE singleton = 1"
        ).fetchone()
        assert state is not None
        persist_home_usage_metrics(
            conn,
            source_generation=int(state["source_generation"]),
            materialized_calls=int(state["record_count"]),
        )

    facts = query_status_context_facts(
        db_path,
        scope={"history": "active", "filters": {}},
        priced_models={"gpt-5.5"},
        credit_models={"gpt-5.5"},
    )

    expected = priced.total_tokens / (priced.total_tokens + unpriced.total_tokens)
    assert facts["pricing_coverage"] == expected
    assert facts["credit_coverage"] == expected
    assert facts["service_tier_coverage"] == expected


def test_home_usage_metrics_fall_back_to_current_thread_summaries(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = _usage_event(
        record_id="active",
        session_id="session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id])
    next_event = _usage_event(
        record_id="next",
        session_id="session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:01:00Z",
        cumulative_total_tokens=2_500,
    )
    upsert_usage_events([next_event], db_path=db_path)

    metrics = query_home_usage_metrics(db_path=db_path)

    assert metrics is not None
    assert metrics["calls"] == 2
    assert metrics["input_tokens"] == event.input_tokens + next_event.input_tokens
    assert metrics["cached_input_tokens"] == (
        event.cached_input_tokens + next_event.cached_input_tokens
    )
    assert metrics["uncached_input_tokens"] == (
        event.uncached_input_tokens + next_event.uncached_input_tokens
    )
    assert metrics["output_tokens"] == event.output_tokens + next_event.output_tokens
    assert metrics["reasoning_output_tokens"] == (
        event.reasoning_output_tokens + next_event.reasoning_output_tokens
    )
    assert metrics["total_tokens"] == event.total_tokens + next_event.total_tokens
    assert metrics["estimated_cost_usd"] == 0.0
    assert metrics["usage_credits"] == 0.0
    assert metrics["pricing_coverage"] == 0.0
    assert metrics["credit_coverage"] == 0.0
    assert metrics["service_tier_coverage"] == 0.0
    assert metrics["materialized_calls"] == 1
