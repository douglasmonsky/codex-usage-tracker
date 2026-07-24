"""Validated lookup for persisted source byte offsets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect_read_only
from codex_usage_tracker.store.sources import (
    SourceFileMetadata,
    validated_source_file_metadata,
)


@dataclass(frozen=True)
class ContextOffsetResolution:
    """One safe seek decision and its bounded diagnostic reason."""

    byte_offset: int | None
    strategy: str
    reason: str
    source_metadata: SourceFileMetadata | None = None


def resolve_context_offset(
    *,
    record_id: str,
    source_file: Path,
    db_path: Path = DEFAULT_DB_PATH,
) -> ContextOffsetResolution:
    """Return an offset only when current source provenance still matches."""
    with connect_read_only(db_path, timeout=1.0) as conn:
        row = conn.execute(
            """
            SELECT
                usage_events.source_file,
                usage_events.source_byte_offset,
                source_files.size_bytes,
                source_files.mtime_ns,
                source_files.parsed_until_byte,
                source_files.parsed_prefix_tail_hash,
                source_files.source_device,
                source_files.source_inode
            FROM usage_events
            JOIN source_files
              ON source_files.source_file = usage_events.source_file
            WHERE usage_events.record_id = ?
            LIMIT 1
            """,
            (record_id,),
        ).fetchone()
    if row is None:
        return ContextOffsetResolution(None, "sequential_fallback", "missing_provenance")

    persisted_path = Path(str(row["source_file"]))
    if persisted_path.resolve() != source_file.resolve():
        return ContextOffsetResolution(
            None,
            "sequential_fallback",
            "source_path_mismatch",
        )

    raw_offset = row["source_byte_offset"]
    if raw_offset is None:
        return ContextOffsetResolution(None, "sequential_fallback", "missing_offset")
    byte_offset = int(raw_offset)
    if byte_offset < 0 or byte_offset >= int(row["size_bytes"]):
        return ContextOffsetResolution(None, "sequential_fallback", "invalid_offset")
    source_metadata = validated_source_file_metadata(source_file, row)
    if source_metadata is None:
        return ContextOffsetResolution(None, "sequential_fallback", "stale_provenance")
    return ContextOffsetResolution(
        byte_offset,
        "offset_seek",
        "validated",
        source_metadata,
    )
