from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.parser.state import ParserState
from codex_usage_tracker.store.api import (
    query_source_record_coverage,
    query_source_records,
    record_source_file_metadata,
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
