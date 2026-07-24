"""Source-log parse planning and metadata persistence."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, TypeAlias

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.parser.state import (
    PARSER_ADAPTER_VERSION,
    ParserState,
    compact_parser_diagnostics,
    parser_state_from_json,
    parser_state_to_json,
)

_PREFIX_TAIL_BYTES = 64 * 1024
_FILESYSTEM_ID_PREFIX = "fsid-v1:"


def _serialize_filesystem_id(value: int) -> str:
    return f"{_FILESYSTEM_ID_PREFIX}{value}"


def _filesystem_id_key(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _serialize_filesystem_id(value)
    if not isinstance(value, str):
        return None
    payload = value.removeprefix(_FILESYSTEM_ID_PREFIX)
    try:
        identifier = int(payload)
    except ValueError:
        return None
    return _serialize_filesystem_id(identifier)


@dataclass(frozen=True)
class SourceParsePlan:
    path: Path
    start_byte: int = 0
    start_line: int = 0
    initial_state: ParserState | None = None
    replace_existing: bool = True


@dataclass(frozen=True)
class SourceFileMetadata:
    size_bytes: int
    mtime_ns: int
    source_device: str
    source_inode: str
    is_archived: int


ParsedSourceFile: TypeAlias = (
    tuple[Path, list[UsageEvent], dict[str, int], ParserState]
    | tuple[Path, list[UsageEvent], dict[str, int], ParserState, int]
)


def source_logs_requiring_parse(
    conn: sqlite3.Connection,
    logs: Iterable[Path],
) -> list[SourceParsePlan]:
    paths = list(logs)
    if not paths:
        return []
    return [plan for plan in (_source_parse_plan(conn, path) for path in paths) if plan is not None]


def _source_parse_plan(conn: sqlite3.Connection, path: Path) -> SourceParsePlan | None:
    metadata = _source_file_metadata(path)
    if metadata is None:
        return None
    row = _source_file_parse_row(conn, path)
    if row is None:
        return SourceParsePlan(path=path)
    return _source_parse_plan_from_row(path, metadata, row)


def _source_file_parse_row(conn: sqlite3.Connection, path: Path) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT size_bytes, mtime_ns, parsed_until_line
             , parsed_until_byte, parsed_prefix_tail_hash
             , source_device, source_inode
             , parser_adapter, parser_state_json
        FROM source_files
        WHERE source_file = ?
        """,
        (str(path),),
    ).fetchone()


def _source_parse_plan_from_row(
    path: Path, metadata: SourceFileMetadata, row: sqlite3.Row
) -> SourceParsePlan | None:
    previous_state = parser_state_from_json(row["parser_state_json"])
    if _requires_full_source_parse(row, previous_state):
        return SourceParsePlan(path=path)
    if _source_metadata_matches(path, row, metadata):
        return None
    if _can_incrementally_parse_source(path, metadata, row):
        return SourceParsePlan(
            path=path,
            start_byte=int(row["parsed_until_byte"]),
            start_line=int(row["parsed_until_line"]),
            initial_state=previous_state,
            replace_existing=False,
        )
    return SourceParsePlan(path=path)


def _requires_full_source_parse(row: sqlite3.Row, previous_state: ParserState | None) -> bool:
    previous_adapter = str(row["parser_adapter"] or "")
    return previous_adapter != PARSER_ADAPTER_VERSION or previous_state is None


def _source_metadata_matches(
    path: Path,
    row: sqlite3.Row,
    metadata: SourceFileMetadata,
) -> bool:
    # macOS can assign a different st_dev after a volume remount. The tracked
    # path and inode remain stable. On device drift, verify the stored prefix
    # tail too so an inode collision on another volume cannot mask replacement.
    device_matches = _filesystem_id_key(row["source_device"]) == metadata.source_device
    parsed_until_byte = int(row["parsed_until_byte"])
    expected_tail = str(row["parsed_prefix_tail_hash"] or "")
    content_matches = device_matches or (
        0 <= parsed_until_byte <= metadata.size_bytes
        and bool(expected_tail)
        and _parsed_prefix_tail_hash(path, parsed_until_byte) == expected_tail
    )
    return (
        int(row["size_bytes"]) == metadata.size_bytes
        and int(row["mtime_ns"]) == metadata.mtime_ns
        and _filesystem_id_key(row["source_inode"]) == metadata.source_inode
        and content_matches
    )


