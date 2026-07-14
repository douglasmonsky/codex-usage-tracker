"""Stable browser-cache identity for dashboard boot payloads."""

from __future__ import annotations

import hashlib
from pathlib import Path


def dashboard_payload_cache_key(
    *,
    db_path: Path,
    api_token: str | None,
    privacy_mode: str,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
    projects_path: Path,
) -> str:
    """Hash every source and configuration input shared by browser caches."""

    source = "|".join(
        [
            str(db_path),
            api_token or "static",
            privacy_mode,
            _file_revision(pricing_path),
            _file_revision(allowance_path),
            _file_revision(rate_card_path),
            _file_revision(thresholds_path),
            _file_revision(projects_path),
            "dashboard-payload-v3",
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def _file_revision(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"
