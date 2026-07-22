"""Dashboard query and materialized thread-summary store coverage."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.store import api as store_api
from codex_usage_tracker.store import dashboard_queries
from codex_usage_tracker.store.api import (
    connect,
    init_db,
    query_dashboard_event_count,
    query_dashboard_events,
    query_request_context_facts,
    query_thread_summaries,
    query_usage_api_event_count,
    query_usage_api_events,
    refresh_usage_index,
    upsert_usage_events,
)
from codex_usage_tracker.store.thread_summaries import (
    _latest_record_id_expression,
    query_thread_summary_count,
)
from tests.store_dashboard_helpers import (
    SECOND_SESSION_ID,
    SESSION_ID,
    _make_codex_home,
    _usage_event,
    _write_archived_log,
)


def test_dashboard_event_query_uses_sql_prefilters(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    model_rows = query_dashboard_events(db_path=db_path, limit=0, model="codex-auto-review")
    effort_rows = query_dashboard_events(db_path=db_path, limit=0, effort="xhigh")
    token_rows = query_dashboard_events(db_path=db_path, limit=0, min_tokens=100)
    thread_rows = query_dashboard_events(
        db_path=db_path,
        limit=0,
        thread="Add Codex token tracking",
    )
    offset_rows = query_dashboard_events(db_path=db_path, limit=2, offset=2)
    session_rows = query_dashboard_events(db_path=db_path, limit=0, thread=SESSION_ID)
    since_rows = query_dashboard_events(db_path=db_path, limit=0, since="2026-05-17")
    future_rows = query_dashboard_events(db_path=db_path, limit=0, until="2000-01-01")

    assert len(model_rows) == 1
    assert model_rows[0]["model"] == "codex-auto-review"
    assert {row["effort"] for row in effort_rows} == {"xhigh"}
    assert {row["total_tokens"] for row in token_rows} == {100, 200}
    assert {row["session_id"] for row in thread_rows} >= {SESSION_ID, SECOND_SESSION_ID}
    assert len(offset_rows) == 2
    assert {row["record_id"] for row in offset_rows}.isdisjoint(
        {row["record_id"] for row in query_dashboard_events(db_path=db_path, limit=2)}
    )
    assert {row["session_id"] for row in session_rows} == {SESSION_ID}
    assert len(since_rows) == 4
    assert future_rows == []


def test_large_history_query_prefilter_uses_sql_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        UsageEvent(
            record_id=f"record-{index}",
            session_id=f"session-{index % 100}",
            thread_name=f"Thread {index % 25}",
            session_updated_at="2026-05-17T18:58:27Z",
            event_timestamp=f"2026-05-{(index % 28) + 1:02d}T12:00:00Z",
            source_file=f"/tmp/synthetic/{index}.jsonl",
            line_number=index + 1,
            turn_id=f"turn-{index}",
            turn_timestamp=f"2026-05-{(index % 28) + 1:02d}T12:00:00Z",
            cwd=f"/tmp/project-{index % 10}",
            model="gpt-5.5" if index % 2 == 0 else "codex-auto-review",
            effort="high" if index % 3 == 0 else "low",
            current_date="2026-05-17",
            timezone="UTC",
            call_initiator="user",
            call_initiator_reason="user_message",
            call_initiator_confidence="high",
            is_archived=0,
            thread_key=f"thread:Thread {index % 25}",
            thread_call_index=None,
            previous_record_id=None,
            next_record_id=None,
            thread_source="user",
            subagent_type=None,
            agent_role=None,
            agent_nickname=None,
            parent_session_id=None,
            parent_thread_name=None,
            parent_session_updated_at=None,
            model_context_window=200000,
            input_tokens=1000 + index,
            cached_input_tokens=200,
            output_tokens=100,
            reasoning_output_tokens=10,
            total_tokens=1100 + index,
            cumulative_input_tokens=1000 + index,
            cumulative_cached_input_tokens=200,
            cumulative_output_tokens=100,
            cumulative_reasoning_output_tokens=10,
            cumulative_total_tokens=1100 + index,
        )
        for index in range(10_000)
    ]
    upsert_usage_events(events, db_path=db_path)

    rows = query_dashboard_events(
        db_path=db_path,
        limit=25,
        model="gpt-5.5",
        effort="high",
        min_tokens=9000,
    )
    with connect(db_path) as conn:
        init_db(conn)
        plan = " ".join(
            str(row["detail"])
            for row in conn.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT *
                FROM usage_events
                WHERE model = ? AND effort = ? AND total_tokens >= ?
                """,
                ("gpt-5.5", "high", 9000),
            )
        )

    assert len(rows) == 25
    assert all(row["model"] == "gpt-5.5" for row in rows)
    assert all(row["effort"] == "high" for row in rows)
    assert all(row["total_tokens"] >= 9000 for row in rows)
    assert "idx_usage_model_effort" in plan


