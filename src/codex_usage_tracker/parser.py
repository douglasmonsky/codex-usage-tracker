"""Parse Codex JSONL session logs into aggregate usage records."""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from pathlib import Path

from codex_usage_tracker.adapters.base import parse_files
from codex_usage_tracker.adapters.codex_jsonl import (
    PARSER_ADAPTER_VERSION,
    PARSER_DIAGNOSTIC_KEYS,
    CodexJsonlAdapter,
    _session_id_from_path,
    compact_parser_diagnostics,
    empty_parser_diagnostics,
)
from codex_usage_tracker.models import SessionInfo, UsageEvent
from codex_usage_tracker.paths import DEFAULT_CODEX_HOME

DEFAULT_PARSER_ADAPTER = CodexJsonlAdapter()
ParserAdapter = CodexJsonlAdapter

__all__ = [
    "PARSER_ADAPTER_VERSION",
    "PARSER_DIAGNOSTIC_KEYS",
    "DEFAULT_PARSER_ADAPTER",
    "ParserAdapter",
    "compact_parser_diagnostics",
    "empty_parser_diagnostics",
    "find_session_logs",
    "inspect_log",
    "load_session_index",
    "parse_usage_events",
    "parse_usage_events_from_file",
]


def load_session_index(codex_home: Path = DEFAULT_CODEX_HOME) -> dict[str, SessionInfo]:
    """Load Codex thread names without reading transcript content."""

    return DEFAULT_PARSER_ADAPTER.load_session_index(codex_home)


def find_session_logs(
    codex_home: Path = DEFAULT_CODEX_HOME, include_archived: bool = False
) -> list[Path]:
    """Find local Codex JSONL logs."""

    return DEFAULT_PARSER_ADAPTER.discover_logs(
        codex_home,
        include_archived=include_archived,
    )


def parse_usage_events(
    paths: Iterable[Path],
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    """Parse all provided logs into aggregate usage events."""

    return parse_files(
        DEFAULT_PARSER_ADAPTER,
        paths,
        session_index=session_index,
        stats=stats,
    )


def parse_usage_events_from_file(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    """Parse one Codex JSONL log without storing raw message content."""

    return DEFAULT_PARSER_ADAPTER.parse_file(path, session_index=session_index, stats=stats)


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
        "source_provider": DEFAULT_PARSER_ADAPTER.source_provider,
        "source_app": DEFAULT_PARSER_ADAPTER.source_app,
        "source_format": DEFAULT_PARSER_ADAPTER.source_format,
        "file_session_id": _session_id_from_path(path),
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
            }
            for event in events
        ],
    }
