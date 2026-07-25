"""Status payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
)
from codex_usage_tracker.diagnostics.conversational_readiness import conversational_readiness
from codex_usage_tracker.pricing.allowance_config import load_allowance_config
from codex_usage_tracker.pricing.config import load_pricing_config
from codex_usage_tracker.server.query_cache import current_source_revision
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_bool_query_value,
    safe_int,
)
from codex_usage_tracker.store.home_observed_queries import (
    query_home_latest_observed_usage,
)
from codex_usage_tracker.store.home_queries import (
    query_home_refresh_metadata,
    query_home_status_counts,
    query_home_usage_metrics,
)

ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]


def handle_readiness_request(*, codex_home: Path, send_json: JsonSender) -> None:
    """Return MCP conversational readiness without querying usage data."""
    send_json(HTTPStatus.OK, dict(conversational_readiness(codex_home=codex_home)))


def handle_status_request(
    query: str,
    *,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle status route errors and response writing."""
    try:
        payload = status_payload(
            query,
            codex_home=codex_home,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            include_archived_default=include_archived_default,
        )
    except sqlite3.Error as exc:
        send_exception("Database error while reading status", exc)
        return
    send_json(HTTPStatus.OK, payload)


def status_payload(
    query: str,
    *,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
) -> dict[str, object]:
    """Build the live status API payload."""
    params = parse_qs(query)
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
    status_counts = query_home_status_counts(db_path=db_path)
    counts = _scoped_usage_counts(status_counts, include_archived=include_archived)
    home_counts = _scoped_usage_counts(status_counts, include_archived=False)
    observed_usage = query_home_latest_observed_usage(
        db_path=db_path,
        include_archived=include_archived,
    )
    if include_archived:
        home_observed_usage = query_home_latest_observed_usage(
            db_path=db_path,
            include_archived=False,
        )
    else:
        home_observed_usage = observed_usage
    dedupe = {
        "dedupe_enabled": bool(status_counts.get("dedupe_enabled")),
        "fingerprint_version": str(status_counts.get("fingerprint_version") or ""),
        **{
            key: _safe_count(status_counts.get(key))
            for key in (
                "physical_rows",
                "canonical_rows",
                "excluded_copied_rows",
                "duplicate_fingerprint_groups",
                "physical_total_tokens",
                "canonical_total_tokens",
                "excluded_total_tokens",
            )
        },
        "duplicate_reasons": dict(status_counts.get("duplicate_reasons") or {}),
    }
    metadata = query_home_refresh_metadata(db_path)
    parser_diagnostics = {
        key.removeprefix("parser_"): safe_int(value)
        for key, value in metadata.items()
        if key.startswith("parser_") and safe_int(value)
    }
    return {
        "schema": "codex-usage-tracker-status-v1",
        "payload_schema": "codex-usage-tracker-live-api-v1",
        "latest_refresh_at": metadata.get("latest_refresh_at"),
        "include_archived": include_archived,
        "row_counts": counts,
        "max_event_timestamp": counts.get("max_event_timestamp"),
        "observed_usage": observed_usage,
        "dedupe": dedupe,
        "parser_adapter": metadata.get("parser_adapter"),
        "parser_diagnostics": parser_diagnostics,
        "conversational_analysis": conversational_readiness(codex_home=codex_home),
        "home_summary": home_summary_payload(
            db_path=db_path,
            metadata=metadata,
            dedupe=dedupe,
            latest_event_at=home_counts.get("max_event_timestamp"),
            observed_usage=home_observed_usage,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
        ),
    }


def _scoped_usage_counts(
    counts: Mapping[str, object],
    *,
    include_archived: bool,
) -> dict[str, object]:
    total_rows = _safe_count(counts.get("total_rows"))
    active_rows = _safe_count(counts.get("active_rows"))
    max_event_timestamp = counts.get(
        "total_max_event_timestamp" if include_archived else "active_max_event_timestamp"
    )
    return {
        "total_rows": total_rows,
        "active_rows": active_rows,
        "scoped_rows": total_rows if include_archived else active_rows,
        "max_event_timestamp": max_event_timestamp,
    }


def home_summary_payload(
    *,
    db_path: Path,
    metadata: Mapping[str, object] | None = None,
    dedupe: Mapping[str, object] | None = None,
    latest_event_at: object = None,
    observed_usage: dict[str, object] | None = None,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
) -> dict[str, object]:
    """Build the bounded active-scope summary used by the Evidence Console Home route."""
    resolved_metadata = metadata if metadata is not None else query_home_refresh_metadata(db_path)
    resolved_dedupe = dedupe if dedupe is not None else query_home_status_counts(db_path=db_path)
    if latest_event_at is None:
        latest_event_at = query_home_status_counts(db_path=db_path).get(
            "active_max_event_timestamp"
        )
    resolved_observed_usage = (
        observed_usage
        if observed_usage is not None
        else query_home_latest_observed_usage(
            db_path=db_path,
            include_archived=False,
        )
    )
    return {
        "schema": "codex-usage-tracker-home-summary-v1",
        "source_revision": current_source_revision(db_path),
        "latest_refresh_at": resolved_metadata.get("latest_refresh_at"),
        "latest_event_at": latest_event_at,
        "accounting": {
            "physical_rows": _safe_count(resolved_dedupe.get("physical_rows")),
            "canonical_rows": _safe_count(resolved_dedupe.get("canonical_rows")),
            "excluded_copied_rows": _safe_count(resolved_dedupe.get("excluded_copied_rows")),
        },
        "usage_metrics": query_home_usage_metrics(db_path=db_path),
        "pricing": _home_pricing_summary(pricing_path),
        "allowance": _home_allowance_summary(
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            observed_usage=resolved_observed_usage,
        ),
    }


def _safe_count(value: object) -> int:
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _home_pricing_summary(pricing_path: Path) -> dict[str, object]:
    pricing = load_pricing_config(pricing_path)
    return {
        "configured": pricing.loaded and not pricing.error,
        "model_count": len(pricing.models),
        "estimated_model_count": len(pricing.estimated_models or set()),
        "error": pricing.error,
    }


def _home_allowance_summary(
    *,
    allowance_path: Path,
    rate_card_path: Path,
    observed_usage: dict[str, object],
) -> dict[str, object]:
    allowance = load_allowance_config(
        allowance_path,
        rate_card_path=rate_card_path,
    )
    window_fields = (
        "key",
        "label",
        "total_credits",
        "remaining_credits",
        "remaining_percent",
        "reset_at",
        "captured_at",
    )
    return {
        "configured": allowance.loaded and not allowance.error,
        "error": allowance.error,
        "observed_usage": observed_usage,
        "windows": [
            {field: getattr(window, field, None) for field in window_fields}
            for window in allowance.windows
        ],
    }
