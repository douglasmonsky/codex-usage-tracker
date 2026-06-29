"""Static dashboard generation from aggregate-only usage rows."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
    summarize_allowance_usage,
)
from codex_usage_tracker.call_origin import ensure_call_origin
from codex_usage_tracker.dashboard_assets import (
    DASHBOARD_STYLESHEETS,
    dashboard_assets_href,
    dashboard_guide_href,
    dashboard_script_srcs,
    format_body_attrs,
    render_dashboard_template,
    versioned_asset_href,
)
from codex_usage_tracker.i18n import dashboard_i18n_payload, language_direction
from codex_usage_tracker.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.pricing import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    load_project_config,
    project_privacy_metadata,
    validate_privacy_mode,
)
from codex_usage_tracker.recommendations import (
    annotate_rows_with_recommendations,
    load_threshold_config,
)
from codex_usage_tracker.store import (
    query_dashboard_event_count,
    query_dashboard_events,
    query_dashboard_token_summary,
    query_latest_observed_usage,
    refresh_metadata,
)
from codex_usage_tracker.threads import annotate_thread_attachments


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
) -> dict[str, object]:
    """Return aggregate-only dashboard data without rendering HTML."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_offset = _normalize_offset(offset)
    rows = (
        annotate_thread_attachments(
            [
                ensure_call_origin(row)
                for row in query_dashboard_events(
                    db_path=db_path,
                    limit=limit,
                    offset=normalized_offset,
                    since=since,
                    include_archived=include_archived,
                )
            ]
        )
        if include_rows
        else []
    )
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(allowance_path, rate_card_path=rate_card_path)
    thresholds = load_threshold_config(thresholds_path)
    projects = load_project_config(projects_path)
    annotated_rows = annotate_rows_with_allowance(
        annotate_rows_with_efficiency(rows, pricing),
        allowance,
    )
    annotated_rows = annotate_rows_with_recommendations(annotated_rows, thresholds)
    annotated_rows = annotate_rows_with_project_identity(annotated_rows, projects)
    annotated_rows = apply_project_privacy_to_rows(annotated_rows, privacy_mode=privacy_mode)
    token_summary = _dashboard_summary(
        db_path=db_path,
        since=since,
        include_archived=include_archived,
        pricing=pricing,
        allowance=allowance,
    )
    allowance_summary = summarize_allowance_usage(
        token_summary["priced_model_rows"],
        allowance,
    )
    observed_usage = query_latest_observed_usage(
        db_path=db_path,
        include_archived=include_archived,
    )
    normalized_limit = _normalize_limit(limit)
    total_available_rows = query_dashboard_event_count(
        db_path=db_path,
        since=since,
        include_archived=include_archived,
    )
    active_available_rows = query_dashboard_event_count(
        db_path=db_path,
        since=since,
        include_archived=False,
    )
    all_history_available_rows = query_dashboard_event_count(
        db_path=db_path,
        since=since,
        include_archived=True,
    )
    metadata = refresh_metadata(db_path)
    parser_diagnostics = {
        key.removeprefix("parser_"): _safe_int(value)
        for key, value in metadata.items()
        if key.startswith("parser_") and _safe_int(value)
    }
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
        "loaded_row_count": len(rows),
        "total_available_rows": total_available_rows,
        "active_available_rows": active_available_rows,
        "all_history_available_rows": all_history_available_rows,
        "archived_available_rows": max(all_history_available_rows - active_available_rows, 0),
        "include_archived": include_archived,
        "history_scope": "all-history" if include_archived else "active",
        "limit": normalized_limit,
        "offset": normalized_offset,
        "has_more": (
            normalized_limit is not None
            and normalized_offset + len(rows) < total_available_rows
        ),
        "next_offset": (
            normalized_offset + len(rows)
            if normalized_limit is not None
            and normalized_offset + len(rows) < total_available_rows
            else None
        ),
        "limit_label": "All" if normalized_limit is None else str(normalized_limit),
        "parser_diagnostics": parser_diagnostics,
        "parser_adapter": metadata.get("parser_adapter"),
        "latest_refresh_at": metadata.get("latest_refresh_at"),
        "payload_cache_key": _payload_cache_key(
            db_path=db_path,
            api_token=api_token,
            include_archived=include_archived,
            since=since,
            privacy_mode=privacy_mode,
        ),
        "payload_cache_version": 1,
        "api_token": api_token or "",
        "context_api_enabled": context_api_enabled,
        "action_thresholds": thresholds.thresholds,
        "thresholds_configured": thresholds.loaded and not thresholds.error,
        "thresholds_error": thresholds.error,
        "project_configured": projects.loaded and not projects.error,
        "project_config_error": projects.error,
        "privacy_mode": privacy_mode,
        "project_metadata_privacy": project_privacy_metadata(privacy_mode),
    }


