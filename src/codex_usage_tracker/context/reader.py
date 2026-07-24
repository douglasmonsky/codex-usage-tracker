"""Lazy raw-context loading for one aggregate usage record."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from codex_usage_tracker.context import entries as context_entries
from codex_usage_tracker.context.action_timing import (
    annotate_action_timing,
)
from codex_usage_tracker.context.constants import (
    CONTEXT_MODE_FULL,
    DEFAULT_CONTEXT_SEEK_BACKWARD_BYTES,
)
from codex_usage_tracker.context.loader import (
    LoadedContextData,
    bounded_context_chars,
    bounded_context_entries,
    elapsed_ms,
)
from codex_usage_tracker.context.offset_window import read_context_offset_window
from codex_usage_tracker.context.serialized import (
    collect_serialized_envelope,
    quick_serialized_context_estimate,
    serialized_context_estimate,
)
from codex_usage_tracker.context.summaries import (
    dedupe_chat_message_echoes,
    summarize_payload,
    summarize_turn_context,
)
from codex_usage_tracker.context.token_estimates import (
    context_encoding,
)
from codex_usage_tracker.context.values import (
    optional_str,
)
from codex_usage_tracker.store.sources import SourceFileMetadata


def _read_context_for_usage_record(
    *,
    row: dict[str, Any],
    source_file: Path,
    line_number: int,
    source_byte_offset: int | None,
    context_read_reason: str,
    source_metadata: SourceFileMetadata | None,
    max_chars: int,
    max_entries: int,
    include_tool_output: bool,
    include_compaction_history: bool,
    context_mode: str,
    max_backward_bytes: int = DEFAULT_CONTEXT_SEEK_BACKWARD_BYTES,
) -> LoadedContextData:
    source_scan_started = perf_counter()
    (
        entries,
        omitted,
        estimate_entries,
        serialized_estimate,
        serialized_estimate_ms,
        action_timing,
        context_read_strategy,
        resolved_read_reason,
        inspected_source_bytes,
    ) = _read_context_entries(
        path=source_file,
        token_line=line_number,
        target_turn_id=optional_str(row.get("turn_id")),
        source_byte_offset=source_byte_offset,
        context_read_reason=context_read_reason,
        source_metadata=source_metadata,
        target_usage_row=row,
        max_backward_bytes=max_backward_bytes,
        max_chars=bounded_context_chars(max_chars),
        max_entries=bounded_context_entries(max_entries),
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
        model=optional_str(row.get("model")),
        context_mode=context_mode,
    )
    return LoadedContextData(
        entries=entries,
        omitted=omitted,
        estimate_entries=estimate_entries,
        serialized_estimate=serialized_estimate,
        serialized_estimate_ms=serialized_estimate_ms,
        action_timing=action_timing,
        source_scan_ms=elapsed_ms(source_scan_started),
        context_read_strategy=context_read_strategy,
        context_read_reason=resolved_read_reason,
        inspected_source_bytes=inspected_source_bytes,
    )


@dataclass
class _ContextReadState:
    target_turn_id: str | None
    full_serialized_analysis: bool
    encoding: Any
    estimator: str
    collecting: bool
    candidates: list[dict[str, Any]] = field(default_factory=list)
    raw_entries: list[dict[str, Any]] = field(default_factory=list)
    field_buckets: dict[str, dict[str, Any]] = field(default_factory=dict)
    serialized_line_count: int = 0
    serialized_raw_char_count: int = 0
    omitted_parse_errors: int = 0
    current_turn_id: str | None = None
    target_turn_found: bool = False
    pre_target_turn_boundary_found: bool = False
    pending_compactions: list[dict[str, Any]] = field(default_factory=list)
    pending_diagnostic_events: list[dict[str, Any]] = field(default_factory=list)


def _read_context_entries(
    path: Path,
    token_line: int,
    target_turn_id: str | None,
    source_byte_offset: int | None,
    context_read_reason: str,
    source_metadata: SourceFileMetadata | None,
    target_usage_row: dict[str, Any],
    max_backward_bytes: int,
    max_chars: int,
    max_entries: int,
    include_tool_output: bool,
    include_compaction_history: bool,
    model: str | None,
    context_mode: str,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    float,
    dict[str, Any],
    str,
    str,
    int,
]:
    if source_byte_offset is not None and target_turn_id is not None:
        offset_result = _read_context_from_offset(
            path=path,
            token_line=token_line,
            target_turn_id=target_turn_id,
            source_byte_offset=source_byte_offset,
            source_metadata=source_metadata,
            target_usage_row=target_usage_row,
            max_backward_bytes=max_backward_bytes,
            include_tool_output=include_tool_output,
            include_compaction_history=include_compaction_history,
            model=model,
            context_mode=context_mode,
        )
        state, offset_inspected_bytes, offset_failure_reason = offset_result
        if state is not None:
            return (
                *_context_read_result(state, max_chars=max_chars, max_entries=max_entries),
                "offset_seek",
                context_read_reason,
                offset_inspected_bytes,
            )
        context_read_reason = offset_failure_reason or "invalid_offset"
    else:
        offset_inspected_bytes = 0
    if target_turn_id is None:
        context_read_reason = "missing_turn_id"

    state, inspected_source_bytes = _read_context_sequentially(
        path=path,
        token_line=token_line,
        target_turn_id=target_turn_id,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
        model=model,
        context_mode=context_mode,
    )
    return (
        *_context_read_result(state, max_chars=max_chars, max_entries=max_entries),
        "sequential_fallback",
        context_read_reason,
        offset_inspected_bytes + inspected_source_bytes,
    )


def _read_context_from_offset(
    *,
    path: Path,
    token_line: int,
    target_turn_id: str,
    source_byte_offset: int,
    source_metadata: SourceFileMetadata | None,
    target_usage_row: dict[str, Any],
    max_backward_bytes: int,
    include_tool_output: bool,
    include_compaction_history: bool,
    model: str | None,
    context_mode: str,
) -> tuple[_ContextReadState | None, int, str | None]:
    window = read_context_offset_window(
        path=path,
        token_line=token_line,
        source_byte_offset=source_byte_offset,
        source_metadata=source_metadata,
        target_usage_row=target_usage_row,
        max_backward_bytes=max_backward_bytes,
    )
    if window.failure_reason is not None:
        return None, window.inspected_source_bytes, window.failure_reason
    state = _new_context_read_state(target_turn_id, model, context_mode)
    for line_number, raw_line in enumerate(
        window.prefix_lines,
        window.first_line_number,
    ):
        _scan_context_line(
            state=state,
            line_number=line_number,
            line=raw_line.decode("utf-8"),
            token_line=token_line,
            include_tool_output=include_tool_output,
            include_compaction_history=include_compaction_history,
        )
    target_matched = _scan_context_line(
        state=state,
        line_number=token_line,
        line=window.target_line.decode("utf-8"),
        token_line=token_line,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
    )
    if not target_matched:
        return None, window.inspected_source_bytes, "target_mismatch"
    if not state.target_turn_found:
        return None, window.inspected_source_bytes, "turn_start_outside_window"
    if window.first_line_number > 1 and not state.pre_target_turn_boundary_found:
        return None, window.inspected_source_bytes, "context_anchor_outside_window"
    return state, window.inspected_source_bytes, None


def _read_context_sequentially(
    *,
    path: Path,
    token_line: int,
    target_turn_id: str | None,
    include_tool_output: bool,
    include_compaction_history: bool,
    model: str | None,
    context_mode: str,
) -> tuple[_ContextReadState, int]:
    state = _new_context_read_state(target_turn_id, model, context_mode)
    inspected_source_bytes = 0
    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if line_number > token_line:
                break
            inspected_source_bytes += len(raw_line)
            if _scan_context_line(
                state=state,
                line_number=line_number,
                line=raw_line.decode("utf-8"),
                token_line=token_line,
                include_tool_output=include_tool_output,
                include_compaction_history=include_compaction_history,
            ):
                break
    return state, inspected_source_bytes


def _new_context_read_state(
    target_turn_id: str | None,
    model: str | None,
    context_mode: str,
) -> _ContextReadState:
    full_serialized_analysis = context_mode == CONTEXT_MODE_FULL
    encoding, estimator = (
        context_encoding(model or "")
        if full_serialized_analysis
        else (None, "chars_per_4_fallback")
    )
    return _ContextReadState(
        target_turn_id=target_turn_id,
        full_serialized_analysis=full_serialized_analysis,
        encoding=encoding,
        estimator=estimator,
        collecting=target_turn_id is None,
    )


def _scan_context_line(
    state: _ContextReadState,
    line_number: int,
    line: str,
    token_line: int,
    include_tool_output: bool,
    include_compaction_history: bool,
) -> bool:
    envelope, parse_error = context_entries.context_envelope_from_line(line)
    if parse_error:
        state.omitted_parse_errors += 1
        return False
    if envelope is None:
        return False
    entry_type, payload, timestamp = context_entries.context_envelope_parts(envelope)
    token_count_boundary = context_entries.is_token_count_boundary(
        line_number,
        token_line,
        entry_type,
        payload,
    )
    if entry_type == "turn_context":
        _start_turn_context(state, line_number, line, timestamp, envelope, payload)
        return False
    if state.collecting:
        _collect_serialized_context(state, line, envelope, entry_type, payload)
    summarized = summarize_payload(
        entry_type=entry_type,
        payload=payload,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
    )
    if _pending_summary_handled(state, line_number, timestamp, entry_type, summarized):
        return token_count_boundary
    if summarized is not None:
        state.candidates.append(
            context_entries.summarized_context_entry(line_number, timestamp, entry_type, summarized)
        )
    return token_count_boundary


def _start_turn_context(
    state: _ContextReadState,
    line_number: int,
    line: str,
    timestamp: str | None,
    envelope: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    was_collecting = state.collecting
    state.current_turn_id = optional_str(payload.get("turn_id"))
    state.collecting = state.target_turn_id is None or state.current_turn_id == state.target_turn_id
    _update_turn_parse_error_scope(state)
    if state.collecting:
        state.target_turn_found = True
        _reset_selected_turn_context(state)
        _collect_serialized_context(state, line, envelope, "turn_context", payload)
        carried_compactions = (
            [entry for entry in state.candidates if entry.get("type") == "compacted"]
            if was_collecting and state.target_turn_id is not None
            else []
        )
        state.candidates = [
            context_entries.context_entry(
                line_number,
                timestamp,
                "turn_context",
                "Turn context",
                summarize_turn_context(payload),
            ),
            *state.pending_compactions,
            *state.pending_diagnostic_events,
            *carried_compactions,
        ]
    state.pending_compactions = []
    state.pending_diagnostic_events = []


def _update_turn_parse_error_scope(state: _ContextReadState) -> None:
    if state.target_turn_id is not None and not state.collecting:
        state.pre_target_turn_boundary_found = True
        state.omitted_parse_errors = 0
    elif state.target_turn_id is None and state.target_turn_found:
        state.omitted_parse_errors = 0


def _reset_selected_turn_context(state: _ContextReadState) -> None:
    state.raw_entries = []
    state.field_buckets = {}
    state.serialized_line_count = 0
    state.serialized_raw_char_count = 0


def _collect_serialized_context(
    state: _ContextReadState,
    line: str,
    envelope: dict[str, Any],
    entry_type: str,
    payload: dict[str, Any],
) -> None:
    if state.full_serialized_analysis:
        collect_serialized_envelope(
            raw_entries=state.raw_entries,
            field_buckets=state.field_buckets,
            envelope=envelope,
            entry_type=entry_type,
            payload=payload,
            encoding=state.encoding,
        )
    else:
        state.serialized_line_count += 1
        state.serialized_raw_char_count += len(line)


def _pending_summary_handled(
    state: _ContextReadState,
    line_number: int,
    timestamp: str | None,
    entry_type: str,
    summarized: dict[str, Any] | None,
) -> bool:
    if state.collecting:
        return False
    if summarized is None:
        return True
    if entry_type == "compacted":
        state.pending_compactions = [
            context_entries.summarized_context_entry(line_number, timestamp, entry_type, summarized)
        ]
        return True
    if summarized.get("carry_into_next_turn") is True:
        state.pending_diagnostic_events = [
            *state.pending_diagnostic_events,
            context_entries.summarized_context_entry(
                line_number, timestamp, entry_type, summarized
            ),
        ][-8:]
    return True


def _context_read_result(
    state: _ContextReadState,
    max_chars: int,
    max_entries: int,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    float,
    dict[str, Any],
]:
    serialized_started = perf_counter()
    if state.full_serialized_analysis:
        serialized_estimate = serialized_context_estimate(
            raw_entries=state.raw_entries,
            field_buckets=state.field_buckets,
            parse_errors=state.omitted_parse_errors,
            encoding=state.encoding,
            estimator=state.estimator,
        )
    else:
        serialized_estimate = quick_serialized_context_estimate(
            raw_line_count=state.serialized_line_count,
            raw_json_char_count=state.serialized_raw_char_count,
            parse_errors=state.omitted_parse_errors,
        )
    serialized_estimate_ms = elapsed_ms(serialized_started)
    candidates = dedupe_chat_message_echoes(state.candidates)
    action_timing = annotate_action_timing(candidates)
    limited, omitted = context_entries.limit_entries(
        candidates,
        max_chars=max_chars,
        max_entries=max_entries,
    )
    omitted["parse_errors"] = state.omitted_parse_errors
    omitted["target_turn_id"] = state.target_turn_id
    omitted["total_entries"] = len(candidates)
    return limited, omitted, candidates, serialized_estimate, serialized_estimate_ms, action_timing
