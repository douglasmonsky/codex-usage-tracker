"""Owner-only operational state outside the analytical fact database."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .database import (
    analytical_digest,
    analytical_generation_digest,
    analytical_generation_exists,
)
from .hydration import CatalogCheckpoint, HydrationSelection
from .models import (
    CutoverControl,
    CutoverState,
    KernelPaths,
)
from .schema import SCHEMA_VERSION

OPERATIONAL_SCHEMA_VERSION = 3
OPERATIONAL_TABLES = frozenset(
    {
        "refresh_runs",
        "source_registry",
        "coverage_control",
        "staged_coverage_control",
        "cutover_control",
        "live_events",
    }
)

_TRANSITIONS = {
    CutoverState.ABSENT: {CutoverState.BUILDING},
    CutoverState.BUILDING: {CutoverState.READY, CutoverState.FAILED},
    CutoverState.READY: {CutoverState.ACTIVE, CutoverState.FAILED},
    CutoverState.ACTIVE: {CutoverState.BUILDING, CutoverState.FAILED},
    CutoverState.FAILED: {CutoverState.BUILDING},
}
_FAILURE_CODE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")

_OPERATIONAL_SQL = """
CREATE TABLE refresh_runs (
    refresh_run_id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    owner_id TEXT,
    lease_expires_at TEXT,
    input_generation INTEGER,
    output_generation INTEGER,
    state TEXT NOT NULL CHECK (
        state IN ('queued', 'running', 'completed', 'failed', 'interrupted')
    ),
    stage TEXT NOT NULL,
    heartbeat_at TEXT,
    progress_percent REAL NOT NULL CHECK (
        progress_percent >= 0 AND progress_percent <= 100
    ),
    planned_high_water_json TEXT NOT NULL,
    changed_source_count INTEGER NOT NULL CHECK (changed_source_count >= 0),
    inserted_count INTEGER NOT NULL CHECK (inserted_count >= 0),
    updated_count INTEGER NOT NULL CHECK (updated_count >= 0),
    deleted_count INTEGER NOT NULL CHECK (deleted_count >= 0),
    stage_timings_json TEXT NOT NULL,
    terminal_error_code TEXT,
    terminal_error_message TEXT,
    completed_result_json TEXT
) STRICT;

CREATE TABLE source_registry (
    source_id TEXT PRIMARY KEY,
    source_location TEXT NOT NULL UNIQUE,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('tracked', 'missing', 'retired')),
    hydration_state TEXT NOT NULL DEFAULT 'hydrated' CHECK (
        hydration_state IN ('deferred', 'hydrating', 'hydrated')
    ),
    observed_size_bytes INTEGER NOT NULL DEFAULT 0 CHECK (
        observed_size_bytes >= 0
    ),
    observed_modified_ns INTEGER NOT NULL DEFAULT 0 CHECK (
        observed_modified_ns >= 0
    ),
    latest_event_at TEXT,
    timestamp_status TEXT NOT NULL DEFAULT 'uncertain' CHECK (
        timestamp_status IN ('certain', 'uncertain')
    ),
    hydrated_generation INTEGER CHECK (hydrated_generation > 0)
) STRICT;

