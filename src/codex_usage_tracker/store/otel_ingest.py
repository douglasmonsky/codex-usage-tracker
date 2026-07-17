"""Incremental ingestion for aggregate-only Codex OTel completion files."""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from codex_usage_tracker.parser.otel import OtelCompletion, parse_otlp_json_line

_CURSOR_ANCHOR_BYTES = 4096


@dataclass(frozen=True)
class OtelIngestResult:
    files_scanned: int = 0
    imported: int = 0
    duplicates: int = 0
    diagnostics: dict[str, int] = field(default_factory=dict)


@dataclass
class _MutableIngestTotals:
    files_scanned: int = 0
    imported: int = 0
    duplicates: int = 0
    diagnostics: Counter[str] = field(default_factory=Counter)

    def freeze(self) -> OtelIngestResult:
        return OtelIngestResult(
            files_scanned=self.files_scanned,
            imported=self.imported,
            duplicates=self.duplicates,
            diagnostics=dict(self.diagnostics),
        )


@dataclass(frozen=True)
class _SourceState:
    device: int
    inode: int
    size: int
    parsed_offset: int
    parsed_line: int
    resume_anchor: str | None


def discover_otel_sources(directory: Path) -> list[Path]:
    """Return current and rotated completion files in deterministic path order."""

    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.glob("codex-completions*.jsonl")
        if path.is_file()
    )


def ingest_otel_completion_files(
    conn: sqlite3.Connection, directory: Path
) -> OtelIngestResult:
    """Resume every completion source at its last fully handled line."""

    totals = _MutableIngestTotals()
    for path in discover_otel_sources(directory):
        source_path = str(path.resolve())
        try:
            state = _source_state(conn, source_path)
            final_stat, next_offset, next_line, resume_anchor = _ingest_complete_lines(
                conn,
                path,
                source_path,
                state,
                totals,
            )
        except FileNotFoundError:
            continue
        _upsert_source_cursor(
            conn,
            source_path,
            final_stat,
            next_offset,
            next_line,
            resume_anchor,
        )
        totals.files_scanned += 1
    return totals.freeze()


def _source_state(conn: sqlite3.Connection, source_path: str) -> _SourceState | None:
    row = conn.execute(
        """
        SELECT device, inode, size, parsed_offset, parsed_line, resume_anchor
        FROM otel_completion_sources
        WHERE source_path = ?
        """,
        (source_path,),
    ).fetchone()
    if row is None:
        return None
    return _SourceState(
        device=int(row["device"]),
        inode=int(row["inode"]),
        size=int(row["size"]),
        parsed_offset=int(row["parsed_offset"]),
        parsed_line=int(row["parsed_line"]),
        resume_anchor=str(row["resume_anchor"]) if row["resume_anchor"] else None,
    )


def _resume_position(
    state: _SourceState | None,
    stat: os.stat_result,
    handle: BinaryIO,
) -> tuple[int, int]:
    if state is None:
        return 0, 0
    unchanged_file = state.device == stat.st_dev and state.inode == stat.st_ino
    has_not_shrunk = stat.st_size >= state.size and stat.st_size >= state.parsed_offset
    anchor_matches = state.resume_anchor is not None and hmac.compare_digest(
        state.resume_anchor,
        _cursor_anchor(handle, state.parsed_offset),
    )
    if unchanged_file and has_not_shrunk and anchor_matches:
        return state.parsed_offset, state.parsed_line
    return 0, 0


def _ingest_complete_lines(
    conn: sqlite3.Connection,
    path: Path,
    source_path: str,
    state: _SourceState | None,
    totals: _MutableIngestTotals,
) -> tuple[os.stat_result, int, int, str]:
    for attempt in range(2):
        result = _read_source_descriptor(
            conn,
            path,
            source_path,
            state if attempt == 0 else None,
            totals,
        )
        initial_stat, final_stat, next_offset, next_line, resume_anchor = result
        if (
            initial_stat.st_dev == final_stat.st_dev
            and initial_stat.st_ino == final_stat.st_ino
        ):
            return final_stat, next_offset, next_line, resume_anchor
    raise FileNotFoundError("OTel source descriptor identity changed during retry")


def _read_source_descriptor(
    conn: sqlite3.Connection,
    path: Path,
    source_path: str,
    state: _SourceState | None,
    totals: _MutableIngestTotals,
) -> tuple[os.stat_result, os.stat_result, int, int, str]:
    with path.open("rb") as handle:
        initial_stat = os.fstat(handle.fileno())
        offset, line_number = _resume_position(state, initial_stat, handle)
        next_offset = offset
        next_line = line_number
        handle.seek(offset)
        while line := handle.readline():
            if not line.endswith(b"\n"):
                break
            next_offset = handle.tell()
            next_line += 1
            try:
                raw = line.decode("utf-8")
            except UnicodeDecodeError:
                totals.diagnostics["otel_invalid_json"] += 1
                continue
            result = parse_otlp_json_line(raw)
            totals.diagnostics.update(result.diagnostics)
            for completion in result.completions:
                if _insert_completion(conn, completion, source_path, next_line):
                    totals.imported += 1
                else:
                    totals.duplicates += 1
        final_stat = os.fstat(handle.fileno())
        resume_anchor = _cursor_anchor(handle, next_offset)
    return initial_stat, final_stat, next_offset, next_line, resume_anchor


def _cursor_anchor(handle: BinaryIO, parsed_offset: int) -> str:
    """Hash a bounded suffix of committed bytes without changing the read position."""

    anchor_start = max(parsed_offset - _CURSOR_ANCHOR_BYTES, 0)
    original_position = handle.tell()
    handle.seek(anchor_start)
    payload = handle.read(parsed_offset - anchor_start)
    handle.seek(original_position)
    return hashlib.sha256(payload).hexdigest()


def _insert_completion(
    conn: sqlite3.Connection,
    completion: OtelCompletion,
    source_path: str,
    source_line: int,
) -> bool:
    cursor = conn.execute(
        """
        INSERT INTO otel_completion_events (
            fingerprint,
            conversation_id,
            event_timestamp,
            input_tokens,
            cached_input_tokens,
            output_tokens,
            reasoning_output_tokens,
            model,
            effort,
            service_tier,
            fast,
            service_tier_source,
            service_tier_confidence,
            app_version,
            source_path,
            source_line,
            match_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fingerprint) DO NOTHING
        """,
        (
            completion.fingerprint,
            completion.conversation_id,
            completion.event_timestamp,
            completion.input_tokens,
            completion.cached_input_tokens,
            completion.output_tokens,
            completion.reasoning_output_tokens,
            completion.model,
            completion.effort,
            completion.service_tier,
            completion.fast,
            completion.service_tier_source,
            completion.service_tier_confidence,
            completion.app_version,
            source_path,
            source_line,
            completion.match_status,
        ),
    )
    return cursor.rowcount == 1


def _upsert_source_cursor(
    conn: sqlite3.Connection,
    source_path: str,
    stat: os.stat_result,
    parsed_offset: int,
    parsed_line: int,
    resume_anchor: str,
) -> None:
    conn.execute(
        """
        INSERT INTO otel_completion_sources (
            source_path, device, inode, size, parsed_offset, parsed_line,
            resume_anchor, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_path) DO UPDATE SET
            device = excluded.device,
            inode = excluded.inode,
            size = excluded.size,
            parsed_offset = excluded.parsed_offset,
            parsed_line = excluded.parsed_line,
            resume_anchor = excluded.resume_anchor,
            updated_at = excluded.updated_at
        """,
        (
            source_path,
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            parsed_offset,
            parsed_line,
            resume_anchor,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
