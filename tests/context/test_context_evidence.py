from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_usage_tracker.context.api import load_call_context
from codex_usage_tracker.store.api import (
    query_diagnostic_fact_calls,
    query_session_usage,
    refresh_usage_index,
)
from tests.store_dashboard_helpers import (
    SESSION_ID,
    _entry,
    _make_codex_home,
    _token_event,
    _write_jsonl,
)


def test_context_loads_raw_log_only_on_demand(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    rows = query_session_usage(db_path=db_path, session_id=SESSION_ID)

    context = load_call_context(rows[0]["record_id"], db_path=db_path)
    context_text = json.dumps(context)

    assert context["loaded_on_demand"] is True
    assert context["raw_context_persisted"] is False
    assert context["context_mode"] == "quick"
    assert context["visible_char_count"] > 0
    assert context["visible_token_estimate"] > 0
    assert context["visible_token_estimator"] in {
        "chars_per_4_fallback",
        "tiktoken:o200k_base",
        "tiktoken:cl100k_base",
    }
    serialized = context["serialized_evidence"]
    assert serialized["available"] is True
    assert serialized["scope"] == "selected_turn_raw_jsonl_fast_estimate"
    assert serialized["upper_bound"] is True
    assert serialized["raw_text_returned"] is False
    assert serialized["deferred"] is True
    assert serialized["deferred_buckets"] is True
    assert serialized["reason"] == "full_serialized_analysis_not_requested"
    assert serialized["raw_line_count"] >= len(context["entries"])
    assert serialized["raw_json_char_count"] > context["visible_char_count"]
    assert serialized["raw_json_token_estimate"] >= context["visible_token_estimate"]
    assert serialized["token_estimator"] == "chars_per_4_fallback"
    assert serialized["buckets"] == []
    full_context = load_call_context(rows[0]["record_id"], db_path=db_path, mode="full")
    full_serialized = full_context["serialized_evidence"]
    assert full_context["context_mode"] == "full"
    assert full_serialized["scope"] == "selected_turn_raw_jsonl"
    assert full_serialized["deferred"] is False
    assert full_serialized["deferred_buckets"] is False
    assert full_serialized["token_estimator"] in {
        "chars_per_4_fallback",
        "tiktoken:o200k_base",
        "tiktoken:cl100k_base",
    }
    serialized_bucket_keys = {bucket["key"] for bucket in full_serialized["buckets"]}
    assert "encrypted_reasoning_state" in serialized_bucket_keys
    assert "local_goal_metadata" in serialized_bucket_keys
    assert "call_anchors" not in context
    assert "thread_anchors" not in context
    assert context["omitted"]["total_entries"] >= context["omitted"]["returned_entries"]
    assert "SECRET RAW PROMPT" in context_text
    assert "sk" + "-proj-" not in context_text
    assert "AKIAIOSFODNN7EXAMPLE" not in context_text
    assert "Authorization: Bearer abc.def" not in context_text
    assert "xoxb-123456789012" not in context_text
    assert "eyJhbGciOiJIUzI1Ni" not in context_text
    assert "client_secret=super-secret-value" not in context_text
    assert "BEGIN OPENSSH PRIVATE KEY" not in context_text
    assert "[REDACTED_OPENAI_KEY]" in context_text
    assert "[REDACTED_AWS_ACCESS_KEY]" in context_text
    assert "[REDACTED_BEARER_TOKEN]" in context_text
    assert "[REDACTED_SLACK_TOKEN]" in context_text
    assert "[REDACTED_JWT]" in context_text
    assert "[REDACTED_PRIVATE_KEY]" in context_text
    assert any(entry["label"] == "message / user" for entry in context["entries"])
    token_entry = next(entry for entry in context["entries"] if entry["label"] == "Token count")
    assert token_entry["token_usage"]["last_token_usage"]["uncached_input_tokens"] >= 0
    compaction_entries = [
        entry for entry in context["entries"] if entry["label"] == "Compaction detected"
    ]
    assert len(compaction_entries) == 2
    compaction_entry = next(
        entry for entry in compaction_entries if entry["compaction"]["replacement_entry_count"] == 2
    )
    event_compaction_entry = next(
        entry for entry in compaction_entries if entry["compaction"]["replacement_entry_count"] == 1
    )
    assert compaction_entry["compaction"]["replacement_history_available"] is True
    assert compaction_entry["compaction"]["replacement_entry_count"] == 2
    assert compaction_entry["compaction"]["replacement_history_included"] is False
    assert event_compaction_entry["compaction"]["replacement_history_available"] is True
    assert event_compaction_entry["compaction"]["replacement_history_included"] is False
    assert "replacement_history" not in compaction_entry["compaction"]
    assert "COMPACTED REPLACEMENT SUMMARY" not in context_text
    assert "EVENT MSG COMPACTION SUMMARY" not in context_text
    assert "ENCRYPTED_STATE_SENTINEL_DO_NOT_RETURN" not in context_text
    assert "LOCAL_GOAL_SENTINEL_DO_NOT_RETURN" not in context_text

    compaction_context = load_call_context(
        rows[0]["record_id"],
        db_path=db_path,
        include_compaction_history=True,
    )
    compaction_context_text = json.dumps(compaction_context)
    compaction_with_history = next(
        entry for entry in compaction_context["entries"] if entry["label"] == "Compaction detected"
    )
    assert compaction_context["include_compaction_history"] is True
    assert compaction_with_history["compaction"]["replacement_history_included"] is True
    assert "COMPACTED REPLACEMENT SUMMARY" in compaction_context_text
    assert "EVENT MSG COMPACTION SUMMARY" in compaction_context_text
    assert "sk" + "-proj-compactedsecret" not in compaction_context_text
    assert "[REDACTED_OPENAI_KEY]" in compaction_context_text

    limited_context = load_call_context(
        rows[0]["record_id"],
        db_path=db_path,
        max_chars=40,
        max_entries=1,
    )
    unlimited_context = load_call_context(
        rows[0]["record_id"],
        db_path=db_path,
        max_chars=0,
        max_entries=0,
    )
    assert limited_context["omitted"]["returned_entries"] == 1
    assert limited_context["omitted"]["older_entries"] > 0
    assert unlimited_context["omitted"]["max_chars"] == 0
    assert unlimited_context["omitted"]["max_entries"] == 0
    assert unlimited_context["omitted"]["older_entries"] == 0
    assert unlimited_context["omitted"]["over_budget_chars"] == 0
    assert len(unlimited_context["entries"]) > len(limited_context["entries"])


def test_context_evidence_includes_lightweight_action_timing(tmp_path: Path) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-508941431113"
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "06"
        / "11"
        / f"rollout-2026-06-11T22-40-00-{session_id}.jsonl"
    )

    def stamped(entry: dict[str, object], timestamp: str) -> dict[str, object]:
        row = dict(entry)
        row["timestamp"] = timestamp
        return row

    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": session_id,
                "thread_name": "Evidence timing",
                "updated_at": "2026-06-11T22:40:08Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            stamped(_entry("session_meta", {"id": session_id}), "2026-06-11T22:40:00.000Z"),
            stamped(
                _entry("turn_context", {"turn_id": "timing-turn", "model": "gpt-5.5"}),
                "2026-06-11T22:40:00.000Z",
            ),
            stamped(
                _entry(
                    "response_item",
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Run focused evidence timing."}],
                    },
                ),
                "2026-06-11T22:40:02.500Z",
            ),
            stamped(
                _entry(
                    "event_msg",
                    {
                        "type": "mcp_tool_call_end",
                        "call_id": "call-timing",
                        "turn_id": "timing-turn",
                        "server_name": "local",
                        "tool_name": "fixture",
                        "duration_ms": 1200,
                        "status": "success",
                    },
                ),
                "2026-06-11T22:40:05.000Z",
            ),
            stamped(_token_event(250, 250), "2026-06-11T22:40:07.250Z"),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    target = query_session_usage(db_path=db_path, session_id=session_id)[0]

    context = load_call_context(
        target["record_id"],
        db_path=db_path,
        max_chars=0,
        max_entries=0,
    )
    entries_by_label = {entry["label"]: entry for entry in context["entries"]}
    action_timing_text = json.dumps(context["action_timing"])

    assert context["action_timing"] == {
        "available": True,
        "scope": "selected_turn_evidence_entries",
        "source": "entry_timestamps",
        "timed_entry_count": 4,
        "total_elapsed_ms": 7250,
        "slowest_gap_ms": 2500,
    }
    assert entries_by_label["Turn context"]["action_timing"]["since_turn_start_ms"] == 0
    assert entries_by_label["message / user"]["action_timing"]["since_previous_entry_ms"] == 2500
    assert entries_by_label["mcp_tool_call_end"]["action_timing"] == {
        "reported_duration_ms": 1200,
        "duration_source": "event.duration_ms",
        "since_turn_start_ms": 5000,
        "since_previous_entry_ms": 2500,
        "timestamp_source": "entry.timestamp",
    }
    assert entries_by_label["Token count"]["action_timing"]["since_turn_start_ms"] == 7250
    assert entries_by_label["Token count"]["action_timing"]["since_previous_entry_ms"] == 2250
    assert ".jsonl" not in action_timing_text
    assert "Run focused evidence timing" not in action_timing_text