CREATE TABLE coverage_control (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    preset TEXT NOT NULL CHECK (
        preset IN ('recent_30d', 'recent_90d', 'complete')
    ),
    captured_at TEXT NOT NULL,
    cutoff_at TEXT,
    complete_history INTEGER NOT NULL CHECK (complete_history IN (0, 1)),
    coverage_revision TEXT NOT NULL,
    cataloged_source_count INTEGER NOT NULL CHECK (
        cataloged_source_count >= 0
    ),
    hydrated_source_count INTEGER NOT NULL CHECK (
        hydrated_source_count >= 0
    ),
    deferred_source_count INTEGER NOT NULL CHECK (
        deferred_source_count >= 0
    ),
    cataloged_bytes INTEGER NOT NULL CHECK (cataloged_bytes >= 0),
    hydrated_bytes INTEGER NOT NULL CHECK (hydrated_bytes >= 0),
    deferred_bytes INTEGER NOT NULL CHECK (deferred_bytes >= 0),
    uncertain_source_count INTEGER NOT NULL CHECK (
        uncertain_source_count >= 0
    ),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE staged_coverage_control (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    preset TEXT NOT NULL CHECK (
        preset IN ('recent_30d', 'recent_90d', 'complete')
    ),
    captured_at TEXT NOT NULL,
    cutoff_at TEXT,
    coverage_revision TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE cutover_control (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    state TEXT NOT NULL CHECK (
        state IN ('absent', 'building', 'ready', 'active', 'failed')
    ),
    active_kernel_location TEXT,
    active_schema INTEGER,
    active_generation INTEGER,
    integrity_digest TEXT,
    staging_integrity_digest TEXT,
    staging_kernel_location TEXT,
    refresh_run_id TEXT,
    rollback_kernel_location TEXT,
    rollback_generation INTEGER,
    rollback_integrity_digest TEXT,
    legacy_cache_location TEXT,
    failure_code TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE live_events (
    event_id INTEGER PRIMARY KEY,
    event_key TEXT NOT NULL UNIQUE,
    publication_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation > 0),
    event_kind TEXT NOT NULL,
    selector TEXT,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
) STRICT;

CREATE INDEX idx_live_events_generation
ON live_events(generation, event_id);
"""


def kernel_paths(root: Path) -> KernelPaths:
    """Return the final side-by-side versioned cache paths."""

    return KernelPaths(
        analytical=root / "codex-usage-kernel-v1.sqlite3",
        operational=root / "codex-usage-kernel-operational-v1.sqlite3",
    )


def initialize_operational_database(path: Path) -> Path:
    """Create the owner-only operational sidecar atomically."""

    target = path.resolve()
    if target.exists():
        _require_database_file(target)
        target.chmod(0o600)
        _migrate_operational(target)
        _validate_operational(target)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.building-{uuid.uuid4().hex}")
    try:
        with sqlite3.connect(staging) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA user_version = {OPERATIONAL_SCHEMA_VERSION}")
            connection.executescript(_OPERATIONAL_SQL)
            connection.execute(
                "INSERT INTO cutover_control(singleton, state) VALUES (1, 'absent')"
            )
        staging.chmod(0o600)
        _validate_operational(staging)
        os.replace(staging, target)
        target.chmod(0o600)
        return target
    finally:
        staging.unlink(missing_ok=True)


def register_source(path: Path, identifier: str, source: Path) -> None:
    """Record the minimum source mapping in the non-exportable sidecar."""

    with _connect(path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO source_registry(
                source_id, source_location, first_seen_at, last_seen_at, state
            )
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'tracked')
            ON CONFLICT(source_id) DO UPDATE SET
                source_location = excluded.source_location,
                last_seen_at = CURRENT_TIMESTAMP,
                state = 'tracked'
            """,
            (identifier, str(source.resolve())),
        )


def record_hydration_catalog(
    path: Path,
    selection: HydrationSelection,
    *,
    hydrated_generation: int,
) -> dict[str, object]:
    """Publish privacy-safe source coverage in the owner-only sidecar."""

    with _connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _record_hydration_catalog_in_connection(
            connection,
            selection,
            hydrated_generation=hydrated_generation,
        )
        connection.execute(
            "DELETE FROM staged_coverage_control WHERE singleton = 1"
        )
    return load_hydration_coverage(path)


def stage_hydration_catalog(
    path: Path,
    selection: HydrationSelection,
) -> None:
    """Record build-time source states without changing active coverage."""

    selected_ids = {
        item.observation.source_id for item in selection.hydrate
    }
    with _connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO staged_coverage_control(
                singleton, preset, captured_at, cutoff_at, coverage_revision
            )
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
                preset = excluded.preset,
                captured_at = excluded.captured_at,
                cutoff_at = excluded.cutoff_at,
                coverage_revision = excluded.coverage_revision,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                selection.preset.value,
                _timestamp(selection.captured_at),
                _timestamp(selection.cutoff_at),
                hydration_selection_revision(selection),
            ),
        )
        for item in selection.hydrate + selection.deferred:
            observation = item.observation
            prior = connection.execute(
                """
                SELECT source_id, hydrated_generation
                FROM source_registry
                WHERE source_id = ? OR source_location = ?
                ORDER BY source_location = ? DESC
                LIMIT 1
                """,
                (
                    observation.source_id,
                    str(observation.path),
                    str(observation.path),
                ),
            ).fetchone()
            hydrated_generation = (
                int(prior["hydrated_generation"])
                if prior is not None
                and prior["hydrated_generation"] is not None
                else None
            )
            if (
                prior is not None
                and str(prior["source_id"]) != observation.source_id
            ):
                connection.execute(
                    """
                    UPDATE source_registry
                    SET last_seen_at = CURRENT_TIMESTAMP,
                        hydration_state = ?
                    WHERE source_id = ?
                    """,
                    (
                        (
                            "hydrating"
                            if observation.source_id in selected_ids
                            else "deferred"
                        ),
                        str(prior["source_id"]),
                    ),
                )
                continue
            connection.execute(
                """
                DELETE FROM source_registry
                WHERE source_location = ? AND source_id != ?
                """,
                (str(observation.path), observation.source_id),
            )
            connection.execute(
                """
                INSERT INTO source_registry(
                    source_id, source_location, first_seen_at, last_seen_at,
                    state, hydration_state, observed_size_bytes,
                    observed_modified_ns, latest_event_at, timestamp_status,
                    hydrated_generation
                )
                VALUES (
                    ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'tracked',
                    ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(source_id) DO UPDATE SET
                    source_location = excluded.source_location,
                    last_seen_at = CURRENT_TIMESTAMP,
                    state = 'tracked',
                    hydration_state = excluded.hydration_state,
                    observed_size_bytes = excluded.observed_size_bytes,
                    observed_modified_ns = excluded.observed_modified_ns,
                    latest_event_at = excluded.latest_event_at,
                    timestamp_status = excluded.timestamp_status,
                    hydrated_generation = COALESCE(
                        excluded.hydrated_generation,
                        source_registry.hydrated_generation
                    )
                """,
                (
                    observation.source_id,
                    str(observation.path),
                    (
                        "hydrating"
                        if observation.source_id in selected_ids
                        else "deferred"
                    ),
                    observation.size_bytes,
                    observation.modified_ns,
                    _timestamp(item.latest_event_at),
                    "certain" if item.timestamp_is_certain else "uncertain",
                    hydrated_generation,
                ),
            )


