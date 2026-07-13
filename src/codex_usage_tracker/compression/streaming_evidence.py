"""Bounded evidence loading for Compression Lab cold builds."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from codex_usage_tracker.compression.evidence import (
    CallEvidence,
    CommandRunEvidence,
    CompressionEvidenceSnapshot,
    FileEventEvidence,
    ToolCallEvidence,
    _call,
    _command_run,
    _coverage,
    _file_event,
    _tool_call,
)
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.output_detectors import ToolOutputBloatDetector
from codex_usage_tracker.compression.repetition_detectors import (
    _SHELL_ROOTS,
    _VALIDATION_ROOTS,
)
from codex_usage_tracker.compression.run_cache import RecordManifestBuilder
from codex_usage_tracker.store.compression_evidence import (
    fold_compression_evidence_rows,
)

_RELEVANT_COMMAND_ROOTS = _SHELL_ROOTS | _VALIDATION_ROOTS
_MIN_TOOL_OUTPUT_BYTES = (ToolOutputBloatDetector().min_output_tokens * 4) - 3


@dataclass(frozen=True, slots=True)
class StreamingEvidenceBundle:
    """Compact detector snapshot plus the manifest built from every raw row."""

    snapshot: CompressionEvidenceSnapshot
    record_manifest: dict[str, dict[str, str]]


@dataclass(slots=True)
class _StreamingAccumulator:
    calls: list[CallEvidence] = field(default_factory=list)
    tool_calls: dict[str, ToolCallEvidence] = field(default_factory=dict)
    command_runs: dict[str, CommandRunEvidence] = field(default_factory=dict)
    file_events: dict[str, FileEventEvidence] = field(default_factory=dict)
    content_exposure: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    content_exposure_by_turn: dict[tuple[str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    tool_exposure: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    command_exposure: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    manifest: RecordManifestBuilder = field(default_factory=RecordManifestBuilder)

    def consume(self, category: str, rows: list[sqlite3.Row]) -> None:
        handlers = {
            "calls": self._consume_calls,
            "turns": self._consume_turns,
            "tool_calls": self._consume_tool_calls,
            "command_runs": self._consume_command_runs,
            "file_events": self._consume_file_events,
            "content_fragments": self._consume_content_fragments,
        }
        handlers[category](rows)

    def _consume_calls(self, rows: list[sqlite3.Row]) -> None:
        for row in rows:
            call = _call(row)
            self.calls.append(call)
            self.manifest.add_call(call)

    def _consume_turns(self, rows: list[sqlite3.Row]) -> None:
        if rows:
            raise AssertionError("streaming compression loads omit conversation turns")

    def _consume_tool_calls(self, rows: list[sqlite3.Row]) -> None:
        for row in rows:
            record_id = str(row[1])
            output_size_bytes = int(row[6] or 0)
            self.manifest.add_identity("tool", record_id, _tool_identity(row))
            self.tool_exposure[record_id] += _output_tokens(output_size_bytes)
            if output_size_bytes >= _MIN_TOOL_OUTPUT_BYTES:
                tool_call = _tool_call(row)
                self.tool_calls[tool_call.tool_call_key] = tool_call

    def _consume_command_runs(self, rows: list[sqlite3.Row]) -> None:
        for row in rows:
            record_id = str(row[1])
            command_root = str(row[3])
            self.manifest.add_identity("command", record_id, _command_identity(row))
            self.command_exposure[record_id] += _output_tokens(int(row[7] or 0))
            if command_root in _RELEVANT_COMMAND_ROOTS:
                command = _command_run(row)
                self.command_runs[command.command_run_key] = command

    def _consume_file_events(self, rows: list[sqlite3.Row]) -> None:
        for row in rows:
            record_id = str(row[1])
            operation = str(row[3])
            path_hash = str(row[4])
            self.manifest.add_identity("file", record_id, _file_identity(row))
            if operation == "read" and path_hash:
                event = _file_event(row)
                self.file_events[event.file_event_key] = event

    def _consume_content_fragments(self, rows: list[sqlite3.Row]) -> None:
        for row in rows:
            record_id = str(row[1])
            turn_key = None if row[2] is None else str(row[2])
            self.manifest.add_identity("fragment", record_id, _fragment_identity(row))
            tokens = _output_tokens(int(row[7] or 0))
            self.content_exposure[record_id] += tokens
            if turn_key is not None:
                self.content_exposure_by_turn[(record_id, turn_key)] += tokens

    def tool_output_exposure(self) -> dict[str, int]:
        return {
            record_id: max(
                self.tool_exposure.get(record_id, 0),
                self.command_exposure.get(record_id, 0),
            )
            for record_id in set(self.tool_exposure).union(self.command_exposure)
        }


def load_streaming_compression_evidence(
    db_path: Path,
    scope: CompressionScope,
    *,
    batch_size: int = 4_096,
) -> StreamingEvidenceBundle:
    """Fold raw evidence into a detector-equivalent compact snapshot."""
    accumulator = _StreamingAccumulator()
    metadata = fold_compression_evidence_rows(
        db_path,
        scope=scope.as_dict(),
        include_turns=False,
        batch_size=batch_size,
        consumer=accumulator.consume,
    )
    snapshot = CompressionEvidenceSnapshot(
        calls=tuple(accumulator.calls),
        turns=(),
        tool_calls=tuple(accumulator.tool_calls.values()),
        command_runs=tuple(accumulator.command_runs.values()),
        file_events=tuple(accumulator.file_events.values()),
        content_fragments=(),
        compactions=(),
        coverage=_coverage(metadata["coverage"]),
        source_revision=f"generation:{int(metadata['source_generation'])}",
        content_exposure_by_record=dict(accumulator.content_exposure),
        content_exposure_by_turn=dict(accumulator.content_exposure_by_turn),
        tool_output_exposure_by_record=accumulator.tool_output_exposure(),
    )
    return StreamingEvidenceBundle(
        snapshot=snapshot,
        record_manifest=accumulator.manifest.build(),
    )


def _output_tokens(output_size_bytes: int) -> int:
    return (output_size_bytes + 3) // 4


def _tool_identity(row: sqlite3.Row) -> tuple[object, ...]:
    return (
        str(row[0]),
        str(row[1]),
        _optional_text(row[2]),
        str(row[3]),
        _optional_text(row[4]),
        _optional_int(row[5]),
        int(row[6] or 0),
    )


def _command_identity(row: sqlite3.Row) -> tuple[object, ...]:
    return (
        str(row[0]),
        str(row[1]),
        _optional_text(row[2]),
        str(row[3]),
        str(row[4] or ""),
        _optional_int(row[5]),
        _optional_text(row[6]),
        int(row[7] or 0),
        _optional_text(row[8]),
    )


def _file_identity(row: sqlite3.Row) -> tuple[object, ...]:
    return (
        str(row[0]),
        str(row[1]),
        _optional_text(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5] or ""),
    )


def _fragment_identity(row: sqlite3.Row) -> tuple[object, ...]:
    return (
        str(row[0]),
        str(row[1]),
        _optional_text(row[2]),
        str(row[3]),
        _optional_text(row[4]),
        str(row[5] or ""),
        str(row[6]),
        int(row[7] or 0),
        bool(row[8]),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    return None if value is None else int(str(value))
