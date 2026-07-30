"""Physical source-occurrence preservation for canonical semantic identities."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict

from ..domain.models import SourceOccurrence
from .repositories import RepositoryConflictError, validate_storage_scalars


class SourceOccurrenceRepository:
    """Store every distinct coordinate while coalescing the exact same copy."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, occurrence: SourceOccurrence) -> SourceOccurrence:
        validate_storage_scalars(asdict(occurrence))
        existing = self.get(occurrence.occurrence_id)
        if existing is not None:
            if existing == occurrence:
                return occurrence
            raise RepositoryConflictError(
                f"source occurrence identity conflicts: {occurrence.occurrence_id!r}"
            )
        self._connection.execute(
            """
            INSERT INTO source_occurrences (
              occurrence_id, semantic_logical_id, manifestation_key,
              source_revision, record_ordinal, byte_start, byte_end,
              adapter_version, first_seen_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                occurrence.occurrence_id,
                occurrence.semantic_logical_id,
                occurrence.manifestation_key,
                occurrence.source_revision,
                occurrence.record_ordinal,
                occurrence.byte_start,
                occurrence.byte_end,
                occurrence.adapter_version,
                occurrence.first_seen_publication_id,
            ),
        )
        return occurrence

    insert = add

    def add_many(self, occurrences: tuple[SourceOccurrence, ...]) -> None:
        for occurrence in occurrences:
            self.add(occurrence)

    def get(self, occurrence_id: str) -> SourceOccurrence | None:
        row = self._connection.execute(
            """
            SELECT occurrence_id, semantic_logical_id, manifestation_key,
                   source_revision, record_ordinal, byte_start, byte_end,
                   adapter_version, first_seen_publication_id
            FROM source_occurrences
            WHERE occurrence_id = ?
            """,
            (occurrence_id,),
        ).fetchone()
        return None if row is None else SourceOccurrence(*row)

    def for_semantic_id(self, semantic_logical_id: str) -> tuple[SourceOccurrence, ...]:
        rows = self._connection.execute(
            """
            SELECT occurrence_id, semantic_logical_id, manifestation_key,
                   source_revision, record_ordinal, byte_start, byte_end,
                   adapter_version, first_seen_publication_id
            FROM source_occurrences
            WHERE semantic_logical_id = ?
            ORDER BY manifestation_key, source_revision, record_ordinal,
                     byte_start, occurrence_id
            """,
            (semantic_logical_id,),
        )
        return tuple(SourceOccurrence(*row) for row in rows)