def restore_hydration_states(path: Path) -> None:
    """Reconcile transient source states after terminal refresh failure."""

    with _connect(path) as connection:
        connection.execute(
            """
            UPDATE source_registry
            SET hydration_state = CASE
                WHEN hydrated_generation IS NOT NULL THEN 'hydrated'
                ELSE 'deferred'
            END,
            last_seen_at = CURRENT_TIMESTAMP
            WHERE hydration_state = 'hydrating'
            """
        )


def load_staged_hydration(path: Path) -> dict[str, object] | None:
    """Return the staged selection identity used for crash recovery."""

    with _connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM staged_coverage_control WHERE singleton = 1"
        ).fetchone()
    if row is None:
        return None
    return {
        "preset": str(row["preset"]),
        "captured_at": str(row["captured_at"]),
        "cutoff_at": row["cutoff_at"],
        "coverage_revision": str(row["coverage_revision"]),
    }


def discard_staged_hydration(path: Path) -> None:
    """Forget an unusable staged selection without changing active coverage."""

    with _connect(path) as connection:
        connection.execute(
            "DELETE FROM staged_coverage_control WHERE singleton = 1"
        )


def _record_hydration_catalog_in_connection(
    connection: sqlite3.Connection,
    selection: HydrationSelection,
    *,
    hydrated_generation: int,
) -> None:
    hydrated_ids = {
        item.observation.source_id for item in selection.hydrate
    }
    catalog = selection.hydrate + selection.deferred
    revision = hydration_selection_revision(selection)
    for item in catalog:
        observation = item.observation
        is_hydrated = observation.source_id in hydrated_ids
        connection.execute(
            """
            DELETE FROM source_registry
            WHERE source_location = ? AND source_id != ?
            """,
            (str(observation.path), observation.source_id),
        )
        connection.execute(
            """
            INSERT INTO source_registry(
                source_id, source_location, first_seen_at, last_seen_at,
                state, hydration_state, observed_size_bytes,
                observed_modified_ns, latest_event_at, timestamp_status,
                hydrated_generation
            )
            VALUES (
                ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'tracked',
                ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(source_id) DO UPDATE SET
                source_location = excluded.source_location,
                last_seen_at = CURRENT_TIMESTAMP,
                state = 'tracked',
                hydration_state = excluded.hydration_state,
                observed_size_bytes = excluded.observed_size_bytes,
                observed_modified_ns = excluded.observed_modified_ns,
                latest_event_at = excluded.latest_event_at,
                timestamp_status = excluded.timestamp_status,
                hydrated_generation = CASE
                    WHEN excluded.hydration_state = 'hydrated'
                    THEN excluded.hydrated_generation
                    ELSE source_registry.hydrated_generation
                END
            """,
            (
                observation.source_id,
                str(observation.path),
                "hydrated" if is_hydrated else "deferred",
                observation.size_bytes,
                observation.modified_ns,
                _timestamp(item.latest_event_at),
                "certain" if item.timestamp_is_certain else "uncertain",
                hydrated_generation if is_hydrated else None,
            ),
        )
    hydrated_bytes = selection.hydrated_bytes
    deferred_bytes = selection.deferred_bytes
    connection.execute(
        """
        INSERT INTO coverage_control(
            singleton, preset, captured_at, cutoff_at, complete_history,
            coverage_revision, cataloged_source_count,
            hydrated_source_count, deferred_source_count, cataloged_bytes,
            hydrated_bytes, deferred_bytes, uncertain_source_count
        )
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(singleton) DO UPDATE SET
            preset = excluded.preset,
            captured_at = excluded.captured_at,
            cutoff_at = excluded.cutoff_at,
            complete_history = excluded.complete_history,
            coverage_revision = excluded.coverage_revision,
            cataloged_source_count = excluded.cataloged_source_count,
            hydrated_source_count = excluded.hydrated_source_count,
            deferred_source_count = excluded.deferred_source_count,
            cataloged_bytes = excluded.cataloged_bytes,
            hydrated_bytes = excluded.hydrated_bytes,
            deferred_bytes = excluded.deferred_bytes,
            uncertain_source_count = excluded.uncertain_source_count,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            selection.preset.value,
            _timestamp(selection.captured_at),
            _timestamp(selection.cutoff_at),
            int(selection.complete_history),
            revision,
            len(catalog),
            len(selection.hydrate),
            len(selection.deferred),
            hydrated_bytes + deferred_bytes,
            hydrated_bytes,
            deferred_bytes,
            selection.uncertain_source_count,
        ),
    )


def hydration_selection_revision(selection: HydrationSelection) -> str:
    """Return the effective source/preset identity for one coverage selection."""

    hydrated_ids = {
        item.observation.source_id for item in selection.hydrate
    }
    catalog = selection.hydrate + selection.deferred
    payload = {
        "preset": selection.preset.value,
        "sources": [
            {
                "source_id": item.observation.source_id,
                "size_bytes": item.observation.size_bytes,
                "modified_ns": item.observation.modified_ns,
                "latest_event_at": _timestamp(item.latest_event_at),
                "hydration_state": (
                    "hydrated"
                    if item.observation.source_id in hydrated_ids
                    else "deferred"
                ),
            }
            for item in sorted(
                catalog,
                key=lambda item: item.observation.source_id,
            )
        ],
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def load_hydration_coverage(path: Path) -> dict[str, object]:
    """Return the active source-coverage truth without touching facts."""

    with _connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM coverage_control WHERE singleton = 1"
        ).fetchone()
    if row is None:
        return {
            "preset": None,
            "captured_at": None,
            "cutoff_at": None,
            "complete_history": False,
            "coverage_revision": None,
            "cataloged_source_count": 0,
            "hydrated_source_count": 0,
            "deferred_source_count": 0,
            "cataloged_bytes": 0,
            "hydrated_bytes": 0,
            "deferred_bytes": 0,
            "uncertain_source_count": 0,
        }
    return {
        "preset": str(row["preset"]),
        "captured_at": str(row["captured_at"]),
        "cutoff_at": row["cutoff_at"],
        "complete_history": bool(row["complete_history"]),
        "coverage_revision": str(row["coverage_revision"]),
        "cataloged_source_count": int(row["cataloged_source_count"]),
        "hydrated_source_count": int(row["hydrated_source_count"]),
        "deferred_source_count": int(row["deferred_source_count"]),
        "cataloged_bytes": int(row["cataloged_bytes"]),
        "hydrated_bytes": int(row["hydrated_bytes"]),
        "deferred_bytes": int(row["deferred_bytes"]),
        "uncertain_source_count": int(row["uncertain_source_count"]),
    }


def hydrated_source_ids(path: Path) -> frozenset[str]:
    """Return sources already represented in a committed generation."""

    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT source_id FROM source_registry
            WHERE hydrated_generation IS NOT NULL
            """
        ).fetchall()
    return frozenset(str(row["source_id"]) for row in rows)


