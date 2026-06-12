from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.call_origin import annotate_rows_with_call_origin


def test_call_origin_uses_event_metadata_between_token_counts(tmp_path: Path) -> None:
    log_path = tmp_path / "session.jsonl"
    rows = [
        _entry("session_meta", {"id": "session-a"}),
        _entry("turn_context", {"turn_id": "turn-a"}),
        _entry("response_item", {"type": "message", "role": "user", "content": []}),
        _entry("event_msg", {"type": "user_message", "message": "raw prompt is ignored"}),
        _entry("response_item", {"type": "message", "role": "assistant", "content": []}),
        _token_event(),
        _entry("response_item", {"type": "function_call_output", "output": "raw output is ignored"}),
        _entry("response_item", {"type": "message", "role": "assistant", "content": []}),
        _token_event(),
        _entry("compacted", {"message": "", "replacement_history": []}),
        _entry("turn_context", {"turn_id": "turn-b"}),
        _token_event(),
        _token_event(),
    ]
    _write_jsonl(log_path, rows)

    annotated = annotate_rows_with_call_origin(
        [
            _row("user", log_path, 6),
            _row("tool", log_path, 9),
            _row("compaction", log_path, 12),
            _row("unknown", log_path, 13),
        ]
    )
    by_id = {row["record_id"]: row for row in annotated}

    assert by_id["user"]["call_initiator"] == "user"
    assert by_id["user"]["call_initiator_reason"] == "user_message"
    assert by_id["tool"]["call_initiator"] == "codex"
    assert by_id["tool"]["call_initiator_reason"] == "tool_result"
    assert by_id["compaction"]["call_initiator"] == "codex"
    assert by_id["compaction"]["call_initiator_reason"] == "post_compaction"
    assert by_id["unknown"]["call_initiator"] == "unknown"
    assert by_id["unknown"]["call_initiator_reason"] == "no_signal"


def test_call_origin_falls_back_to_subagent_metadata_when_source_missing(tmp_path: Path) -> None:
    annotated = annotate_rows_with_call_origin(
        [
            {
                "record_id": "subagent",
                "source_file": str(tmp_path / "missing.jsonl"),
                "line_number": 1,
                "thread_source": "subagent",
            },
            {
                "record_id": "normal",
                "source_file": str(tmp_path / "missing.jsonl"),
                "line_number": 2,
                "thread_source": "user",
            },
        ]
    )
    by_id = {row["record_id"]: row for row in annotated}

    assert by_id["subagent"]["call_initiator"] == "codex"
    assert by_id["subagent"]["call_initiator_reason"] == "thread_source"
    assert by_id["normal"]["call_initiator"] == "unknown"
    assert by_id["normal"]["call_initiator_reason"] == "source_unavailable"


def _row(record_id: str, source_file: Path, line_number: int) -> dict[str, object]:
    return {
        "record_id": record_id,
        "source_file": str(source_file),
        "line_number": line_number,
        "thread_source": "user",
    }


def _token_event() -> dict[str, object]:
    return _entry("event_msg", {"type": "token_count"})


def _entry(entry_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {"type": entry_type, "payload": payload}


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
