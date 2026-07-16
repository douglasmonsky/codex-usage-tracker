"""Incremental ingestion for aggregate-only Codex OTel completion files."""

from __future__ import annotations

import os
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from codex_usage_tracker.parser.otel import OtelCompletion, parse_otlp_json_line


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
            initial_stat = path.stat()
            state = _source_state(conn, source_path)
            offset, line_number = _resume_position(state, initial_stat)
            next_offset, next_line = _ingest_complete_lines(
                conn,
                path,
                source_path,
                offset,
                line_number,
                totals,
            )
            final_stat = path.stat()
        except FileNotFoundError:
            continue
        _upsert_source_cursor(
            conn,
            source_path,
            final_stat,
            next_offset,
            next_line,
        )
        totals.files_scanned += 1
    return totals.freeze()


def _source_state(conn: sqlite3.Connection, source_path: str) -> _SourceState | None:
    row = conn.execute(
        """
        SELECT device, inode, size, parsed_offset, parsed_line
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
    )


def _resume_position(
    state: _SourceState | None, stat: os.stat_result
) -> tuple[int, int]:
    if state is None:
        return 0, 0
    unchanged_file = state.device == stat.st_dev and state.inode == stat.st_ino
    has_not_shrunk = stat.st_size >= state.size and stat.st_size >= state.parsed_offset
    if unchanged_file and has_not_shrunk:
        return state.parsed_offset, state.parsed_line
    return 0, 0


def _ingest_complete_lines(
    conn: sqlite3.Connection,
    path: Path,
    source_path: str,
    offset: int,
    line_number: int,
    totals: _MutableIngestTotals,
) -> tuple[int, int]:
    next_offset = offset
    next_line = line_number
    with path.open("rb") as handle:
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
    return next_offset, next_line


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
) -> None:
    conn.execute(
        """
        INSERT INTO otel_completion_sources (
            source_path, device, inode, size, parsed_offset, parsed_line, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_path) DO UPDATE SET
            device = excluded.device,
            inode = excluded.inode,
            size = excluded.size,
            parsed_offset = excluded.parsed_offset,
            parsed_line = excluded.parsed_line,
            updated_at = excluded.updated_at
        """,
        (
            source_path,
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            parsed_offset,
            parsed_line,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
