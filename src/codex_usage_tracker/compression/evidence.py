"""Typed, versionable evidence snapshots for compression analysis."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.compression.models import (
    ComponentExposure,
    ComponentName,
    CompressionScope,
)
from codex_usage_tracker.store.compression_evidence import query_compression_evidence_rows


@dataclass(frozen=True, slots=True)
class CallEvidence:
    record_id: str
    session_id: str
    thread_key: str
    event_timestamp: str
    model: str | None
    effort: str | None
    is_archived: bool
    thread_call_index: int | None
    previous_record_id: str | None
    exposure: ComponentExposure
    cache_ratio: float
    context_window_percent: float

    def revision_identity(self) -> tuple[Any, ...]:
        return (
            self.record_id,
            self.session_id,
            self.thread_key,
            self.event_timestamp,
            self.model,
            self.effort,
            self.is_archived,
            self.thread_call_index,
            self.previous_record_id,
            self.exposure.cached_input,
            self.exposure.uncached_input,
            self.exposure.output,
            self.exposure.reasoning_output,
            self.cache_ratio,
            self.context_window_percent,
        )


@dataclass(frozen=True, slots=True)
class TurnEvidence:
    turn_key: str
    record_id: str
    session_id: str
    role: str
    event_timestamp: str | None
    content_size_bytes: int
    indexed_content_included: bool

    def revision_identity(self) -> tuple[Any, ...]:
        return (
            self.turn_key,
            self.record_id,
            self.session_id,
            self.role,
            self.event_timestamp,
            self.content_size_bytes,
            self.indexed_content_included,
        )


@dataclass(frozen=True, slots=True)
class ToolCallEvidence:
    tool_call_key: str
    record_id: str
    turn_key: str | None
    tool_name: str
    status: str | None
    duration_ms: int | None
    output_size_bytes: int

    def revision_identity(self) -> tuple[Any, ...]:
        return (
            self.tool_call_key,
            self.record_id,
            self.turn_key,
            self.tool_name,
            self.status,
            self.duration_ms,
            self.output_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class CommandRunEvidence:
    command_run_key: str
    record_id: str
    turn_key: str | None
    command_root: str
    command_label: str
    exit_code: int | None
    status: str | None
    output_size_bytes: int
    retry_group: str | None

    def revision_identity(self) -> tuple[Any, ...]:
        return (
            self.command_run_key,
            self.record_id,
            self.turn_key,
            self.command_root,
            self.command_label,
            self.exit_code,
            self.status,
            self.output_size_bytes,
            self.retry_group,
        )


@dataclass(frozen=True, slots=True)
class FileEventEvidence:
    file_event_key: str
    record_id: str
    turn_key: str | None
    operation: str
    path_hash: str
    path_identity: str

    def revision_identity(self) -> tuple[Any, ...]:
        return (
            self.file_event_key,
            self.record_id,
            self.turn_key,
            self.operation,
            self.path_hash,
            self.path_identity,
        )


@dataclass(frozen=True, slots=True)
class ContentFragmentEvidence:
    fragment_id: str
    record_id: str
    turn_key: str | None
    fragment_kind: str
    role: str | None
    safe_label: str
    content_hash: str
    content_size_bytes: int
    includes_raw_fragment: bool

    @property
    def estimated_tokens(self) -> int:
        return (self.content_size_bytes + 3) // 4

    def revision_identity(self) -> tuple[Any, ...]:
        return (
            self.fragment_id,
            self.record_id,
            self.turn_key,
            self.fragment_kind,
            self.role,
            self.safe_label,
            self.content_hash,
            self.content_size_bytes,
            self.includes_raw_fragment,
        )


@dataclass(frozen=True, slots=True)
class EvidenceCoverage:
    call_count: int = 0
    turn_count: int = 0
    tool_call_count: int = 0
    command_run_count: int = 0
    file_event_count: int = 0
    content_fragment_count: int = 0
    compaction_count: int = 0
    indexed_call_count: int = 0
    source_record_count: int = 0
    parser_warning_record_count: int = 0
    parser_adapters: tuple[str, ...] = field(default_factory=tuple)
    parser_versions: tuple[str, ...] = field(default_factory=tuple)
    content_index_enabled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "call_count": self.call_count,
            "turn_count": self.turn_count,
            "tool_call_count": self.tool_call_count,
            "command_run_count": self.command_run_count,
            "file_event_count": self.file_event_count,
            "content_fragment_count": self.content_fragment_count,
            "compaction_count": self.compaction_count,
            "indexed_call_count": self.indexed_call_count,
            "source_record_count": self.source_record_count,
            "parser_warning_record_count": self.parser_warning_record_count,
            "parser_adapters": list(self.parser_adapters),
            "parser_versions": list(self.parser_versions),
            "content_index_enabled": self.content_index_enabled,
        }


@dataclass(frozen=True, slots=True)
class CompressionEvidenceSnapshot:
    calls: tuple[CallEvidence, ...]
    turns: tuple[TurnEvidence, ...]
    tool_calls: tuple[ToolCallEvidence, ...]
    command_runs: tuple[CommandRunEvidence, ...]
    file_events: tuple[FileEventEvidence, ...]
    content_fragments: tuple[ContentFragmentEvidence, ...]
    compactions: tuple[ContentFragmentEvidence, ...]
    coverage: EvidenceCoverage
    source_revision: str

    def call(self, record_id: str) -> CallEvidence | None:
        return next((row for row in self.calls if row.record_id == record_id), None)

    def component_exposure(self, record_id: str, component: ComponentName) -> int:
        call = self.call(record_id)
        if call is not None and component in _CALL_COMPONENTS:
            return call.exposure.value(component)
        if component == "content_fragment":
            return _content_fragment_exposure(self.content_fragments, record_id)
        if component == "tool_output":
            return _tool_output_exposure(self.tool_calls, self.command_runs, record_id)
        return 0


_CALL_COMPONENTS = cast(
    frozenset[ComponentName],
    frozenset({"cached_input", "uncached_input", "output", "reasoning_output"}),
)


def _content_fragment_exposure(
    fragments: tuple[ContentFragmentEvidence, ...],
    record_id: str,
) -> int:
    return sum(row.estimated_tokens for row in fragments if row.record_id == record_id)


def _tool_output_exposure(
    tools: tuple[ToolCallEvidence, ...],
    commands: tuple[CommandRunEvidence, ...],
    record_id: str,
) -> int:
    tool_output = sum(
        (row.output_size_bytes + 3) // 4 for row in tools if row.record_id == record_id
    )
    command_output = sum(
        (row.output_size_bytes + 3) // 4 for row in commands if row.record_id == record_id
    )
    return max(tool_output, command_output)


def load_compression_evidence(
    db_path: Path,
    scope: CompressionScope,
) -> CompressionEvidenceSnapshot:
    """Load and normalize one scoped evidence snapshot from SQLite."""
    payload = query_compression_evidence_rows(
        db_path,
        scope=scope.as_dict(),
        include_turns=False,
    )
    calls = tuple(_call(row) for row in payload["calls"])
    turns = tuple(_turn(row) for row in payload["turns"])
    tools = tuple(_tool_call(row) for row in payload["tool_calls"])
    commands = tuple(_command_run(row) for row in payload["command_runs"])
    files = tuple(_file_event(row) for row in payload["file_events"])
    fragments = tuple(_fragment(row) for row in payload["content_fragments"])
    compaction_ids = {str(row["fragment_id"]) for row in payload["compactions"]}
    coverage = _coverage(payload["coverage"])
    return CompressionEvidenceSnapshot(
        calls=calls,
        turns=turns,
        tool_calls=tools,
        command_runs=commands,
        file_events=files,
        content_fragments=fragments,
        compactions=tuple(row for row in fragments if row.fragment_id in compaction_ids),
        coverage=coverage,
        source_revision=f"generation:{int(payload['source_generation'])}",
    )


# Offsets mirror the private SQL projections in store/compression_evidence.py.
# Positional access avoids millions of named row lookups on cold builds.
def _call(row: sqlite3.Row) -> CallEvidence:
    return CallEvidence(
        record_id=str(row[0]),
        session_id=str(row[1]),
        thread_key=str(row[2]),
        event_timestamp=str(row[3]),
        model=_optional_text(row[4]),
        effort=_optional_text(row[5]),
        is_archived=bool(row[6]),
        thread_call_index=_optional_int(row[7]),
        previous_record_id=_optional_text(row[8]),
        exposure=ComponentExposure(
            cached_input=_integer(row[9]),
            uncached_input=_integer(row[10]),
            output=_integer(row[11]),
            reasoning_output=_integer(row[12]),
        ),
        cache_ratio=float(row[13] or 0),
        context_window_percent=float(row[14] or 0),
    )


def _turn(row: sqlite3.Row) -> TurnEvidence:
    return TurnEvidence(
        turn_key=str(row[0]),
        record_id=str(row[1]),
        session_id=str(row[2]),
        role=str(row[3]),
        event_timestamp=_optional_text(row[4]),
        content_size_bytes=_integer(row[5]),
        indexed_content_included=bool(row[6]),
    )


def _tool_call(row: sqlite3.Row) -> ToolCallEvidence:
    return ToolCallEvidence(
        tool_call_key=str(row[0]),
        record_id=str(row[1]),
        turn_key=_optional_text(row[2]),
        tool_name=str(row[3]),
        status=_optional_text(row[4]),
        duration_ms=_optional_int(row[5]),
        output_size_bytes=_integer(row[6]),
    )


def _command_run(row: sqlite3.Row) -> CommandRunEvidence:
    return CommandRunEvidence(
        command_run_key=str(row[0]),
        record_id=str(row[1]),
        turn_key=_optional_text(row[2]),
        command_root=str(row[3]),
        command_label=str(row[4] or ""),
        exit_code=_optional_int(row[5]),
        status=_optional_text(row[6]),
        output_size_bytes=_integer(row[7]),
        retry_group=_optional_text(row[8]),
    )


def _file_event(row: sqlite3.Row) -> FileEventEvidence:
    return FileEventEvidence(
        file_event_key=str(row[0]),
        record_id=str(row[1]),
        turn_key=_optional_text(row[2]),
        operation=str(row[3]),
        path_hash=str(row[4]),
        path_identity=str(row[5] or ""),
    )


def _fragment(row: sqlite3.Row) -> ContentFragmentEvidence:
    return ContentFragmentEvidence(
        fragment_id=str(row[0]),
        record_id=str(row[1]),
        turn_key=_optional_text(row[2]),
        fragment_kind=str(row[3]),
        role=_optional_text(row[4]),
        safe_label=str(row[5] or ""),
        content_hash=str(row[6]),
        content_size_bytes=_integer(row[7]),
        includes_raw_fragment=bool(row[8]),
    )


def _coverage(row: dict[str, Any]) -> EvidenceCoverage:
    return EvidenceCoverage(
        call_count=_integer(row.get("call_count")),
        turn_count=_integer(row.get("turn_count")),
        tool_call_count=_integer(row.get("tool_call_count")),
        command_run_count=_integer(row.get("command_run_count")),
        file_event_count=_integer(row.get("file_event_count")),
        content_fragment_count=_integer(row.get("content_fragment_count")),
        compaction_count=_integer(row.get("compaction_count")),
        indexed_call_count=_integer(row.get("indexed_call_count")),
        source_record_count=_integer(row.get("source_record_count")),
        parser_warning_record_count=_integer(row.get("parser_warning_record_count")),
        parser_adapters=tuple(str(value) for value in row.get("parser_adapters") or []),
        parser_versions=tuple(str(value) for value in row.get("parser_versions") or []),
        content_index_enabled=bool(row.get("content_index_enabled")),
    )


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _integer(value: Any) -> int:
    return max(0, int(value or 0))


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
