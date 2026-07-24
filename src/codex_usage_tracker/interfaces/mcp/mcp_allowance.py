"""Allowance intelligence MCP implementation tools."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from codex_usage_tracker.allowance_intelligence import (
    build_allowance_diagnostics_report,
    build_allowance_export_report,
    build_allowance_history_report,
)
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_RATE_CARD_PATH,
)
from codex_usage_tracker.server import allowance_v2
from codex_usage_tracker.server.analysis_jobs import AnalysisJobRegistry

_ALLOWANCE_ANALYSIS_JOBS = AnalysisJobRegistry()


def usage_allowance_status(
    include_archived: bool = False,
    privacy_mode: str = "strict",
    since_revision: str | None = None,
) -> dict[str, Any]:
    """Compatibility tool; prefer ``usage_allowance(operation="status")``."""
    payload = allowance_v2.allowance_status_payload(
        _query(include_archived=include_archived, since_revision=since_revision),
        db_path=DEFAULT_DB_PATH,
        privacy_mode=privacy_mode,
        include_archived_default=False,
    )
    data_state = payload.get("data_state")
    if data_state in {"stale", "empty"}:
        payload["next"] = {
            "action": "usage_refresh_start",
            "status_action": "usage_refresh_status",
            "then": "usage_allowance_status",
            "poll_after_ms": 60_000,
        }
    else:
        seconds = int(dict(payload.get("next") or {}).get("poll_after_seconds", 30))
        payload["next"] = {
            "action": "usage_allowance_status",
            "poll_after_ms": seconds * 1_000,
        }
    return payload


def usage_allowance_series(
    range_preset: str = "7d",
    start_at: str | None = None,
    end_at: str | None = None,
    granularity: str = "auto",
    window_kind: str = "weekly",
    cohort_id: str | None = None,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Compatibility tool; prefer ``usage_allowance(operation="series")``."""
    return allowance_v2.allowance_series_payload(
        _query(
            range_preset=range_preset,
            start_at=start_at,
            end_at=end_at,
            granularity=granularity,
            window_kind=window_kind,
            cohort_id=cohort_id,
            include_archived=include_archived,
        ),
        db_path=DEFAULT_DB_PATH,
        include_archived_default=False,
    )


def usage_allowance_evidence(
    limit: int = 50,
    before: str | None = None,
    order: str = "desc",
    window_kind: str | None = None,
    cohort_id: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    include_archived: bool = False,
    privacy_mode: str = "strict",
) -> dict[str, Any]:
    """Compatibility tool; prefer ``usage_allowance(operation="evidence")``."""
    return allowance_v2.allowance_evidence_payload(
        _query(
            limit=limit,
            before=before,
            order=order,
            window_kind=window_kind,
            cohort_id=cohort_id,
            start_at=start_at,
            end_at=end_at,
            include_archived=include_archived,
            privacy_mode=privacy_mode,
        ),
        db_path=DEFAULT_DB_PATH,
        privacy_mode=privacy_mode,
        include_archived_default=False,
    )


def usage_allowance_analysis(
    window_kind: str = "weekly",
    cohort_id: str = "codex",
    forecast_horizon: int = 1,
    include_archived: bool = False,
    min_cycles_per_side: int | None = None,
    permutation_count: int | None = None,
    start_if_missing: bool = True,
) -> dict[str, Any]:
    """Compatibility tool; prefer ``usage_allowance(operation="analysis")``."""
    query = _query(
        window_kind=window_kind,
        cohort_id=cohort_id,
        forecast_horizon=forecast_horizon,
        include_archived=include_archived,
        min_cycles_per_side=min_cycles_per_side,
        permutation_count=permutation_count,
    )
    payload = allowance_v2.allowance_analysis_payload(
        query,
        db_path=DEFAULT_DB_PATH,
        include_archived_default=False,
    )
    if payload.get("status") != "missing" or not start_if_missing:
        return payload
    return allowance_v2.start_allowance_analysis_job(
        query,
        db_path=DEFAULT_DB_PATH,
        registry=_ALLOWANCE_ANALYSIS_JOBS,
        include_archived_default=False,
    )


def usage_allowance_analysis_status(job_id: str) -> dict[str, object]:
    """Poll one in-process allowance analysis job."""
    return allowance_v2.allowance_analysis_job_status(
        job_id,
        registry=_ALLOWANCE_ANALYSIS_JOBS,
    )


def usage_allowance_history(
    window_kind: str | None = None,
    limit: int = 1000,
    include_archived: bool = False,
    privacy_mode: str = "strict",
) -> dict[str, Any]:
    """Return normalized observed allowance history aggregate JSON."""
    return build_allowance_history_report(
        db_path=DEFAULT_DB_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=_report_limit(limit),
        privacy_mode=privacy_mode,
    ).payload


def usage_allowance_diagnostics(
    window_kind: str | None = None,
    limit: int = 10000,
    include_archived: bool = False,
    privacy_mode: str = "strict",
) -> dict[str, Any]:
    """Diagnose allowance movement against local credit estimates."""
    return build_allowance_diagnostics_report(
        db_path=DEFAULT_DB_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=_report_limit(limit),
        privacy_mode=privacy_mode,
    ).payload


def usage_allowance_export(
    window_kind: str | None = None,
    limit: int = 10000,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return strict-privacy allowance evidence bundle for manual sharing."""
    return build_allowance_export_report(
        db_path=DEFAULT_DB_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=_report_limit(limit),
    ).payload


def _report_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit


def _query(**values: object) -> str:
    normalized = {
        key: str(value).lower() if isinstance(value, bool) else value
        for key, value in values.items()
        if value is not None
    }
    return urlencode(normalized)