def validated_source_file_metadata(
    path: Path,
    row: sqlite3.Row,
) -> SourceFileMetadata | None:
    """Return the exact validated file identity snapshot, when still current."""
    try:
        metadata = _source_file_metadata(path)
        if metadata is None:
            return None
        return metadata if _source_metadata_matches(path, row, metadata) else None
    except OSError:
        return None


def source_file_handle_metadata_matches(
    handle: BinaryIO,
    metadata: SourceFileMetadata,
) -> bool:
    """Confirm an open descriptor is the file identity that was validated."""
    try:
        stat = os.fstat(handle.fileno())
    except OSError:
        return False
    return (
        int(stat.st_size) == metadata.size_bytes
        and int(stat.st_mtime_ns) == metadata.mtime_ns
        and _serialize_filesystem_id(int(stat.st_dev)) == metadata.source_device
        and _serialize_filesystem_id(int(stat.st_ino)) == metadata.source_inode
    )


def _can_incrementally_parse_source(
    path: Path, metadata: SourceFileMetadata, row: sqlite3.Row
) -> bool:
    previous_size = int(row["size_bytes"])
    previous_byte = int(row["parsed_until_byte"])
    expected_tail = str(row["parsed_prefix_tail_hash"] or "")
    # The inode and stored prefix tail protect append-only parsing. Requiring
    # st_dev as well turns a harmless macOS remount into a full-history rebuild.
    return (
        0 < previous_byte <= previous_size < metadata.size_bytes
        and _filesystem_id_key(row["source_inode"]) == metadata.source_inode
        and bool(expected_tail)
        and _parsed_prefix_tail_hash(path, previous_byte) == expected_tail
    )


def upsert_source_file_metadata(
    conn: sqlite3.Connection,
    *,
    parsed_files: Iterable[ParsedSourceFile],
) -> None:
    """Record metadata for source files parsed during refresh."""

    parsed = list(parsed_files)
    if not parsed:
        return
    indexed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: list[dict[str, Any]] = []
    for parsed_file in parsed:
        path, events, diagnostics, parser_state, final_line_number = _parsed_source_file_parts(
            parsed_file
        )
        row = _source_file_metadata_row(
            path=path,
            events=events,
            diagnostics=diagnostics,
            parser_state=parser_state,
            indexed_at=indexed_at,
            final_line_number=final_line_number,
        )
        if row is not None:
            rows.append(row)
    if not rows:
        return
    columns = [
        "source_file_id",
        "source_file",
        "source_file_hash",
        "is_archived",
        "size_bytes",
        "mtime_ns",
        "parsed_until_line",
        "parsed_until_byte",
        "parsed_prefix_tail_hash",
        "parsed_row_count",
        "source_generation",
        "source_device",
        "source_inode",
        "latest_record_id",
        "latest_event_timestamp",
        "parser_adapter",
        "parser_diagnostics_json",
        "parser_state_json",
        "last_indexed_at",
    ]
    placeholders = ", ".join("?" for _column in columns)
    update_clause = ", ".join(
        f"{column}=excluded.{column}"
        for column in columns
        if column not in {"source_file_id", "source_generation"}
    )
    update_clause += """,
        source_generation = source_files.source_generation + CASE
            WHEN source_files.parsed_until_byte != excluded.parsed_until_byte
              OR source_files.parsed_until_line != excluded.parsed_until_line
              OR source_files.parsed_prefix_tail_hash != excluded.parsed_prefix_tail_hash
              OR source_files.parser_adapter != excluded.parser_adapter
            THEN 1 ELSE 0 END
    """
    conn.executemany(
        (
            f"INSERT INTO source_files ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(source_file_id) DO UPDATE SET {update_clause}"
        ),
        [[row[column] for column in columns] for row in rows],
    )


