"""SQLite-backed canonical identity registry."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Any

from ..domain.identity import (
    IdentityCollisionError,
    IdentityContractError,
    canonical_cbor,
    semantic_id,
)

IDENTITY_VERSION = "v1"


class IdentityRegistryError(RuntimeError):
    """The identity registry could not persist or retrieve a validated row."""


@dataclass(frozen=True)
class IdentityRecord:
    """One persisted identity-registry row."""

    logical_id: str
    entity_kind: str
    identity_version: str
    identity_cbor: bytes
    identity_sha256: str
    first_seen_publication_id: str
    last_seen_publication_id: str


def _record(row: Any) -> IdentityRecord:
    return IdentityRecord(
        logical_id=str(row[0]),
        entity_kind=str(row[1]),
        identity_version=str(row[2]),
        identity_cbor=bytes(row[3]),
        identity_sha256=str(row[4]),
        first_seen_publication_id=str(row[5]),
        last_seen_publication_id=str(row[6]),
    )


class IdentityRegistry:
    """Persist and collision-check semantic identities in an analytical DB."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, logical_id: str) -> IdentityRecord | None:
        """Return a registered identity without changing transaction state."""

        row = self._connection.execute(
            """
            SELECT
              logical_id,
              entity_kind,
              identity_version,
              identity_cbor,
              identity_sha256,
              first_seen_publication_id,
              last_seen_publication_id
            FROM identity_registry
            WHERE logical_id = ?
            """,
            (logical_id,),
        ).fetchone()
        return None if row is None else _record(row)

    def register(
        self,
        logical_id: str,
        entity_kind: str,
        identity_tuple: Any,
        publication_id: str,
    ) -> IdentityRecord:
        """Register one identity without committing the caller-owned transaction."""

        identity_cbor = canonical_cbor(identity_tuple)
        identity_sha256 = hashlib.sha256(identity_cbor).hexdigest()
        existing = self.get(logical_id)
        if existing is not None:
            if (
                existing.entity_kind != entity_kind
                or existing.identity_version != IDENTITY_VERSION
                or existing.identity_cbor != identity_cbor
                or existing.identity_sha256 != identity_sha256
            ):
                raise IdentityCollisionError(logical_id)
            self._connection.execute(
                """
                UPDATE identity_registry
                SET last_seen_publication_id = ?
                WHERE logical_id = ?
                """,
                (publication_id, logical_id),
            )
            updated = self.get(logical_id)
            if updated is None:
                raise IdentityRegistryError(
                    f"updated identity disappeared from registry: {logical_id}"
                )
            return updated

        if logical_id != semantic_id(entity_kind, identity_tuple):
            raise IdentityContractError(
                f"logical ID does not match canonical identity: {logical_id}"
            )

        digest_row = self._connection.execute(
            """
            SELECT logical_id, identity_cbor
            FROM identity_registry
            WHERE entity_kind = ?
              AND identity_version = ?
              AND identity_sha256 = ?
            """,
            (entity_kind, IDENTITY_VERSION, identity_sha256),
        ).fetchone()
        if digest_row is not None:
            raise IdentityCollisionError(logical_id)

        self._connection.execute(
            """
            INSERT INTO identity_registry (
              logical_id,
              entity_kind,
              identity_version,
              identity_cbor,
              identity_sha256,
              first_seen_publication_id,
              last_seen_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                logical_id,
                entity_kind,
                IDENTITY_VERSION,
                identity_cbor,
                identity_sha256,
                publication_id,
                publication_id,
            ),
        )
        registered = self.get(logical_id)
        if registered is None:
            raise IdentityRegistryError(
                f"inserted identity disappeared from registry: {logical_id}"
            )
        return registered

    def register_semantic(
        self,
        entity_kind: str,
        identity_tuple: Any,
        publication_id: str,
    ) -> IdentityRecord:
        """Derive and persist a semantic logical ID in one operation."""

        logical_id = semantic_id(entity_kind, identity_tuple)
        return self.register(
            logical_id,
            entity_kind,
            identity_tuple,
            publication_id,
        )
