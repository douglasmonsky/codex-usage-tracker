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
from .schema import create_secondary_indexes, drop_secondary_indexes


@dataclass(frozen=True)
class WriteResult:
    inserted_calls: int
    inserted_tools: int
    deleted_rows: int
    canonical_calls: int
    excluded_calls: int
    transaction_ms: tuple[float, ...]


@dataclass(frozen=True)
class _FactKeyMaps:
    sources: dict[str, int]
    threads: dict[str, int]
    turns: dict[str, int]
    model_calls: dict[str, int]


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


def commit_initial_batches(
    path: Path,
    batches: tuple[tuple[SourcePlan, ParsedBatch, NormalizedBatch], ...],
    *,
    generation: int,
    generation_plans: tuple[SourcePlan, ...],
    initialize_generation: bool,
    transaction_ms: list[float],
    assert_fence: Callable[[], None] | None = None,
) -> None:
    """Write bounded parsed batches without cumulative rescans."""

    with _timed_writer(
        path,
        transaction_ms,
        assert_fence,
        require_capabilities=False,
        staging_bulk=True,
    ) as connection:
        if initialize_generation:
            _insert_generation(connection, generation, generation_plans)
        for plan, parsed, normalized in batches:
            _upsert_source(connection, plan, parsed, normalized, generation)
            _upsert_threads(connection, normalized.threads)
            _upsert_turns(
                connection,
                normalized.turns,
                accumulate_existing=True,
            )
            for table, rows in (
                ("model_calls", normalized.model_calls),
                ("tool_calls", normalized.tool_calls),
                ("activity_events", normalized.activities),
                ("allowance_observations", normalized.allowances),
            ):
                _insert_rows(connection, table, rows)


def finalize_initial_refresh(
    path: Path,
    *,
    generation: int,
    transaction_ms: list[float],
    assert_fence: Callable[[], None] | None = None,
    on_indexing: Callable[[], None] | None = None,
    on_indexes_built: Callable[[], None] | None = None,
) -> WriteResult:
    """Validate and publish counts once after the complete initial stream."""

    canonicalize_initial_duplicates(
        path,
        transaction_ms,
        assert_fence=assert_fence,
    )
    if on_indexing is not None:
        on_indexing()
    with _timed_writer(
        path,
        transaction_ms,
        assert_fence,
        require_capabilities=False,
        staging_bulk=True,
    ) as connection:
        create_secondary_indexes(connection)
    if on_indexes_built is not None:
        on_indexes_built()
    with _read_counts(path, generation) as counts:
        inserted_calls, inserted_tools, canonical, excluded = counts
    with _timed_writer(path, transaction_ms, assert_fence) as connection:
        connection.execute(
            """
            UPDATE generations
            SET inserted_count = ?,
                deleted_count = 0,
                canonical_count = ?,
                excluded_count = ?,
                integrity_status = 'valid'
            WHERE generation = ?
            """,
            (
                inserted_calls + inserted_tools,
                canonical,
                excluded,
                generation,
            ),
        )
    return WriteResult(
        inserted_calls=inserted_calls,
        inserted_tools=inserted_tools,
        deleted_rows=0,
        canonical_calls=canonical,
        excluded_calls=excluded,
        transaction_ms=tuple(transaction_ms),
    )


