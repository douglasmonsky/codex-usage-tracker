"""Versioned detector-fact and manifest contracts owned by the usage store."""

from __future__ import annotations

import hashlib
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

COMPRESSION_FACTS_VERSION = 2
MIN_TOOL_OUTPUT_TOKENS = 4_096
MIN_TOOL_OUTPUT_BYTES = (MIN_TOOL_OUTPUT_TOKENS * 4) - 3
SHELL_ROOTS = frozenset({"git", "nl", "rg", "sed"})
VALIDATION_ROOTS = frozenset(
    {"mypy", "npm", "npx", "pytest", "pyright", "ruff", "test", "unittest"}
)
RELEVANT_COMMAND_ROOTS = SHELL_ROOTS | VALIDATION_ROOTS
_HASH_MODULUS = 1 << 256


@dataclass(slots=True)
class ManifestAccumulator:
    """Combine evidence identities without retaining their object graph."""

    count: int = 0
    total: int = 0
    xor: int = 0

    def add(self, kind: str, identity: Any) -> None:
        encoded = "\x1f".join(repr(part) for part in (kind, identity)).encode("utf-8")
        value = (zlib.crc32(encoded) << 32) | zlib.adler32(encoded)
        self.count += 1
        self.total = (self.total + value) % _HASH_MODULUS
        self.xor ^= value

    def merge(self, other: ManifestAccumulator) -> None:
        self.count += other.count
        self.total = (self.total + other.total) % _HASH_MODULUS
        self.xor ^= other.xor

    def storage_values(self) -> tuple[int, str, str]:
        return self.count, f"{self.total:064x}", f"{self.xor:064x}"

    @classmethod
    def from_storage(
        cls,
        count: int,
        total_hex: str,
        xor_hex: str,
    ) -> ManifestAccumulator:
        return cls(
            count=int(count),
            total=int(total_hex or "0", 16),
            xor=int(xor_hex or "0", 16),
        )

    def revision(self) -> str:
        encoded = f"{self.count}:{self.total:064x}:{self.xor:064x}".encode()
        return hashlib.sha256(encoded).hexdigest()[:24]


def call_revision_identity(row: Sequence[Any]) -> tuple[object, ...]:
    return (
        str(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        optional_text(row[4]),
        optional_text(row[5]),
        bool(row[6]),
        int(row[9] or 0),
        int(row[10] or 0),
        int(row[11] or 0),
        int(row[12] or 0),
        float(row[13] or 0),
        float(row[14] or 0),
    )


def tool_revision_identity(row: Sequence[Any]) -> tuple[object, ...]:
    return (
        str(row[0]),
        str(row[1]),
        optional_text(row[2]),
        str(row[3]),
        optional_text(row[4]),
        optional_int(row[5]),
        int(row[6] or 0),
    )


def command_revision_identity(row: Sequence[Any]) -> tuple[object, ...]:
    return (
        str(row[0]),
        str(row[1]),
        optional_text(row[2]),
        str(row[3]),
        str(row[4] or ""),
        optional_int(row[5]),
        optional_text(row[6]),
        int(row[7] or 0),
        optional_text(row[8]),
    )


def file_revision_identity(row: Sequence[Any]) -> tuple[object, ...]:
    return (
        str(row[0]),
        str(row[1]),
        optional_text(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5] or ""),
    )


def fragment_revision_identity(row: Sequence[Any]) -> tuple[object, ...]:
    return (
        str(row[0]),
        str(row[1]),
        optional_text(row[2]),
        str(row[3]),
        optional_text(row[4]),
        str(row[5] or ""),
        str(row[6]),
        int(row[7] or 0),
        bool(row[8]),
    )


def optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    return value if isinstance(value, int) else int(str(value))
