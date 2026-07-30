"""Pure, versioned semantic identity primitives."""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any

_KIND = re.compile(r"^[a-z][a-z0-9-]*$")


class IdentityContractError(ValueError):
    """An identity value cannot be represented by the versioned contract."""


class IdentityCollisionError(IdentityContractError):
    """One logical ID was presented with two different canonical identities."""

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
    """Encode the restricted CK-02 identity vocabulary as canonical CBOR."""

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
        pairs = [(canonical_cbor(key), canonical_cbor(item)) for key, item in value.items()]
        pairs.sort(key=lambda pair: (len(pair[0]), pair[0]))
        return _head(5, len(pairs)) + b"".join(key + item for key, item in pairs)
    raise IdentityContractError(f"unsupported canonical CBOR identity type: {type(value).__name__}")


def semantic_id(kind: str, identity_tuple: Any) -> str:
    """Return the exact CK-02 v1 logical ID for a structural identity tuple."""

    if _KIND.fullmatch(kind) is None:
        raise IdentityContractError(f"invalid identity kind: {kind}")
    digest = hashlib.sha256(canonical_cbor(identity_tuple)).digest()
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return f"{kind}:v1:{encoded}"
