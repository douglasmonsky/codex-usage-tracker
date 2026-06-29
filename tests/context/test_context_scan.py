from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.context.api import load_call_context
from codex_usage_tracker.store.api import query_session_usage, refresh_usage_index
from tests.store_dashboard_helpers import _entry, _token_event, _write_jsonl


def test_context_scan_counts_parse_errors_without_losing_selected_turn(tmp_path: Path) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-508941433333"
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "06"
        / "11"
        / f"rollout-2026-06-11T22-50-00-{session_id}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [{"id": session_id, "thread_name": "Parse error context", "updated_at": "2026-06-11T22:55:00Z"}],
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(_entry("session_meta", {"id": session_id})) + "\n")
        handle.write("{not valid json\n")
        handle.write(json.dumps(_entry("turn_context", {"turn_id": "parse-turn", "model": "gpt-5.5"})) + "\n")
        handle.write(
            json.dumps(
                _entry(
                    "response_item",
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "still load this turn"}],
                    },
                )
            )
            + "\n"
        )
        handle.write(json.dumps(_token_event(300, 200)) + "\n")
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    target = query_session_usage(db_path=db_path, session_id=session_id)[0]

    context = load_call_context(target["record_id"], db_path=db_path)
    labels = [entry["label"] for entry in context["entries"]]

    assert context["omitted"]["parse_errors"] == 1
    assert context["serialized_evidence"]["parse_errors"] == 1
    assert "message / user" in labels
