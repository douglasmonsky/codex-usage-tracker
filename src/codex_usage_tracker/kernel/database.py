"""Connection and lifecycle owner for the analytical kernel database."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .schema import (
    ANALYTICAL_TABLES,
    APPLICATION_ID,
    REQUIRED_SCHEMA_OBJECTS,
    SCHEMA_VERSION,
    create_schema,
)


def initialize_analytical_database(
    path: Path,
    *,
    replace: bool = False,
) -> Path:
    """Create and atomically install a fresh current-schema cache."""

    target = path.resolve()
    if target.exists() and not replace:
        _require_database_file(target)
        _owner_only(target)
        failures = validate_analytical_database(target)
        if failures:
            raise ValueError("; ".join(failures))
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.building-{uuid.uuid4().hex}")
    try:
        connection = sqlite3.connect(staging)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = DELETE")
            create_schema(connection)
            connection.commit()
        finally:
            connection.close()
        _owner_only(staging)
        failures = validate_analytical_database(staging)
        if failures:
            raise ValueError("; ".join(failures))
        os.replace(staging, target)
        _owner_only(target)
        return target
    finally:
        staging.unlink(missing_ok=True)


@contextmanager
def open_writer(
    path: Path,
    *,
    require_capabilities: bool = True,
    staging_bulk: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Open one short-lived WAL writer with integrity pragmas enabled."""

    target = path.resolve()
    _require_database_file(target)
    _owner_only(target)
    connection = sqlite3.connect(target, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        _validate_connection_schema(
            connection,
            require_capabilities=require_capabilities,
        )
        connection.execute("PRAGMA busy_timeout = 5000")
        if staging_bulk:
            connection.execute("PRAGMA journal_mode = OFF")
            connection.execute("PRAGMA synchronous = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA cache_size = -262144")
            connection.execute("PRAGMA locking_mode = EXCLUSIVE")
        else:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
        yield connection
    finally:
        connection.close()


@contextmanager
def open_read_snapshot(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a read-only query snapshot that can never initiate a build."""

    target = path.resolve()
    _require_database_file(target)
    _owner_only(target)
    uri = target.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA query_only = ON")
        _validate_connection_schema(connection)
        connection.execute("BEGIN")
        yield connection
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


@contextmanager
def short_writer_transaction(
    path: Path,
    *,
    require_capabilities: bool = True,
    staging_bulk: bool = False,
    on_transaction_ms: Callable[[float], None] | None = None,
) -> Iterator[sqlite3.Connection]:
    """Hold one explicit writer transaction only for the caller's small batch."""

    with open_writer(
        path,
        require_capabilities=require_capabilities,
        staging_bulk=staging_bulk,
    ) as connection:
        connection.execute("BEGIN IMMEDIATE")
        started = time.perf_counter()
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            if on_transaction_ms is not None:
                on_transaction_ms((time.perf_counter() - started) * 1000)


def validate_analytical_database(path: Path) -> list[str]:
    """Return deterministic schema and integrity failures."""

    if not path.is_file():
        return [f"analytical database does not exist: {path.name}"]
    failures: list[str] = []
    try:
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                failures.append(
                    f"analytical schema version is not {SCHEMA_VERSION}"
                )
            if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                failures.append("analytical application ID is invalid")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema WHERE type = 'table'"
                )
            }
            if tables != ANALYTICAL_TABLES:
                failures.append(
                    "analytical table set differs from schema v1: "
                    f"{sorted(tables)}"
                )
            objects = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema "
                    "WHERE type IN ('index', 'view')"
                )
            }
            missing_objects = REQUIRED_SCHEMA_OBJECTS - objects
            if missing_objects:
                failures.append(
                    "analytical schema capabilities are missing: "
                    f"{sorted(missing_objects)}"
                )
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            if integrity != "ok":
                failures.append(f"analytical quick_check failed: {integrity}")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                failures.append("analytical foreign-key check failed")
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        failures.append(f"analytical database is unreadable: {exc}")
    return failures


def analytical_digest(path: Path) -> str:
    """Return the digest used to bind a validated cutover artifact."""

    target = path.resolve()
    failures = validate_analytical_database(target)
    if failures:
        raise ValueError("; ".join(failures))
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def analytical_generation_digest(path: Path, generation: int) -> str:
    """Bind a published generation using bounded schema and generation metadata."""

    with open_read_snapshot(path) as connection:
        row = connection.execute(
            "SELECT * FROM generations WHERE generation = ? "
            "AND integrity_status = 'valid'",
            (generation,),
        ).fetchone()
        if row is None:
            raise ValueError("analytical artifact does not contain valid generation")
        payload = {
            "application_id": APPLICATION_ID,
            "schema_version": SCHEMA_VERSION,
            "generation": dict(row),
        }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "generation-sha256:" + hashlib.sha256(encoded).hexdigest()


def analytical_generation_exists(path: Path, generation: int) -> bool:
    """Return whether a validated artifact contains the requested generation."""

    if generation < 0:
        return False
    with open_read_snapshot(path) as connection:
        row = connection.execute(
            "SELECT 1 FROM generations WHERE generation = ?",
            (generation,),
        ).fetchone()
    return row is not None


def _validate_connection_schema(
    connection: sqlite3.Connection,
    *,
    require_capabilities: bool = True,
) -> None:
    """Run bounded header/catalog checks before exposing a normal connection."""

    version = connection.execute("PRAGMA user_version").fetchone()[0]
    application_id = connection.execute("PRAGMA application_id").fetchone()[0]
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table'"
        )
    }
    objects = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type IN ('index', 'view')"
        )
    }
    if (
        version != SCHEMA_VERSION
        or application_id != APPLICATION_ID
        or tables != ANALYTICAL_TABLES
        or (
            require_capabilities
            and not objects >= REQUIRED_SCHEMA_OBJECTS
        )
    ):
        raise ValueError("analytical database schema identity is invalid")


def analytical_schema_version(path: Path) -> int | None:
    """Read only the bounded SQLite schema header for upgrade routing."""

    target = path.resolve()
    if not target.is_file():
        return None
    try:
        with sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True) as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.DatabaseError as exc:
        raise ValueError("analytical database schema header is unreadable") from exc


def _require_database_file(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"database path is not a regular file: {path.name}")


def _owner_only(path: Path) -> None:
    path.chmod(0o600)
