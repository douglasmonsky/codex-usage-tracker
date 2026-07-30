"""Parameterized repositories for canonical database-v1 facts.

The repositories in this module own canonical rows, not source discovery or
publication orchestration.  SQL identifiers are selected from a fixed
production allowlist; all fact values are bound parameters.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Generic, TypeVar, cast

from ..domain.models import (
    AccountingSummary,
    ConfiguredProducer,
    ConfiguredSource,
    MeasurementAggregate,
    ModelCallTokens,
    SourceManifestation,
)


class RepositoryConflictError(ValueError):
    """A stable key was reused for a different canonical row."""


RowT = TypeVar("RowT")

_SELECTED_FACT_TABLES = frozenset(
    {
        "adapters",
        "projects",
        "resources",
        "model_profiles",
        "sessions",
        "turns",
        "model_call_locations",
        "model_calls",
        "tool_invocations",
        "tool_resources",
        "state_changes",
        "activities",
        "compaction_boundaries",
        "allowance_limits",
        "allowance_cycles",
        "allowance_observations",
        "allowance_intervals",
        "rate_card_revisions",
    }
)

_MIN_INT64 = -(2**63)
_MAX_INT64 = 2**63 - 1
_NONNEGATIVE_SUFFIXES = (
    "_bytes",
    "_count",
    "_depth",
    "_duration_us",
    "_mask",
    "_offset",
    "_order",
    "_ordinal",
    "_rank",
    "_tokens",
)
_NONNEGATIVE_FIELDS = frozenset(
    {
        "byte_end",
        "byte_start",
        "manifestation_key",
        "relationship_version",
        "selected",
        "transition_version",
    }
)
_UTC_SUFFIXES = ("_at_us", "_from_us", "_through_us", "_start_us", "_end_us")
_UTC_FIELDS = frozenset({"reset_time_us"})
_BOOLEAN_FIELDS = frozenset(
    {
        "ratio_eligible",
        "reasoning_in_output",
        "sample_truncated",
        "selected",
        "source_coverage_changed",
        "tail_pending",
        "write_intent",
    }
)
_JSON_SUFFIX = "_json"
_DECIMAL_FIELDS = frozenset({"used_percent", "remaining_percent", "percent_delta"})


def _row_values(row: object) -> dict[str, Any]:
    if not is_dataclass(row) or isinstance(row, type):
        raise TypeError("repository rows must be dataclass instances")
    values = cast(dict[str, Any], asdict(row))
    validate_storage_scalars(values)
    return values


def validate_storage_scalars(values: dict[str, Any]) -> None:
    """Reject Python scalar values SQLite would otherwise coerce silently."""

    for field_name, value in values.items():
        if value is None:
            continue
        if field_name.endswith(_UTC_SUFFIXES) or field_name in _UTC_FIELDS:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be a signed 64-bit integer or null")
            if not _MIN_INT64 <= value <= _MAX_INT64:
                raise ValueError(f"{field_name} exceeds signed 64-bit range")
        elif field_name in _BOOLEAN_FIELDS:
            if type(value) is not int or value not in (0, 1):
                raise TypeError(f"{field_name} must be the integer boolean 0 or 1")
        elif field_name in _NONNEGATIVE_FIELDS or field_name.endswith(_NONNEGATIVE_SUFFIXES):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be a nonnegative integer or null")
            if value < 0 or value > _MAX_INT64:
                raise ValueError(f"{field_name} must fit a nonnegative signed 64-bit integer")
        elif field_name.endswith(_JSON_SUFFIX):
            _validate_canonical_json(field_name, value)
        elif field_name in _DECIMAL_FIELDS:
            _validate_canonical_decimal(field_name, value)


def _validate_canonical_json(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be canonical JSON text or null")
    try:
        decoded = json.loads(value)
        canonical = json.dumps(
            decoded,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be valid RFC 8259 JSON") from error
    if value != canonical:
        raise ValueError(f"{field_name} must use canonical JSON serialization")


def _validate_canonical_decimal(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be canonical finite decimal text or null")
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field_name} must be a finite decimal") from error
    if not decimal.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    canonical = format(decimal.normalize(), "f")
    if canonical == "-0":
        canonical = "0"
    if value != canonical:
        raise ValueError(f"{field_name} must use canonical finite decimal serialization")


def _selected_columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    if table not in _SELECTED_FACT_TABLES:
        raise ValueError(f"table is not a selected typed fact table: {table!r}")
    columns = tuple(str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})"))
    if not columns:
        raise ValueError(f"selected typed fact table is unavailable: {table!r}")
    return columns


class SelectedFactRepository(Generic[RowT]):
    """Insert and retrieve one explicitly selected typed fact-table row."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        key_column: str,
        row_type: type[RowT],
    ) -> None:
        self._connection = connection
        self._table = table
        self._row_type = row_type
        table_columns = _selected_columns(connection, table)
        row_columns = tuple(field.name for field in fields(cast(Any, row_type)))
        if key_column not in row_columns or key_column not in table_columns:
            raise ValueError(f"invalid key column {key_column!r} for {table}")
        if row_columns != table_columns:
            missing = tuple(column for column in table_columns if column not in row_columns)
            unexpected = tuple(column for column in row_columns if column not in table_columns)
            raise ValueError(
                f"typed row inventory must exactly match {table!r}; "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )
        self._key_column = key_column
        self._columns = row_columns

    def add(self, row: RowT) -> RowT:
        """Coalesce an identical canonical fact and reject an identity conflict."""

        values = _row_values(row)
        existing = self.get(values[self._key_column])
        if existing is not None:
            if existing == row:
                return existing
            raise RepositoryConflictError(
                f"{self._table} canonical key conflicts: {values[self._key_column]!r}"
            )
        columns_sql = ", ".join(self._columns)
        placeholders = ", ".join("?" for _ in self._columns)
        self._connection.execute(
            f"INSERT INTO {self._table} ({columns_sql}) VALUES ({placeholders})",
            tuple(values[column] for column in self._columns),
        )
        return row

    insert = add

    def get(self, key: object) -> RowT | None:
        columns_sql = ", ".join(self._columns)
        result = self._connection.execute(
            f"SELECT {columns_sql} FROM {self._table} WHERE {self._key_column} = ?",
            (key,),
        ).fetchone()
        if result is None:
            return None
        return self._row_type(**dict(zip(self._columns, result, strict=True)))


class ConfiguredProducerRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def put(self, producer: ConfiguredProducer) -> ConfiguredProducer:
        _row_values(producer)
        existing_by_id = self.get_by_id(producer.producer_id)
        if existing_by_id is not None and (
            existing_by_id.configured_producer_key != producer.configured_producer_key
            or existing_by_id.first_seen_publication_id != producer.first_seen_publication_id
        ):
            raise RepositoryConflictError(
                "producer ID maps to a different stable configured producer tuple"
            )
        existing = self.get_by_key(producer.configured_producer_key)
        if existing is not None and existing.producer_id != producer.producer_id:
            raise RepositoryConflictError(
                "configured producer key maps to a different producer identity"
            )
        self._connection.execute(
            """
            INSERT INTO source_producers (
              producer_id, configured_producer_key, display_label,
              first_seen_publication_id, last_seen_publication_id
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(producer_id) DO UPDATE SET
              display_label = excluded.display_label,
              last_seen_publication_id = excluded.last_seen_publication_id
            """,
            (
                producer.producer_id,
                producer.configured_producer_key,
                producer.display_label,
                producer.first_seen_publication_id,
                producer.last_seen_publication_id,
            ),
        )
        persisted = self.get_by_id(producer.producer_id)
        assert persisted is not None
        return persisted

    add = put

    def get_by_key(self, configured_producer_key: str) -> ConfiguredProducer | None:
        row = self._connection.execute(
            """
            SELECT producer_id, configured_producer_key, display_label,
                   first_seen_publication_id, last_seen_publication_id
            FROM source_producers
            WHERE configured_producer_key = ?
            """,
            (configured_producer_key,),
        ).fetchone()
        return None if row is None else ConfiguredProducer(*row)

    def get_by_id(self, producer_id: str) -> ConfiguredProducer | None:
        row = self._connection.execute(
            """
            SELECT producer_id, configured_producer_key, display_label,
                   first_seen_publication_id, last_seen_publication_id
            FROM source_producers
            WHERE producer_id = ?
            """,
            (producer_id,),
        ).fetchone()
        return None if row is None else ConfiguredProducer(*row)


class ConfiguredSourceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def put(self, source: ConfiguredSource) -> ConfiguredSource:
        _row_values(source)
        existing_by_id = self.get_by_id(source.source_id)
        if existing_by_id is not None and (
            existing_by_id.adapter_id,
            existing_by_id.producer_id,
            existing_by_id.source_kind,
            existing_by_id.adapter_native_source_key,
            existing_by_id.first_seen_publication_id,
        ) != (
            source.adapter_id,
            source.producer_id,
            source.source_kind,
            source.adapter_native_source_key,
            source.first_seen_publication_id,
        ):
            raise RepositoryConflictError(
                "source ID maps to a different stable configured source tuple"
            )
        existing = self.get_by_configured_key(
            adapter_id=source.adapter_id,
            producer_id=source.producer_id,
            source_kind=source.source_kind,
            adapter_native_source_key=source.adapter_native_source_key,
        )
        if existing is not None and existing.source_id != source.source_id:
            raise RepositoryConflictError(
                "configured source key maps to a different source identity"
            )
        self._connection.execute(
            """
            INSERT INTO sources (
              source_id, adapter_id, producer_id, source_kind,
              adapter_native_source_key, selected_history_preset,
              selected_from_us, selected_through_us,
              first_seen_publication_id, last_seen_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
              selected_history_preset = excluded.selected_history_preset,
              selected_from_us = excluded.selected_from_us,
              selected_through_us = excluded.selected_through_us,
              last_seen_publication_id = excluded.last_seen_publication_id
            """,
            tuple(asdict(source).values()),
        )
        persisted = self.get_by_id(source.source_id)
        assert persisted is not None
        return persisted

    add = put

    def get_by_configured_key(
        self,
        *,
        adapter_id: str,
        producer_id: str,
        source_kind: str,
        adapter_native_source_key: str,
    ) -> ConfiguredSource | None:
        row = self._connection.execute(
            """
            SELECT source_id, adapter_id, producer_id, source_kind,
                   adapter_native_source_key, selected_history_preset,
                   selected_from_us, selected_through_us,
                   first_seen_publication_id, last_seen_publication_id
            FROM sources
            WHERE adapter_id = ? AND producer_id = ? AND source_kind = ?
              AND adapter_native_source_key = ?
            """,
            (adapter_id, producer_id, source_kind, adapter_native_source_key),
        ).fetchone()
        return None if row is None else ConfiguredSource(*row)

    def get_by_id(self, source_id: str) -> ConfiguredSource | None:
        row = self._connection.execute(
            """
            SELECT source_id, adapter_id, producer_id, source_kind,
                   adapter_native_source_key, selected_history_preset,
                   selected_from_us, selected_through_us,
                   first_seen_publication_id, last_seen_publication_id
            FROM sources
            WHERE source_id = ?
            """,
            (source_id,),
        ).fetchone()
        return None if row is None else ConfiguredSource(*row)


class SourceManifestationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def put(self, manifestation: SourceManifestation) -> SourceManifestation:
        _row_values(manifestation)
        existing_by_id = self.get_by_id(manifestation.manifestation_id)
        if existing_by_id is not None and (
            existing_by_id.manifestation_key,
            existing_by_id.source_id,
            existing_by_id.adapter_native_file_key,
            existing_by_id.technical_path_key,
            existing_by_id.first_seen_publication_id,
        ) != (
            manifestation.manifestation_key,
            manifestation.source_id,
            manifestation.adapter_native_file_key,
            manifestation.technical_path_key,
            manifestation.first_seen_publication_id,
        ):
            raise RepositoryConflictError(
                "manifestation ID maps to a different stable manifestation tuple"
            )
        existing = self.get_by_file_key(
            source_id=manifestation.source_id,
            adapter_native_file_key=manifestation.adapter_native_file_key,
        )
        if existing is not None and (
            existing.manifestation_id != manifestation.manifestation_id
            or existing.manifestation_key != manifestation.manifestation_key
        ):
            raise RepositoryConflictError(
                "stable file key maps to a different manifestation identity"
            )
        values = tuple(asdict(manifestation).values())
        self._connection.execute(
            """
            INSERT INTO source_manifestations (
              manifestation_id, manifestation_key, source_id,
              adapter_native_file_key, technical_path_key, display_label,
              filesystem_identity_json, size_bytes, modified_at_us,
              prefix_sha256, suffix_sha256, content_revision, source_rank,
              state, time_range_start_us, time_range_end_us,
              time_range_confidence, selected, first_seen_publication_id,
              last_seen_publication_id, ended_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(manifestation_id) DO UPDATE SET
              technical_path_key = excluded.technical_path_key,
              display_label = excluded.display_label,
              filesystem_identity_json = excluded.filesystem_identity_json,
              size_bytes = excluded.size_bytes,
              modified_at_us = excluded.modified_at_us,
              prefix_sha256 = excluded.prefix_sha256,
              suffix_sha256 = excluded.suffix_sha256,
              content_revision = excluded.content_revision,
              source_rank = excluded.source_rank,
              state = excluded.state,
              time_range_start_us = excluded.time_range_start_us,
              time_range_end_us = excluded.time_range_end_us,
              time_range_confidence = excluded.time_range_confidence,
              selected = excluded.selected,
              last_seen_publication_id = excluded.last_seen_publication_id,
              ended_publication_id = excluded.ended_publication_id
            """,
            values,
        )
        persisted = self.get_by_id(manifestation.manifestation_id)
        assert persisted is not None
        return persisted

    add = put

    def get_by_file_key(
        self, *, source_id: str, adapter_native_file_key: str
    ) -> SourceManifestation | None:
        columns = tuple(field.name for field in fields(SourceManifestation))
        row = self._connection.execute(
            f"SELECT {', '.join(columns)} FROM source_manifestations "
            "WHERE source_id = ? AND adapter_native_file_key = ?",
            (source_id, adapter_native_file_key),
        ).fetchone()
        return None if row is None else SourceManifestation(*row)

    def get_by_id(self, manifestation_id: str) -> SourceManifestation | None:
        columns = tuple(field.name for field in fields(SourceManifestation))
        row = self._connection.execute(
            f"SELECT {', '.join(columns)} FROM source_manifestations WHERE manifestation_id = ?",
            (manifestation_id,),
        ).fetchone()
        return None if row is None else SourceManifestation(*row)


@dataclass(frozen=True, slots=True)
class RepositoryTiming:
    operation: str
    elapsed_ns: int


class AccountingRepository:
    """Read exact accounting grains without imputing missing measurements."""

    _TOKEN_COLUMNS = (
        "uncached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
    )

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        observe_timing: Callable[[RepositoryTiming], None] | None = None,
    ) -> None:
        self._connection = connection
        self._clock_ns = clock_ns
        self._observe_timing = observe_timing

    def _measure(self, operation: str, query: Callable[[], RowT]) -> RowT:
        started_ns = self._clock_ns()
        try:
            return query()
        finally:
            elapsed_ns = self._clock_ns() - started_ns
            if elapsed_ns < 0:
                raise ValueError("repository timing clock moved backwards")
            if self._observe_timing is not None:
                self._observe_timing(RepositoryTiming(operation, elapsed_ns))

    def model_call_tokens(self) -> tuple[ModelCallTokens, ...]:
        def query() -> tuple[ModelCallTokens, ...]:
            rows = self._connection.execute(
                """
                SELECT call_id, uncached_input_tokens, cached_input_tokens,
                       reasoning_tokens, output_tokens
                FROM model_calls_visible
                ORDER BY call_id
                """
            )
            return tuple(ModelCallTokens(*row) for row in rows)

        return self._measure("model_call_tokens", query)

    def summary(self) -> AccountingSummary:
        def query() -> AccountingSummary:
            expressions: list[str] = ["COUNT(*)"]
            for column in self._TOKEN_COLUMNS:
                expressions.extend(
                    (
                        f"SUM({column})",
                        f"COUNT({column})",
                        f"COUNT(*) - COUNT({column})",
                    )
                )
            row = self._connection.execute(
                f"SELECT {', '.join(expressions)} FROM model_calls_visible"
            ).fetchone()
            assert row is not None
            aggregates = [
                MeasurementAggregate(row[index], row[index + 1], row[index + 2])
                for index in range(1, len(row), 3)
            ]
            occurrence_count = int(
                self._connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM source_occurrences AS occurrence
                    JOIN model_call_locations AS call
                      ON call.call_id = occurrence.semantic_logical_id
                    """
                ).fetchone()[0]
            )
            return AccountingSummary(int(row[0]), occurrence_count, *aggregates)

        return self._measure("accounting_summary", query)
