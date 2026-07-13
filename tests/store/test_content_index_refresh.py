from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.store import content_index_bulk
from codex_usage_tracker.store.api import connect, init_db, refresh_usage_index
from tests.store_dashboard_helpers import _entry, _token_event, _write_jsonl


def test_refresh_batches_content_index_row_writes(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / ".codex"
    log_dir = codex_home / "sessions" / "2026" / "05" / "17"
    log_dir.mkdir(parents=True)
    log_path = log_dir / ("rollout-2026-05-17T14-58-23-019e374d-c19f-7da3-a44f-8de043a7a64e.jsonl")
    rows: list[dict[str, object]] = []
    for index in range(3):
        rows.extend(
            [
                _entry("turn_context", {"turn_id": f"turn-{index}", "model": "gpt-5.5"}),
                _entry(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": f"BATCH SENTINEL {index}"}],
                    },
                ),
                _token_event(1_000 * (index + 1), 100),
            ]
        )
    _write_jsonl(log_path, rows)
    db_path = tmp_path / "usage.sqlite3"
    fragment_write_sizes: list[int] = []
    original_upsert = content_index_bulk._upsert_fragment_rows

    def counting_upsert(conn, rows: list[dict[str, object]]) -> None:
        fragment_write_sizes.append(len(rows))
        original_upsert(conn, rows)

    monkeypatch.setattr(content_index_bulk, "_upsert_fragment_rows", counting_upsert)

    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert fragment_write_sizes == [3]


def test_refresh_indexes_content_sources_in_parallel(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / ".codex"
    log_dir = codex_home / "sessions" / "2026" / "05" / "17"
    log_dir.mkdir(parents=True)
    session_ids = [f"019e37d{index:x}-bb36-76ba-aa33-ed0beaf4f9ce" for index in range(10)]
    for index, session_id in enumerate(session_ids):
        log_path = log_dir / f"rollout-2026-05-17T14-58-2{index}-{session_id}.jsonl"
        _write_jsonl(
            log_path,
            [
                _entry("turn_context", {"turn_id": f"turn-{index}", "model": "gpt-5.5"}),
                _entry(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": f"PARALLEL CONTENT SENTINEL {index}",
                            }
                        ],
                    },
                ),
                _token_event(1_000 * (index + 1), 100),
            ],
        )
    db_path = tmp_path / "usage.sqlite3"
    progress_events: list[dict[str, object]] = []
    monkeypatch.setenv("CODEX_USAGE_TRACKER_CONTENT_INDEX_WORKERS", "2")

    refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        progress_callback=progress_events.append,
    )

    assert any(
        event.get("phase") == "parsing" and event.get("workers") == 2 for event in progress_events
    )
    with connect(db_path) as conn:
        init_db(conn)
        fragment_count = conn.execute(
            "SELECT COUNT(*) FROM content_fragments "
            "WHERE fragment_text LIKE 'PARALLEL CONTENT SENTINEL%'"
        ).fetchone()[0]
    assert fragment_count == len(session_ids)
    assert any(
        event.get("phase") == "indexing_content" and event.get("workers") == 1
        for event in progress_events
    )