def hydrated_source_locations(path: Path) -> frozenset[Path]:
    """Return paths whose committed facts must survive file replacement."""

    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT source_location FROM source_registry
            WHERE hydrated_generation IS NOT NULL
            """
        ).fetchall()
    return frozenset(Path(str(row["source_location"])) for row in rows)


def hydration_catalog_checkpoints(
    path: Path,
) -> dict[str, CatalogCheckpoint]:
    """Load reusable structural timestamps for unchanged sources."""

    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT source_id, observed_size_bytes, observed_modified_ns,
                   latest_event_at
            FROM source_registry
            WHERE state = 'tracked'
            """
        ).fetchall()
    return {
        str(row["source_id"]): CatalogCheckpoint(
            size_bytes=int(row["observed_size_bytes"]),
            modified_ns=int(row["observed_modified_ns"]),
            latest_event_at=_read_timestamp(row["latest_event_at"]),
        )
        for row in rows
    }


def record_legacy_cache_metadata(path: Path, legacy_cache: Path) -> None:
    """Preserve an opaque downgrade pointer without opening the legacy file."""

    with _connect(path) as connection:
        connection.execute(
            """
            UPDATE cutover_control
            SET legacy_cache_location = ?, updated_at = CURRENT_TIMESTAMP
            WHERE singleton = 1
            """,
            (str(legacy_cache.resolve()),),
        )