def test_upsert_refreshes_thread_adjacency_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        _usage_event(
            record_id="a1",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:00Z",
            cumulative_total_tokens=100,
        ),
        _usage_event(
            record_id="b1",
            session_id="session-b",
            thread_key="thread:Beta",
            event_timestamp="2026-05-17T12:00:01Z",
            cumulative_total_tokens=50,
        ),
        _usage_event(
            record_id="a2",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:02Z",
            cumulative_total_tokens=200,
        ),
        _usage_event(
            record_id="a3",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:03Z",
            cumulative_total_tokens=300,
        ),
    ]

    upsert_usage_events(events, db_path=db_path)
    rows = query_dashboard_events(db_path=db_path, limit=0, include_archived=True)
    by_id = {row["record_id"]: row for row in rows}

    assert by_id["a1"]["thread_call_index"] == 1
    assert by_id["a1"]["previous_record_id"] is None
    assert by_id["a1"]["next_record_id"] == "a2"
    assert by_id["a2"]["thread_call_index"] == 2
    assert by_id["a2"]["previous_record_id"] == "a1"
    assert by_id["a2"]["next_record_id"] == "a3"
    assert by_id["a3"]["thread_call_index"] == 3
    assert by_id["a3"]["previous_record_id"] == "a2"
    assert by_id["a3"]["next_record_id"] is None
    assert by_id["b1"]["thread_call_index"] == 1
    assert by_id["b1"]["previous_record_id"] is None
    assert by_id["b1"]["next_record_id"] is None


def test_dashboard_rows_include_call_timing_from_thread_adjacency(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        replace(
            _usage_event(
                record_id="a1",
                session_id="session-a",
                thread_key="thread:Alpha",
                event_timestamp="2026-05-17T12:00:10Z",
                cumulative_total_tokens=100,
            ),
            turn_id="turn-alpha",
            turn_timestamp="2026-05-17T12:00:00Z",
        ),
        replace(
            _usage_event(
                record_id="a2",
                session_id="session-a",
                thread_key="thread:Alpha",
                event_timestamp="2026-05-17T12:00:45Z",
                cumulative_total_tokens=200,
            ),
            turn_id="turn-alpha",
            turn_timestamp="2026-05-17T12:00:00Z",
        ),
        replace(
            _usage_event(
                record_id="a3",
                session_id="session-a",
                thread_key="thread:Alpha",
                event_timestamp="2026-05-17T12:05:05Z",
                cumulative_total_tokens=300,
            ),
            turn_id="turn-beta",
            turn_timestamp="2026-05-17T12:05:00Z",
        ),
        replace(
            _usage_event(
                record_id="b1",
                session_id="session-b",
                thread_key="thread:Beta",
                event_timestamp="2026-05-17T12:00:30Z",
                cumulative_total_tokens=50,
            ),
            turn_id="turn-beta-thread",
            turn_timestamp="2026-05-17T12:00:20Z",
        ),
    ]

    upsert_usage_events(events, db_path=db_path)
    rows = query_dashboard_events(db_path=db_path, limit=0, include_archived=True)
    by_id = {row["record_id"]: row for row in rows}

    assert by_id["a1"]["previous_call_event_timestamp"] is None
    assert by_id["a1"]["call_started_at"] == "2026-05-17T12:00:00Z"
    assert by_id["a1"]["call_duration_seconds"] == 10.0
    assert by_id["a1"]["previous_call_delta_seconds"] is None

    assert by_id["a2"]["previous_call_event_timestamp"] == "2026-05-17T12:00:10Z"
    assert by_id["a2"]["call_started_at"] == "2026-05-17T12:00:10Z"
    assert by_id["a2"]["call_duration_seconds"] == 35.0
    assert by_id["a2"]["previous_call_delta_seconds"] == 35.0

    assert by_id["a3"]["previous_call_event_timestamp"] == "2026-05-17T12:00:45Z"
    assert by_id["a3"]["call_started_at"] == "2026-05-17T12:05:00Z"
    assert by_id["a3"]["call_duration_seconds"] == 5.0
    assert by_id["a3"]["previous_call_delta_seconds"] == 260.0

    assert by_id["b1"]["call_started_at"] == "2026-05-17T12:00:20Z"
    assert by_id["b1"]["call_duration_seconds"] == 10.0
    assert by_id["b1"]["previous_call_delta_seconds"] is None

    by_duration = query_usage_api_events(
        db_path=db_path,
        limit=1,
        include_archived=True,
        sort="duration",
        direction="desc",
    )
    by_gap = query_usage_api_events(
        db_path=db_path,
        limit=1,
        include_archived=True,
        sort="gap",
        direction="desc",
    )
    assert by_duration[0]["record_id"] == "a2"
    assert by_gap[0]["record_id"] == "a3"


