"""Owner-only operational state outside the analytical fact database."""

from __future__ import annotations

import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .database import (
    analytical_digest,
    analytical_generation_digest,
    analytical_generation_exists,
)
from .models import (
    CutoverControl,
    CutoverState,
    KernelPaths,
)
from .schema import SCHEMA_VERSION

OPERATIONAL_SCHEMA_VERSION = 2
OPERATIONAL_TABLES = frozenset(
    {"refresh_runs", "source_registry", "cutover_control", "live_events"}
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
    state TEXT NOT NULL CHECK (state IN ('tracked', 'missing', 'retired'))
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