def load_cutover_control(path: Path) -> CutoverControl:
    """Load the sole operational activation record."""

    with _connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM cutover_control WHERE singleton = 1"
        ).fetchone()
    if row is None:
        raise ValueError("operational sidecar is missing cutover control")
    return _control_from_row(row)


def reset_cutover_for_schema_upgrade(path: Path) -> None:
    """Clear reconstructible publication pointers for an explicit rebuild."""

    with _connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE cutover_control
            SET state = 'absent',
                active_kernel_location = NULL,
                active_schema = NULL,
                active_generation = NULL,
                integrity_digest = NULL,
                staging_integrity_digest = NULL,
                staging_kernel_location = NULL,
                refresh_run_id = NULL,
                rollback_kernel_location = NULL,
                rollback_generation = NULL,
                rollback_integrity_digest = NULL,
                failure_code = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE singleton = 1
            """
        )
        connection.commit()


def rollback_cutover(path: Path) -> CutoverControl:
    """Atomically restore the previously validated analytical artifact."""

    with _connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM cutover_control WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise ValueError("operational sidecar is missing cutover control")
        current = _control_from_row(row)
        rollback = current.rollback_kernel_path
        generation = current.rollback_generation
        digest = current.rollback_integrity_digest
        if rollback is None or generation is None or digest is None:
            raise ValueError("no validated rollback artifact is available")
        _validate_artifact(rollback, generation=generation, digest=digest)
        restored = CutoverControl(
            state=CutoverState.ACTIVE,
            active_kernel_path=rollback,
            active_schema=SCHEMA_VERSION,
            active_generation=generation,
            integrity_digest=digest,
            rollback_kernel_path=current.active_kernel_path,
            rollback_generation=current.active_generation,
            rollback_integrity_digest=current.integrity_digest,
            legacy_cache_path=current.legacy_cache_path,
        )
        _write_control(connection, restored)
    return load_cutover_control(path)


def transition_cutover(
    path: Path,
    state: CutoverState,
    *,
    active_kernel_path: Path | None = None,
    generation: int | None = None,
    staging_kernel_path: Path | None = None,
    refresh_run_id: str | None = None,
    integrity_digest: str | None = None,
    failure_code: str | None = None,
) -> CutoverControl:
    """Atomically validate and replace the cutover control record."""

    with _connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM cutover_control WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise ValueError("operational sidecar is missing cutover control")
        current = _control_from_row(row)
        _validate_transition(
            current,
            state,
            active_kernel_path=active_kernel_path,
            generation=generation,
            staging_kernel_path=staging_kernel_path,
            refresh_run_id=refresh_run_id,
            integrity_digest=integrity_digest,
            failure_code=failure_code,
        )
        next_control = _next_control(
            current,
            state,
            active_kernel_path=active_kernel_path,
            generation=generation,
            staging_kernel_path=staging_kernel_path,
            refresh_run_id=refresh_run_id,
            integrity_digest=integrity_digest,
            failure_code=failure_code,
        )
        _write_control(connection, next_control)
    return load_cutover_control(path)


def promote_cutover(
    path: Path,
    *,
    active_kernel_path: Path,
    generation: int,
    integrity_digest: str,
    hydration_selection: HydrationSelection | None = None,
) -> CutoverControl:
    """Validate one generation once and atomically publish its control record."""

    _validate_artifact(
        active_kernel_path,
        generation=generation,
        digest=integrity_digest,
    )
    with _connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM cutover_control WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise ValueError("operational sidecar is missing cutover control")
        current = _control_from_row(row)
        if current.state not in {CutoverState.BUILDING, CutoverState.READY}:
            raise ValueError("promotion requires a building or ready cutover")
        if current.staging_kernel_path != active_kernel_path.resolve():
            raise ValueError("active kernel must equal the staging artifact")
        ready = _ready_control(
            current,
            None,
            None,
            None,
            None,
            integrity_digest,
            None,
        )
        active = _active_control(
            ready,
            active_kernel_path.resolve(),
            generation,
            None,
            None,
            None,
            None,
        )
        if hydration_selection is not None:
            _record_hydration_catalog_in_connection(
                connection,
                hydration_selection,
                hydrated_generation=generation,
            )
        connection.execute(
            "DELETE FROM staged_coverage_control WHERE singleton = 1"
        )
        _write_control(connection, active)
    return load_cutover_control(path)


def _validate_transition(
    current: CutoverControl,
    state: CutoverState,
    *,
    active_kernel_path: Path | None,
    generation: int | None,
    staging_kernel_path: Path | None,
    refresh_run_id: str | None,
    integrity_digest: str | None,
    failure_code: str | None,
) -> None:
    if state not in _TRANSITIONS[current.state]:
        raise ValueError(
            f"invalid cutover transition: {current.state.value} -> {state.value}"
        )
    validators = {
        CutoverState.BUILDING: _validate_building,
        CutoverState.FAILED: _validate_failed,
    }
    if state is CutoverState.READY:
        _validate_ready(current, integrity_digest)
        return
    if state is CutoverState.ACTIVE:
        _validate_active(current, active_kernel_path, generation)
        return
    validator = validators.get(state)
    if validator is not None:
        validator(
            active_kernel_path,
            generation,
            staging_kernel_path,
            refresh_run_id,
            integrity_digest,
            failure_code,
        )


def _validate_building(
    _active: Path | None,
    _generation: int | None,
    staging: Path | None,
    refresh_run_id: str | None,
    _digest: str | None,
    _failure: str | None,
) -> None:
    if staging is None or refresh_run_id is None:
        raise ValueError("building requires staging path and refresh run")


def _validate_ready(
    current: CutoverControl,
    digest: str | None,
) -> None:
    staging = current.staging_kernel_path
    if staging is None or digest is None:
        raise ValueError("ready requires an integrity digest")
    _validate_artifact(staging, digest=digest)


def _validate_active(
    current: CutoverControl,
    active: Path | None,
    generation: int | None,
) -> None:
    if active is None or generation is None:
        raise ValueError("active requires kernel path and generation")
    if current.staging_kernel_path != active:
        raise ValueError("active kernel must equal the validated staging artifact")
    if current.staging_integrity_digest is None:
        raise ValueError("active kernel has no validated integrity digest")
    _validate_artifact(
        active,
        generation=generation,
        digest=current.staging_integrity_digest,
    )


def _validate_failed(
    _active: Path | None,
    _generation: int | None,
    _staging: Path | None,
    _refresh_run_id: str | None,
    _digest: str | None,
    failure: str | None,
) -> None:
    if failure is None or _FAILURE_CODE.fullmatch(failure) is None:
        raise ValueError("failed requires a bounded failure code")


def _next_control(
    current: CutoverControl,
    state: CutoverState,
    *,
    active_kernel_path: Path | None,
    generation: int | None,
    staging_kernel_path: Path | None,
    refresh_run_id: str | None,
    integrity_digest: str | None,
    failure_code: str | None,
) -> CutoverControl:
    builders = {
        CutoverState.BUILDING: _building_control,
        CutoverState.READY: _ready_control,
        CutoverState.ACTIVE: _active_control,
        CutoverState.FAILED: _failed_control,
    }
    return builders[state](
        current,
        active_kernel_path,
        generation,
        staging_kernel_path,
        refresh_run_id,
        integrity_digest,
        failure_code,
    )


def _building_control(
    current: CutoverControl,
    _active: Path | None,
    _generation: int | None,
    staging: Path | None,
    refresh_run_id: str | None,
    _digest: str | None,
    _failure: str | None,
) -> CutoverControl:
    return CutoverControl(
        state=CutoverState.BUILDING,
        active_kernel_path=current.active_kernel_path,
        active_schema=current.active_schema,
        active_generation=current.active_generation,
        integrity_digest=current.integrity_digest,
        staging_integrity_digest=None,
        staging_kernel_path=staging,
        refresh_run_id=refresh_run_id,
        rollback_kernel_path=current.rollback_kernel_path,
        rollback_generation=current.rollback_generation,
        rollback_integrity_digest=current.rollback_integrity_digest,
        legacy_cache_path=current.legacy_cache_path,
    )


def _ready_control(
    current: CutoverControl,
    _active: Path | None,
    _generation: int | None,
    _staging: Path | None,
    _refresh_run_id: str | None,
    digest: str | None,
    _failure: str | None,
) -> CutoverControl:
    return CutoverControl(
        state=CutoverState.READY,
        active_kernel_path=current.active_kernel_path,
        active_schema=current.active_schema,
        active_generation=current.active_generation,
        integrity_digest=current.integrity_digest,
        staging_integrity_digest=digest,
        staging_kernel_path=current.staging_kernel_path,
        refresh_run_id=current.refresh_run_id,
        rollback_kernel_path=current.rollback_kernel_path,
        rollback_generation=current.rollback_generation,
        rollback_integrity_digest=current.rollback_integrity_digest,
        legacy_cache_path=current.legacy_cache_path,
    )


def _active_control(
    current: CutoverControl,
    active: Path | None,
    generation: int | None,
    _staging: Path | None,
    _refresh_run_id: str | None,
    _digest: str | None,
    _failure: str | None,
) -> CutoverControl:
    rollback = current.rollback_kernel_path
    rollback_generation = current.rollback_generation
    rollback_digest = current.rollback_integrity_digest
    if current.active_kernel_path and current.active_kernel_path != active:
        rollback = current.active_kernel_path
        rollback_generation = current.active_generation
        rollback_digest = current.integrity_digest
    return CutoverControl(
        state=CutoverState.ACTIVE,
        active_kernel_path=active,
        active_schema=SCHEMA_VERSION,
        active_generation=generation,
        integrity_digest=current.staging_integrity_digest,
        rollback_kernel_path=rollback,
        rollback_generation=rollback_generation,
        rollback_integrity_digest=rollback_digest,
        legacy_cache_path=current.legacy_cache_path,
    )


def _failed_control(
    current: CutoverControl,
    _active: Path | None,
    _generation: int | None,
    _staging: Path | None,
    _refresh_run_id: str | None,
    _digest: str | None,
    failure: str | None,
) -> CutoverControl:
    return CutoverControl(
        state=CutoverState.FAILED,
        active_kernel_path=current.active_kernel_path,
        active_schema=current.active_schema,
        active_generation=current.active_generation,
        integrity_digest=current.integrity_digest,
        staging_integrity_digest=current.staging_integrity_digest,
        staging_kernel_path=current.staging_kernel_path,
        refresh_run_id=current.refresh_run_id,
        rollback_kernel_path=current.rollback_kernel_path,
        rollback_generation=current.rollback_generation,
        rollback_integrity_digest=current.rollback_integrity_digest,
        legacy_cache_path=current.legacy_cache_path,
        failure_code=failure,
    )


def _write_control(
    connection: sqlite3.Connection,
    control: CutoverControl,
) -> None:
    connection.execute(
        """
        UPDATE cutover_control
        SET state = ?,
            active_kernel_location = ?,
            active_schema = ?,
            active_generation = ?,
            integrity_digest = ?,
            staging_integrity_digest = ?,
            staging_kernel_location = ?,
            refresh_run_id = ?,
            rollback_kernel_location = ?,
            rollback_generation = ?,
            rollback_integrity_digest = ?,
            legacy_cache_location = ?,
            failure_code = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE singleton = 1
        """,
        (
            control.state.value,
            _string_path(control.active_kernel_path),
            control.active_schema,
            control.active_generation,
            control.integrity_digest,
            control.staging_integrity_digest,
            _string_path(control.staging_kernel_path),
            control.refresh_run_id,
            _string_path(control.rollback_kernel_path),
            control.rollback_generation,
            control.rollback_integrity_digest,
            _string_path(control.legacy_cache_path),
            control.failure_code,
        ),
    )


@contextmanager
def _connect(path: Path) -> Iterator[sqlite3.Connection]:
    target = path.resolve()
    _require_database_file(target)
    target.chmod(0o600)
    connection = sqlite3.connect(target, isolation_level="DEFERRED")
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
    finally:
        connection.close()


def _validate_operational(path: Path) -> None:
    with _connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != OPERATIONAL_SCHEMA_VERSION:
            raise ValueError("operational schema version is invalid")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        if tables != OPERATIONAL_TABLES:
            raise ValueError(f"operational table set is invalid: {sorted(tables)}")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("operational quick_check failed")


def _migrate_operational(path: Path) -> None:
    """Upgrade only the immediately preceding public sidecar schema."""

    with sqlite3.connect(path) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version == OPERATIONAL_SCHEMA_VERSION:
            return
        if version != 2:
            raise ValueError("operational schema version is invalid")
        connection.executescript(
            f"""
            BEGIN IMMEDIATE;
            ALTER TABLE source_registry
            ADD COLUMN hydration_state TEXT NOT NULL DEFAULT 'hydrated'
            CHECK (hydration_state IN ('deferred', 'hydrating', 'hydrated'));
            ALTER TABLE source_registry
            ADD COLUMN observed_size_bytes INTEGER NOT NULL DEFAULT 0
            CHECK (observed_size_bytes >= 0);
            ALTER TABLE source_registry
            ADD COLUMN observed_modified_ns INTEGER NOT NULL DEFAULT 0
            CHECK (observed_modified_ns >= 0);
            ALTER TABLE source_registry ADD COLUMN latest_event_at TEXT;
            ALTER TABLE source_registry
            ADD COLUMN timestamp_status TEXT NOT NULL DEFAULT 'uncertain'
            CHECK (timestamp_status IN ('certain', 'uncertain'));
            ALTER TABLE source_registry
            ADD COLUMN hydrated_generation INTEGER
            CHECK (hydrated_generation > 0);
            CREATE TABLE coverage_control (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                preset TEXT NOT NULL CHECK (
                    preset IN ('recent_30d', 'recent_90d', 'complete')
                ),
                captured_at TEXT NOT NULL,
                cutoff_at TEXT,
                complete_history INTEGER NOT NULL
                    CHECK (complete_history IN (0, 1)),
                coverage_revision TEXT NOT NULL,
                cataloged_source_count INTEGER NOT NULL
                    CHECK (cataloged_source_count >= 0),
                hydrated_source_count INTEGER NOT NULL
                    CHECK (hydrated_source_count >= 0),
                deferred_source_count INTEGER NOT NULL
                    CHECK (deferred_source_count >= 0),
                cataloged_bytes INTEGER NOT NULL
                    CHECK (cataloged_bytes >= 0),
                hydrated_bytes INTEGER NOT NULL
                    CHECK (hydrated_bytes >= 0),
                deferred_bytes INTEGER NOT NULL
                    CHECK (deferred_bytes >= 0),
                uncertain_source_count INTEGER NOT NULL
                    CHECK (uncertain_source_count >= 0),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) STRICT;
            CREATE TABLE staged_coverage_control (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                preset TEXT NOT NULL CHECK (
                    preset IN ('recent_30d', 'recent_90d', 'complete')
                ),
                captured_at TEXT NOT NULL,
                cutoff_at TEXT,
                coverage_revision TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) STRICT;
            UPDATE source_registry
            SET hydrated_generation = (
                SELECT active_generation
                FROM cutover_control
                WHERE singleton = 1
            )
            WHERE hydration_state = 'hydrated'
                AND (
                    SELECT active_generation
                    FROM cutover_control
                    WHERE singleton = 1
                ) IS NOT NULL;
            PRAGMA user_version = {OPERATIONAL_SCHEMA_VERSION};
            COMMIT;
            """
        )


def _control_from_row(row: sqlite3.Row) -> CutoverControl:
    return CutoverControl(
        state=CutoverState(row["state"]),
        active_kernel_path=_path(row["active_kernel_location"]),
        active_schema=row["active_schema"],
        active_generation=row["active_generation"],
        integrity_digest=row["integrity_digest"],
        staging_integrity_digest=row["staging_integrity_digest"],
        staging_kernel_path=_path(row["staging_kernel_location"]),
        refresh_run_id=row["refresh_run_id"],
        rollback_kernel_path=_path(row["rollback_kernel_location"]),
        rollback_generation=row["rollback_generation"],
        rollback_integrity_digest=row["rollback_integrity_digest"],
        legacy_cache_path=_path(row["legacy_cache_location"]),
        failure_code=row["failure_code"],
        updated_at=row["updated_at"],
    )


def _path(value: str | None) -> Path | None:
    return Path(value) if value else None


def _string_path(value: Path | None) -> str | None:
    return str(value.resolve()) if value else None


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _validate_artifact(
    path: Path,
    *,
    digest: str,
    generation: int | None = None,
) -> None:
    observed = (
        analytical_generation_digest(path, generation)
        if digest.startswith("generation-sha256:") and generation is not None
        else analytical_digest(path)
    )
    if observed != digest:
        raise ValueError("analytical artifact digest does not match")
    if generation is not None and not analytical_generation_exists(path, generation):
        raise ValueError("analytical artifact does not contain generation")


def _require_database_file(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"database path is not a regular file: {path.name}")
