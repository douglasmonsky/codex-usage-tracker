"""Typed CK-06 repositories for committed cursors and bounded diagnostics."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..domain.measurements import validate_nonnegative_int64
from .repositories import validate_storage_scalars


def _digest(value: str, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class SourceCursorRecord:
    manifestation_key: int
    source_revision: str
    byte_offset: int
    record_ordinal: int
    source_size_bytes: int
    prefix_through_cursor_sha256: str
    suffix_sha256: str
    latest_source_order: int
    parser_version: str
    adapter_version: str
    committed_publication_id: str
    updated_at_us: int

    def __post_init__(self) -> None:
        for field in ("manifestation_key", "byte_offset", "record_ordinal", "source_size_bytes", "latest_source_order"):
            validate_nonnegative_int64(getattr(self, field), allow_none=False)
        if self.byte_offset > self.source_size_bytes:
            raise ValueError("cursor byte offset cannot exceed source size")
        _digest(self.prefix_through_cursor_sha256, "prefix_through_cursor_sha256")
        _digest(self.suffix_sha256, "suffix_sha256")
        validate_storage_scalars({"updated_at_us": self.updated_at_us})


@dataclass(frozen=True, slots=True)
class SourceDiagnosticRecord:
    manifestation_key: int
    source_revision: str
    byte_start: int
    byte_end: int
    diagnostic_code: str
    record_ordinal: int | None
    first_seen_publication_id: str

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.manifestation_key, allow_none=False)
        validate_nonnegative_int64(self.byte_start, allow_none=False)
        validate_nonnegative_int64(self.byte_end, allow_none=False)
        if self.byte_start >= self.byte_end:
            raise ValueError("diagnostic range must contain bytes")
        validate_nonnegative_int64(self.record_ordinal)
        if not self.diagnostic_code:
            raise ValueError("diagnostic code is required")


class SourceCursorRepository:
    """The only writer for the analytical source cursor table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def put(self, cursor: SourceCursorRecord) -> SourceCursorRecord:
        self._connection.execute(
            """
            INSERT INTO source_cursors (
              manifestation_key, source_revision, byte_offset, record_ordinal,
              source_size_bytes, prefix_through_cursor_sha256, suffix_sha256,
              latest_source_order, parser_version, adapter_version,
              committed_publication_id, updated_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(manifestation_key) DO UPDATE SET
              source_revision = excluded.source_revision,
              byte_offset = excluded.byte_offset,
              record_ordinal = excluded.record_ordinal,
              source_size_bytes = excluded.source_size_bytes,
              prefix_through_cursor_sha256 = excluded.prefix_through_cursor_sha256,
              suffix_sha256 = excluded.suffix_sha256,
              latest_source_order = excluded.latest_source_order,
              parser_version = excluded.parser_version,
              adapter_version = excluded.adapter_version,
              committed_publication_id = excluded.committed_publication_id,
              updated_at_us = excluded.updated_at_us
            """,
            (
                cursor.manifestation_key,
                cursor.source_revision,
                cursor.byte_offset,
                cursor.record_ordinal,
                cursor.source_size_bytes,
                cursor.prefix_through_cursor_sha256,
                cursor.suffix_sha256,
                cursor.latest_source_order,
                cursor.parser_version,
                cursor.adapter_version,
                cursor.committed_publication_id,
                cursor.updated_at_us,
            ),
        )
        return cursor

    def get(self, manifestation_key: int) -> SourceCursorRecord | None:
        row = self._connection.execute(
            """
            SELECT manifestation_key, source_revision, byte_offset, record_ordinal,
                   source_size_bytes, prefix_through_cursor_sha256, suffix_sha256,
                   latest_source_order, parser_version, adapter_version,
                   committed_publication_id, updated_at_us
            FROM source_cursors WHERE manifestation_key = ?
            """,
            (manifestation_key,),
        ).fetchone()
        return None if row is None else SourceCursorRecord(*row)


class SourceDiagnosticRepository:
    """Append-only bounded parse diagnostic coordinates without error bodies."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, diagnostic: SourceDiagnosticRecord) -> SourceDiagnosticRecord:
        self._connection.execute(
            """
            INSERT INTO source_diagnostics (
              manifestation_key, source_revision, byte_start, byte_end,
              diagnostic_code, record_ordinal, first_seen_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(manifestation_key, source_revision, byte_start, byte_end, diagnostic_code)
            DO NOTHING
            """,
            (
                diagnostic.manifestation_key,
                diagnostic.source_revision,
                diagnostic.byte_start,
                diagnostic.byte_end,
                diagnostic.diagnostic_code,
                diagnostic.record_ordinal,
                diagnostic.first_seen_publication_id,
            ),
        )
        return diagnostic

    insert = add