def _parsed_source_file_parts(
    parsed_file: ParsedSourceFile,
) -> tuple[Path, list[UsageEvent], dict[str, int], ParserState, int | None]:
    path, events, diagnostics, parser_state, *rest = parsed_file
    final_line_number = rest[0] if rest else None
    return path, events, diagnostics, parser_state, final_line_number


def _source_file_metadata_row(
    *,
    path: Path,
    events: list[UsageEvent],
    diagnostics: dict[str, int],
    parser_state: ParserState,
    indexed_at: str,
    final_line_number: int | None = None,
) -> dict[str, Any] | None:
    metadata = _source_file_metadata(path)
    if metadata is None:
        return None
    latest_event = _latest_source_usage_event(events)
    parsed_until_line = final_line_number or _count_lines(path)
    parsed_until_byte = metadata.size_bytes
    return {
        "source_file_id": _source_file_id(path),
        "source_file": str(path),
        "source_file_hash": _source_file_hash(path),
        "is_archived": metadata.is_archived,
        "size_bytes": metadata.size_bytes,
        "mtime_ns": metadata.mtime_ns,
        "parsed_until_line": parsed_until_line,
        "parsed_until_byte": parsed_until_byte,
        "parsed_prefix_tail_hash": _parsed_prefix_tail_hash(path, parsed_until_byte),
        "parsed_row_count": parsed_until_line,
        "source_generation": 1,
        "source_device": metadata.source_device,
        "source_inode": metadata.source_inode,
        "latest_record_id": _latest_source_record_id(latest_event, parser_state),
        "latest_event_timestamp": _latest_source_event_timestamp(latest_event, parser_state),
        "parser_adapter": PARSER_ADAPTER_VERSION,
        "parser_diagnostics_json": json.dumps(
            compact_parser_diagnostics(diagnostics),
            sort_keys=True,
        ),
        "parser_state_json": parser_state_to_json(parser_state),
        "last_indexed_at": indexed_at,
    }


def _latest_source_record_id(
    latest_event: UsageEvent | None, parser_state: ParserState
) -> str | None:
    return latest_event.record_id if latest_event else parser_state.latest_record_id


def _latest_source_event_timestamp(
    latest_event: UsageEvent | None, parser_state: ParserState
) -> str | None:
    return latest_event.event_timestamp if latest_event else parser_state.latest_event_timestamp


def _latest_source_usage_event(events: list[UsageEvent]) -> UsageEvent | None:
    return max(
        events,
        key=lambda event: (
            event.event_timestamp,
            event.cumulative_total_tokens,
            event.line_number,
            event.record_id,
        ),
        default=None,
    )


def _source_file_metadata(path: Path) -> SourceFileMetadata | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return SourceFileMetadata(
        size_bytes=int(stat.st_size),
        mtime_ns=int(stat.st_mtime_ns),
        source_device=_serialize_filesystem_id(int(stat.st_dev)),
        source_inode=_serialize_filesystem_id(int(stat.st_ino)),
        is_archived=_is_archived_source_file(path),
    )


def _is_archived_source_file(path: Path) -> int:
    normalized = str(path).replace("\\", "/")
    return int("/archived_sessions/" in normalized or normalized.startswith("archived_sessions/"))


def _source_file_id(path: Path) -> str:
    return _source_file_hash(path)


def _source_file_hash(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _parsed_prefix_tail_hash(path: Path, parsed_until_byte: int) -> str:
    start = max(0, parsed_until_byte - _PREFIX_TAIL_BYTES)
    with path.open("rb") as handle:
        handle.seek(start)
        payload = handle.read(parsed_until_byte - start)
    return hashlib.sha256(payload).hexdigest()


def _count_lines(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            return sum(1 for _line in handle)
    except OSError:
        return 0