def test_context_loading_uses_one_source_scan_for_evidence_and_serialized_estimate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]
    source_file = Path(str(row["source_file"]))
    open_count = 0
    real_open = Path.open

    def counting_open(path: Path, *args: object, **kwargs: object):
        nonlocal open_count
        if path == source_file:
            open_count += 1
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)

    context = load_call_context(row["record_id"], db_path=db_path, diagnostics=True)

    assert open_count == 1
    assert any(entry["label"] == "message / user" for entry in context["entries"])
    assert context["include_tool_output"] is False
    assert context["context_mode"] == "quick"
    assert context["serialized_evidence"]["available"] is True
    assert context["serialized_evidence"]["deferred_buckets"] is True
    assert "call_anchors" not in context
    assert "thread_anchors" not in context
    assert context["diagnostics"]["source_scan_ms"] >= 0
    assert context["diagnostics"]["serialized_estimate_ms"] >= 0


def test_context_carries_incoming_compaction_history_into_selected_turn(tmp_path: Path) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-508941431111"
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "06"
        / "11"
        / f"rollout-2026-06-11T22-20-00-{session_id}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": session_id,
                "thread_name": "Compaction boundary",
                "updated_at": "2026-06-11T22:30:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "before-compact", "model": "gpt-5.5"}),
            _token_event(100, 100),
            _entry(
                "compacted",
                {
                    "message": "",
                    "replacement_history": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "INCOMING REPLACEMENT HISTORY sk-proj-boundarysecret",
                                }
                            ],
                        }
                    ],
                },
            ),
            _entry("turn_context", {"turn_id": "after-compact", "model": "gpt-5.5"}),
            _entry("event_msg", {"type": "context_compacted"}),
            _token_event(300, 200),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    target = next(
        row
        for row in query_session_usage(db_path=db_path, session_id=session_id)
        if row["turn_id"] == "after-compact"
    )

    context = load_call_context(
        target["record_id"],
        db_path=db_path,
        include_compaction_history=True,
    )
    compaction_entries = [
        entry for entry in context["entries"] if entry["label"] == "Compaction detected"
    ]

    assert [entry["line_number"] for entry in compaction_entries] == [4, 6]
    assert compaction_entries[0]["compaction"]["replacement_entry_count"] == 1
    assert compaction_entries[0]["compaction"]["replacement_history_included"] is True
    assert compaction_entries[1]["compaction"]["replacement_entry_count"] == 0
    assert "Compaction marker found" in compaction_entries[1]["text"]
    context_text = json.dumps(context)
    assert "INCOMING REPLACEMENT HISTORY" in context_text
    assert "sk-proj-boundarysecret" not in context_text
    assert "[REDACTED_OPENAI_KEY]" in context_text


