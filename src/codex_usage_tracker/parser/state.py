"""Parser cursor state and aggregate diagnostic helpers."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import Any

from codex_usage_tracker.core.call_origin import CallOriginFlags
from codex_usage_tracker.core.models import DiagnosticFact
from codex_usage_tracker.ingest.facts import (
    diagnostic_fact_from_json,
    diagnostic_fact_to_json,
)

PARSER_ADAPTER_VERSION = "codex-jsonl-v2"
PARSER_DIAGNOSTIC_KEYS = (
    "invalid_json",
    "missing_payload",
    "unknown_filename_format",
    "unknown_event_shape",
    "missing_info",
    "missing_last_token_usage",
    "missing_total_token_usage",
    "missing_cumulative_total",
    "duplicate_cumulative_total",
    "invalid_integer",
    "partial_field_count",
    "invalid_model_context_window",
    "skipped_events",
)


@dataclass(frozen=True)
class ParserState:
    """Aggregate-only parser cursor for continuing append-only JSONL parsing."""

    session_id: str | None = None
    session_meta: dict[str, str | None] = field(default_factory=dict)
    current_turn: dict[str, Any] = field(default_factory=dict)
    last_cumulative_total: int = -1
    call_origin_segment: tuple[CallOriginFlags, ...] = ()
    diagnostic_facts_segment: tuple[DiagnosticFact, ...] = ()
    latest_record_id: str | None = None
    latest_event_timestamp: str | None = None


def parser_state_from_json(raw: str | None) -> ParserState | None:
    """Decode a persisted aggregate-only parser cursor."""

    payload = _parser_state_payload(raw)
    if payload is None:
        return None
    return ParserState(
        session_id=optional_str(payload.get("session_id")),
        session_meta=_string_dict(payload.get("session_meta")),
        current_turn=_string_dict(payload.get("current_turn")),
        last_cumulative_total=_json_int(payload.get("last_cumulative_total"), -1),
        call_origin_segment=_call_origin_segment_from_json(payload),
        diagnostic_facts_segment=_diagnostic_facts_segment_from_json(payload),
        latest_record_id=optional_str(payload.get("latest_record_id")),
        latest_event_timestamp=optional_str(payload.get("latest_event_timestamp")),
    )


def _parser_state_payload(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return None
    return payload


def _call_origin_segment_from_json(
    payload: dict[str, Any],
) -> tuple[CallOriginFlags, ...]:
    return tuple(
        _call_origin_flags_from_json(item)
        for item in _json_list(payload.get("call_origin_segment"))
    )


def _diagnostic_facts_segment_from_json(
    payload: dict[str, Any],
) -> tuple[DiagnosticFact, ...]:
    return tuple(
        fact
        for fact in (
            diagnostic_fact_from_json(item)
            for item in _json_list(payload.get("diagnostic_facts_segment"))
        )
        if fact is not None
    )


def _json_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def parser_state_to_json(state: ParserState) -> str:
    """Encode an aggregate-only parser cursor for source-file refresh metadata."""

    return json.dumps(
        {
            "version": 1,
            "session_id": state.session_id,
            "session_meta": state.session_meta,
            "current_turn": state.current_turn,
            "last_cumulative_total": state.last_cumulative_total,
            "call_origin_segment": [
                {
                    "user_message": flags.user_message,
                    "compaction": flags.compaction,
                    "tool_result": flags.tool_result,
                    "codex_activity": flags.codex_activity,
                }
                for flags in state.call_origin_segment
            ],
            "diagnostic_facts_segment": [
                diagnostic_fact_to_json(fact) for fact in state.diagnostic_facts_segment
            ],
            "latest_record_id": state.latest_record_id,
            "latest_event_timestamp": state.latest_event_timestamp,
        },
        sort_keys=True,
    )


def empty_parser_diagnostics() -> dict[str, int]:
    """Return all parser diagnostic counters initialized to zero."""

    return {key: 0 for key in PARSER_DIAGNOSTIC_KEYS}


def compact_parser_diagnostics(stats: MutableMapping[str, int]) -> dict[str, int]:
    """Return non-zero parser diagnostics in stable key order."""

    return {key: int(stats.get(key, 0)) for key in PARSER_DIAGNOSTIC_KEYS if stats.get(key, 0)}


def optional_str(value: object) -> str | None:
    """Return the value when it is a string, otherwise None."""

    if isinstance(value, str):
        return value
    return None


def _string_dict(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item if isinstance(item, str) else None
        for key, item in value.items()
        if isinstance(key, str)
    }


def _json_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _call_origin_flags_from_json(value: object) -> CallOriginFlags:
    if not isinstance(value, dict):
        return CallOriginFlags()
    return CallOriginFlags(
        user_message=value.get("user_message") is True,
        compaction=value.get("compaction") is True,
        tool_result=value.get("tool_result") is True,
        codex_activity=value.get("codex_activity") is True,
    )
