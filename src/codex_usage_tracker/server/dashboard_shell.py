"""Dashboard shell payload helpers for the local server."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.core.conversational_readiness import conversational_readiness
from codex_usage_tracker.core.i18n import dashboard_i18n_payload, normalize_language
from codex_usage_tracker.dashboard.api import dashboard_payload
from codex_usage_tracker.dashboard.load_window import dashboard_load_window_payload
from codex_usage_tracker.server.utils import first_query_value, parse_bool_query_value


def dashboard_shell_payload(
    query: str,
    *,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
    projects_path: Path,
    privacy_mode: str,
    since: str | None,
    api_token: str,
    context_api_enabled: bool,
    include_archived_default: bool,
    language_default: str,
    limit_default: int,
) -> dict[str, object]:
    """Build the lightweight shell payload served before live hydration."""
    params = parse_qs(query)
    include_archived = _shell_include_archived(
        params,
        include_archived_default=include_archived_default,
    )
    language = normalize_language(first_query_value(params.get("lang")) or language_default)
    payload = dashboard_payload(
        db_path=db_path,
        limit=limit_default,
        offset=0,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
        privacy_mode=privacy_mode,
        since=since,
        api_token=api_token,
        context_api_enabled=context_api_enabled,
        include_archived=include_archived,
        language=language,
        include_rows=False,
    )
    payload["conversational_analysis"] = conversational_readiness(codex_home=codex_home)
    return payload


def react_dashboard_boot_payload(
    query: str,
    *,
    api_token: str,
    context_api_enabled: bool,
    include_archived_default: bool,
    language_default: str,
    limit_default: int,
    privacy_mode: str,
    since: str | None,
) -> dict[str, object]:
    """Build a database-free boot payload for asynchronous React hydration."""
    params = parse_qs(query)
    include_archived = _shell_include_archived(
        params,
        include_archived_default=include_archived_default,
    )
    language = normalize_language(first_query_value(params.get("lang")) or language_default)
    return {
        **dashboard_i18n_payload(language),
        "rows": [],
        "summary": {},
        "shell_boot": True,
        "readiness_deferred": True,
        "loaded_row_count": 0,
        "include_archived": include_archived,
        "history_scope": "all-history" if include_archived else "active",
        **dashboard_load_window_payload(
            None,
            since=since,
            limit=limit_default,
            live=bool(api_token),
        ),
        "limit": limit_default,
        "offset": 0,
        "has_more": False,
        "next_offset": None,
        "limit_label": str(limit_default),
        "api_token": api_token or "",
        "context_api_enabled": context_api_enabled,
        "refresh_jobs_available": bool(api_token),
        "privacy_mode": privacy_mode,
    }


def _shell_include_archived(
    params: dict[str, list[str]],
    *,
    include_archived_default: bool,
) -> bool:
    include_archived = include_archived_default
    history_scope = first_query_value(params.get("history"))
    if history_scope == "all":
        include_archived = True
    elif history_scope == "active":
        include_archived = False
    return parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived,
    )
