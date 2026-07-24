from __future__ import annotations

import copy
from pathlib import Path

import pytest

from codex_usage_tracker.context.api import load_call_context
from codex_usage_tracker.store.api import query_session_usage, refresh_usage_index
from codex_usage_tracker.store.connection import connect
from tests.store_dashboard_helpers import (
    SESSION_ID,
    _entry,
    _make_codex_home,
    _token_event,
    _write_jsonl,
)


def _without_diagnostics(payload: dict[str, object]) -> dict[str, object]:
    normalized = copy.deepcopy(payload)
    normalized.pop("diagnostics", None)
    return normalized


@pytest.mark.parametrize(
    ("mode", "include_tool_output", "include_compaction_history"),
    [
        ("quick", False, False),
        ("quick", True, True),
        ("full", False, True),
        ("full", True, False),
    ],
)
def test_offset_and_sequential_context_payloads_are_equivalent(
    tmp_path: Path,
    mode: str,
    include_tool_output: bool,
    include_compaction_history: bool,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]

    offset_payload = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
        diagnostics=True,
        mode=mode,
    )
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE usage_events SET source_byte_offset = NULL WHERE record_id = ?",
            (row["record_id"],),
        )
    sequential_payload = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
        diagnostics=True,
        mode=mode,
    )

    assert offset_payload["diagnostics"]["context_read_strategy"] == "offset_seek"
    assert sequential_payload["diagnostics"]["context_read_strategy"] == "sequential_fallback"
    assert (
        offset_payload["diagnostics"]["inspected_source_bytes"]
        < Path(str(row["source_file"])).stat().st_size
    )
    assert _without_diagnostics(offset_payload) == _without_diagnostics(sequential_payload)


def test_stale_offset_falls_back_without_changing_context_payload(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]
    source_path = Path(str(row["source_file"]))

    expected = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )
    with source_path.open("ab") as handle:
        handle.write(b"{not valid json\n")
    actual = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )

    assert actual["diagnostics"]["context_read_strategy"] == "sequential_fallback"
    assert actual["diagnostics"]["context_read_reason"] == "stale_provenance"
    assert _without_diagnostics(actual) == _without_diagnostics(expected)


def test_offset_falls_back_when_turn_start_is_outside_backward_window(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]

    expected = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
        max_backward_bytes=1,
    )
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE usage_events SET source_byte_offset = NULL WHERE record_id = ?",
            (row["record_id"],),
        )
    sequential = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )

    assert expected["diagnostics"]["context_read_strategy"] == "sequential_fallback"
    assert expected["diagnostics"]["context_read_reason"] == "turn_start_outside_window"
    assert (
        expected["diagnostics"]["inspected_source_bytes"]
        > sequential["diagnostics"]["inspected_source_bytes"]
    )
    assert _without_diagnostics(expected) == _without_diagnostics(sequential)


def test_invalid_offset_alignment_falls_back_to_equivalent_payload(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE usage_events SET source_byte_offset = source_byte_offset + 1 "
            "WHERE record_id = ?",
            (row["record_id"],),
        )

    fallback = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE usage_events SET source_byte_offset = NULL WHERE record_id = ?",
            (row["record_id"],),
        )
    sequential = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )

    assert fallback["diagnostics"]["context_read_strategy"] == "sequential_fallback"
    assert fallback["diagnostics"]["context_read_reason"] == "invalid_offset"
    assert _without_diagnostics(fallback) == _without_diagnostics(sequential)


def test_offset_and_sequential_reads_match_with_malformed_json(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    original = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]
    source_path = Path(str(original["source_file"]))
    token_offset = int(original["source_byte_offset"])
    source_bytes = source_path.read_bytes()
    source_path.write_bytes(
        source_bytes[:token_offset] + b"{malformed synthetic json\n" + source_bytes[token_offset:]
    )
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]

    offset_payload = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE usage_events SET source_byte_offset = NULL WHERE record_id = ?",
            (row["record_id"],),
        )
    sequential_payload = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )

    assert offset_payload["omitted"]["parse_errors"] == 1
    assert sequential_payload["omitted"]["parse_errors"] == 1
    assert _without_diagnostics(offset_payload) == _without_diagnostics(sequential_payload)


def test_offset_and_sequential_reads_match_near_file_boundaries(tmp_path: Path) -> None:
    session_id = "019f9000-0000-7000-8000-000000000032"
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "07"
        / "24"
        / f"rollout-2026-07-24T00-00-00-{session_id}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [{"id": session_id, "thread_name": "Offset boundaries"}],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "near-start", "model": "gpt-5.5"}),
            _token_event(100, 100),
            *[
                _entry(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": f"filler-{index}"}],
                    },
                )
                for index in range(12)
            ],
            _entry("turn_context", {"turn_id": "near-end", "model": "gpt-5.5"}),
            _token_event(300, 200),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    rows = {
        str(row["turn_id"]): row
        for row in query_session_usage(db_path=db_path, session_id=session_id)
    }

    assert rows["near-start"]["line_number"] == 3
    assert rows["near-end"]["line_number"] == 17
    for turn_id in ("near-start", "near-end"):
        row = rows[turn_id]
        offset_payload = load_call_context(
            str(row["record_id"]),
            db_path=db_path,
            max_chars=0,
            max_entries=0,
            diagnostics=True,
        )
        with connect(db_path) as conn:
            conn.execute(
                "UPDATE usage_events SET source_byte_offset = NULL WHERE record_id = ?",
                (row["record_id"],),
            )
        sequential_payload = load_call_context(
            str(row["record_id"]),
            db_path=db_path,
            max_chars=0,
            max_entries=0,
            diagnostics=True,
        )

        assert offset_payload["diagnostics"]["context_read_strategy"] == "offset_seek"
        assert _without_diagnostics(offset_payload) == _without_diagnostics(sequential_payload)
