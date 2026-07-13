"""Streaming accumulation for normalized content indexing."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from codex_usage_tracker.parser.state import optional_str
from codex_usage_tracker.store.content_extract import (
    _extract_pending_fragments,
    _is_token_count,
)
from codex_usage_tracker.store.content_index_event_store import upsert_pending_event_rows
from codex_usage_tracker.store.content_index_events import (
    PendingCommandRun,
    PendingFileEvent,
    PendingToolCall,
    extract_pending_local_events,
)
from codex_usage_tracker.store.content_index_models import (
    UsageContentRow,
    _PendingContentRows,
    _PendingFragment,
)
from codex_usage_tracker.store.content_persistence import (
    _upsert_fragment_rows,
    _upsert_turn_rows,
)
from codex_usage_tracker.store.content_rows import (
    _append_pending_content_rows,
    _content_row_timestamp,
    _empty_pending_content_rows,
)

_CONTENT_WRITE_BATCH_RECORDS = 250


def _flush_pending_content_rows(
    conn: sqlite3.Connection,
    batch: _PendingContentRows,
) -> None:
    if batch.turn_rows:
        _upsert_turn_rows(conn, batch.turn_rows)
    if batch.fragment_rows:
        _upsert_fragment_rows(conn, batch.fragment_rows)
    upsert_pending_event_rows(conn, batch.event_rows)
    batch.turn_rows.clear()
    batch.fragment_rows.clear()
    batch.event_rows.tool_call_rows.clear()
    batch.event_rows.command_run_rows.clear()
    batch.event_rows.file_event_rows.clear()
    batch.linked_records = 0


@dataclass
class _StreamingContentAccumulator:
    pending: list[_PendingFragment] = field(default_factory=list)
    tool_calls: list[PendingToolCall] = field(default_factory=list)
    command_runs: list[PendingCommandRun] = field(default_factory=list)
    file_events: list[PendingFileEvent] = field(default_factory=list)
    rows: _PendingContentRows = field(default_factory=_empty_pending_content_rows)
    turn_id: str | None = None
    turn_index: int = 0
    parse_warnings: int = 0
    created_at: str = field(default_factory=_content_row_timestamp)

    def consume(
        self,
        conn: sqlite3.Connection,
        *,
        envelope: dict[str, object],
        payload: dict[str, object],
        line_number: int,
        usage_row: UsageContentRow | None,
    ) -> None:
        entry_type = envelope.get("type")
        timestamp = optional_str(envelope.get("timestamp"))
        if entry_type == "turn_context":
            self.turn_id = optional_str(payload.get("turn_id"))
            self.turn_index += 1
            return
        if _is_token_count(entry_type, payload):
            self._link_usage_row(conn, usage_row)
            return
        self.pending.extend(
            _extract_pending_fragments(
                envelope=envelope,
                payload=payload,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=self.turn_id,
                turn_index=self.turn_index,
            )
        )
        events = extract_pending_local_events(
            envelope=envelope,
            payload=payload,
            line_number=line_number,
            timestamp=timestamp,
        )
        self.tool_calls.extend(events.tool_calls)
        self.command_runs.extend(events.command_runs)
        self.file_events.extend(events.file_events)

    def _link_usage_row(
        self,
        conn: sqlite3.Connection,
        usage_row: UsageContentRow | None,
    ) -> None:
        if usage_row is None:
            return
        _append_pending_content_rows(
            self.rows,
            pending=self.pending,
            tool_calls=self.tool_calls,
            command_runs=self.command_runs,
            file_events=self.file_events,
            usage_row=usage_row,
            created_at=self.created_at,
        )
        if self.rows.linked_records >= _CONTENT_WRITE_BATCH_RECORDS:
            _flush_pending_content_rows(conn, self.rows)
        self.pending.clear()
        self.tool_calls.clear()
        self.command_runs.clear()
        self.file_events.clear()
