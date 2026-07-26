from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from codex_usage_tracker.store import usage_event_writer as writer_module
from codex_usage_tracker.store.api import (
    connect,
    refresh_usage_index,
    upsert_usage_events,
)
from tests.store_dashboard_helpers import (
    _entry,
    _make_codex_home,
    _token_event,
    _usage_event,
)


def test_refresh_derived_fact_callback_receives_full_and_append_targets(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    calls: list[tuple[tuple[str, ...], frozenset[str], bool, bool]] = []

    def sync(
        conn,
        record_ids: tuple[str, ...],
        thread_keys: frozenset[str],
        full_rebuild: bool,
    ) -> None:
        calls.append((record_ids, thread_keys, full_rebuild, conn.in_transaction))

    refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        derived_fact_sync=sync,
    )
    source_path = next((codex_home / "sessions").glob("**/*.jsonl"))
    with source_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                _entry(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "APPENDED"}],
                    },
                )
            )
            + "\n"
        )
        handle.write(json.dumps(_token_event(8_000, 400)) + "\n")
    refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        derived_fact_sync=sync,
    )

    assert len(calls) == 2
    assert calls[0][2:] == (True, True)
    assert calls[1][2:] == (False, True)
    assert len(calls[0][0]) > 0
    assert len(calls[1][0]) == 1
    assert calls[0][1]
    assert calls[1][1]


def test_stream_refresh_does_not_resync_source_records_after_direct_upsert(
    tmp_path: Path,
    monkeypatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    def unexpected_sync(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("stream finalization repeated source-record synchronization")

    monkeypatch.setattr(writer_module, "sync_source_records", unexpected_sync)
    result = refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        source_records = conn.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
    assert source_records == result.inserted_or_updated_events


def test_replaced_source_requests_full_derived_fact_reconciliation(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    full_rebuild_flags: list[bool] = []

    def sync(
        _conn,
        _record_ids: tuple[str, ...],
        _thread_keys: frozenset[str],
        full_rebuild: bool,
    ) -> None:
        full_rebuild_flags.append(full_rebuild)

    refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        derived_fact_sync=sync,
    )
    source_path = next((codex_home / "sessions").glob("**/*.jsonl"))
    source_path.write_text(
        source_path.read_text(encoding="utf-8").replace("gpt-5.5", "gpt-5.6"),
        encoding="utf-8",
    )
    refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        derived_fact_sync=sync,
    )

    assert full_rebuild_flags == [True, True]


def test_append_safe_usage_links_do_not_recompute_the_existing_thread(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    initial = [
        _usage_event(
            record_id=f"record-{index}",
            session_id="session",
            thread_key="thread:append-safe",
            event_timestamp=f"2026-01-01T00:0{index}:00Z",
            cumulative_total_tokens=(index + 1) * 100,
        )
        for index in range(2)
    ]
    upsert_usage_events(initial, db_path)

    def unexpected_full_link_refresh(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("append-safe refresh recomputed the existing thread")

    monkeypatch.setattr(
        writer_module,
        "_refresh_usage_event_links_for_threads",
        unexpected_full_link_refresh,
    )
    appended = _usage_event(
        record_id="record-2",
        session_id="session",
        thread_key="thread:append-safe",
        event_timestamp="2026-01-01T00:02:00Z",
        cumulative_total_tokens=300,
    )
    upsert_usage_events([appended], db_path)

    with connect(db_path) as conn:
        links = [
            tuple(row)
            for row in conn.execute(
                "SELECT record_id, thread_call_index, previous_record_id, next_record_id "
                "FROM usage_events ORDER BY thread_call_index"
            )
        ]
    assert links == [
        ("record-0", 1, None, "record-1"),
        ("record-1", 2, "record-0", "record-2"),
        ("record-2", 3, "record-1", None),
    ]