def commit_empty_initial_refresh(
    path: Path,
    *,
    generation: int,
    assert_fence: Callable[[], None] | None = None,
) -> WriteResult:
    """Publish a valid zero-fact generation for truthful partial coverage."""

    transaction_ms: list[float] = []
    prepare_initial_refresh(
        path,
        transaction_ms,
        assert_fence=assert_fence,
    )
    with _timed_writer(
        path,
        transaction_ms,
        assert_fence,
        require_capabilities=False,
        staging_bulk=True,
    ) as connection:
        _insert_generation(connection, generation, ())
    return finalize_initial_refresh(
        path,
        generation=generation,
        transaction_ms=transaction_ms,
        assert_fence=assert_fence,
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
            SELECT 'fp_' || lower(hex(canonical_call_id))
            FROM model_call_facts
                GROUP BY canonical_call_id
                HAVING COUNT(*) > 1
                ORDER BY canonical_call_id
                """
            )
        )
    for chunk in _chunks(fingerprints):
        with _timed_writer(
            path,
            transaction_ms,
            assert_fence,
            require_capabilities=False,
            staging_bulk=True,
        ) as connection:
            _canonicalize(connection, chunk, reselect=True)


def prepare_initial_refresh(
    path: Path,
    transaction_ms: list[float],
    *,
    assert_fence: Callable[[], None] | None = None,
) -> None:
    """Drop query indexes only on the unpublished cold-build artifact."""

    with _timed_writer(
        path,
        transaction_ms,
        assert_fence,
        staging_bulk=True,
    ) as connection:
        drop_secondary_indexes(connection)


_WRITE_BATCH_ROWS = 350
_RowT = TypeVar("_RowT")


@contextmanager
def _timed_writer(
    path: Path,
    timings: list[float],
    assert_fence: Callable[[], None] | None = None,
    *,
    require_capabilities: bool = True,
    staging_bulk: bool = False,
) -> Iterator[sqlite3.Connection]:
    if assert_fence is not None:
        assert_fence()
    started = time.perf_counter()
    transaction = (
        short_writer_transaction(path)
        if require_capabilities and not staging_bulk
        else short_writer_transaction(
            path,
            require_capabilities=require_capabilities,
            staging_bulk=staging_bulk,
        )
    )
    with transaction as connection:
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


def _chunks(
    rows: tuple[_RowT, ...],
    *,
    size: int = _WRITE_BATCH_ROWS,
) -> Iterator[tuple[_RowT, ...]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


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
    source_keys = _selector_key_map(
        connection,
        "sources",
        "source_key",
        "source_id",
        (row["source_id"] for row in rows),
    )
    for row in rows:
        compact = dict(row)
        compact["source_key"] = _mapped_key(
            source_keys,
            row["source_id"],
            "sources",
        )
        columns = tuple(compact)
        values = tuple(compact.values())
        connection.execute(
            f"""
            INSERT INTO threads({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT(thread_id) DO NOTHING
            """,
            values,
        )


def _upsert_turns(
    connection: sqlite3.Connection,
    rows: tuple[dict[str, Any], ...],
    *,
    accumulate_existing: bool = False,
) -> None:
    thread_keys = _selector_key_map(
        connection,
        "threads",
        "thread_key",
        "thread_id",
        (row["thread_id"] for row in rows),
    )
    for row in rows:
        compact = dict(row)
        compact["thread_key"] = _mapped_key(
            thread_keys,
            row["thread_id"],
            "threads",
        )
        columns = tuple(compact)
        conflict_action = (
            """
            DO UPDATE SET
                ended_at = COALESCE(excluded.ended_at, turns.ended_at),
                status = excluded.status,
                completion_basis = COALESCE(
                    excluded.completion_basis,
                    turns.completion_basis
                ),
                last_source_offset = MAX(
                    turns.last_source_offset,
                    excluded.last_source_offset
                ),
                model_call_count = (
                    turns.model_call_count + excluded.model_call_count
                ),
                tool_call_count = (
                    turns.tool_call_count + excluded.tool_call_count
                ),
                skill_count = turns.skill_count + excluded.skill_count,
                compaction_count = (
                    turns.compaction_count + excluded.compaction_count
                ),
                patch_count = turns.patch_count + excluded.patch_count,
                error_count = turns.error_count + excluded.error_count,
                last_generation = excluded.last_generation
            """
            if accumulate_existing
            else "DO NOTHING"
        )
        connection.execute(
            f"""
            INSERT INTO turns({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT(turn_id) {conflict_action}
            """,
            tuple(compact.values()),
        )


def _insert_rows(
    connection: sqlite3.Connection,
    table: str,
    rows: tuple[dict[str, Any], ...],
) -> int:
    profile_keys: dict[tuple[str, ...], int] = {}
    fact_keys = _fact_key_maps(connection, table, rows)
    if table == "allowance_observations":
        return sum(
            _insert_allowance_state(
                connection,
                row,
                fact_keys=fact_keys,
            )
            for row in rows
        )
    prepared: dict[
        tuple[str, tuple[str, ...]],
        list[tuple[Any, ...]],
    ] = {}
    for row in rows:
        physical_table, compact = _compact_fact_row(
            connection,
            table,
            row,
            profile_keys,
            fact_keys,
        )
        columns = tuple(compact)
        prepared.setdefault(
            (physical_table, columns),
            [],
        ).append(tuple(compact.values()))
    inserted = 0
    for (physical_table, columns), values in prepared.items():
        cursor = connection.executemany(
            f"""
            INSERT INTO {physical_table}({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT DO NOTHING
            """,
            values,
        )
        inserted += max(0, cursor.rowcount)
    return inserted


def _compact_fact_row(
    connection: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
    profile_keys: dict[tuple[str, ...], int],
    fact_keys: _FactKeyMaps,
) -> tuple[str, dict[str, Any]]:
    table_map = {
        "model_calls": "model_call_facts",
        "tool_calls": "tool_call_facts",
        "activity_events": "activity_facts",
    }
    physical_table = table_map.get(table)
    if physical_table is None:
        raise ValueError(f"unsupported analytical fact table: {table}")

    compact = dict(row)
    compact["source_key"] = _mapped_key(
        fact_keys.sources,
        compact.pop("source_id"),
        "sources",
    )
    compact["thread_key"] = _mapped_key(
        fact_keys.threads,
        compact.pop("thread_id"),
        "threads",
    )
    compact["turn_key"] = _mapped_optional_key(
        fact_keys.turns,
        compact.pop("turn_id", None),
    )
    if table == "model_calls":
        model_profile = (
            str(compact.pop("model")),
            str(compact.pop("effort") or ""),
            str(compact.pop("service_tier") or ""),
            str(compact.pop("origin")),
        )
        if model_profile not in profile_keys:
            profile_keys[model_profile] = _model_profile_key(
                connection,
                model_profile,
            )
        compact["model_profile_key"] = profile_keys[model_profile]
        compact["model_call_id"] = _selector_blob(
            compact["model_call_id"],
            "call_",
        )
        compact["canonical_call_id"] = _selector_blob(
            compact["canonical_call_id"],
            "fp_",
        )
    if table == "tool_calls":
        tool_name = str(compact.pop("tool_name"))
        tool_profile = (
            tool_name,
            str(compact.pop("server_name") or ""),
            str(compact.pop("namespace") or ""),
            str(compact.pop("tool_category")),
            str(compact.pop("operation", tool_name)),
        )
        if tool_profile not in profile_keys:
            profile_keys[tool_profile] = _tool_profile_key(
                connection,
                tool_profile,
            )
        compact["tool_profile_key"] = profile_keys[tool_profile]
        compact["tool_call_id"] = _selector_blob(
            compact["tool_call_id"],
            "tool_",
        )
        compact["nearest_model_call_key"] = _mapped_optional_key(
            fact_keys.model_calls,
            compact.pop("nearest_model_call_id", None),
        )
    if table == "activity_events":
        compact["activity_event_id"] = _selector_blob(
            compact["activity_event_id"],
            "act_",
        )
    return physical_table, compact


def _model_profile_key(
    connection: sqlite3.Connection,
    profile: tuple[str, str, str, str],
) -> int:
    connection.execute(
        """
        INSERT INTO model_profiles(model, effort_key, service_tier_key, origin)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(model, effort_key, service_tier_key, origin) DO NOTHING
        """,
        profile,
    )
    row = connection.execute(
        """
        SELECT model_profile_key
        FROM model_profiles
        WHERE model = ?
          AND effort_key = ?
          AND service_tier_key = ?
          AND origin = ?
        """,
        profile,
    ).fetchone()
    if row is None:
        raise RuntimeError("model profile was not persisted")
    return int(row[0])


def _tool_profile_key(
    connection: sqlite3.Connection,
    profile: tuple[str, str, str, str, str],
) -> int:
    connection.execute(
        """
        INSERT INTO tool_profiles(
            tool_name,
            server_name_key,
            namespace_key,
            tool_category,
            operation
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(
            tool_name,
            server_name_key,
            namespace_key,
            tool_category,
            operation
        ) DO NOTHING
        """,
        profile,
    )
    row = connection.execute(
        """
        SELECT tool_profile_key
        FROM tool_profiles
        WHERE tool_name = ?
          AND server_name_key = ?
          AND namespace_key = ?
          AND tool_category = ?
          AND operation = ?
        """,
        profile,
    ).fetchone()
    if row is None:
        raise RuntimeError("tool profile was not persisted")
    return int(row[0])


def _fact_key_maps(
    connection: sqlite3.Connection,
    table: str,
    rows: tuple[dict[str, Any], ...],
) -> _FactKeyMaps:
    sources = _selector_key_map(
        connection,
        "sources",
        "source_key",
        "source_id",
        (row["source_id"] for row in rows),
    )
    threads = (
        _selector_key_map(
            connection,
            "threads",
            "thread_key",
            "thread_id",
            (row["thread_id"] for row in rows),
        )
        if table != "allowance_observations"
        else {}
    )
    turns = (
        _selector_key_map(
            connection,
            "turns",
            "turn_key",
            "turn_id",
            (row.get("turn_id") for row in rows),
        )
        if table != "allowance_observations"
        else {}
    )
    call_field = (
        "nearest_model_call_id"
        if table == "tool_calls"
        else "source_model_call_id"
    )
    model_calls = (
        _selector_key_map(
            connection,
            "model_call_facts",
            "model_call_key",
            "model_call_id",
            (row.get(call_field) for row in rows),
            selector_prefix="call_",
        )
        if table in {"tool_calls", "allowance_observations"}
        else {}
    )
    return _FactKeyMaps(
        sources=sources,
        threads=threads,
        turns=turns,
        model_calls=model_calls,
    )


def _selector_key_map(
    connection: sqlite3.Connection,
    table: str,
    key_column: str,
    selector_column: str,
    selectors: Iterator[object],
    *,
    selector_prefix: str | None = None,
) -> dict[str, int]:
    originals = tuple(
        sorted({str(selector) for selector in selectors if selector is not None})
    )
    if not originals:
        return {}
    stored_by_original: dict[str, object] = {
        selector: (
            _selector_blob(selector, selector_prefix)
            if selector_prefix is not None
            else selector
        )
        for selector in originals
    }
    original_by_stored = {
        stored: original for original, stored in stored_by_original.items()
    }
    resolved: dict[str, int] = {}
    stored = tuple(stored_by_original.values())
    for chunk in _chunks(stored, size=800):
        placeholders = ", ".join("?" for _ in chunk)
        for row in connection.execute(
            f"""
            SELECT {selector_column}, {key_column}
            FROM {table}
            WHERE {selector_column} IN ({placeholders})
            """,
            chunk,
        ):
            resolved[original_by_stored[row[0]]] = int(row[1])
    missing = set(originals) - resolved.keys()
    if missing:
        raise ValueError(f"missing {table} selectors: {len(missing)}")
    return resolved


def _mapped_key(
    values: dict[str, int],
    selector: object,
    table: str,
) -> int:
    value = values.get(str(selector))
    if value is None:
        raise ValueError(f"missing {table} selector")
    return value


def _mapped_optional_key(
    values: dict[str, int],
    selector: object,
) -> int | None:
    if selector is None:
        return None
    return values.get(str(selector))


def _insert_allowance_state(
    connection: sqlite3.Connection,
    row: dict[str, Any],
    *,
    fact_keys: _FactKeyMaps | None = None,
) -> int:
    source_key = (
        _mapped_key(fact_keys.sources, row["source_id"], "sources")
        if fact_keys is not None
        else _required_key(
            connection,
            "sources",
            "source_key",
            "source_id",
            str(row["source_id"]),
        )
    )
    trigger_key = (
        _mapped_optional_key(
            fact_keys.model_calls,
            row.get("source_model_call_id"),
        )
        if fact_keys is not None
        else _optional_key(
            connection,
            "model_call_facts",
            "model_call_key",
            "model_call_id",
            row.get("source_model_call_id"),
        )
    )
    prior = connection.execute(
        """
        SELECT
            allowance_state_key,
            used_percent,
            duration_minutes,
            resets_at,
            model,
            service_tier,
            provenance,
            validation_warnings
        FROM allowance_states
        WHERE source_key = ?
          AND window_kind = ?
          AND limit_id IS ?
          AND plan_type IS ?
        ORDER BY last_observed_at DESC, allowance_state_key DESC
        LIMIT 1
        """,
        (
            source_key,
            row["window_kind"],
            row.get("limit_id"),
            row.get("plan_type"),
        ),
    ).fetchone()
    state_values = (
        row["used_percent"],
        row.get("duration_minutes"),
        row.get("resets_at"),
        row.get("model"),
        row.get("service_tier"),
        row["provenance"],
        row["validation_warnings"],
    )
    if prior is not None and tuple(prior[1:]) == state_values:
        connection.execute(
            """
            UPDATE allowance_states
            SET last_observed_at = ?,
                observation_count = observation_count + 1,
                observation_trigger_call_key = ?,
                generation = ?
            WHERE allowance_state_key = ?
            """,
            (
                row["observed_at"],
                trigger_key,
                row["generation"],
                int(prior[0]),
            ),
        )
        return 0

    cursor = connection.execute(
        """
        INSERT INTO allowance_states(
            allowance_observation_id,
            source_key,
            first_observed_at,
            last_observed_at,
            observation_count,
            window_kind,
            limit_id,
            plan_type,
            used_percent,
            duration_minutes,
            resets_at,
            model,
            service_tier,
            observation_trigger_call_key,
            generation,
            duplicate_state,
            provenance,
            validation_warnings
        )
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(allowance_observation_id) DO NOTHING
        """,
        (
            _selector_blob(row["allowance_observation_id"], "allow_"),
            source_key,
            row["observed_at"],
            row["observed_at"],
            row["window_kind"],
            row.get("limit_id"),
            row.get("plan_type"),
            row["used_percent"],
            row.get("duration_minutes"),
            row.get("resets_at"),
            row.get("model"),
            row.get("service_tier"),
            trigger_key,
            row["generation"],
            row["duplicate_state"],
            row["provenance"],
            row["validation_warnings"],
        ),
    )
    return max(0, cursor.rowcount)


def _required_key(
    connection: sqlite3.Connection,
    table: str,
    key_column: str,
    selector_column: str,
    selector: str,
) -> int:
    value = _optional_key(
        connection,
        table,
        key_column,
        selector_column,
        selector,
    )
    if value is None:
        raise ValueError(f"missing {table} selector")
    return value


def _optional_key(
    connection: sqlite3.Connection,
    table: str,
    key_column: str,
    selector_column: str,
    selector: object,
) -> int | None:
    if selector is None:
        return None
    stored_selector = (
        _selector_blob(selector, "call_")
        if table == "model_call_facts" and selector_column == "model_call_id"
        else str(selector)
    )
    row = connection.execute(
        f"SELECT {key_column} FROM {table} WHERE {selector_column} = ?",
        (stored_selector,),
    ).fetchone()
    return None if row is None else int(row[0])


def _selector_blob(selector: object, prefix: str) -> bytes:
    value = str(selector)
    if not value.startswith(prefix):
        raise ValueError(f"invalid selector prefix: {prefix}")
    return bytes.fromhex(value[len(prefix) :])


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
        SELECT
            'call_' || lower(hex(facts.model_call_id)),
            'fp_' || lower(hex(facts.canonical_call_id))
        FROM model_call_facts AS facts
        JOIN sources USING (source_key)
        WHERE facts.canonical_call_id IN ({placeholders})
        ORDER BY facts.canonical_call_id,
                 CASE
                     WHEN ? = 0
                AND facts.duplicate_state = 'canonical'
                     THEN 0
                     ELSE 1
                 END,
                 CASE sources.archive_state
                     WHEN 'active' THEN 0
                     WHEN 'archived' THEN 1
                     ELSE 2
                 END,
            facts.model_call_id
        """,
        (
            *(_selector_blob(item, "fp_") for item in fingerprints),
            int(reselect),
        ),
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
        UPDATE model_call_facts
        SET duplicate_state = ?, duplicate_reason = ?
        WHERE model_call_id = unhex(substr(?, 6))
        """,
        updates,
    )
    connection.executemany(
        """
        UPDATE allowance_states
        SET duplicate_state = ?
        WHERE observation_trigger_call_key = (
            SELECT model_call_key
            FROM model_call_facts
            WHERE model_call_id = unhex(substr(?, 6))
        )
        """,
        ((state, model_call_id) for state, _reason, model_call_id in updates),
    )


def _small_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