def generate_dashboard(
    db_path: Path,
    output_path: Path = DEFAULT_DASHBOARD_PATH,
    limit: int | None = 5000,
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
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    guide_href = dashboard_guide_href(output_path)
    asset_base = dashboard_assets_href(output_path)
    stylesheet_hrefs = [
        versioned_asset_href(output_path, asset_base, stylesheet)
        for stylesheet in DASHBOARD_STYLESHEETS
    ]
    script_srcs = dashboard_script_srcs(output_path, asset_base)
    previous_payload = _previous_dashboard_payload(output_path)
    payload_dict = dashboard_payload(
        db_path=db_path,
        limit=limit,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        since=since,
        api_token=api_token,
        context_api_enabled=context_api_enabled,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
        privacy_mode=privacy_mode,
        include_archived=include_archived,
        language=language,
        include_rows=include_rows,
    )
    payload_dict["pricing_snapshot_warning"] = _pricing_snapshot_warning(
        previous_payload, payload_dict
    )
    output_path.write_text(
        render_dashboard_html(
            payload_dict,
            output_path=output_path,
            guide_href=guide_href,
            stylesheet_hrefs=stylesheet_hrefs,
            **script_srcs,
        ),
        encoding="utf-8",
    )
    return output_path


def render_dashboard_html(
    payload_dict: dict[str, object],
    output_path: Path = DEFAULT_DASHBOARD_PATH,
    guide_href: str | None = None,
    *,
    body_attrs: dict[str, str] | None = None,
    stylesheet_hrefs: Sequence[str] | None = None,
    format_script_src: str | None = None,
    data_script_src: str | None = None,
    analysis_script_src: str | None = None,
    cells_script_src: str | None = None,
    details_script_src: str | None = None,
    insights_script_src: str | None = None,
    tables_script_src: str | None = None,
    filters_script_src: str | None = None,
    state_script_src: str | None = None,
    payload_cache_script_src: str | None = None,
    i18n_script_src: str | None = None,
    tooltips_script_src: str | None = None,
    status_script_src: str | None = None,
    actions_script_src: str | None = None,
    live_script_src: str | None = None,
    events_script_src: str | None = None,
    diagnostics_snapshots_script_src: str | None = None,
    diagnostics_facts_script_src: str | None = None,
    diagnostics_script_src: str | None = None,
    call_diagnostics_script_src: str | None = None,
    call_investigator_script_src: str | None = None,
    script_src: str | None = None,
) -> str:
    """Render dashboard HTML for a prepared aggregate payload."""

    asset_base = "codex-usage-tracker-assets"
    payload = json.dumps(payload_dict, ensure_ascii=True).replace("</", "<\\/")
    script_srcs = dashboard_script_srcs(output_path, asset_base)
    script_overrides = {
        "format_script_src": format_script_src,
        "data_script_src": data_script_src,
        "analysis_script_src": analysis_script_src,
        "cells_script_src": cells_script_src,
        "details_script_src": details_script_src,
        "insights_script_src": insights_script_src,
        "tables_script_src": tables_script_src,
        "filters_script_src": filters_script_src,
        "state_script_src": state_script_src,
        "payload_cache_script_src": payload_cache_script_src,
        "i18n_script_src": i18n_script_src,
        "tooltips_script_src": tooltips_script_src,
        "status_script_src": status_script_src,
        "actions_script_src": actions_script_src,
        "live_script_src": live_script_src,
        "events_script_src": events_script_src,
        "diagnostics_snapshots_script_src": diagnostics_snapshots_script_src,
        "diagnostics_facts_script_src": diagnostics_facts_script_src,
        "diagnostics_script_src": diagnostics_script_src,
        "call_diagnostics_script_src": call_diagnostics_script_src,
        "call_investigator_script_src": call_investigator_script_src,
        "script_src": script_src,
    }
    script_srcs.update(
        {key: value for key, value in script_overrides.items() if value is not None}
    )
    return render_dashboard_template(
        payload,
        guide_href=guide_href,
        language=str(payload_dict.get("language") or "en"),
        direction=str(
            payload_dict.get("language_direction")
            or language_direction(str(payload_dict.get("language") or "en"))
        ),
        body_attrs=format_body_attrs(body_attrs),
        stylesheet_hrefs=stylesheet_hrefs
        or [
            versioned_asset_href(output_path, asset_base, stylesheet)
            for stylesheet in DASHBOARD_STYLESHEETS
        ],
        script_srcs=script_srcs,
    )


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


def _payload_cache_key(
    *,
    db_path: Path,
    api_token: str | None,
    include_archived: bool,
    since: str | None,
    privacy_mode: str,
) -> str:
    source = "|".join(
        [
            str(db_path),
            api_token or "static",
            "all" if include_archived else "active",
            since or "",
            privacy_mode,
            "dashboard-payload-v1",
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def _pricing_snapshot_warning(
    previous_payload: dict[str, Any] | None, current_payload: dict[str, object]
) -> str | None:
    if not previous_payload:
        return None
    previous = previous_payload.get("pricing_snapshot")
    current = current_payload.get("pricing_snapshot")
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return None
    previous_fingerprint = previous.get("fingerprint")
    current_fingerprint = current.get("fingerprint")
    if not previous_fingerprint or not current_fingerprint:
        return None
    if previous_fingerprint == current_fingerprint:
        return None
    previous_label = previous.get("fetched_at") or previous.get("pinned_at") or previous_fingerprint
    current_label = current.get("fetched_at") or current.get("pinned_at") or current_fingerprint
    return f"Pricing snapshot changed since the previous dashboard render: {previous_label} -> {current_label}."


def _previous_dashboard_payload(output_path: Path) -> dict[str, Any] | None:
    if not output_path.exists():
        return None
    try:
        text = output_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _USAGE_DATA_RE.search(text)
    if not match:
        return None
    try:
        raw = json.loads(match.group("payload"))
    except json.JSONDecodeError:
        return None
    return raw if isinstance(raw, dict) else None


















def _safe_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


_USAGE_DATA_RE = re.compile(
    r'<script id="usage-data" type="application/json">(?P<payload>.*?)</script>',
    re.DOTALL,
)
