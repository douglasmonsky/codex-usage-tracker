"""Static dashboard generation from aggregate-only usage rows."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
    summarize_allowance_usage,
)
from codex_usage_tracker.call_origin import ensure_call_origin
from codex_usage_tracker.dashboard_diagnostics import dashboard_parser_diagnostics
from codex_usage_tracker.i18n import dashboard_i18n_payload, language_direction, translations_for
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
from codex_usage_tracker.usage_impact import (
    annotate_rows_with_usage_impact,
    copy_usage_impact_from_context,
)

DASHBOARD_STYLESHEETS = (
    "dashboard.css",
    "dashboard_call.css",
    "dashboard_insights.css",
    "dashboard_layout.css",
    "dashboard_tables.css",
    "dashboard_detail.css",
    "dashboard_responsive.css",
)

DASHBOARD_SCRIPT_ASSETS = (
    ("format_script_src", "__FORMAT_SCRIPT_SRC__", "dashboard_format.js"),
    ("data_script_src", "__DATA_SCRIPT_SRC__", "dashboard_data.js"),
    ("analysis_script_src", "__ANALYSIS_SCRIPT_SRC__", "dashboard_analysis.js"),
    ("cells_script_src", "__CELLS_SCRIPT_SRC__", "dashboard_cells.js"),
    ("details_script_src", "__DETAILS_SCRIPT_SRC__", "dashboard_details.js"),
    ("insights_script_src", "__INSIGHTS_SCRIPT_SRC__", "dashboard_insights.js"),
    ("tables_script_src", "__TABLES_SCRIPT_SRC__", "dashboard_tables.js"),
    ("filters_script_src", "__FILTERS_SCRIPT_SRC__", "dashboard_filters.js"),
    ("state_script_src", "__STATE_SCRIPT_SRC__", "dashboard_state.js"),
    ("payload_cache_script_src", "__PAYLOAD_CACHE_SCRIPT_SRC__", "dashboard_payload_cache.js"),
    ("i18n_script_src", "__I18N_SCRIPT_SRC__", "dashboard_i18n.js"),
    ("tooltips_script_src", "__TOOLTIPS_SCRIPT_SRC__", "dashboard_tooltips.js"),
    ("status_script_src", "__STATUS_SCRIPT_SRC__", "dashboard_status.js"),
    ("actions_script_src", "__ACTIONS_SCRIPT_SRC__", "dashboard_actions.js"),
    ("live_script_src", "__LIVE_SCRIPT_SRC__", "dashboard_live.js"),
    ("events_script_src", "__EVENTS_SCRIPT_SRC__", "dashboard_events.js"),
    (
        "call_diagnostics_script_src",
        "__CALL_DIAGNOSTICS_SCRIPT_SRC__",
        "dashboard_call_diagnostics.js",
    ),
    (
        "call_investigator_script_src",
        "__CALL_INVESTIGATOR_SCRIPT_SRC__",
        "dashboard_call_investigator.js",
    ),
    ("script_src", "__SCRIPT_SRC__", "dashboard.js"),
)

DEFAULT_DASHBOARD_SCRIPT_SRCS = {
    key: f"codex-usage-tracker-assets/{filename}"
    for key, _placeholder, filename in DASHBOARD_SCRIPT_ASSETS
}


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
    estimate_usage_impact: bool = True,
) -> dict[str, object]:
    """Return aggregate-only dashboard data without rendering HTML."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_limit = _normalize_limit(limit)
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
    if not estimate_usage_impact:
        for row in annotated_rows:
            row["usage_impact"] = {"primary": None, "secondary": None}
    elif include_rows and (normalized_limit is not None or normalized_offset):
        impact_context_rows = annotate_rows_with_allowance(
            annotate_rows_with_efficiency(
                [
                    ensure_call_origin(row)
                    for row in query_dashboard_events(
                        db_path=db_path,
                        limit=None,
                        offset=0,
                        since=since,
                        include_archived=include_archived,
                    )
                ],
                pricing,
            ),
            allowance,
        )
        annotated_rows = copy_usage_impact_from_context(annotated_rows, impact_context_rows)
    else:
        annotated_rows = annotate_rows_with_usage_impact(annotated_rows)
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
    parser_diagnostics = dashboard_parser_diagnostics(metadata)
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
    estimate_usage_impact: bool = True,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    guide_href = _dashboard_guide_href(output_path)
    asset_base = _dashboard_assets_href(output_path)
    stylesheet_hrefs = [
        _versioned_asset_href(output_path, asset_base, stylesheet)
        for stylesheet in DASHBOARD_STYLESHEETS
    ]
    script_srcs = _dashboard_script_srcs(output_path, asset_base)
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
        estimate_usage_impact=estimate_usage_impact,
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
    call_diagnostics_script_src: str | None = None,
    call_investigator_script_src: str | None = None,
    script_src: str | None = None,
) -> str:
    """Render dashboard HTML for a prepared aggregate payload."""

    asset_base = "codex-usage-tracker-assets"
    payload = json.dumps(payload_dict, ensure_ascii=True).replace("</", "<\\/")
    script_srcs = _dashboard_script_srcs(output_path, asset_base)
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
        "call_diagnostics_script_src": call_diagnostics_script_src,
        "call_investigator_script_src": call_investigator_script_src,
        "script_src": script_src,
    }
    script_srcs.update(
        {key: value for key, value in script_overrides.items() if value is not None}
    )
    return _html(
        payload,
        guide_href=guide_href,
        language=str(payload_dict.get("language") or "en"),
        direction=str(
            payload_dict.get("language_direction")
            or language_direction(str(payload_dict.get("language") or "en"))
        ),
        body_attrs=_format_body_attrs(body_attrs),
        stylesheet_hrefs=stylesheet_hrefs
        or [
            _versioned_asset_href(output_path, asset_base, stylesheet)
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


def _dashboard_guide_href(output_path: Path) -> str | None:
    override = os.environ.get("CODEX_USAGE_TRACKER_DOCS_URL")
    if override:
        return override
    try:
        docs_source = resources.files("codex_usage_tracker.plugin_data").joinpath("docs")
        docs_target = output_path.parent / "codex-usage-tracker-guide"
        if docs_target.exists():
            shutil.rmtree(docs_target)
        _copy_resource_tree(docs_source, docs_target)
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None
    return "codex-usage-tracker-guide/dashboard-guide.html"


def _dashboard_assets_href(output_path: Path) -> str:
    assets_source = resources.files("codex_usage_tracker.plugin_data").joinpath("dashboard")
    assets_target = output_path.parent / "codex-usage-tracker-assets"
    if assets_target.exists():
        shutil.rmtree(assets_target)
    _copy_resource_tree(assets_source, assets_target)
    return "codex-usage-tracker-assets"


def _versioned_asset_href(output_path: Path, asset_base: str, filename: str) -> str:
    asset_path = output_path.parent / asset_base / filename
    try:
        digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()[:12]
    except OSError:
        return f"{asset_base}/{filename}"
    return f"{asset_base}/{filename}?v={digest}"


def _dashboard_script_srcs(output_path: Path, asset_base: str) -> dict[str, str]:
    return {
        key: _versioned_asset_href(output_path, asset_base, filename)
        for key, _placeholder, filename in DASHBOARD_SCRIPT_ASSETS
    }


def _copy_resource_tree(source: Any, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            _copy_resource_tree(child, destination)
        else:
            destination.write_bytes(child.read_bytes())


def _html(
    payload: str,
    guide_href: str | None = None,
    *,
    language: str = "en",
    direction: str | None = None,
    stylesheet_hrefs: Sequence[str] = ("codex-usage-tracker-assets/dashboard.css",),
    script_srcs: Mapping[str, str] | None = None,
    body_attrs: str = "",
) -> str:
    template = _read_dashboard_asset("dashboard_template.html")
    translations = translations_for(language)
    html_direction = direction or language_direction(language)
    guide_link = (
        f'<a class="guide-link" href="{html.escape(guide_href, quote=True)}" '
        f'data-i18n="docs.dashboard_guide">{html.escape(translations["docs.dashboard_guide"])}</a>'
        if guide_href
        else ""
    )
    stylesheet_links = "\n  ".join(
        f'<link rel="stylesheet" href="{html.escape(href, quote=True)}">'
        for href in stylesheet_hrefs
    )
    resolved_script_srcs = {**DEFAULT_DASHBOARD_SCRIPT_SRCS, **dict(script_srcs or {})}
    rendered = (
        template.replace("__HTML_LANG__", html.escape(language, quote=True))
        .replace("__HTML_DIR__", html.escape(html_direction, quote=True))
        .replace("__BODY_ATTRS__", body_attrs)
        .replace("__TITLE__", html.escape(translations["dashboard.title"]))
        .replace("__STYLESHEET_LINKS__", stylesheet_links)
        .replace("__GUIDE_LINK__", guide_link)
        .replace("__PAYLOAD__", payload)
    )
    for key, placeholder, _filename in DASHBOARD_SCRIPT_ASSETS:
        rendered = rendered.replace(
            placeholder,
            html.escape(resolved_script_srcs[key], quote=True),
        )
    return rendered


def _format_body_attrs(attrs: dict[str, str] | None) -> str:
    if not attrs:
        return ""
    rendered = []
    for key, value in attrs.items():
        if not key:
            continue
        rendered.append(f'{html.escape(key, quote=True)}="{html.escape(str(value), quote=True)}"')
    return " " + " ".join(rendered) if rendered else ""


def _read_dashboard_asset(name: str) -> str:
    asset = resources.files("codex_usage_tracker.plugin_data").joinpath("dashboard", name)
    return asset.read_text(encoding="utf-8")


_USAGE_DATA_RE = re.compile(
    r'<script id="usage-data" type="application/json">(?P<payload>.*?)</script>',
    re.DOTALL,
)