def test_upsert_materializes_thread_summaries(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        _usage_event(
            record_id="a1",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:00Z",
            cumulative_total_tokens=100,
        ),
        _usage_event(
            record_id="a2",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:02Z",
            cumulative_total_tokens=220,
        ),
        _usage_event(
            record_id="b1",
            session_id="session-b",
            thread_key="thread:Beta",
            event_timestamp="2026-05-17T12:00:01Z",
            cumulative_total_tokens=90,
        ),
    ]

    upsert_usage_events(events, db_path=db_path)
    summaries = query_thread_summaries(db_path=db_path, limit=0, include_archived=False)
    by_key = {row["thread_key"]: row for row in summaries}

    assert set(by_key) == {"thread:Alpha", "thread:Beta"}
    assert query_thread_summary_count(db_path=db_path) == 2
    assert query_thread_summary_count(db_path=db_path, search="alpha") == 1
    assert query_thread_summary_count(db_path=db_path, search="missing") == 0
    assert by_key["thread:Alpha"]["call_count"] == 2
    assert by_key["thread:Alpha"]["session_count"] == 1
    assert by_key["thread:Alpha"]["total_tokens"] == 220
    assert by_key["thread:Alpha"]["cached_input_tokens"] == 40
    assert by_key["thread:Alpha"]["call_initiator_summary"] == "mostly_user"
    assert by_key["thread:Alpha"]["is_archived_scope"] == "active"
    assert by_key["thread:Alpha"]["estimated_cost_usd"] is None
    assert by_key["thread:Alpha"]["usage_credits"] is None
    assert by_key["thread:Alpha"]["latest_record_id"] == "a2"
    assert by_key["thread:Beta"]["latest_record_id"] == "b1"

    with connect(db_path) as conn:
        init_db(conn)
        persisted = conn.execute("SELECT COUNT(*) AS count FROM thread_summaries").fetchone()
    assert persisted is not None
    assert persisted["count"] == 4


def test_thread_summary_latest_record_lookup_uses_thread_index(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id="indexed",
                session_id="session-indexed",
                thread_key="thread:Indexed",
                event_timestamp="2026-05-17T12:00:00Z",
                cumulative_total_tokens=100,
            )
        ],
        db_path=db_path,
    )

    with connect(db_path) as conn:
        init_db(conn)
        plan = [
            str(row["detail"])
            for row in conn.execute(
                f"""
                EXPLAIN QUERY PLAN
                SELECT {_latest_record_id_expression(include_archived=True)}
                FROM thread_summaries AS t
                WHERE t.is_archived_scope = 'all-history'
                """
            ).fetchall()
        ]

    assert any("idx_usage_thread_key_timestamp (thread_key=?)" in detail for detail in plan)
    assert not any("SCAN u" in detail for detail in plan)


