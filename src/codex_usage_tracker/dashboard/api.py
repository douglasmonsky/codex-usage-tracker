"""Shared Evidence Console payload construction from aggregate usage rows."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.core.call_origin import ensure_call_origin
from codex_usage_tracker.core.i18n import dashboard_i18n_payload
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.core.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    load_project_config,
    project_privacy_metadata,
    validate_privacy_mode,
)
from codex_usage_tracker.core.threads import annotate_thread_attachments
from codex_usage_tracker.dashboard.cache_identity import dashboard_payload_cache_key
from codex_usage_tracker.dashboard.load_window import dashboard_load_window_payload
from codex_usage_tracker.pricing.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
    summarize_allowance_usage,
)
from codex_usage_tracker.pricing.api import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.reports.recommendations import (
    annotate_rows_with_recommendations,
    load_threshold_config,
)
from codex_usage_tracker.store.api import (
    query_dashboard_event_counts,
    query_dashboard_events,
    query_dashboard_token_summary,
    query_latest_observed_usage,
    refresh_metadata,
)
from codex_usage_tracker.store.dedupe_queries import query_dedupe_diagnostics


def dashboard_payload(
    db_path: Path,
    limit: int | None = 5000,
    offset: int = 0,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    since: str | None = None,
    api_token: str | None = None,
    context_api_enabled: bool = False,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    privacy_mode: str = "normal",
    include_archived: bool = False,
    language: str | None = None,
    include_rows: bool = True,
    load_window: str | None = None,
) -> dict[str, object]:
    """Return aggregate-only dashboard data without rendering HTML."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_offset = _normalize_offset(offset)
    rows = _dashboard_source_rows(
        db_path=db_path,
        limit=limit,
        offset=normalized_offset,
        since=since,
        include_archived=include_archived,
        include_rows=include_rows,
    )
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(allowance_path, rate_card_path=rate_card_path)
    thresholds = load_threshold_config(thresholds_path)
    projects = load_project_config(projects_path)
    annotated_rows = _annotated_dashboard_rows(
        rows,
        pricing=pricing,
        allowance=allowance,
        thresholds=thresholds,
        projects=projects,
        privacy_mode=privacy_mode,
    )
    token_summary = _dashboard_summary(
        db_path=db_path,
        since=since,
        include_archived=include_archived,
        pricing=pricing,
        allowance=allowance,
    )
    allowance_summary = summarize_allowance_usage(
        cast(list[dict[str, Any]], token_summary["priced_model_rows"]),
        allowance,
    )
    observed_usage = query_latest_observed_usage(
        db_path=db_path,
        include_archived=include_archived,
    )
    normalized_limit = _normalize_limit(limit)
    row_counts = _dashboard_available_row_counts(
        db_path=db_path,
        since=since,
        include_archived=include_archived,
    )
    metadata = refresh_metadata(db_path)
    parser_diagnostics = _parser_diagnostics_payload(metadata)
    dedupe = query_dedupe_diagnostics(db_path=db_path, limit=0)["summary"]
    row_count = len(annotated_rows)
    return {
        **dashboard_i18n_payload(language),
        "rows": annotated_rows,
        "summary": token_summary["summary"],
        "shell_boot": not include_rows,
        "pricing_configured": pricing.loaded and not pricing.error,
        "pricing_source": pricing.source,
        "pricing_snapshot": _pricing_snapshot(pricing.loaded, pricing.source, pricing.models),
        "allowance_configured": allowance.loaded and not allowance.error,
        "allowance_source": allowance_summary["source"],
        "allowance_windows": allowance_summary["windows"],
        "allowance_error": allowance_summary["error"],
        "observed_usage": observed_usage,
        "rate_card_configured": allowance_summary["rate_card_loaded"],
        "rate_card_error": allowance_summary["rate_card_error"],
        "loaded_row_count": row_count,
        **row_counts,
        "include_archived": include_archived,
        "history_scope": "all-history" if include_archived else "active",
        **dashboard_load_window_payload(
            load_window, since=since, limit=normalized_limit, live=bool(api_token)
        ),
        **_dashboard_pagination_payload(
            limit=normalized_limit,
            offset=normalized_offset,
            row_count=row_count,
            total_available_rows=int(row_counts["total_available_rows"]),
        ),
        "parser_diagnostics": parser_diagnostics,
        "dedupe": dedupe,
        "parser_adapter": metadata.get("parser_adapter"),
        "latest_refresh_at": metadata.get("latest_refresh_at"),
        "payload_cache_key": dashboard_payload_cache_key(
            db_path=db_path,
            api_token=api_token,
            privacy_mode=privacy_mode,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            thresholds_path=thresholds_path,
            projects_path=projects_path,
        ),
        "payload_cache_version": 3,
        "api_token": api_token or "",
        "context_api_enabled": context_api_enabled,
        "refresh_jobs_available": bool(api_token),
        "action_thresholds": thresholds.thresholds,
        "thresholds_configured": thresholds.loaded and not thresholds.error,
        "thresholds_error": thresholds.error,
        "project_configured": projects.loaded and not projects.error,
        "project_config_error": projects.error,
        "privacy_mode": privacy_mode,
        "project_metadata_privacy": project_privacy_metadata(privacy_mode),
    }


