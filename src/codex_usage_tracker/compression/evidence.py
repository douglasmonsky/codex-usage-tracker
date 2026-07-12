"""Typed, versionable evidence snapshots for compression analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.compression.models import (
    ComponentExposure,
    ComponentName,
    CompressionScope,
)
from codex_usage_tracker.store.compression_evidence import query_compression_evidence


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


@dataclass(frozen=True, slots=True)
class TurnEvidence:
    turn_key: str
    record_id: str
    session_id: str
    role: str
    event_timestamp: str | None
    content_size_bytes: int
    indexed_content_included: bool


@dataclass(frozen=True, slots=True)
class ToolCallEvidence:
    tool_call_key: str
    record_id: str
    turn_key: str | None
    tool_name: str
    status: str | None
    duration_ms: int | None
    output_size_bytes: int


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


@dataclass(frozen=True, slots=True)
class FileEventEvidence:
    file_event_key: str
    record_id: str
    turn_key: str | None
    operation: str
    path_hash: str
    path_identity: str


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
    payload = query_compression_evidence(
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


def _call(row: dict[str, Any]) -> CallEvidence:
    return CallEvidence(
        record_id=str(row["record_id"]),
        session_id=str(row["session_id"]),
        thread_key=str(row["thread_key"]),
        event_timestamp=str(row["event_timestamp"]),
        model=_optional_text(row.get("model")),
        effort=_optional_text(row.get("effort")),
        is_archived=bool(row.get("is_archived")),
        thread_call_index=_optional_int(row.get("thread_call_index")),
        previous_record_id=_optional_text(row.get("previous_record_id")),
        exposure=ComponentExposure(
            cached_input=_integer(row.get("cached_input_tokens")),
            uncached_input=_integer(row.get("uncached_input_tokens")),
            output=_integer(row.get("output_tokens")),
            reasoning_output=_integer(row.get("reasoning_output_tokens")),
        ),
        cache_ratio=float(row.get("cache_ratio") or 0),
        context_window_percent=float(row.get("context_window_percent") or 0),
    )


def _turn(row: dict[str, Any]) -> TurnEvidence:
    return TurnEvidence(
        turn_key=str(row["turn_key"]),
        record_id=str(row["record_id"]),
        session_id=str(row["session_id"]),
        role=str(row["role"]),
        event_timestamp=_optional_text(row.get("event_timestamp")),
        content_size_bytes=_integer(row.get("content_size_bytes")),
        indexed_content_included=bool(row.get("indexed_content_included")),
    )


def _tool_call(row: dict[str, Any]) -> ToolCallEvidence:
    return ToolCallEvidence(
        tool_call_key=str(row["tool_call_key"]),
        record_id=str(row["record_id"]),
        turn_key=_optional_text(row.get("turn_key")),
        tool_name=str(row["tool_name"]),
        status=_optional_text(row.get("status")),
        duration_ms=_optional_int(row.get("duration_ms")),
        output_size_bytes=_integer(row.get("output_size_bytes")),
    )


def _command_run(row: dict[str, Any]) -> CommandRunEvidence:
    return CommandRunEvidence(
        command_run_key=str(row["command_run_key"]),
        record_id=str(row["record_id"]),
        turn_key=_optional_text(row.get("turn_key")),
        command_root=str(row["command_root"]),
        command_label=str(row.get("command_label") or ""),
        exit_code=_optional_int(row.get("exit_code")),
        status=_optional_text(row.get("status")),
        output_size_bytes=_integer(row.get("output_size_bytes")),
        retry_group=_optional_text(row.get("retry_group")),
    )


def _file_event(row: dict[str, Any]) -> FileEventEvidence:
    return FileEventEvidence(
        file_event_key=str(row["file_event_key"]),
        record_id=str(row["record_id"]),
        turn_key=_optional_text(row.get("turn_key")),
        operation=str(row["operation"]),
        path_hash=str(row["path_hash"]),
        path_identity=str(row.get("path_identity") or ""),
    )


def _fragment(row: dict[str, Any]) -> ContentFragmentEvidence:
    return ContentFragmentEvidence(
        fragment_id=str(row["fragment_id"]),
        record_id=str(row["record_id"]),
        turn_key=_optional_text(row.get("turn_key")),
        fragment_kind=str(row["fragment_kind"]),
        role=_optional_text(row.get("role")),
        safe_label=str(row.get("safe_label") or ""),
        content_hash=str(row["content_hash"]),
        content_size_bytes=_integer(row.get("content_size_bytes")),
        includes_raw_fragment=bool(row.get("includes_raw_fragment")),
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
