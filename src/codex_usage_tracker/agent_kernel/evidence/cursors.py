"""Versioned HMAC-bound keyset cursors.

The cursor contains only canonical ordering and binding metadata.  It never
contains an offset, SQL fragment, expected result, or grading data.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any

Clock = Callable[[], int]
_CURSOR_VERSION = 1
_SCHEMA = "codex-usage-tracker.keyset-cursor.v1"
_ALLOWED_KINDS = frozenset({"query", "evidence"})


class CursorError(ValueError):
    """A cursor is malformed or cannot be used for this request."""


class CursorTamperedError(CursorError):
    """The cursor signature or canonical payload is invalid."""


class CursorExpiredError(CursorError):
    """The cursor is outside its bounded validity interval."""


class CursorMismatchError(CursorError):
    """The cursor belongs to another request, plan, view, or publication."""


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CursorError("cursor order contains a non-finite decimal")
        rendered = format(value.normalize(), "f")
        return "0" if rendered == "-0" else rendered
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CursorError("cursor mappings require string keys")
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical(item) for item in value]
    raise CursorError(f"cursor contains unsupported value: {type(value).__name__}")


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _canonical(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _encode_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_part(value: str) -> bytes:
    if not value or any(character.isspace() for character in value):
        raise CursorTamperedError("cursor encoding is malformed")
    try:
        return base64.b64decode(
            value + ("=" * (-len(value) % 4)),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, binascii.Error) as error:
        raise CursorTamperedError("cursor encoding is malformed") from error


@dataclass(frozen=True, slots=True)
class CursorBinding:
    """All identities that make a keyset position meaningful."""

    kind: str
    plan_id: str
    plan_version: int
    publication_id: str
    request_digest: str
    order: tuple[Any, ...]
    issued_at_us: int
    expires_at_us: int
    view: str | None = None
    direction: str = "forward"
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if self.kind not in _ALLOWED_KINDS:
            raise CursorError(f"unsupported cursor kind: {self.kind!r}")
        for label, value in (
            ("plan_id", self.plan_id),
            ("publication_id", self.publication_id),
            ("request_digest", self.request_digest),
            ("direction", self.direction),
        ):
            if not isinstance(value, str) or not value:
                raise CursorError(f"{label} must be a non-empty string")
        if isinstance(self.plan_version, bool) or self.plan_version < 1:
            raise CursorError("plan_version must be a positive integer")
        if not isinstance(self.order, tuple) or not self.order:
            raise CursorError("cursor order must be a non-empty tuple")
        _canonical(self.order)
        if (
            isinstance(self.issued_at_us, bool)
            or isinstance(self.expires_at_us, bool)
            or self.issued_at_us < 0
            or self.expires_at_us <= self.issued_at_us
        ):
            raise CursorError("cursor validity interval is invalid")
        if self.kind == "evidence" and (not isinstance(self.view, str) or not self.view):
            raise CursorError("evidence cursors require a view")
        if self.kind == "query" and self.view is not None:
            raise CursorError("query cursors cannot carry an evidence view")
        if not isinstance(self.metadata, Mapping):
            raise CursorError("cursor metadata must be a mapping")
        frozen_metadata = MappingProxyType(dict(_canonical(self.metadata)))
        object.__setattr__(self, "metadata", frozen_metadata)

    def payload(self) -> dict[str, Any]:
        return {
            "schema": _SCHEMA,
            "version": _CURSOR_VERSION,
            "kind": self.kind,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "publication_id": self.publication_id,
            "request_digest": self.request_digest,
            "order": list(self.order),
            "issued_at_us": self.issued_at_us,
            "expires_at_us": self.expires_at_us,
            "view": self.view,
            "direction": self.direction,
            "metadata": dict(self.metadata),
        }


class CursorCodec:
    """Serialize and verify opaque cursor positions with HMAC-SHA256."""

    def __init__(self, secret: bytes, *, clock: Clock) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise CursorError("cursor secret must contain at least 32 bytes")
        if not callable(clock):
            raise CursorError("cursor clock must be callable")
        self._secret = secret
        self._clock = clock

    def encode(self, binding: CursorBinding) -> str:
        payload = _canonical_bytes(binding.payload())
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return f"v{_CURSOR_VERSION}.{_encode_part(payload)}.{_encode_part(signature)}"

    def decode(
        self,
        token: str,
        *,
        expected_kind: str,
        expected_plan_id: str,
        expected_plan_version: int,
        expected_publication_id: str,
        expected_request_digest: str,
        expected_view: str | None = None,
        expected_direction: str = "forward",
    ) -> CursorBinding:
        if not isinstance(token, str):
            raise CursorTamperedError("cursor must be text")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != f"v{_CURSOR_VERSION}":
            raise CursorTamperedError("cursor version or framing is invalid")
        payload = _decode_part(parts[1])
        signature = _decode_part(parts[2])
        expected_signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise CursorTamperedError("cursor signature is invalid")
        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CursorTamperedError("cursor payload is invalid JSON") from error
        if not isinstance(decoded, dict) or _canonical_bytes(decoded) != payload:
            raise CursorTamperedError("cursor payload is not canonical")
        if decoded.get("schema") != _SCHEMA or decoded.get("version") != _CURSOR_VERSION:
            raise CursorTamperedError("cursor payload version is invalid")
        expected_keys = {
            "schema",
            "version",
            "kind",
            "plan_id",
            "plan_version",
            "publication_id",
            "request_digest",
            "order",
            "issued_at_us",
            "expires_at_us",
            "view",
            "direction",
            "metadata",
        }
        if set(decoded) != expected_keys:
            raise CursorTamperedError("cursor payload fields are invalid")
        try:
            binding = CursorBinding(
                kind=decoded["kind"],
                plan_id=decoded["plan_id"],
                plan_version=decoded["plan_version"],
                publication_id=decoded["publication_id"],
                request_digest=decoded["request_digest"],
                order=tuple(decoded["order"]),
                issued_at_us=decoded["issued_at_us"],
                expires_at_us=decoded["expires_at_us"],
                view=decoded["view"],
                direction=decoded["direction"],
                metadata=decoded["metadata"],
            )
        except (KeyError, TypeError, CursorError) as error:
            raise CursorTamperedError("cursor payload values are invalid") from error
        if self._clock() > binding.expires_at_us:
            raise CursorExpiredError("cursor expired; restart from the first page")
        actual = (
            binding.kind,
            binding.plan_id,
            binding.plan_version,
            binding.publication_id,
            binding.request_digest,
            binding.view,
            binding.direction,
        )
        expected = (
            expected_kind,
            expected_plan_id,
            expected_plan_version,
            expected_publication_id,
            expected_request_digest,
            expected_view,
            expected_direction,
        )
        if actual != expected:
            raise CursorMismatchError(
                "cursor belongs to another request or publication; restart from the first page"
            )
        return binding
