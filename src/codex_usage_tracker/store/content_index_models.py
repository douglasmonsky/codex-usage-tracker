"""Shared records for local content indexing."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from codex_usage_tracker.store.content_index_event_store import PendingEventRows


@dataclass(frozen=True)
class ContentIndexResult:
    """Content indexing counts for one refresh operation."""

    source_files: int
    conversation_turns: int
    content_fragments: int
    parse_warnings: int = 0


@dataclass(frozen=True)
class ContentIndexPlan:
    """Plan for full or append-only content indexing of a source log."""

    source_path: Path
    replace_existing: bool = True
    start_byte: int = 0
    start_line: int = 0


@dataclass(frozen=True)
class _PendingFragment:
    role: str
    fragment_kind: str
    safe_label: str
    text: str
    line_start: int
    line_end: int
    turn_id: str | None
    turn_index: int
    event_timestamp: str | None


@dataclass
class _PendingContentRows:
    turn_rows: list[dict[str, object]]
    fragment_rows: list[dict[str, object]]
    event_rows: PendingEventRows
    linked_records: int = 0


@dataclass(frozen=True)
class _ExtractedContentRows:
    source_path: str
    has_usage_rows: bool
    turn_rows: list[dict[str, object]]
    fragment_rows: list[dict[str, object]]
    event_rows: PendingEventRows
    parse_warnings: int = 0


ContentIndexProgressCallback = Callable[[dict[str, object]], None]
UsageContentRow = sqlite3.Row | Mapping[str, object]
