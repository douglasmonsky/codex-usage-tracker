"""Bounded analytical writer and recoverable operational refresh lease."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from .database import short_writer_transaction
from .discovery import SourcePlan
from .normalize import NormalizedBatch
from .parser import PARSER_ADAPTER, PARSER_VERSION, ParsedBatch


@dataclass(frozen=True)
class WriteResult:
    inserted_calls: int
    inserted_tools: int
    deleted_rows: int
    canonical_calls: int
    excluded_calls: int
    transaction_ms: tuple[float, ...]


def commit_refresh(
    path: Path,
    plans: tuple[SourcePlan, ...],
    parsed: tuple[ParsedBatch, ...],
    normalized: tuple[NormalizedBatch, ...],
    *,
    generation: int,
    reselect_canonical: bool = False,
    assert_fence: Callable[[], None] | None = None,
    generation_plans: tuple[SourcePlan, ...] | None = None,
    canonicalize_touched: bool = True,
) -> WriteResult:
    """Stage a generation in bounded transactions, then publish it atomically."""

    transaction_ms: list[float] = []
    deleted_rows = 0
    touched_fingerprints: set[str] = set()
    with _timed_writer(path, transaction_ms, assert_fence) as connection:
        _insert_generation(
            connection,
            generation,
            generation_plans if generation_plans is not None else plans,
        )
        for plan, parsed_batch, batch in zip(
            plans,
            parsed,
            normalized,
            strict=True,
        ):
            if plan.replace_existing and plan.prior_source_id:
                deleted, removed_fingerprints = _delete_source(
                    connection,
                    plan.prior_source_id,
                )
                deleted_rows += deleted
                touched_fingerprints.update(removed_fingerprints)
            if plan.prior_source_id is None or plan.replace_existing:
                _upsert_source(connection, plan, parsed_batch, batch, generation)
        _upsert_threads(
            connection,
            tuple(row for batch in normalized for row in batch.threads),
        )
        _upsert_turns(
            connection,
            tuple(row for batch in normalized for row in batch.turns),
        )
        connection.execute(
            "UPDATE generations SET deleted_count = ? WHERE generation = ?",
            (deleted_rows, generation),
        )

    table_rows = (
        ("model_calls", _rows(normalized, "model_calls")),
        ("tool_calls", _rows(normalized, "tool_calls")),
        ("activity_events", _rows(normalized, "activities")),
        ("allowance_observations", _rows(normalized, "allowances")),
    )
    for table, rows in table_rows:
        for chunk in _chunks(rows):
            with _timed_writer(path, transaction_ms, assert_fence) as connection:
                _insert_rows(connection, table, chunk)
    if canonicalize_touched:
        touched_fingerprints.update(
            str(row["canonical_call_id"]) for row in table_rows[0][1]
        )
        for fingerprint_chunk in _chunks(tuple(sorted(touched_fingerprints))):
            with _timed_writer(path, transaction_ms, assert_fence) as connection:
                _canonicalize(
                    connection,
                    fingerprint_chunk,
                    reselect=reselect_canonical,
                )

    with _read_counts(path, generation) as counts:
        inserted_calls, inserted_tools, canonical, excluded = counts

    with _timed_writer(path, transaction_ms, assert_fence) as connection:
        for plan, parsed_batch, batch in zip(
            plans,
            parsed,
            normalized,
            strict=True,
        ):
            _upsert_source(connection, plan, parsed_batch, batch, generation)
        connection.execute(
            """
            UPDATE generations
            SET inserted_count = ?, deleted_count = ?,
                canonical_count = ?, excluded_count = ?,
                integrity_status = 'valid'
            WHERE generation = ?
            """,
            (
                inserted_calls + inserted_tools,
                deleted_rows,
                canonical,
                excluded,
                generation,
            ),
        )
    return WriteResult(
        inserted_calls=inserted_calls,
        inserted_tools=inserted_tools,
        deleted_rows=deleted_rows,
        canonical_calls=canonical,
        excluded_calls=excluded,
        transaction_ms=tuple(transaction_ms),
    )


def canonicalize_initial_duplicates(
    path: Path,
    transaction_ms: list[float],
    *,
    assert_fence: Callable[[], None] | None = None,
) -> None:
    """Resolve only actual initial-hydration collisions."""

    with sqlite3.connect(path) as connection:
        fingerprints = tuple(
            str(row[0])
            for row in connection.execute(
                """
                SELECT canonical_call_id
                FROM model_calls
                GROUP BY canonical_call_id
                HAVING COUNT(*) > 1
                ORDER BY canonical_call_id
                """
            )
        )
    for chunk in _chunks(fingerprints):
        with _timed_writer(path, transaction_ms, assert_fence) as connection:
            _canonicalize(connection, chunk, reselect=True)


_WRITE_BATCH_ROWS = 350
_RowT = TypeVar("_RowT")


@contextmanager
def _timed_writer(
    path: Path,
    timings: list[float],
    assert_fence: Callable[[], None] | None = None,
) -> Iterator[sqlite3.Connection]:
    if assert_fence is not None:
        assert_fence()
    started = time.perf_counter()
    with short_writer_transaction(path) as connection:
        yield connection
        if assert_fence is not None:
            assert_fence()
    timings.append((time.perf_counter() - started) * 1000)


def _rows(
    batches: tuple[NormalizedBatch, ...],
    attribute: str,
) -> tuple[dict[str, Any], ...]:
    return tuple(
        row
        for batch in batches
        for row in getattr(batch, attribute)
    )


def _chunks(rows: tuple[_RowT, ...]) -> Iterator[tuple[_RowT, ...]]:
    for start in range(0, len(rows), _WRITE_BATCH_ROWS):
        yield rows[start : start + _WRITE_BATCH_ROWS]


@contextmanager
def _read_counts(
    path: Path,
    generation: int,
) -> Iterator[tuple[int, int, int, int]]:
    connection = sqlite3.connect(path)
    try:
        calls = connection.execute(
            "SELECT COUNT(*) FROM model_calls WHERE generation = ?",
            (generation,),
        ).fetchone()[0]
        tools = connection.execute(
            "SELECT COUNT(*) FROM tool_calls WHERE generation = ?",
            (generation,),
        ).fetchone()[0]
        canonical = connection.execute(
            "SELECT COUNT(*) FROM model_calls WHERE duplicate_state = 'canonical'"
        ).fetchone()[0]
        excluded = connection.execute(
            "SELECT COUNT(*) FROM model_calls WHERE duplicate_state != 'canonical'"
        ).fetchone()[0]
        yield int(calls), int(tools), int(canonical), int(excluded)
    finally:
        connection.close()


def _insert_generation(
    connection: sqlite3.Connection,
    generation: int,
    plans: tuple[SourcePlan, ...],
) -> None:
    revision = "|".join(
        f"{plan.observation.source_id}:{plan.end_byte}" for plan in plans
    )
    connection.execute(
        """
        INSERT INTO generations(
            generation, source_revision_digest, created_at,
            high_water_digest, inserted_count, updated_count,
            deleted_count, canonical_count, excluded_count,
            parser_versions, integrity_status
        )
        VALUES (?, ?, CURRENT_TIMESTAMP, ?, 0, 0, 0, 0, 0, ?, 'pending')
        ON CONFLICT(generation) DO UPDATE SET
            source_revision_digest = excluded.source_revision_digest,
            high_water_digest = excluded.high_water_digest,
            parser_versions = excluded.parser_versions,
            integrity_status = 'pending'
        """,
        (
            generation,
            _small_digest(revision),
            _small_digest(revision + ":water"),
            json.dumps({PARSER_ADAPTER: PARSER_VERSION}, sort_keys=True),
        ),
    )


def _upsert_source(
    connection: sqlite3.Connection,
    plan: SourcePlan,
    parsed: ParsedBatch,
    batch: NormalizedBatch,
    generation: int,
) -> None:
    observation = plan.observation
    connection.execute(
        """
        INSERT INTO sources(
            source_id, source_kind, archive_state, device_identity_hash,
            file_identity_hash, safe_label, size_bytes, modified_at,
            parsed_byte_offset, parsed_line_number, trailing_incomplete_bytes,
            trailing_incomplete_hash, replacement_fingerprint, parser_adapter,
            parser_version, parser_state_json, first_observed_at,
            last_observed_at, last_generation, parse_warning_count,
            unsupported_shape_count
        )
        VALUES (?, 'session', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            archive_state = excluded.archive_state,
            size_bytes = excluded.size_bytes,
            modified_at = excluded.modified_at,
            parsed_byte_offset = excluded.parsed_byte_offset,
            parsed_line_number = excluded.parsed_line_number,
            trailing_incomplete_bytes = excluded.trailing_incomplete_bytes,
            trailing_incomplete_hash = excluded.trailing_incomplete_hash,
            replacement_fingerprint = excluded.replacement_fingerprint,
            parser_state_json = excluded.parser_state_json,
            last_observed_at = CURRENT_TIMESTAMP,
            last_generation = excluded.last_generation,
            parse_warning_count = CASE
                WHEN sources.last_generation = excluded.last_generation
                THEN MAX(
                    sources.parse_warning_count,
                    excluded.parse_warning_count
                )
                ELSE sources.parse_warning_count
                     + excluded.parse_warning_count
            END,
            unsupported_shape_count = CASE
                WHEN sources.last_generation = excluded.last_generation
                THEN MAX(
                    sources.unsupported_shape_count,
                    excluded.unsupported_shape_count
                )
                ELSE sources.unsupported_shape_count
                     + excluded.unsupported_shape_count
            END
        """,
        (
            observation.source_id,
            "archived" if observation.is_archived else "active",
            observation.device_identity_hash,
            observation.file_identity_hash,
            f"Source {observation.source_id[-8:]}",
            observation.size_bytes,
            str(observation.modified_ns),
            plan.end_byte,
            plan.end_line,
            observation.trailing_incomplete_bytes,
            observation.trailing_incomplete_hash,
            plan.observation.prefix_fingerprint,
            PARSER_ADAPTER,
            PARSER_VERSION,
            batch.parser_state_json,
            generation,
            parsed.parse_warning_count,
            parsed.unsupported_shape_count,
        ),
    )


def _upsert_threads(connection: sqlite3.Connection, rows: tuple[dict[str, Any], ...]) -> None:
    for row in rows:
        columns = tuple(row)
        values = tuple(row.values())
        connection.execute(
            f"""
            INSERT INTO threads({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT(thread_id) DO NOTHING
            """,
            values,
        )


def _upsert_turns(connection: sqlite3.Connection, rows: tuple[dict[str, Any], ...]) -> None:
    for row in rows:
        columns = tuple(row)
        connection.execute(
            f"""
            INSERT INTO turns({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT(turn_id) DO NOTHING
            """,
            tuple(row.values()),
        )


def _insert_rows(
    connection: sqlite3.Connection,
    table: str,
    rows: tuple[dict[str, Any], ...],
) -> int:
    inserted = 0
    for row in rows:
        columns = tuple(row)
        cursor = connection.execute(
            f"""
            INSERT INTO {table}({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT DO NOTHING
            """,
            tuple(row.values()),
        )
        inserted += max(0, cursor.rowcount)
    return inserted


def _delete_source(
    connection: sqlite3.Connection,
    source_id: str,
) -> tuple[int, set[str]]:
    fingerprints = {
        str(row[0])
        for row in connection.execute(
            "SELECT canonical_call_id FROM model_calls WHERE source_id = ?",
            (source_id,),
        )
    }
    counts = [
        connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE source_id = ?",
            (source_id,),
        ).fetchone()[0]
        for table in (
            "model_calls",
            "tool_calls",
            "activity_events",
            "allowance_observations",
        )
    ]
    connection.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))
    return sum(int(value) for value in counts), fingerprints


def _canonicalize(
    connection: sqlite3.Connection,
    fingerprints: tuple[str, ...],
    *,
    reselect: bool,
) -> None:
    if not fingerprints:
        return
    placeholders = ", ".join("?" for _ in fingerprints)
    rows = connection.execute(
        f"""
        SELECT model_calls.model_call_id, model_calls.canonical_call_id
        FROM model_calls
        JOIN sources USING (source_id)
        WHERE canonical_call_id IN ({placeholders})
        ORDER BY model_calls.canonical_call_id,
                 CASE
                     WHEN ? = 0
                          AND model_calls.duplicate_state = 'canonical'
                     THEN 0
                     ELSE 1
                 END,
                 CASE sources.archive_state
                     WHEN 'active' THEN 0
                     WHEN 'archived' THEN 1
                     ELSE 2
                 END,
                 model_calls.model_call_id
        """,
        (*fingerprints, int(reselect)),
    ).fetchall()
    updates: list[tuple[str, str | None, str]] = []
    prior_fingerprint: str | None = None
    for row in rows:
        fingerprint = str(row[1])
        canonical = fingerprint != prior_fingerprint
        updates.append(
            (
                "canonical" if canonical else "copied",
                None if canonical else "copied_usage_fingerprint",
                str(row[0]),
            )
        )
        prior_fingerprint = fingerprint
    connection.executemany(
        """
        UPDATE model_calls
        SET duplicate_state = ?, duplicate_reason = ?
        WHERE model_call_id = ?
        """,
        updates,
    )
def _small_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
