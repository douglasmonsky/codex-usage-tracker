from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.parser.state import PARSER_ADAPTER_VERSION, ParserState
from codex_usage_tracker.reports.api import build_source_coverage_report
from codex_usage_tracker.store import sources
from codex_usage_tracker.store.api import (
    connect,
    init_db,
    query_source_record_coverage,
    query_source_records,
    record_source_file_metadata,
    reset_usage_database,
    upsert_usage_events,
)
from tests.store_dashboard_helpers import _usage_event


def test_upsert_usage_events_persists_source_record_provenance(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        _usage_event(
            record_id="source-a",
            session_id="session-a",
            thread_key="thread:Source A",
            event_timestamp="2026-05-17T18:00:00Z",
            cumulative_total_tokens=100,
        ),
        _usage_event(
            record_id="source-b",
            session_id="session-a",
            thread_key="thread:Source A",
            event_timestamp="2026-05-17T18:05:00Z",
            cumulative_total_tokens=200,
        ),
    ]

    upsert_usage_events(events, db_path=db_path)

    unlimited_rows = query_source_records(db_path=db_path, limit=0)
    none_limit_rows = query_source_records(db_path=db_path, limit=None)
    coverage_rows = query_source_record_coverage(db_path=db_path)
    report = build_source_coverage_report(db_path=db_path)

    assert [row["record_id"] for row in unlimited_rows] == ["source-a", "source-b"]
    assert [row["record_id"] for row in none_limit_rows] == ["source-a", "source-b"]
    assert unlimited_rows[0]["raw_shape_label"] == "token_count"
    assert unlimited_rows[0]["parser_adapter"] == "codex-jsonl"
    assert unlimited_rows[0]["parser_version"] == "codex-jsonl-v2"
    assert unlimited_rows[0]["hash_basis"] == "source_file_id:line_number:record_id"
    assert unlimited_rows[0]["created_from"] == "usage_events"
    assert len(str(unlimited_rows[0]["source_file_id"])) == 64
    assert len(str(unlimited_rows[0]["source_record_hash"])) == 64
    assert coverage_rows == [
        {
            "raw_shape_label": "token_count",
            "parser_adapter": "codex-jsonl",
            "parser_version": "codex-jsonl-v2",
            "record_count": 2,
            "source_file_count": 2,
            "warning_record_count": 0,
        }
    ]
    assert report.payload["schema"] == "codex-usage-tracker-source-coverage-v1"
    assert report.payload["content_mode"] == "aggregate_only"
    assert report.payload["includes_indexed_content"] is False
    assert report.payload["includes_raw_fragments"] is False
    assert report.payload["source_record_count"] == 2
    assert report.payload["source_file_count"] == 2
    assert "Codex source coverage" in report.render()


def test_source_file_metadata_refreshes_source_record_parser_details(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    source_path = tmp_path / "sessions" / "synthetic.jsonl"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("{}\n", encoding="utf-8")
    event = replace(
        _usage_event(
            record_id="source-metadata",
            session_id="session-metadata",
            thread_key="thread:Source Metadata",
            event_timestamp="2026-05-17T19:00:00Z",
            cumulative_total_tokens=300,
        ),
        source_file=str(source_path),
        line_number=7,
    )

    upsert_usage_events([event], db_path=db_path)
    record_source_file_metadata(
        db_path=db_path,
        parsed_files=[
            (
                source_path,
                [event],
                {},
                ParserState(
                    latest_record_id=event.record_id,
                    latest_event_timestamp=event.event_timestamp,
                ),
            )
        ],
    )

    rows = query_source_records(db_path=db_path, limit=0)

    assert len(rows) == 1
    assert rows[0]["record_id"] == "source-metadata"
    assert rows[0]["source_file"] == str(source_path)
    assert rows[0]["line_number"] == 7
    assert rows[0]["parser_adapter"] == "codex-jsonl"
    assert rows[0]["parser_version"] == "codex-jsonl-v2"


def test_source_file_metadata_uses_parser_final_line_number(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    source_path = tmp_path / "sessions" / "fast-metadata.jsonl"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("{}\n", encoding="utf-8")
    event = replace(
        _usage_event(
            record_id="source-fast-metadata",
            session_id="session-fast-metadata",
            thread_key="thread:Fast Metadata",
            event_timestamp="2026-05-17T19:30:00Z",
            cumulative_total_tokens=350,
        ),
        source_file=str(source_path),
        line_number=7,
    )
    upsert_usage_events([event], db_path=db_path)

    def fail_count_lines(_path: Path) -> int:
        raise AssertionError("final parser line number should avoid recounting source file")

    monkeypatch.setattr(sources, "_count_lines", fail_count_lines)

    record_source_file_metadata(
        db_path=db_path,
        parsed_files=[
            (
                source_path,
                [event],
                {},
                ParserState(
                    latest_record_id=event.record_id,
                    latest_event_timestamp=event.event_timestamp,
                ),
                7,
            )
        ],
    )

    rows = query_source_records(db_path=db_path, limit=0)
    assert len(rows) == 1
    assert rows[0]["record_id"] == "source-fast-metadata"
    assert rows[0]["line_number"] == 7


def test_reset_usage_database_clears_content_index_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = _usage_event(
        record_id="content-reset",
        session_id="session-reset",
        thread_key="thread:Content Reset",
        event_timestamp="2026-05-17T20:00:00Z",
        cumulative_total_tokens=400,
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO conversation_turns (
                turn_key,
                record_id,
                session_id,
                role,
                parser_adapter,
                parser_version
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "turn:content-reset",
                event.record_id,
                event.session_id,
                "user",
                "codex-jsonl",
                PARSER_ADAPTER_VERSION,
            ),
        )
        conn.execute(
            """
            INSERT INTO content_fragments (
                fragment_id,
                record_id,
                turn_key,
                fragment_kind,
                content_hash,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "fragment:content-reset",
                event.record_id,
                "turn:content-reset",
                "message",
                "hash",
                "2026-05-17T20:00:00Z",
            ),
        )

    reset_usage_database(db_path=db_path)

    with connect(db_path) as conn:
        init_db(conn)
        turn_count = conn.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()
        fragment_count = conn.execute("SELECT COUNT(*) FROM content_fragments").fetchone()

    assert turn_count is not None
    assert fragment_count is not None
    assert turn_count[0] == 0
    assert fragment_count[0] == 0
