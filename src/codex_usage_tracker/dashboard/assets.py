"""Dashboard static asset and template helpers."""

from __future__ import annotations

import hashlib
import html
import os
import shutil
from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.i18n import language_direction, translations_for

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
        "diagnostics_snapshots_script_src",
        "__DIAGNOSTICS_SNAPSHOTS_SCRIPT_SRC__",
        "dashboard_diagnostics_snapshots.js",
    ),
    (
        "diagnostics_facts_script_src",
        "__DIAGNOSTICS_FACTS_SCRIPT_SRC__",
        "dashboard_diagnostics_facts.js",
    ),
    ("diagnostics_script_src", "__DIAGNOSTICS_SCRIPT_SRC__", "dashboard_diagnostics.js"),
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


def dashboard_guide_href(output_path: Path) -> str | None:
    override = os.environ.get("CODEX_USAGE_TRACKER_DOCS_URL")
    if override:
        return override
    try:
        docs_source = resources.files("codex_usage_tracker.plugin_data").joinpath("docs")
        docs_target = output_path.parent / "codex-usage-tracker-guide"
        if docs_target.exists():
            shutil.rmtree(docs_target)
        _copy_dashboard_resource_tree(docs_source, docs_target)
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None
    return "codex-usage-tracker-guide/dashboard-guide.html"


def dashboard_assets_href(output_path: Path) -> str:
    assets_source = resources.files("codex_usage_tracker.plugin_data").joinpath("dashboard")
    assets_target = output_path.parent / "codex-usage-tracker-assets"
    if assets_target.exists():
        shutil.rmtree(assets_target)
    _copy_dashboard_resource_tree(assets_source, assets_target)
    return "codex-usage-tracker-assets"


def versioned_asset_href(output_path: Path, asset_base: str, filename: str) -> str:
    asset_path = output_path.parent / asset_base / filename
    try:
        digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()[:12]
    except OSError:
        return f"{asset_base}/{filename}"
    return f"{asset_base}/{filename}?v={digest}"


def dashboard_script_srcs(output_path: Path, asset_base: str) -> dict[str, str]:
    return {
        key: versioned_asset_href(output_path, asset_base, filename)
        for key, _placeholder, filename in DASHBOARD_SCRIPT_ASSETS
    }


def _copy_dashboard_resource_tree(source: Any, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            _copy_dashboard_resource_tree(child, destination)
        else:
            destination.write_bytes(child.read_bytes())


def render_dashboard_template(
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


def format_body_attrs(attrs: dict[str, str] | None) -> str:
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
