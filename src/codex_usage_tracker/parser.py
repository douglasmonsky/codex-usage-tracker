"""Parse Codex JSONL session logs into aggregate usage records."""

from __future__ import annotations

import json
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass
from pathlib import Path

from codex_usage_tracker import parser_state as _parser_state
from codex_usage_tracker.models import SessionInfo, UsageEvent
from codex_usage_tracker.parser_jsonl_v1 import (
    ParsedUsageFile,
    parse_codex_jsonl_v1,
)
from codex_usage_tracker.parser_jsonl_values import session_id_from_path
from codex_usage_tracker.parser_state import (
    PARSER_ADAPTER_VERSION,
    ParserState,
    compact_parser_diagnostics,
    empty_parser_diagnostics,
    optional_str,
)
from codex_usage_tracker.paths import DEFAULT_CODEX_HOME

PARSER_DIAGNOSTIC_KEYS = _parser_state.PARSER_DIAGNOSTIC_KEYS

@dataclass(frozen=True)
class ParserAdapter:
    """Versioned parser adapter for one Codex log format family."""

    version: str = PARSER_ADAPTER_VERSION

    def parse_file(
        self,
        path: Path,
        session_index: dict[str, SessionInfo] | None = None,
        stats: MutableMapping[str, int] | None = None,
    ) -> list[UsageEvent]:
        return self.parse_file_with_state(
            path,
            session_index=session_index,
            stats=stats,
        ).events

    def parse_file_with_state(
        self,
        path: Path,
        session_index: dict[str, SessionInfo] | None = None,
        stats: MutableMapping[str, int] | None = None,
        *,
        start_byte: int = 0,
        start_line: int = 0,
        initial_state: ParserState | None = None,
    ) -> ParsedUsageFile:
        return parse_codex_jsonl_v1(
            path,
            session_index=session_index,
            stats=stats,
            start_byte=start_byte,
            start_line=start_line,
            initial_state=initial_state,
        )


DEFAULT_PARSER_ADAPTER = ParserAdapter()


def load_session_index(codex_home: Path = DEFAULT_CODEX_HOME) -> dict[str, SessionInfo]:
    """Load Codex thread names without reading transcript content."""

    index_path = codex_home / "session_index.jsonl"
    sessions: dict[str, SessionInfo] = {}
    if not index_path.exists():
        return sessions

    with index_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = payload.get("id")
            if not isinstance(session_id, str):
                continue
            sessions[session_id] = SessionInfo(
                session_id=session_id,
                thread_name=optional_str(payload.get("thread_name")),
                updated_at=optional_str(payload.get("updated_at")),
            )
    return sessions


def find_session_logs(
    codex_home: Path = DEFAULT_CODEX_HOME, include_archived: bool = False
) -> list[Path]:
    """Find local Codex JSONL logs."""

    paths = list((codex_home / "sessions").glob("**/*.jsonl"))
    if include_archived:
        paths.extend((codex_home / "archived_sessions").glob("*.jsonl"))
    return sorted(path for path in paths if path.is_file())


def parse_usage_events(
    paths: Iterable[Path],
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    """Parse all provided logs into aggregate usage events."""

    index = session_index or {}
    events: list[UsageEvent] = []
    for path in paths:
        events.extend(parse_usage_events_from_file(path, index, stats=stats))
    return events


def parse_usage_events_from_file(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    """Parse one Codex JSONL log without storing raw message content."""

    return DEFAULT_PARSER_ADAPTER.parse_file(path, session_index=session_index, stats=stats)


def parse_usage_events_from_file_with_state(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
    *,
    start_byte: int = 0,
    start_line: int = 0,
    initial_state: ParserState | None = None,
) -> ParsedUsageFile:
    """Parse one Codex JSONL log and return an aggregate-only continuation cursor."""

    return DEFAULT_PARSER_ADAPTER.parse_file_with_state(
        path,
        session_index=session_index,
        stats=stats,
        start_byte=start_byte,
        start_line=start_line,
        initial_state=initial_state,
    )


parser_state_from_json = _parser_state.parser_state_from_json
parser_state_to_json = _parser_state.parser_state_to_json


def inspect_log(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
) -> dict[str, object]:
    """Return aggregate-only parser observations for one log without DB writes."""

    stats = empty_parser_diagnostics()
    events = parse_usage_events_from_file(path, session_index=session_index, stats=stats)
    session_ids = sorted({event.session_id for event in events})
    models = sorted({event.model for event in events if event.model})
    efforts = sorted({event.effort for event in events if event.effort})
    first_event = events[0] if events else None
    last_event = events[-1] if events else None
    return {
        "path": str(path),
        "adapter": DEFAULT_PARSER_ADAPTER.version,
        "file_session_id": session_id_from_path(path),
        "event_count": len(events),
        "session_ids": session_ids,
        "models": models,
        "efforts": efforts,
        "first_event_timestamp": first_event.event_timestamp if first_event else None,
        "last_event_timestamp": last_event.event_timestamp if last_event else None,
        "diagnostics": compact_parser_diagnostics(stats),
        "events": [
            {
                "record_id": event.record_id,
                "line_number": event.line_number,
                "event_timestamp": event.event_timestamp,
                "session_id": event.session_id,
                "turn_id": event.turn_id,
                "model": event.model,
                "effort": event.effort,
                "input_tokens": event.input_tokens,
                "cached_input_tokens": event.cached_input_tokens,
                "uncached_input_tokens": event.uncached_input_tokens,
                "output_tokens": event.output_tokens,
                "reasoning_output_tokens": event.reasoning_output_tokens,
                "total_tokens": event.total_tokens,
                "cumulative_total_tokens": event.cumulative_total_tokens,
                "is_archived": event.is_archived,
                "thread_key": event.thread_key,
            }
            for event in events
        ],
    }
