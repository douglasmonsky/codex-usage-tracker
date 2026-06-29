"""Lazy raw-context loading for one aggregate usage record."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from codex_usage_tracker.context_action_timing import (
    annotate_action_timing,
    normalize_millisecond_value,
)
from codex_usage_tracker.context_loader import (
    LoadedContextData,
    attach_context_diagnostics,
    bounded_context_chars,
    bounded_context_entries,
    context_response_payload,
    context_source_location,
    elapsed_ms,
    load_context_usage_record,
)
from codex_usage_tracker.context_serialized import (
    collect_serialized_envelope,
    quick_serialized_context_estimate,
    serialized_context_estimate,
)
from codex_usage_tracker.context_summaries import (
    dedupe_chat_message_echoes,
    summarize_payload,
    summarize_turn_context,
)
from codex_usage_tracker.context_token_estimates import (
    context_encoding,
    estimate_visible_tokens,
)
from codex_usage_tracker.context_values import (
    nonnegative_float,
    optional_str,
    redact_text,
)
from codex_usage_tracker.paths import DEFAULT_DB_PATH

DEFAULT_CONTEXT_CHARS = 20_000
DEFAULT_CONTEXT_ENTRIES = 80
CONTEXT_MODE_QUICK = "quick"
CONTEXT_MODE_FULL = "full"
CONTEXT_MODES = {CONTEXT_MODE_QUICK, CONTEXT_MODE_FULL}

def load_call_context(
    record_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
    max_entries: int = DEFAULT_CONTEXT_ENTRIES,
    include_tool_output: bool = False,
    include_compaction_history: bool = False,
    diagnostics: bool = False,
    mode: str = CONTEXT_MODE_QUICK,
) -> dict[str, Any]:
    """Load logged turn context for one model call from its source JSONL file.

    This intentionally reads raw transcript-like content only on demand. The returned
    context is not written back to SQLite or embedded in the dashboard HTML.
    """

    context_mode = _normalize_context_mode(mode)
    diagnostic_payload: dict[str, Any] | None = {} if diagnostics else None
    row = load_context_usage_record(
        db_path=db_path,
        record_id=record_id,
        diagnostic_payload=diagnostic_payload,
    )
    source_file, source_file_bytes, line_number = context_source_location(
        row, record_id=record_id
    )
    loaded = _read_context_for_usage_record(
        row=row,
        source_file=source_file,
        line_number=line_number,
        max_chars=max_chars,
        max_entries=max_entries,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
        context_mode=context_mode,
    )
    visible_estimate = estimate_visible_tokens(
        loaded.estimate_entries, optional_str(row.get("model"))
    )
    payload = context_response_payload(
        row=row,
        source_file=source_file,
        line_number=line_number,
        context_mode=context_mode,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
        visible_estimate=visible_estimate,
        loaded=loaded,
    )
    attach_context_diagnostics(
        payload=payload,
        diagnostic_payload=diagnostic_payload,
        loaded=loaded,
        source_file_bytes=source_file_bytes,
        line_number=line_number,
    )
    return payload


def _read_context_for_usage_record(
    *,
    row: dict[str, Any],
    source_file: Path,
    line_number: int,
    max_chars: int,
    max_entries: int,
    include_tool_output: bool,
    include_compaction_history: bool,
    context_mode: str,
) -> LoadedContextData:
    source_scan_started = perf_counter()
    (
        entries,
        omitted,
        estimate_entries,
        serialized_estimate,
        serialized_estimate_ms,
        action_timing,
    ) = _read_context_entries(
        path=source_file,
        token_line=line_number,
        target_turn_id=optional_str(row.get("turn_id")),
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
    )


def _normalize_context_mode(mode: str) -> str:
    normalized = str(mode or CONTEXT_MODE_QUICK).strip().lower()
    if normalized not in CONTEXT_MODES:
        raise ValueError(
            f"Unsupported context mode: {mode}. Expected one of: "
            f"{', '.join(sorted(CONTEXT_MODES))}"
        )
    return normalized


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
    pending_compactions: list[dict[str, Any]] = field(default_factory=list)
    pending_diagnostic_events: list[dict[str, Any]] = field(default_factory=list)


def _read_context_entries(
    path: Path,
    token_line: int,
    target_turn_id: str | None,
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
]:
    state = _new_context_read_state(target_turn_id, model, context_mode)

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line_number > token_line:
                break
            if _scan_context_line(
                state=state,
                line_number=line_number,
                line=line,
                token_line=token_line,
                include_tool_output=include_tool_output,
                include_compaction_history=include_compaction_history,
            ):
                break

    return _context_read_result(state, max_chars=max_chars, max_entries=max_entries)


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


def _context_envelope_from_line(line: str) -> tuple[dict[str, Any] | None, bool]:
    try:
        envelope = json.loads(line)
    except json.JSONDecodeError:
        return None, True
    if not isinstance(envelope, dict):
        return None, False
    return envelope, False


def _scan_context_line(
    state: _ContextReadState,
    line_number: int,
    line: str,
    token_line: int,
    include_tool_output: bool,
    include_compaction_history: bool,
) -> bool:
    envelope, parse_error = _context_envelope_from_line(line)
    if parse_error:
        state.omitted_parse_errors += 1
        return False
    if envelope is None:
        return False
    entry_type, payload, timestamp = _context_envelope_parts(envelope)
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
        return False
    if summarized is not None:
        state.candidates.append(_summarized_context_entry(line_number, timestamp, entry_type, summarized))
    return _is_token_count_boundary(line_number, token_line, entry_type, payload)


def _context_envelope_parts(envelope: dict[str, Any]) -> tuple[str, dict[str, Any], str | None]:
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
    return optional_str(envelope.get("type")) or "unknown", payload, optional_str(envelope.get("timestamp"))


def _is_token_count_boundary(
    line_number: int,
    token_line: int,
    entry_type: str,
    payload: dict[str, Any],
) -> bool:
    return line_number >= token_line and entry_type == "event_msg" and payload.get("type") == "token_count"


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
    if state.collecting:
        _reset_selected_turn_context(state)
        _collect_serialized_context(state, line, envelope, "turn_context", payload)
        carried_compactions = (
            [entry for entry in state.candidates if entry.get("type") == "compacted"]
            if was_collecting and state.target_turn_id is not None
            else []
        )
        state.candidates = [
            _context_entry(
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
            _summarized_context_entry(line_number, timestamp, entry_type, summarized)
        ]
        return True
    if summarized.get("carry_into_next_turn") is True:
        state.pending_diagnostic_events = [
            *state.pending_diagnostic_events,
            _summarized_context_entry(line_number, timestamp, entry_type, summarized),
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
    limited, omitted = _limit_entries(candidates, max_chars=max_chars, max_entries=max_entries)
    omitted["parse_errors"] = state.omitted_parse_errors
    omitted["target_turn_id"] = state.target_turn_id
    omitted["total_entries"] = len(candidates)
    return limited, omitted, candidates, serialized_estimate, serialized_estimate_ms, action_timing


def _summarized_context_entry(
    line_number: int,
    timestamp: str | None,
    entry_type: str,
    summarized: dict[str, Any],
) -> dict[str, Any]:
    return _context_entry(
        line_number,
        timestamp,
        entry_type,
        summarized["label"],
        summarized["text"],
        tool_output_omitted=bool(summarized.get("tool_output_omitted")),
        token_usage=summarized.get("token_usage")
        if isinstance(summarized.get("token_usage"), dict)
        else None,
        compaction=summarized.get("compaction")
        if isinstance(summarized.get("compaction"), dict)
        else None,
        action_duration_ms=nonnegative_float(summarized.get("action_duration_ms")),
    )



def _context_entry(
    line_number: int,
    timestamp: str | None,
    entry_type: str,
    label: str,
    text: str,
    *,
    tool_output_omitted: bool = False,
    token_usage: dict[str, Any] | None = None,
    compaction: dict[str, Any] | None = None,
    action_duration_ms: float | None = None,
) -> dict[str, Any]:
    entry = {
        "line_number": line_number,
        "timestamp": timestamp,
        "type": entry_type,
        "label": label,
        "text": redact_text(text),
        "truncated": False,
    }
    if tool_output_omitted:
        entry["tool_output_omitted"] = True
    if token_usage:
        entry["token_usage"] = token_usage
    if compaction:
        entry["compaction"] = compaction
    if action_duration_ms is not None:
        entry["action_timing"] = {
            "reported_duration_ms": normalize_millisecond_value(action_duration_ms),
            "duration_source": "event.duration_ms",
        }
    return entry


def _limit_entries(
    entries: list[dict[str, Any]],
    max_chars: int,
    max_entries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    limited_reversed: list[dict[str, Any]] = []
    remaining = None if max_chars <= 0 else max_chars
    omitted_entries = 0
    omitted_chars = 0
    selected = entries if max_entries <= 0 else entries[-max_entries:]

    for entry in reversed(selected):
        text = str(entry.get("text") or "")
        if remaining is None:
            limited_reversed.append(entry)
            continue
        if remaining <= 0:
            omitted_entries += 1
            omitted_chars += len(text)
            continue
        if len(text) > remaining:
            entry = dict(entry)
            entry["text"] = text[:remaining] + "\n[TRUNCATED]"
            entry["truncated"] = True
            omitted_chars += len(text) - remaining
            remaining = 0
        else:
            remaining -= len(text)
        limited_reversed.append(entry)

    limited = list(reversed(limited_reversed))
    return limited, {
        "older_entries": 0 if max_entries <= 0 else max(0, len(entries) - max_entries),
        "over_budget_entries": omitted_entries,
        "over_budget_chars": omitted_chars,
        "max_chars": max_chars,
        "max_entries": max_entries,
        "returned_entries": len(limited),
    }
