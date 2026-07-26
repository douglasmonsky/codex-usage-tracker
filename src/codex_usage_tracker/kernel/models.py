"""Small value objects shared by the kernel database owners."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CutoverState(str, Enum):
    """Lifecycle states for the side-by-side kernel cache."""

    ABSENT = "absent"
    BUILDING = "building"
    READY = "ready"
    ACTIVE = "active"
    FAILED = "failed"


@dataclass(frozen=True)
class KernelPaths:
    """Versioned analytical and operational database paths."""

    analytical: Path
    operational: Path


@dataclass(frozen=True)
class CutoverControl:
    """One atomically committed cache-activation record."""

    state: CutoverState
    active_kernel_path: Path | None = None
    active_schema: int | None = None
    active_generation: int | None = None
    integrity_digest: str | None = None
    staging_integrity_digest: str | None = None
    staging_kernel_path: Path | None = None
    refresh_run_id: str | None = None
    rollback_kernel_path: Path | None = None
    rollback_generation: int | None = None
    rollback_integrity_digest: str | None = None
    legacy_cache_path: Path | None = None
    failure_code: str | None = None
    updated_at: str | None = None
