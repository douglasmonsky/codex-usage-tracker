"""Validated bounded source reads for indexed context offsets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.context.values import optional_str
from codex_usage_tracker.store.sources import (
    SourceFileMetadata,
    source_file_handle_metadata_matches,
)


@dataclass(frozen=True)
class ContextOffsetWindow:
    prefix_lines: tuple[bytes, ...]
    target_line: bytes
    first_line_number: int
    inspected_source_bytes: int
    failure_reason: str | None = None


def read_context_offset_window(
    *,
    path: Path,
    token_line: int,
    source_byte_offset: int,
    source_metadata: SourceFileMetadata | None,
    target_usage_row: dict[str, Any],
    max_backward_bytes: int,
) -> ContextOffsetWindow:
    window_start = max(0, source_byte_offset - max(0, max_backward_bytes))
    with path.open("rb") as handle:
        if source_metadata is None or not source_file_handle_metadata_matches(
            handle,
            source_metadata,
        ):
            return _failed_window("stale_provenance")
        handle.seek(window_start)
        prefix = handle.read(source_byte_offset - window_start)
        inspected_source_bytes = len(prefix)
        if window_start > 0:
            newline_index = prefix.find(b"\n")
            if newline_index < 0:
                return _failed_window(
                    "turn_start_outside_window",
                    inspected_source_bytes,
                )
            prefix = prefix[newline_index + 1 :]
        if prefix and not prefix.endswith(b"\n"):
            return _failed_window("invalid_offset", inspected_source_bytes)
        target_line = handle.readline()
        inspected_source_bytes += len(target_line)
    if not target_line:
        return _failed_window("invalid_offset", inspected_source_bytes)
    if not _target_token_event_matches(target_line, target_usage_row):
        return _failed_window("target_mismatch", inspected_source_bytes)
    prefix_lines = tuple(prefix.splitlines(keepends=True))
    return ContextOffsetWindow(
        prefix_lines=prefix_lines,
        target_line=target_line,
        first_line_number=token_line - len(prefix_lines),
        inspected_source_bytes=inspected_source_bytes,
    )


def _failed_window(
    reason: str,
    inspected_source_bytes: int = 0,
) -> ContextOffsetWindow:
    return ContextOffsetWindow((), b"", 0, inspected_source_bytes, reason)


def _target_token_event_matches(
    line: bytes,
    target_usage_row: dict[str, Any],
) -> bool:
    target = _token_event_target(line)
    if target is None:
        return False
    timestamp, last_usage, total_usage = target
    return timestamp == optional_str(target_usage_row.get("event_timestamp")) and (
        _target_usage_values_match(last_usage, total_usage, target_usage_row)
    )


def _token_event_target(
    line: bytes,
) -> tuple[str | None, dict[str, Any], dict[str, Any]] | None:
    try:
        envelope = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(envelope, dict):
        return None
    raw_payload = envelope.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    if envelope.get("type") != "event_msg" or payload.get("type") != "token_count":
        return None
    raw_info = payload.get("info")
    info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
    raw_last_usage = info.get("last_token_usage")
    last_usage: dict[str, Any] = raw_last_usage if isinstance(raw_last_usage, dict) else {}
    raw_total_usage = info.get("total_token_usage")
    total_usage: dict[str, Any] = raw_total_usage if isinstance(raw_total_usage, dict) else {}
    return optional_str(envelope.get("timestamp")), last_usage, total_usage


def _target_usage_values_match(
    last_usage: dict[str, Any],
    total_usage: dict[str, Any],
    target_usage_row: dict[str, Any],
) -> bool:
    expected_fields = (
        (last_usage, "input_tokens", "input_tokens"),
        (last_usage, "cached_input_tokens", "cached_input_tokens"),
        (last_usage, "output_tokens", "output_tokens"),
        (last_usage, "reasoning_output_tokens", "reasoning_output_tokens"),
        (last_usage, "total_tokens", "total_tokens"),
        (total_usage, "input_tokens", "cumulative_input_tokens"),
        (total_usage, "cached_input_tokens", "cumulative_cached_input_tokens"),
        (total_usage, "output_tokens", "cumulative_output_tokens"),
        (
            total_usage,
            "reasoning_output_tokens",
            "cumulative_reasoning_output_tokens",
        ),
        (total_usage, "total_tokens", "cumulative_total_tokens"),
    )
    return all(
        _target_integer_matches(values.get(source_key), target_usage_row.get(row_key))
        for values, source_key, row_key in expected_fields
    )


def _target_integer_matches(value: object, expected: object) -> bool:
    if isinstance(value, (bool, float)):
        return False
    try:
        parsed = int(value) if isinstance(value, (int, str)) else None
        expected_value = int(expected) if isinstance(expected, (int, str)) else None
    except ValueError:
        return False
    return parsed is not None and parsed == expected_value