def test_thread_summary_latest_record_lookup_preserves_legacy_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    legacy_event = _usage_event(
        record_id="legacy",
        session_id="session-legacy",
        thread_key="thread:Legacy",
        event_timestamp="2026-05-17T12:00:00Z",
        cumulative_total_tokens=100,
    )

    upsert_usage_events([legacy_event], db_path=db_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE usage_events SET thread_key = NULL WHERE record_id = 'legacy'")

    summaries = query_thread_summaries(db_path=db_path, limit=0)
    assert summaries[0]["thread_key"] == "thread:Legacy"
    assert summaries[0]["latest_record_id"] == "legacy"


def test_thread_call_paging_merges_indexed_and_legacy_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        _usage_event(
            record_id=record_id,
            session_id="session-alpha",
            thread_key="thread:Alpha",
            event_timestamp=f"2026-05-17T12:00:0{index}Z",
            cumulative_total_tokens=index * 100,
        )
        for index, record_id in enumerate(("a1", "a2", "legacy"), start=1)
    ]
    upsert_usage_events(events, db_path=db_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE usage_events SET thread_key = NULL WHERE record_id = 'legacy'")

    first_page = query_usage_api_events(
        db_path=db_path,
        thread_key="thread:Alpha",
        limit=2,
        include_archived=True,
    )
    second_page = query_usage_api_events(
        db_path=db_path,
        thread_key="thread:Alpha",
        limit=2,
        offset=2,
        include_archived=True,
    )

    assert [row["record_id"] for row in first_page] == ["legacy", "a2"]
    assert [row["record_id"] for row in second_page] == ["a1"]
    assert (
        query_usage_api_event_count(
            db_path=db_path,
            thread_key="thread:Alpha",
            include_archived=True,
        )
        == 3
    )


def test_thread_summaries_keep_active_and_all_history_scopes_separate(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    _write_archived_log(codex_home)
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path, include_archived=True)
    active_summaries = query_thread_summaries(db_path=db_path, limit=0)
    all_summaries = query_thread_summaries(
        db_path=db_path,
        limit=0,
        include_archived=True,
    )

    assert {row["is_archived_scope"] for row in active_summaries} == {"active"}
    assert {row["is_archived_scope"] for row in all_summaries} == {"all-history"}
    assert sum(row["call_count"] for row in active_summaries) == 4
    assert sum(row["call_count"] for row in all_summaries) == 5
    assert sum(row["archived_call_count"] for row in active_summaries) == 0
    assert sum(row["archived_call_count"] for row in all_summaries) == 1
    assert all(row["latest_record_id"] for row in active_summaries)
    assert all(row["latest_record_id"] for row in all_summaries)


def test_dashboard_query_limit_zero_loads_all_rows(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert len(query_dashboard_events(db_path=db_path, limit=2)) == 2
    assert len(query_dashboard_events(db_path=db_path, limit=0)) == 4
    assert query_dashboard_event_count(db_path=db_path) == 4


def test_dashboard_event_counts_are_computed_together(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    _write_archived_log(codex_home)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path, include_archived=True)

    query = getattr(dashboard_queries, "query_dashboard_event_counts", None)

    assert query is not None, "dashboard count scopes should share one aggregate query"
    assert query(db_path=db_path) == {
        "active_available_rows": 4,
        "all_history_available_rows": 5,
    }


def test_request_context_facts_use_one_read_transaction_and_canonical_totals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=_make_codex_home(tmp_path), db_path=db_path)
    with connect(db_path) as connection:
        record_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT record_id FROM usage_events ORDER BY record_id LIMIT 2"
            )
        ]
        connection.execute(
            "UPDATE usage_events SET is_duplicate = 1, canonical_record_id = ? WHERE record_id = ?",
            (record_ids[0], record_ids[1]),
        )

    statements: list[str] = []
    original_connect = store_api.sqlite3.connect

    def traced_connect(*args: object, **kwargs: object) -> object:
        connection = original_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr("codex_usage_tracker.store.api.sqlite3.connect", traced_connect)
    facts = query_request_context_facts(
        db_path=db_path,
        scope={"history": "all"},
        priced_models={"gpt-5.5"},
        credit_models={"gpt-5.5"},
    )

    assert facts["physical_rows"] == 4
    assert facts["canonical_rows"] == 3
    assert facts["copied_rows_excluded"] == 1
    assert facts["pricing_coverage"] == 1.0
    assert facts["credit_coverage"] == 1.0
    assert sum(statement.strip().upper() == "BEGIN" for statement in statements) == 1
    assert (
        sum(statement.lstrip().upper().startswith(("SELECT", "WITH")) for statement in statements)
        == 1
    )