def _dashboard_source_rows(
    *,
    db_path: Path,
    limit: int | None,
    offset: int,
    since: str | None,
    include_archived: bool,
    include_rows: bool,
) -> list[dict[str, Any]]:
    if not include_rows:
        return []
    rows = [
        ensure_call_origin(row)
        for row in query_dashboard_events(
            db_path=db_path,
            limit=limit,
            offset=offset,
            since=since,
            include_archived=include_archived,
        )
    ]
    return annotate_thread_attachments(rows)


def _annotated_dashboard_rows(
    rows: list[dict[str, Any]],
    *,
    pricing: Any,
    allowance: Any,
    thresholds: Any,
    projects: Any,
    privacy_mode: str,
) -> list[dict[str, Any]]:
    annotated_rows = annotate_rows_with_allowance(
        annotate_rows_with_efficiency(rows, pricing),
        allowance,
    )
    annotated_rows = annotate_rows_with_recommendations(annotated_rows, thresholds)
    annotated_rows = annotate_rows_with_project_identity(annotated_rows, projects)
    return apply_project_privacy_to_rows(annotated_rows, privacy_mode=privacy_mode)


def _dashboard_available_row_counts(
    *, db_path: Path, since: str | None, include_archived: bool
) -> dict[str, int]:
    counts = query_dashboard_event_counts(db_path=db_path, since=since)
    active_available_rows = counts["active_available_rows"]
    all_history_available_rows = counts["all_history_available_rows"]
    total_available_rows = all_history_available_rows if include_archived else active_available_rows
    return {
        "total_available_rows": total_available_rows,
        "active_available_rows": active_available_rows,
        "all_history_available_rows": all_history_available_rows,
        "archived_available_rows": max(all_history_available_rows - active_available_rows, 0),
    }


def _dashboard_pagination_payload(
    *, limit: int | None, offset: int, row_count: int, total_available_rows: int
) -> dict[str, object]:
    has_more = limit is not None and offset + row_count < total_available_rows
    return {
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + row_count if has_more else None,
        "limit_label": "All" if limit is None else str(limit),
    }


def _parser_diagnostics_payload(metadata: dict[str, str]) -> dict[str, int]:
    return {
        key.removeprefix("parser_"): _safe_int(value)
        for key, value in metadata.items()
        if key.startswith("parser_") and _safe_int(value)
    }


def _dashboard_summary(
    *,
    db_path: Path,
    since: str | None,
    include_archived: bool,
    pricing: Any,
    allowance: Any,
) -> dict[str, object]:
    token_summary = query_dashboard_token_summary(
        db_path=db_path,
        since=since,
        include_archived=include_archived,
    )
    model_rows = [
        {key: value for key, value in row.items() if key != "row_count"}
        for row in token_summary["model_rows"]
    ]
    priced_model_rows = annotate_rows_with_allowance(
        annotate_rows_with_efficiency(model_rows, pricing, model_field="model"),
        allowance,
        model_field="model",
    )
    estimated_cost = sum(
        float(row.get("estimated_cost_usd") or 0)
        for row in priced_model_rows
        if isinstance(row.get("estimated_cost_usd"), int | float)
    )
    usage_credits = sum(
        float(row.get("usage_credits") or 0)
        for row in priced_model_rows
        if isinstance(row.get("usage_credits"), int | float)
    )
    return {
        "summary": {
            "visible_calls": token_summary["row_count"],
            "input_tokens": token_summary["input_tokens"],
            "cached_input_tokens": token_summary["cached_input_tokens"],
            "uncached_input_tokens": token_summary["uncached_input_tokens"],
            "output_tokens": token_summary["output_tokens"],
            "reasoning_output_tokens": token_summary["reasoning_output_tokens"],
            "total_tokens": token_summary["total_tokens"],
            "estimated_cost_usd": estimated_cost,
            "usage_credits": usage_credits,
        },
        "priced_model_rows": priced_model_rows,
    }


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return int(limit)


def _normalize_offset(offset: int | None) -> int:
    if offset is None or offset <= 0:
        return 0
    return int(offset)


def _pricing_snapshot(
    loaded: bool,
    source: dict[str, Any] | None,
    models: dict[str, dict[str, float]],
) -> dict[str, Any]:
    if not loaded:
        return {"configured": False, "fingerprint": None}
    public_source = {
        key: value
        for key, value in (source or {}).items()
        if key
        in {
            "name",
            "url",
            "tier",
            "fetched_at",
            "model_count",
            "official_model_count",
            "estimated_model_count",
            "pinned",
            "pinned_at",
        }
    }
    public_source.setdefault("model_count", len(models))
    rates_fingerprint = hashlib.sha256(
        json.dumps(models, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:12]
    fingerprint = hashlib.sha256(
        json.dumps(
            {**public_source, "rates_fingerprint": rates_fingerprint},
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "configured": True,
        "fingerprint": fingerprint,
        "rates_fingerprint": rates_fingerprint,
        **public_source,
    }


def _safe_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0
