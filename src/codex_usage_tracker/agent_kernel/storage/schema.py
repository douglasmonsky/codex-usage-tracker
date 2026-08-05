"""Exact database-v1 schema resources and verification helpers.

The SQL lives beside this module so the production package, rather than an
experiment or a prose document, is the executable schema authority.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files

SCHEMA_CONTRACT_ID = "codex-usage-tracker.agent-kernel.schema-contract.v1"
SCHEMA_CONTRACT_SHA256 = "998343ba4b52bb39decfcb436f8a862d41884fc6f6a6b4e88f7e8f8e42446295"
SCHEMA_VERSION = "1"
ANALYTICAL_DATABASE_IDENTITY = "codex-usage-tracker.agent-kernel.v1"
OPERATIONAL_DATABASE_IDENTITY = "codex-usage-tracker.agent-kernel.operations.v1"


@dataclass(frozen=True)
class SchemaObject:
    """One explicit SQLite object, retained in creation order."""

    object_type: str
    name: str
    table_name: str
    sql: str


def _resource_text(name: str) -> str:
    return (
        files("codex_usage_tracker.agent_kernel.storage").joinpath(name).read_text(encoding="utf-8")
    )


def _normalize_ddl(ddl: str) -> str:
    lines = ddl.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip(" \t") for line in lines]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


ANALYTICAL_DDL = _normalize_ddl(_resource_text("analytical.sql"))
OPERATIONAL_DDL = _normalize_ddl(_resource_text("operational.sql"))


def canonical_schema_digest() -> str:
    """Return the schema-contract digest over both normalized DDL resources."""

    payload = (
        f"{SCHEMA_CONTRACT_ID}\nanalytical\n{ANALYTICAL_DDL}operational\n{OPERATIONAL_DDL}"
    ).encode()
    return sha256(payload).hexdigest()


def schema_ddl(kind: str) -> str:
    """Return the normalized DDL for an analytical or operational database."""

    if kind == "analytical":
        return ANALYTICAL_DDL
    if kind == "operational":
        return OPERATIONAL_DDL
    raise ValueError(f"unknown database kind: {kind!r}")


def schema_objects(kind: str) -> tuple[SchemaObject, ...]:
    """Return the exact user-defined object inventory in DDL creation order."""

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(schema_ddl(kind))
        rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
        ).fetchall()
        return tuple(SchemaObject(*row) for row in rows)
    finally:
        connection.close()


ANALYTICAL_INVENTORY = schema_objects("analytical")
OPERATIONAL_INVENTORY = schema_objects("operational")


def expected_inventory(kind: str) -> tuple[SchemaObject, ...]:
    if kind == "analytical":
        return ANALYTICAL_INVENTORY
    if kind == "operational":
        return OPERATIONAL_INVENTORY
    raise ValueError(f"unknown database kind: {kind!r}")
