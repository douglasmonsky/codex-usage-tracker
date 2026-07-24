from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest

import codex_usage_tracker.context.api as context_api
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


def _without_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    normalized.pop("diagnostics", None)
    return normalized


def _write_context_source(
    tmp_path: Path,
    *,
    session_id: str,
    rows: list[dict[str, object] | str],
) -> tuple[Path, Path]:
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
        [{"id": session_id, "thread_name": "Offset safety"}],
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(row if isinstance(row, str) else json.dumps(row))
            handle.write("\n")
    return codex_home, log_path


def test_valid_token_line_for_later_call_cannot_satisfy_requested_record(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    rows = query_session_usage(db_path=db_path, session_id=SESSION_ID)
    first, later = rows[0], rows[1]
    expected = load_call_context(
        str(first["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE usage_events SET source_byte_offset = ? WHERE record_id = ?",
            (later["source_byte_offset"], first["record_id"]),
        )

    actual = load_call_context(
        str(first["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )

    assert actual["diagnostics"]["context_read_strategy"] == "sequential_fallback"
    assert actual["diagnostics"]["context_read_reason"] == "target_mismatch"
    assert _without_diagnostics(actual) == _without_diagnostics(expected)


def test_replacement_between_validation_and_open_forces_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]
    source_path = Path(str(row["source_file"]))
    original_reader = context_api._read_context_for_usage_record
    replaced = False

    def replace_then_read(**kwargs: Any) -> Any:
        nonlocal replaced
        if not replaced:
            replacement = source_path.with_suffix(".replacement")
            replacement.write_bytes(source_path.read_bytes())
            os.replace(replacement, source_path)
            replaced = True
        return original_reader(**kwargs)

    monkeypatch.setattr(
        context_api,
        "_read_context_for_usage_record",
        replace_then_read,
    )

    payload = load_call_context(
        str(row["record_id"]),
        db_path=db_path,
        diagnostics=True,
    )

    assert payload["diagnostics"]["context_read_strategy"] == "sequential_fallback"
    assert payload["diagnostics"]["context_read_reason"] == "stale_provenance"


def test_offset_falls_back_when_pre_turn_carry_anchor_is_outside_window(
    tmp_path: Path,
) -> None:
    session_id = "019f9000-0000-7000-8000-000000000033"
    codex_home, _log_path = _write_context_source(
        tmp_path,
        session_id=session_id,
        rows=[
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "before", "model": "gpt-5.5"}),
            _token_event(100, 100),
            _entry(
                "compacted",
                {
                    "message": "",
                    "replacement_history": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "Carry this summary"}],
                        }
                    ],
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "x" * 150_000}],
                },
            ),
            _entry("turn_context", {"turn_id": "selected", "model": "gpt-5.5"}),
            _token_event(300, 200),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    target = next(
        row
        for row in query_session_usage(db_path=db_path, session_id=session_id)
        if row["turn_id"] == "selected"
    )

    payload = load_call_context(
        str(target["record_id"]),
        db_path=db_path,
        include_compaction_history=True,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )

    assert payload["diagnostics"]["context_read_strategy"] == "sequential_fallback"
    assert payload["diagnostics"]["context_read_reason"] == "context_anchor_outside_window"
    assert any(entry["label"] == "Compaction detected" for entry in payload["entries"])


def test_malformed_diagnostics_are_scoped_to_bounded_context_anchor(
    tmp_path: Path,
) -> None:
    session_id = "019f9000-0000-7000-8000-000000000034"
    codex_home, _log_path = _write_context_source(
        tmp_path,
        session_id=session_id,
        rows=[
            _entry("session_meta", {"id": session_id}),
            "{malformed history",
            _entry("turn_context", {"turn_id": "old", "model": "gpt-5.5"}),
            _token_event(100, 100),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "x" * 150_000}],
                },
            ),
            _entry("turn_context", {"turn_id": "anchor", "model": "gpt-5.5"}),
            _token_event(200, 100),
            _entry("turn_context", {"turn_id": "selected", "model": "gpt-5.5"}),
            _token_event(400, 200),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    target = next(
        row
        for row in query_session_usage(db_path=db_path, session_id=session_id)
        if row["turn_id"] == "selected"
    )

    offset_payload = load_call_context(
        str(target["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE usage_events SET source_byte_offset = NULL WHERE record_id = ?",
            (target["record_id"],),
        )
    sequential_payload = load_call_context(
        str(target["record_id"]),
        db_path=db_path,
        max_chars=0,
        max_entries=0,
        diagnostics=True,
    )

    assert offset_payload["diagnostics"]["context_read_strategy"] == "offset_seek"
    assert offset_payload["omitted"]["parse_errors"] == 0
    assert _without_diagnostics(offset_payload) == _without_diagnostics(sequential_payload)
