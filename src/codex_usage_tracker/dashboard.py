"""Static dashboard generation from aggregate-only usage rows."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
    summarize_allowance_usage,
)
from codex_usage_tracker.i18n import dashboard_i18n_payload, translations_for
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
) -> dict[str, object]:
    """Return aggregate-only dashboard data without rendering HTML."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_offset = _normalize_offset(offset)
    rows = annotate_thread_attachments(
        query_dashboard_events(
            db_path=db_path,
            limit=limit,
            offset=normalized_offset,
            since=since,
            include_archived=include_archived,
        )
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
    allowance_summary = summarize_allowance_usage(annotated_rows, allowance)
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
        "pricing_configured": pricing.loaded and not pricing.error,
        "pricing_source": pricing.source,
        "pricing_snapshot": _pricing_snapshot(pricing.loaded, pricing.source, pricing.models),
        "allowance_configured": allowance.loaded and not allowance.error,
        "allowance_source": allowance_summary["source"],
        "allowance_windows": allowance_summary["windows"],
        "allowance_error": allowance_summary["error"],
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
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    guide_href = _dashboard_guide_href(output_path)
    asset_base = _dashboard_assets_href(output_path)
    stylesheet_href = _versioned_asset_href(output_path, asset_base, "dashboard.css")
    format_script_src = _versioned_asset_href(output_path, asset_base, "dashboard_format.js")
    data_script_src = _versioned_asset_href(output_path, asset_base, "dashboard_data.js")
    state_script_src = _versioned_asset_href(output_path, asset_base, "dashboard_state.js")
    script_src = _versioned_asset_href(output_path, asset_base, "dashboard.js")
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
    )
    payload_dict["pricing_snapshot_warning"] = _pricing_snapshot_warning(
        previous_payload, payload_dict
    )
    payload = json.dumps(payload_dict, ensure_ascii=True).replace("</", "<\\/")
    output_path.write_text(
        _html(
            payload,
            guide_href=guide_href,
            language=str(payload_dict["language"]),
            stylesheet_href=stylesheet_href,
            format_script_src=format_script_src,
            data_script_src=data_script_src,
            state_script_src=state_script_src,
            script_src=script_src,
        ),
        encoding="utf-8",
    )
    return output_path


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
    stylesheet_href: str = "codex-usage-tracker-assets/dashboard.css",
    format_script_src: str = "codex-usage-tracker-assets/dashboard_format.js",
    data_script_src: str = "codex-usage-tracker-assets/dashboard_data.js",
    state_script_src: str = "codex-usage-tracker-assets/dashboard_state.js",
    script_src: str = "codex-usage-tracker-assets/dashboard.js",
) -> str:
    template = _read_dashboard_asset("dashboard_template.html")
    translations = translations_for(language)
    guide_link = (
        f'<a class="guide-link" href="{html.escape(guide_href, quote=True)}" '
        f'data-i18n="docs.dashboard_guide">{html.escape(translations["docs.dashboard_guide"])}</a>'
        if guide_href
        else ""
    )
    return (
        template.replace("__HTML_LANG__", html.escape(language, quote=True))
        .replace("__TITLE__", html.escape(translations["dashboard.title"]))
        .replace("__STYLESHEET_HREF__", html.escape(stylesheet_href, quote=True))
        .replace("__GUIDE_LINK__", guide_link)
        .replace("__PAYLOAD__", payload)
        .replace("__FORMAT_SCRIPT_SRC__", html.escape(format_script_src, quote=True))
        .replace("__DATA_SCRIPT_SRC__", html.escape(data_script_src, quote=True))
        .replace("__STATE_SCRIPT_SRC__", html.escape(state_script_src, quote=True))
        .replace("__SCRIPT_SRC__", html.escape(script_src, quote=True))
    )


def _read_dashboard_asset(name: str) -> str:
    asset = resources.files("codex_usage_tracker.plugin_data").joinpath("dashboard", name)
    return asset.read_text(encoding="utf-8")


def _safe_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


_USAGE_DATA_RE = re.compile(
    r'<script id="usage-data" type="application/json">(?P<payload>.*?)</script>',
    re.DOTALL,
)
