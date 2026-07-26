"""Stable privacy-safe identities for rebuildable kernel facts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | Mapping[str, "JsonValue"]

_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._()@+-]{0,63}\Z")
_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:[\\/]")


def stable_id(namespace: str, *parts: str | int) -> str:
    """Return a namespaced ID independent of row order and SQLite state."""

    if not re.fullmatch(r"[a-z][a-z0-9_]{1,15}", namespace):
        raise ValueError("identity namespace must be short lowercase ASCII")
    digest = hashlib.blake2b(digest_size=16, person=b"codex-kernel-v1")
    digest.update(namespace.encode("ascii"))
    for part in parts:
        encoded = str(part).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return f"{namespace}_{digest.hexdigest()}"


def source_id(
    *,
    source_kind: str,
    device_identity: str,
    file_identity: str,
) -> str:
    """Build a stable opaque source ID without using a source path."""

    return stable_id("src", source_kind, device_identity, file_identity)


def event_id(source: str, *, byte_offset: int, event_kind: str) -> str:
    """Build one stable physical source-event identity."""

    if byte_offset < 0:
        raise ValueError("byte_offset must be non-negative")
    return stable_id("evt", source, byte_offset, event_kind)


def canonical_fingerprint(values: Mapping[str, JsonValue]) -> str:
    """Hash canonical semantic inputs for deduplication across sources."""

    payload = json.dumps(
        values,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    digest = hashlib.sha256(b"codex-kernel-canonical-v1\0" + payload).hexdigest()
    return f"fp_{digest}"


def safe_label(candidate: str) -> str:
    """Validate one bounded display label that cannot contain a path."""

    if (
        not candidate
        or "/" in candidate
        or "\\" in candidate
        or ".." in candidate
        or "\x00" in candidate
        or _WINDOWS_DRIVE.search(candidate)
        or not _LABEL.fullmatch(candidate)
    ):
        raise ValueError("label must be bounded privacy-safe display text")
    return candidate
