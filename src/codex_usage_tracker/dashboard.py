"""Static dashboard generation from aggregate-only usage rows."""

from __future__ import annotations

import html
import hashlib
import json
import os
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
    summarize_allowance_usage,
)
from codex_usage_tracker.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.pricing import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.store import query_dashboard_event_count, query_dashboard_events
from codex_usage_tracker.threads import annotate_thread_attachments


def dashboard_payload(
    db_path: Path,
    limit: int | None = 5000,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    since: str | None = None,
) -> dict[str, object]:
    """Return aggregate-only dashboard data without rendering HTML."""

    rows = annotate_thread_attachments(
        query_dashboard_events(db_path=db_path, limit=limit, since=since)
    )
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(allowance_path)
    annotated_rows = annotate_rows_with_allowance(
        annotate_rows_with_efficiency(rows, pricing),
        allowance,
    )
    allowance_summary = summarize_allowance_usage(annotated_rows, allowance)
    normalized_limit = _normalize_limit(limit)
    return {
        "rows": annotated_rows,
        "pricing_configured": pricing.loaded and not pricing.error,
        "pricing_source": pricing.source,
        "allowance_configured": allowance.loaded and not allowance.error,
        "allowance_source": allowance_summary["source"],
        "allowance_windows": allowance_summary["windows"],
        "allowance_error": allowance_summary["error"],
        "loaded_row_count": len(rows),
        "total_available_rows": query_dashboard_event_count(db_path=db_path, since=since),
        "limit": normalized_limit,
        "limit_label": "All" if normalized_limit is None else str(normalized_limit),
    }


def generate_dashboard(
    db_path: Path,
    output_path: Path = DEFAULT_DASHBOARD_PATH,
    limit: int | None = 5000,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    since: str | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    guide_href = _dashboard_guide_href(output_path)
    asset_base = _dashboard_assets_href(output_path)
    stylesheet_href = _versioned_asset_href(output_path, asset_base, "dashboard.css")
    script_src = _versioned_asset_href(output_path, asset_base, "dashboard.js")
    payload = json.dumps(
        dashboard_payload(
            db_path=db_path,
            limit=limit,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            since=since,
        ),
        ensure_ascii=True,
    ).replace("</", "<\\/")
    output_path.write_text(
        _html(
            payload,
            guide_href=guide_href,
            stylesheet_href=stylesheet_href,
            script_src=script_src,
        ),
        encoding="utf-8",
    )
    return output_path


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return int(limit)


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
    stylesheet_href: str = "codex-usage-tracker-assets/dashboard.css",
    script_src: str = "codex-usage-tracker-assets/dashboard.js",
) -> str:
    template = _read_dashboard_asset("dashboard_template.html")
    guide_link = (
        f'<a class="guide-link" href="{html.escape(guide_href, quote=True)}">Dashboard guide</a>'
        if guide_href
        else ""
    )
    return (
        template.replace("__TITLE__", html.escape("Codex Usage Dashboard"))
        .replace("__STYLESHEET_HREF__", html.escape(stylesheet_href, quote=True))
        .replace("__GUIDE_LINK__", guide_link)
        .replace("__PAYLOAD__", payload)
        .replace("__SCRIPT_SRC__", html.escape(script_src, quote=True))
    )


def _read_dashboard_asset(name: str) -> str:
    asset = resources.files("codex_usage_tracker.plugin_data").joinpath("dashboard", name)
    return asset.read_text(encoding="utf-8")
