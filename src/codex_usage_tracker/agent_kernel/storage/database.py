"""SQLite connection modes and validation for the isolated database-v1 pair."""

from __future__ import annotations

import os
import sqlite3
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .schema import (
    ANALYTICAL_DATABASE_IDENTITY,
    OPERATIONAL_DATABASE_IDENTITY,
    SCHEMA_CONTRACT_ID,
    SCHEMA_CONTRACT_SHA256,
    SCHEMA_VERSION,
    canonical_schema_digest,
    expected_inventory,
    schema_ddl,
)

Clock = Callable[[], int]


class DatabaseContractError(RuntimeError):
    """A database does not meet the agent-kernel storage contract."""


class DatabaseIdentityError(DatabaseContractError):
    """A legacy, foreign, or wrong-sidecar database was supplied."""


class DatabaseValidationError(DatabaseContractError):
    """SQLite or schema validation found a contract violation."""


def _verify_owner_only_file(path: Path) -> None:
    if path.is_symlink():
        raise DatabaseContractError(f"database path must not be a symlink: {path}")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise DatabaseContractError(f"database path must be a regular file: {path}")
    if info.st_uid != os.getuid():
        raise DatabaseContractError(f"database is not owned by this user: {path}")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise DatabaseContractError(f"database permissions must be 0600: {path}")


def _verify_owner_only_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.exists() or sidecar.is_symlink():
            _verify_owner_only_file(sidecar)


@dataclass(frozen=True)
class DatabaseValidation:
    quick_check: str
    integrity_check: str | None
    foreign_key_violations: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DatabaseSize:
    """Exact on-disk SQLite byte baseline at one observation."""

    database_bytes: int
    wal_bytes: int
    shm_bytes: int
    page_size: int
    page_count: int


def measure_database_size(path: Path, connection: sqlite3.Connection) -> DatabaseSize:
    """Measure compact SQLite files without reading source content."""

    path = Path(path)
    wal_path = Path(f"{path}-wal")
    shm_path = Path(f"{path}-shm")
    return DatabaseSize(
        database_bytes=path.stat().st_size,
        wal_bytes=wal_path.stat().st_size if wal_path.exists() else 0,
        shm_bytes=shm_path.stat().st_size if shm_path.exists() else 0,
        page_size=int(connection.execute("PRAGMA page_size").fetchone()[0]),
        page_count=int(connection.execute("PRAGMA page_count").fetchone()[0]),
    )


def utc_microseconds() -> int:
    """Default deterministic seam for callers that need to replace wall time."""

    return time.time_ns() // 1_000


def _identity_for(kind: str) -> str:
    if kind == "analytical":
        return ANALYTICAL_DATABASE_IDENTITY
    if kind == "operational":
        return OPERATIONAL_DATABASE_IDENTITY
    raise ValueError(f"unknown database kind: {kind!r}")


def _configure(connection: sqlite3.Connection, *, builder: bool = False) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA cache_size = -20000")
    connection.execute("PRAGMA mmap_size = 0")
    connection.execute("PRAGMA temp_store = MEMORY")
    if builder:
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
    else:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA wal_autocheckpoint = 1000")


def _connect(
    path: Path, *, read_only: bool = False, must_exist: bool = False
) -> sqlite3.Connection:
    if read_only or must_exist:
        mode = "ro" if read_only else "rw"
        uri = f"file:{quote(str(path.resolve()))}?mode={mode}"
        connection = sqlite3.connect(uri, uri=True)
        if read_only:
            connection.execute("PRAGMA query_only = ON")
    else:
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _metadata(kind: str) -> dict[str, str]:
    return {
        "database_identity": _identity_for(kind),
        "schema_contract_id": SCHEMA_CONTRACT_ID,
        "schema_contract_sha256": SCHEMA_CONTRACT_SHA256,
        "schema_version": SCHEMA_VERSION,
        **(
            {
                "raw_content_stored": "false",
                "time_unit": "utc_microseconds",
                "interval_semantics": "[start,end)",
            }
            if kind == "analytical"
            else {}
        ),
    }


