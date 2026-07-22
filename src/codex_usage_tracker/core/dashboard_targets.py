"""Privacy-safe, deterministic links to cataloged dashboard views."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit

from codex_usage_tracker.dashboard_service import DashboardServiceStatus

DASHBOARD_TARGET_SCHEMA = "codex-usage-tracker-dashboard-target-v1"
DASHBOARD_TARGET_FALLBACK = "codex-usage-tracker serve-dashboard --open"

_FILTERS_BY_VIEW: dict[str, frozenset[str]] = {
    "overview": frozenset(),
    "investigator": frozenset({"finding"}),
    "compression-lab": frozenset(),
    "calls": frozenset({"explore", "detail", "source", "sort", "direction", "density", "page"}),
    "call": frozenset({"return", "mode"}),
    "threads": frozenset({"expand", "risk", "thread_call_sort", "thread_call_page"}),
    "usage-drain": frozenset(
        {
            "usage_plan",
            "usage_effort",
            "usage_subagents",
            "usage_sample",
            "usage_confidence",
            "limit_window",
        }
    ),
    "cache-context": frozenset(),
    "diagnostics": frozenset({"diagnostic_source"}),
    "reports": frozenset({"report"}),
    "settings": frozenset(),
}
_PRIVACY_MODES = frozenset({"normal", "redacted", "strict"})
_HISTORY_SCOPES = frozenset({"active", "all"})
_RECORD_ID = re.compile(r"(?:[0-9a-f]{64}|record-[0-9]{1,10})")
_SESSION_ID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_SESSION_THREAD_KEY = re.compile(rf"session:{_SESSION_ID}")
_DIAGNOSTIC_FACT = re.compile(
    r"(?:activity|command_family|compaction|function|loop|mcp_server|mcp_tool|outcome|skill|tool):[a-z0-9_.:-]{1,80}"
)
_LIMIT_EVIDENCE = frozenset({"stable", "decreased"})
_REPORT_IDS = frozenset(
    {
        "fast-mode-proxy",
        "cost-curves",
        "usage-remaining",
        "allowance-change",
        "weekly-credits",
        "usage-drain-model",
    }
)
_ENUM_FILTERS: dict[str, frozenset[str]] = {
    "explore": frozenset({"calls", "tools", "files"}),
    "detail": frozenset({"first"}),
    "source": frozenset({"all", "project", "session", "git", "source-file", "missing"}),
    "sort": frozenset(
        {
            "time",
            "duration",
            "gap",
            "attention",
            "thread",
            "initiator",
            "model",
            "effort",
            "total",
            "cached",
            "uncached",
            "output",
            "reasoning",
            "cost",
            "usage",
            "cache",
            "context",
        }
    ),
    "direction": frozenset({"asc", "desc"}),
    "density": frozenset({"dense", "roomy"}),
    "return": frozenset(_FILTERS_BY_VIEW) - {"call"},
    "mode": frozenset({"summary", "full"}),
    "expand": frozenset({"first", "all"}),
    "risk": frozenset({"all", "Low", "Medium", "High"}),
    "thread_call_sort": frozenset(
        {
            "newest",
            "duration",
            "gap",
            "initiator",
            "model",
            "effort",
            "tokens",
            "cached",
            "uncached",
            "output",
            "reasoning",
            "cost",
            "cache",
        }
    ),
    "usage_plan": frozenset({"Weekly", "weekly", "five_hour"}),
    "usage_effort": frozenset({"low", "medium", "high"}),
    "limit_window": frozenset({"weekly", "five_hour"}),
    "diagnostic_source": frozenset({"facts", "tools", "compactions"}),
}
_INTEGER_FILTERS = {
    "finding": (1, 10_000),
    "page": (1, 10_000),
    "thread_call_page": (1, 10_000),
    "usage_sample": (1, 10_000),
}


def build_dashboard_target(
    *,
    view: str,
    record_id: str | None = None,
    thread_key: str | None = None,
    diagnostic_fact: str | None = None,
    limit_evidence: str | None = None,
    history: str = "active",
    filters: Mapping[str, object] | None = None,
    privacy_mode: str = "normal",
    service_origin: str | None = None,
    service_status: DashboardServiceStatus | None = None,
) -> dict[str, Any]:
    """Build a reviewed dashboard target without copying arbitrary input fields."""

    if view not in _FILTERS_BY_VIEW:
        raise ValueError(f"unknown dashboard view: {view}")
    if privacy_mode not in _PRIVACY_MODES:
        raise ValueError(f"unknown privacy mode: {privacy_mode}")
    if history not in _HISTORY_SCOPES:
        raise ValueError(f"unknown dashboard history scope: {history}")

    normalized_filters = _normalize_filters(view, filters or {})
    target: dict[str, Any] = {
        "schema": DASHBOARD_TARGET_SCHEMA,
        "view": view,
    }
    query: dict[str, str] = {"view": view}
    _add_selector(target, query, view, "record_id", "record", record_id, "call", privacy_mode)
    _add_selector(
        target, query, view, "thread_key", "thread_key", thread_key, "threads", privacy_mode
    )
    _add_selector(
        target,
        query,
        view,
        "diagnostic_fact",
        "diagnostic_fact",
        diagnostic_fact,
        "diagnostics",
        privacy_mode,
    )
    _add_selector(
        target,
        query,
        view,
        "limit_evidence",
        "limit_hypothesis",
        limit_evidence,
        "usage-drain",
        privacy_mode,
    )
    query.update({key: _query_value(value) for key, value in normalized_filters.items()})
    if history != "active":
        query["history"] = history

    relative_url = f"/react-dashboard.html?{urlencode(sorted(query.items()))}"
    origin = _active_origin(service_origin, service_status)
    target.update(
        {
            "filters": normalized_filters,
            "history": history,
            "privacy_mode": privacy_mode,
            "relative_url": relative_url,
            "absolute_url": f"{origin}{relative_url}" if origin else None,
            "fallback_instruction": None if origin else DASHBOARD_TARGET_FALLBACK,
        }
    )
    return target


def build_dashboard_target_v2(
    *,
    evidence_kind: str,
    selector_id: str,
    history: str = "active",
    analysis_id: str | None = None,
    service_origin: str | None = None,
    service_status: DashboardServiceStatus | None = None,
) -> dict[str, Any]:
    """Build a deterministic evidence handoff without changing the v1 compatibility shape."""
    if evidence_kind not in {"finding", "call", "thread", "allowance", "analysis"}:
        raise ValueError(f"unsupported evidence kind: {evidence_kind}")
    safe_id = (
        isinstance(selector_id, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@+ -]{0,255}", selector_id) is not None
    )
    if evidence_kind == "call":
        safe_id = isinstance(selector_id, str) and is_canonical_record_id(selector_id)
    if evidence_kind == "thread":
        safe_id = isinstance(selector_id, str) and is_canonical_thread_key(selector_id)
    if not safe_id:
        raise ValueError("selector_id is invalid")
    if history not in _HISTORY_SCOPES:
        raise ValueError(f"unknown dashboard history scope: {history}")
    if (
        analysis_id is not None
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,255}", analysis_id) is None
    ):
        raise ValueError("analysis_id is invalid")
    selector_keys = {
        "call": "record_id",
        "thread": "thread_key",
        "allowance": "evidence_id",
        "analysis": "analysis_id",
        "finding": "finding_id",
    }
    target_kind = "none" if evidence_kind == "analysis" else evidence_kind
    query_key = selector_keys[evidence_kind]
    query = {"view": "evidence", "kind": target_kind, query_key: selector_id}
    if history != "active":
        query["history"] = history
    if analysis_id is not None and evidence_kind == "finding":
        query["analysis_id"] = analysis_id
    relative_url = f"/react-dashboard.html?{urlencode(sorted(query.items()))}"
    origin = _active_origin(service_origin, service_status)
    selectors = {query_key: selector_id}
    if evidence_kind == "finding" and analysis_id is not None:
        selectors["analysis_id"] = analysis_id
    return {
        "schema": "codex-usage-tracker-dashboard-target-v2",
        "target_id": f"evidence:{evidence_kind}:{selector_id}:{history}",
        "surface": "evidence",
        "evidence_kind": target_kind,
        "analysis_id": analysis_id,
        "expires_at": None,
        "view": "evidence",
        "selectors": selectors,
        "scope": {
            "since": None,
            "until": None,
            "history": history,
            "privacy_mode": "normal",
            "filters": {},
        },
        "history": history,
        "relative_url": relative_url,
        "absolute_url": f"{origin}{relative_url}" if origin else None,
        "fallback_instruction": None if origin else DASHBOARD_TARGET_FALLBACK,
    }


def build_limits_target_v2(
    *,
    operation: str,
    window: str,
    range_preset: str,
    since: str | None,
    until: str | None,
    analysis_id: str | None = None,
    service_origin: str | None = None,
    service_status: DashboardServiceStatus | None = None,
) -> dict[str, Any]:
    """Build an allowlisted v2 handoff to the current Limits dashboard surface."""
    if operation not in {"status", "series", "evidence", "analysis"}:
        raise ValueError(f"unsupported allowance operation: {operation}")
    if window not in {"weekly", "five_hour"}:
        raise ValueError(f"unsupported allowance window: {window}")
    if range_preset not in {"24h", "7d", "8w", "6m"}:
        raise ValueError(f"unsupported allowance range: {range_preset}")
    if (
        analysis_id is not None
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,255}", analysis_id) is None
    ):
        raise ValueError("analysis_id is invalid")
    normalized_since = _limits_timestamp(since, "since")
    normalized_until = _limits_timestamp(until, "until")
    if (
        normalized_since is not None
        and normalized_until is not None
        and datetime.fromisoformat(normalized_since) > datetime.fromisoformat(normalized_until)
    ):
        raise ValueError("since must not be after until")
    query = {
        "view": "limits",
        "operation": operation,
        "window": window,
        "range": range_preset,
    }
    if analysis_id is not None:
        query["analysis_id"] = analysis_id
    relative_url = f"/react-dashboard.html?{urlencode(sorted(query.items()))}"
    origin = _active_origin(service_origin, service_status)
    selectors = {
        "operation": operation,
        "window_kind": window,
        "range": range_preset,
    }
    if analysis_id is not None:
        selectors["analysis_id"] = analysis_id
    return {
        "schema": "codex-usage-tracker-dashboard-target-v2",
        "target_id": f"limits:{operation}:{window}:{range_preset}:{analysis_id or 'current'}",
        "surface": "limits",
        "evidence_kind": "allowance",
        "analysis_id": analysis_id,
        "expires_at": None,
        "view": "limits",
        "selectors": selectors,
        "scope": {
            "since": normalized_since,
            "until": normalized_until,
            "history": "active",
            "privacy_mode": "strict",
            "filters": {"window_kind": window},
        },
        "history": "active",
        "relative_url": relative_url,
        "absolute_url": f"{origin}{relative_url}" if origin else None,
        "fallback_instruction": None if origin else DASHBOARD_TARGET_FALLBACK,
    }


def _limits_timestamp(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a timezone-aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware ISO-8601 timestamp")
    return parsed.astimezone(timezone.utc).isoformat()


def _normalize_filters(view: str, filters: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key in sorted(_FILTERS_BY_VIEW[view] & filters.keys()):
        value = _normalize_filter_value(key, filters[key])
        if value is not None:
            normalized[key] = value
    return normalized


def _normalize_filter_value(key: str, value: object) -> object | None:
    if key in _ENUM_FILTERS:
        candidate = value.strip() if isinstance(value, str) else None
        return candidate if candidate in _ENUM_FILTERS[key] else None
    if key in _INTEGER_FILTERS:
        minimum, maximum = _INTEGER_FILTERS[key]
        return (
            value
            if isinstance(value, int)
            and not isinstance(value, bool)
            and minimum <= value <= maximum
            else None
        )
    if key == "usage_subagents":
        if isinstance(value, bool):
            return value
        return value if isinstance(value, int) and 0 <= value <= 100 else None
    if key == "usage_confidence":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        if not math.isfinite(value) or not 0 <= value <= 1:
            return None
        return int(value) if value == 0 or float(value).is_integer() else value
    if key == "report":
        return value if isinstance(value, str) and value in _REPORT_IDS else None
    return None


def _add_selector(
    target: dict[str, Any],
    query: dict[str, str],
    view: str,
    target_key: str,
    query_key: str,
    value: str | None,
    required_view: str,
    privacy_mode: str,
) -> None:
    if value is None:
        return
    if view != required_view:
        raise ValueError(f"{target_key} is not allowed for dashboard view {view}")
    normalized = _normalize_identifier(value, target_key, privacy_mode)
    if normalized is None:
        raise ValueError(f"{target_key} must be a bounded privacy-safe identifier")
    target[target_key] = normalized
    query[query_key] = normalized


def _normalize_identifier(value: object, target_key: str, privacy_mode: str) -> str | None:
    if not isinstance(value, str):
        return None
    if target_key == "record_id":
        return value if _RECORD_ID.fullmatch(value) else None
    if target_key == "thread_key":
        if _SESSION_THREAD_KEY.fullmatch(value):
            return value
        if privacy_mode == "normal" and _normal_thread_key(value):
            return value
        return None
    if target_key == "diagnostic_fact":
        return value if _DIAGNOSTIC_FACT.fullmatch(value) else None
    if target_key == "limit_evidence":
        return value if value in _LIMIT_EVIDENCE else None
    return None


def _normal_thread_key(value: str) -> bool:
    if not value.startswith("thread:"):
        return False
    label = value.removeprefix("thread:")
    return (
        bool(label)
        and len(label) <= 80
        and not any(character in label for character in "\r\n\t/\\?#{}[]")
    )


def is_canonical_record_id(value: str) -> bool:
    """Return whether a public canonical record identifier is dashboard-safe."""
    return _RECORD_ID.fullmatch(value) is not None


def is_canonical_thread_key(value: str) -> bool:
    """Return whether a canonical session/thread key is bounded and safe."""
    return _SESSION_THREAD_KEY.fullmatch(value) is not None or _normal_thread_key(value)


def _query_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.15f}".rstrip("0").rstrip(".") or "0"
    return str(value)


def _active_origin(
    service_origin: str | None,
    service_status: DashboardServiceStatus | None,
) -> str | None:
    if service_status is not None and service_status.reachable:
        return service_status.url
    if service_origin is not None:
        parsed = urlsplit(service_origin)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("dashboard service origin must be an active loopback HTTP origin")
        if parsed.username or parsed.password:
            raise ValueError("dashboard service origin must not include credentials")
        port = parsed.port
        if port is None or not 1024 <= port <= 65535:
            raise ValueError("dashboard service origin must include port 1024 through 65535")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("dashboard service origin must not include a path, query, or fragment")
        return service_origin.rstrip("/")
    return None
