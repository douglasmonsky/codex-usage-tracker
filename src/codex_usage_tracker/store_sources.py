"""Source-log parse planning and metadata persistence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.models import UsageEvent
from codex_usage_tracker.parser import (
    ParserState,
    compact_parser_diagnostics,
    parser_state_from_json,
    parser_state_to_json,
)


@dataclass(frozen=True)
class SourceParsePlan:
    path: Path
    start_byte: int = 0
    start_line: int = 0
    initial_state: ParserState | None = None
    replace_existing: bool = True


ParsedSourceFile = tuple[Path, list[UsageEvent], dict[str, int], ParserState]


def source_logs_requiring_parse(
    conn: sqlite3.Connection,
    logs: Iterable[Path],
) -> list[SourceParsePlan]:
    paths = list(logs)
    if not paths:
        return []
    changed: list[SourceParsePlan] = []
    for path in paths:
        metadata = _source_file_metadata(path)
        if metadata is None:
            continue
        row = conn.execute(
            """
            SELECT size_bytes, mtime_ns, parsed_until_line
                , parsed_until_byte, parser_state_json
            FROM source_files
            WHERE source_file = ?
            """,
            (str(path),),
        ).fetchone()
        if row is None:
            changed.append(SourceParsePlan(path=path))
            continue
        previous_size = int(row["size_bytes"])
        previous_mtime_ns = int(row["mtime_ns"])
        previous_byte = int(row["parsed_until_byte"])
        previous_line = int(row["parsed_until_line"])
        previous_state = parser_state_from_json(row["parser_state_json"])
        if previous_state is None:
            changed.append(SourceParsePlan(path=path))
            continue
        if (
            previous_size == metadata["size_bytes"]
            and previous_mtime_ns == metadata["mtime_ns"]
        ):
            continue
        if metadata["size_bytes"] > previous_size and 0 < previous_byte <= previous_size:
            changed.append(
                SourceParsePlan(
                    path=path,
                    start_byte=previous_byte,
                    start_line=previous_line,
                    initial_state=previous_state,
                    replace_existing=False,
                )
            )
            continue
        changed.append(SourceParsePlan(path=path))
    return changed


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
    for path, events, diagnostics, parser_state in parsed:
        metadata = _source_file_metadata(path)
        if metadata is None:
            continue
        latest_event = max(
            events,
            key=lambda event: (
                event.event_timestamp,
                event.cumulative_total_tokens,
                event.line_number,
                event.record_id,
            ),
            default=None,
        )
        rows.append(
            {
                "source_file_id": _source_file_id(path),
                "source_file": str(path),
                "source_file_hash": _source_file_hash(path),
                "is_archived": int(metadata["is_archived"]),
                "size_bytes": int(metadata["size_bytes"]),
                "mtime_ns": int(metadata["mtime_ns"]),
                "parsed_until_line": _count_lines(path),
                "parsed_until_byte": int(metadata["size_bytes"]),
                "latest_record_id": (
                    latest_event.record_id
                    if latest_event
                    else parser_state.latest_record_id
                ),
                "latest_event_timestamp": (
                    latest_event.event_timestamp
                    if latest_event
                    else parser_state.latest_event_timestamp
                ),
                "parser_adapter": "codex-jsonl-v1",
                "parser_diagnostics_json": json.dumps(
                    compact_parser_diagnostics(diagnostics),
                    sort_keys=True,
                ),
                "parser_state_json": parser_state_to_json(parser_state),
                "last_indexed_at": indexed_at,
            }
        )
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
        "latest_record_id",
        "latest_event_timestamp",
        "parser_adapter",
        "parser_diagnostics_json",
        "parser_state_json",
        "last_indexed_at",
    ]
    placeholders = ", ".join("?" for _column in columns)
    update_clause = ", ".join(
        f"{column}=excluded.{column}" for column in columns if column != "source_file_id"
    )
    conn.executemany(
        (
            f"INSERT INTO source_files ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(source_file_id) DO UPDATE SET {update_clause}"
        ),
        [[row[column] for column in columns] for row in rows],
    )


def _source_file_metadata(path: Path) -> dict[str, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "is_archived": _is_archived_source_file(path),
    }


def _is_archived_source_file(path: Path) -> int:
    normalized = str(path).replace("\\", "/")
    return int("/archived_sessions/" in normalized or normalized.startswith("archived_sessions/"))


def _source_file_id(path: Path) -> str:
    return _source_file_hash(path)


def _source_file_hash(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _count_lines(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            return sum(1 for _line in handle)
    except OSError:
        return 0
