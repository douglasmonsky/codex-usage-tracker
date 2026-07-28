from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

_KIND = re.compile(r"^[a-z][a-z0-9-]*$")


class IdentityContractError(ValueError):
    """Base identity-vector failure."""


class IdentityCollisionError(IdentityContractError):
    """Raised when one digest is presented with two normalized tuples."""

    def __init__(self, logical_id: str) -> None:
        self.logical_id = logical_id
        super().__init__(f"identity collision for {logical_id}")


def _head(major: int, value: int) -> bytes:
    if value < 0:
        raise IdentityContractError("canonical CBOR length must be nonnegative")
    initial = major << 5
    if value < 24:
        return bytes((initial | value,))
    if value <= 0xFF:
        return bytes((initial | 24, value))
    if value <= 0xFFFF:
        return bytes((initial | 25,)) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes((initial | 26,)) + value.to_bytes(4, "big")
    if value <= 0xFFFFFFFFFFFFFFFF:
        return bytes((initial | 27,)) + value.to_bytes(8, "big")
    raise IdentityContractError("canonical CBOR integer exceeds 64-bit encoding")


def canonical_cbor(value: Any) -> bytes:
    """Encode the restricted identity vocabulary with canonical CBOR ordering."""

    if value is None:
        return b"\xf6"
    if value is False:
        return b"\xf4"
    if value is True:
        return b"\xf5"
    if isinstance(value, int):
        return _head(0, value) if value >= 0 else _head(1, -1 - value)
    if isinstance(value, bytes):
        return _head(2, len(value)) + value
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return _head(3, len(encoded)) + encoded
    if isinstance(value, (list, tuple)):
        encoded_items = b"".join(canonical_cbor(item) for item in value)
        return _head(4, len(value)) + encoded_items
    if isinstance(value, dict):
        pairs = [
            (canonical_cbor(key), canonical_cbor(item))
            for key, item in value.items()
        ]
        pairs.sort(key=lambda pair: (len(pair[0]), pair[0]))
        return _head(5, len(pairs)) + b"".join(
            key + item for key, item in pairs
        )
    raise IdentityContractError(
        f"unsupported canonical CBOR identity type: {type(value).__name__}"
    )


def semantic_id(kind: str, identity_tuple: Any) -> str:
    """Return the v1 logical ID for a normalized structural identity tuple."""

    if _KIND.fullmatch(kind) is None:
        raise IdentityContractError(f"invalid identity kind: {kind}")
    digest = hashlib.sha256(canonical_cbor(identity_tuple)).digest()
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return f"{kind}:v1:{encoded}"


@dataclass
class RegisteredEntity:
    identity_bytes: bytes
    occurrences: list[dict[str, Any]] = field(default_factory=list)


class IdentityRegistry:
    """Tiny collision-checking canonicalization oracle."""

    def __init__(self) -> None:
        self.entities: dict[str, RegisteredEntity] = {}

    def register(
        self,
        logical_id: str,
        identity_tuple: Any,
        *,
        occurrence: dict[str, Any] | None = None,
    ) -> None:
        normalized = canonical_cbor(identity_tuple)
        entity = self.entities.get(logical_id)
        if entity is None:
            entity = RegisteredEntity(identity_bytes=normalized)
            self.entities[logical_id] = entity
        elif entity.identity_bytes != normalized:
            raise IdentityCollisionError(logical_id)
        if occurrence is not None and occurrence not in entity.occurrences:
            entity.occurrences.append(occurrence)
