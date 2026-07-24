"""Context loader payload and source validation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from codex_usage_tracker.context.values import positive_int
from codex_usage_tracker.store.usage_record_queries import query_usage_record


@dataclass
class LoadedContextData:
    entries: list[dict[str, Any]]
    omitted: dict[str, Any]
    estimate_entries: list[dict[str, Any]]
    serialized_estimate: dict[str, Any]
    serialized_estimate_ms: float
    action_timing: dict[str, Any]
    source_scan_ms: float
    context_read_strategy: str
    context_read_reason: str
    inspected_source_bytes: int


def elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


def load_context_usage_record(
    *,
    db_path: Path,
    record_id: str,
    diagnostic_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    db_lookup_started = perf_counter()
    row = query_usage_record(db_path=db_path, record_id=record_id)
    if diagnostic_payload is not None:
        diagnostic_payload["db_lookup_ms"] = elapsed_ms(db_lookup_started)
    if row is None:
        raise ValueError(f"No usage record found for record_id: {record_id}")
    return row


def context_source_location(row: dict[str, Any], *, record_id: str) -> tuple[Path, int, int]:
    source_file = Path(str(row.get("source_file") or ""))
    if not source_file.exists():
        raise FileNotFoundError(f"Source log not found: {source_file}")
    line_number = positive_int(row.get("line_number"))
    if line_number is None:
        raise ValueError(f"Usage record has no valid source line: {record_id}")
    return source_file, source_file.stat().st_size, line_number


def bounded_context_chars(max_chars: int) -> int:
    return max_chars if max_chars <= 0 else max(1_000, max_chars)


def bounded_context_entries(max_entries: int) -> int:
    return max_entries if max_entries <= 0 else max(1, max_entries)


def context_response_payload(
    *,
    row: dict[str, Any],
    source_file: Path,
    line_number: int,
    context_mode: str,
    include_tool_output: bool,
    include_compaction_history: bool,
    visible_estimate: dict[str, Any],
    loaded: LoadedContextData,
) -> dict[str, Any]:
    return {
        "schema": "codex-usage-tracker-context-v1",
        "loaded_on_demand": True,
        "raw_context_persisted": False,
        "context_mode": context_mode,
        "include_tool_output": include_tool_output,
        "include_compaction_history": include_compaction_history,
        "visible_char_count": visible_estimate["visible_char_count"],
        "visible_token_estimate": visible_estimate["visible_token_estimate"],
        "visible_token_estimator": visible_estimate["visible_token_estimator"],
        "serialized_evidence": loaded.serialized_estimate,
        "action_timing": loaded.action_timing,
        "record": context_record_payload(row),
        "source": {
            "file": str(source_file),
            "line_number": line_number,
        },
        "entries": loaded.entries,
        "omitted": loaded.omitted,
    }


def context_record_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": row.get("record_id"),
        "session_id": row.get("session_id"),
        "thread_name": row.get("thread_name"),
        "turn_id": row.get("turn_id"),
        "event_timestamp": row.get("event_timestamp"),
        "model": row.get("model"),
        "effort": row.get("effort"),
        "parent_session_id": row.get("parent_session_id"),
        "parent_thread_name": row.get("parent_thread_name"),
        "total_tokens": row.get("total_tokens"),
        "cumulative_total_tokens": row.get("cumulative_total_tokens"),
    }


def attach_context_diagnostics(
    *,
    payload: dict[str, Any],
    diagnostic_payload: dict[str, Any] | None,
    loaded: LoadedContextData,
    source_file_bytes: int,
    line_number: int,
) -> None:
    if diagnostic_payload is None:
        return
    diagnostic_payload["source_scan_ms"] = loaded.source_scan_ms
    diagnostic_payload["serialized_estimate_ms"] = loaded.serialized_estimate_ms
    diagnostic_payload["source_file_bytes"] = source_file_bytes
    diagnostic_payload["source_line_number"] = line_number
    diagnostic_payload["context_read_strategy"] = loaded.context_read_strategy
    diagnostic_payload["context_read_reason"] = loaded.context_read_reason
    diagnostic_payload["inspected_source_bytes"] = loaded.inspected_source_bytes
    diagnostic_payload["entries_before_limit"] = int(loaded.omitted.get("total_entries") or 0)
    diagnostic_payload["entries_returned"] = len(loaded.entries)
    payload["diagnostics"] = diagnostic_payload
    diagnostic_payload["json_bytes"] = json_byte_count(payload)


def json_byte_count(payload: dict[str, Any]) -> int:
    previous_size: int | None = None
    diagnostics = payload.get("diagnostics")
    while True:
        size = len(json.dumps(payload, ensure_ascii=True).encode("utf-8"))
        if size == previous_size or not isinstance(diagnostics, dict):
            return size
        diagnostics["json_bytes"] = size
        previous_size = size
