"""Diagnostic snapshot payload helpers for the dashboard server."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from codex_usage_tracker.diagnostic_snapshots import (
    build_diagnostic_usage_drain_report,
    refresh_diagnostic_snapshots,
)


class SnapshotReport(Protocol):
    payload: dict[str, object]


class SnapshotReportBuilder(Protocol):
    def __call__(
        self,
        *,
        db_path: Path,
        include_archived: bool,
        refresh: bool,
    ) -> SnapshotReport: ...


def refresh_all_diagnostic_snapshots_payload(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived: bool,
    refresh_lock: Any,
) -> dict[str, object]:
    """Refresh every diagnostic snapshot and return the aggregate payload."""
    with refresh_lock:
        return refresh_diagnostic_snapshots(
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            include_archived=include_archived,
        )


def diagnostic_snapshot_payload(
    *,
    db_path: Path,
    include_archived: bool,
    refresh: bool,
    refresh_lock: Any,
    build_report: SnapshotReportBuilder,
) -> dict[str, object]:
    """Read or refresh one persisted diagnostic snapshot payload."""
    if refresh:
        with refresh_lock:
            return build_report(
                db_path=db_path,
                include_archived=include_archived,
                refresh=True,
            ).payload
    return build_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=False,
    ).payload


def usage_drain_snapshot_payload(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived: bool,
    refresh: bool,
    refresh_lock: Any,
) -> dict[str, object]:
    """Read or refresh the usage-drain diagnostic snapshot payload."""
    if refresh:
        with refresh_lock:
            return build_diagnostic_usage_drain_report(
                db_path=db_path,
                pricing_path=pricing_path,
                allowance_path=allowance_path,
                rate_card_path=rate_card_path,
                include_archived=include_archived,
                refresh=True,
            ).payload
    return build_diagnostic_usage_drain_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
        refresh=False,
    ).payload
