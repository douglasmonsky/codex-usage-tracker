"""Explicit local paths supplied by interface composition roots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApplicationPaths:
    """All local filesystem dependencies needed by core application services."""

    codex_home: Path
    db_path: Path
    pricing_path: Path
    allowance_path: Path
    rate_card_path: Path
    thresholds_path: Path
    projects_path: Path