def test_context_carries_safe_diagnostic_events_into_selected_turn(tmp_path: Path) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-508941431112"
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "06"
        / "11"
        / f"rollout-2026-06-11T22-25-00-{session_id}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": session_id,
                "thread_name": "Diagnostic boundary",
                "updated_at": "2026-06-11T22:35:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "before-diagnostic", "model": "gpt-5.5"}),
            _token_event(100, 100),
            _entry(
                "event_msg",
                {
                    "type": "thread_rolled_back",
                    "num_turns": 1,
                    "reason": "SECRET ROLLBACK",
                },
            ),
            _entry("event_msg", {"type": "turn_aborted", "reason": "SECRET ABORT"}),
            _entry("turn_context", {"turn_id": "after-diagnostic", "model": "gpt-5.5"}),
            _token_event(300, 200),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    fact_calls = query_diagnostic_fact_calls(
        db_path=db_path,
        fact_type="outcome",
        fact_name="thread_rolled_back",
        limit=0,
    )
    target = next(
        row
        for row in query_session_usage(db_path=db_path, session_id=session_id)
        if row["turn_id"] == "after-diagnostic"
    )

    context = load_call_context(target["record_id"], db_path=db_path)
    entries_by_label = {entry["label"]: entry for entry in context["entries"]}
    context_text = json.dumps(context)

    assert [row["record_id"] for row in fact_calls] == [target["record_id"]]
    assert entries_by_label["thread_rolled_back"]["line_number"] == 4
    assert '"num_turns": 1' in entries_by_label["thread_rolled_back"]["text"]
    assert entries_by_label["turn_aborted"]["line_number"] == 5
    assert "SECRET ROLLBACK" not in context_text
    assert "SECRET ABORT" not in context_text


def test_context_dedupes_adjacent_chat_message_echoes(tmp_path: Path) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-508941432222"
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "06"
        / "11"
        / f"rollout-2026-06-11T22-40-00-{session_id}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [{"id": session_id, "thread_name": "Echo dedupe", "updated_at": "2026-06-11T22:45:00Z"}],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "echo-turn", "model": "gpt-5.5"}),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "same user text"}],
                },
            ),
            _entry("event_msg", {"type": "user_message", "message": "same user text"}),
            _entry("event_msg", {"type": "agent_message", "message": "same assistant text"}),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "same assistant text"}],
                },
            ),
            _token_event(300, 200),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    target = query_session_usage(db_path=db_path, session_id=session_id)[0]

    context = load_call_context(target["record_id"], db_path=db_path)
    labels = [entry["label"] for entry in context["entries"]]
    texts = [entry["text"] for entry in context["entries"]]

    assert "message / user" in labels
    assert "message / assistant" in labels
    assert "user_message" not in labels
    assert "agent_message" not in labels
    assert texts.count("same user text") == 1
    assert texts.count("same assistant text") == 1
