from __future__ import annotations

from collections import Counter
from typing import Any

from codex_usage_tracker.diagnostics.snapshot_source_scan import record_function_call


def test_record_function_call_tracks_read_command_event() -> None:
    counters = _source_scan_counters()
    meta: Counter[str] = Counter()
    call_names: dict[str, str] = {}
    call_roots: dict[str, str] = {}
    call_git_interactions: dict[str, tuple[str, str, str, str]] = {}
    call_read_events: dict[str, list[int]] = {}
    call_record_ids: dict[str, str] = {}
    source_read_events: list[int] = []

    record_function_call(
        {
            "call_id": "call-read",
            "name": "exec_command",
            "arguments": {"cmd": "cat src/example.py"},
        },
        order=7,
        counters=counters,
        meta=meta,
        call_names=call_names,
        call_roots=call_roots,
        call_git_interactions=call_git_interactions,
        call_read_events=call_read_events,
        call_record_ids=call_record_ids,
        source_read_events=source_read_events,
        representative_record_id=None,
    )

    assert counters["function_calls"] == Counter({"exec_command": 1})
    assert counters["command_calls"] == Counter({"cat": 1})
    assert counters["command_children"]["cat"] == Counter({"example.py": 1})
    assert counters["read_command_count"] == 1
    assert counters["read_events"] == [
        {
            "reader": "direct_file_read:cat",
            "root": "cat",
            "path_key": "4e4ec982419e",
            "path_label": "example.py",
            "path_hash": "4e4ec982419e",
            "order": 7,
            "modified_later": False,
            "record_id": "",
        }
    ]
    assert counters["read_events_by_reader"] == Counter({"direct_file_read:cat": 1})
    assert counters["read_events_by_path"] == Counter({"4e4ec982419e": 1})
    assert call_names == {"call-read": "exec_command"}
    assert call_roots == {"call-read": "cat"}
    assert call_read_events == {"call-read": [0]}
    assert call_record_ids == {}
    assert source_read_events == [0]
    assert not call_git_interactions
    assert not meta


def test_record_function_call_tracks_git_interaction() -> None:
    counters = _source_scan_counters()
    call_git_interactions: dict[str, tuple[str, str, str, str]] = {}

    record_function_call(
        {
            "call_id": "call-git",
            "name": "exec_command",
            "arguments": {"cmd": "git status --short"},
        },
        order=8,
        counters=counters,
        meta=Counter(),
        call_names={},
        call_roots={},
        call_git_interactions=call_git_interactions,
        call_read_events={},
        call_record_ids={},
        source_read_events=[],
        representative_record_id=None,
    )

    interaction_key = ("git", "status", "read_only", "read_only")
    assert counters["command_calls"] == Counter({"git": 1})
    assert counters["command_children"]["git"] == Counter({"status": 1})
    assert counters["git_interaction_calls"] == Counter({interaction_key: 1})
    assert counters["git_interactions_by_category"] == Counter({"read_only": 1})
    assert counters["git_interactions_by_mutability"] == Counter({"read_only": 1})
    assert counters["git_interactions_by_root"] == Counter({"git": 1})
    assert call_git_interactions == {"call-git": interaction_key}


def test_record_function_call_counts_missing_shell_command() -> None:
    counters = _source_scan_counters()
    meta: Counter[str] = Counter()

    record_function_call(
        {"id": "call-missing", "name": "exec_command", "arguments": {}},
        order=9,
        counters=counters,
        meta=meta,
        call_names={},
        call_roots={},
        call_git_interactions={},
        call_read_events={},
        call_record_ids={},
        source_read_events=[],
        representative_record_id=None,
    )

    assert counters["function_calls"] == Counter({"exec_command": 1})
    assert not counters["command_calls"]
    assert meta == Counter({"missing_command": 1})


def _source_scan_counters() -> dict[str, Any]:
    return {
        "function_calls": Counter(),
        "command_calls": Counter(),
        "command_children": {},
        "git_interaction_calls": Counter(),
        "git_interactions_by_category": Counter(),
        "git_interactions_by_mutability": Counter(),
        "git_interactions_by_root": Counter(),
        "read_events": [],
        "read_command_count": 0,
        "read_events_by_reader": Counter(),
        "read_events_by_path": Counter(),
        "read_path_refs": {},
        "function_record_ids": {},
        "command_record_ids": {},
        "git_interaction_record_ids": {},
        "read_reader_record_ids": {},
        "read_path_record_ids": {},
    }