def initialize_database(path: Path, kind: str, *, builder: bool = False) -> sqlite3.Connection:
    """Create a new database exactly once, or validate an existing one."""

    path = Path(path)
    if canonical_schema_digest() != SCHEMA_CONTRACT_SHA256:
        raise DatabaseContractError("packaged DDL digest differs from schema contract")
    if path.exists() and path.stat().st_size:
        _verify_owner_only_file(path)
        _verify_owner_only_sidecars(path)
        connection = _connect(path, must_exist=True)
        try:
            # Reject an old tracker database before a writer PRAGMA can mutate it.
            validate_database(connection, kind)
            _configure(connection, builder=builder)
        except Exception:
            connection.close()
            raise
        return connection
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _verify_owner_only_file(path)
    else:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    connection = _connect(path)
    try:
        connection.execute("PRAGMA page_size = 4096")
        _configure(connection, builder=builder)
        connection.executescript(schema_ddl(kind))
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)"
            if kind == "analytical"
            else "INSERT INTO operational_metadata(key, value) VALUES (?, ?)",
            _metadata(kind).items(),
        )
        connection.commit()
        _verify_owner_only_file(path)
        _verify_owner_only_sidecars(path)
        validate_database(connection, kind)
    except Exception:
        connection.close()
        raise
    return connection


def open_writer(path: Path, kind: str = "analytical") -> sqlite3.Connection:
    """Open an existing contract database with production write settings."""

    path = Path(path)
    _verify_owner_only_file(path)
    _verify_owner_only_sidecars(path)
    connection = _connect(path, must_exist=True)
    try:
        # A foreign database must not receive a WAL-mode write merely because it
        # was supplied to this isolated storage layer.
        validate_database(connection, kind)
        _configure(connection)
        _verify_owner_only_sidecars(path)
    except Exception:
        connection.close()
        raise
    return connection


def open_builder(path: Path, kind: str = "analytical") -> sqlite3.Connection:
    """Open an unpublished owner-only builder with its isolated settings."""

    return initialize_database(Path(path), kind, builder=True)


def open_read_only(path: Path, kind: str = "analytical") -> sqlite3.Connection:
    """Open a validated SQLite URI read-only connection without journal writes."""

    path = Path(path)
    _verify_owner_only_file(path)
    _verify_owner_only_sidecars(path)
    connection = _connect(path, read_only=True)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    validate_database(connection, kind)
    return connection


def initialize_analytical(path: Path) -> sqlite3.Connection:
    return initialize_database(path, "analytical")


def initialize_operational(path: Path) -> sqlite3.Connection:
    return initialize_database(path, "operational")


def validate_database(
    connection: sqlite3.Connection, kind: str, *, integrity: bool = False
) -> DatabaseValidation:
    """Fail closed on old/foreign schemas and SQLite consistency failures."""

    metadata_table = "metadata" if kind == "analytical" else "operational_metadata"
    try:
        actual_metadata = dict(connection.execute(f"SELECT key, value FROM {metadata_table}"))
    except sqlite3.DatabaseError as error:
        raise DatabaseIdentityError(f"not a database-v1 {kind} database") from error
    required_metadata = _metadata(kind)
    mismatches = {
        key: (expected, actual_metadata.get(key))
        for key, expected in required_metadata.items()
        if actual_metadata.get(key) != expected
    }
    if mismatches:
        raise DatabaseIdentityError(f"foreign or legacy {kind} database metadata: {mismatches}")
    actual_objects = tuple(
        (row["type"], row["name"], row["tbl_name"], row["sql"])
        for row in connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
        )
    )
    expected_objects = tuple(
        (item.object_type, item.name, item.table_name, item.sql)
        for item in expected_inventory(kind)
    )
    if actual_objects != expected_objects:
        raise DatabaseValidationError(f"{kind} schema inventory differs from database-v1")
    quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
    if quick_check != "ok":
        raise DatabaseValidationError(f"SQLite quick_check failed: {quick_check}")
    foreign_key_violations = tuple(
        tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
    )
    if foreign_key_violations:
        raise DatabaseValidationError(f"foreign key violations: {foreign_key_violations}")
    integrity_check = None
    if integrity:
        integrity_check = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity_check != "ok":
            raise DatabaseValidationError(f"SQLite integrity_check failed: {integrity_check}")
    return DatabaseValidation(quick_check, integrity_check, foreign_key_violations)
