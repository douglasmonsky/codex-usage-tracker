"""Stable CLI adapters over the transport-independent application services."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Protocol, TextIO, cast
from urllib.parse import urlsplit

from codex_usage_tracker.analytics.analysis_models import (
    ANALYSIS_GOALS,
    AnalysisGoal,
    AnalysisRequest,
    ComparisonWindow,
)
from codex_usage_tracker.application.container import build_application_container
from codex_usage_tracker.application.paths import ApplicationPaths
from codex_usage_tracker.application.query_models import (
    ALL_QUERY_MEASURES,
    QUERY_ENTITY_CAPABILITIES,
    QueryEntity,
    QueryFilters,
    QueryMeasure,
    QueryOrder,
    QueryRequest,
)
from codex_usage_tracker.application.requests import HistoryScope, StatusRequest
from codex_usage_tracker.application.services import ApplicationServices
from codex_usage_tracker.core.contracts import payload_mapping
from codex_usage_tracker.core.dashboard_targets import build_dashboard_target_v2
from codex_usage_tracker.core.paths import DEFAULT_CODEX_HOME
from codex_usage_tracker.dashboard_service import dashboard_service_status
from codex_usage_tracker.diagnostics.conversational_readiness import conversational_readiness


class CliApplicationServices(Protocol):
    def status(self, request: StatusRequest) -> object: ...
    def analyze(self, request: AnalysisRequest) -> object: ...
    def query(self, request: QueryRequest) -> object: ...


_REPLACEMENTS = {
    "summary": "analyze' or 'query",
    "dashboard": "open",
    "open-dashboard": "open",
    "serve-dashboard": "service serve",
    "dashboard-service": "service",
    "dogfood-agentic": "admin dogfood",
}


def run_status(
    args: argparse.Namespace,
    *,
    services: CliApplicationServices | None = None,
    stdout: TextIO | None = None,
) -> int:
    request = StatusRequest(
        db_path=args.db,
        pricing_path=args.pricing,
        codex_home=DEFAULT_CODEX_HOME,
        home=DEFAULT_CODEX_HOME.parent,
        scope=_scope(args),
    )
    _write_json((services or _default_services(args)).status(request), stdout)
    return 0


def run_query(
    args: argparse.Namespace,
    *,
    services: CliApplicationServices | None = None,
    stdout: TextIO | None = None,
) -> int:
    entity = cast(QueryEntity, args.entity)
    measures = _csv_values(args.measures) or _default_measures(entity)
    unsupported = set(measures) - ALL_QUERY_MEASURES
    if unsupported:
        raise ValueError(f"unsupported query measure: {sorted(unsupported)[0]}")
    request = QueryRequest(
        entity=entity,
        measures=cast(tuple[QueryMeasure, ...], measures),
        filters=_query_filters(args),
        group_by=_csv_values(args.group_by),
        order_by=args.order_by,
        order=cast(QueryOrder, args.order),
        limit=args.limit,
        cursor=args.cursor,
        history=cast(HistoryScope, args.history),
    )
    _write_json((services or _default_services(args)).query(request), stdout)
    return 0


def run_analyze(
    args: argparse.Namespace,
    *,
    services: CliApplicationServices | None = None,
    stdout: TextIO | None = None,
) -> int:
    goal = cast(AnalysisGoal, args.goal)
    if goal not in ANALYSIS_GOALS:
        raise ValueError(f"unsupported analysis goal: {goal}")
    request = AnalysisRequest(
        goal=goal,
        filters=_query_filters(args),
        history=cast(HistoryScope, args.history_scope),
        evidence_limit=args.evidence_limit,
        comparison=_comparison(args.comparison),
        execution=args.execution,
    )
    _write_json((services or _default_services(args)).analyze(request), stdout)
    return 0


def run_open(
    args: argparse.Namespace,
    *,
    stdout: TextIO | None = None,
    service_origin: str | None = None,
    open_url: Callable[[str], bool] = webbrowser.open,
) -> int:
    origin = service_origin if service_origin is not None else _active_service_origin()
    target = _open_target(args, origin)
    url = target.get("absolute_url")
    if not isinstance(url, str):
        raise RuntimeError(
            "Evidence Console is unavailable; run 'codex-usage-tracker service serve'."
        )
    if args.as_json:
        _write_json(target, stdout)
        return 0
    if not open_url(url):
        raise RuntimeError("the browser did not accept the Evidence Console URL")
    return 0


def warn_legacy_alias(
    args: argparse.Namespace,
    *,
    stderr: TextIO | None = None,
    interactive: bool | None = None,
) -> None:
    alias = getattr(args, "compatibility_alias", None)
    stream = sys.stderr if stderr is None else stderr
    is_interactive = stream.isatty() if interactive is None else interactive
    if not alias or not is_interactive:
        return
    replacement = _REPLACEMENTS.get(alias, _replacement_from_alias(alias))
    print(
        f"Deprecated: '{alias}' is a compatibility alias; use '{replacement}'.",
        file=stream,
    )


def _default_services(args: argparse.Namespace) -> CliApplicationServices:
    container = build_application_container(
        ApplicationPaths(
            codex_home=DEFAULT_CODEX_HOME,
            db_path=args.db,
            pricing_path=args.pricing,
            allowance_path=args.allowance,
            rate_card_path=args.rate_card,
            thresholds_path=args.thresholds,
            projects_path=args.projects,
        )
    )
    return ApplicationServices(
        container=container,
        readiness_provider=conversational_readiness,
    )


def _scope(args: argparse.Namespace):
    from codex_usage_tracker.application.requests import RequestScope

    return RequestScope(
        since=getattr(args, "since", None),
        until=getattr(args, "until", None),
        history=getattr(args, "history", getattr(args, "history_scope", "active")),
        privacy_mode=args.privacy_mode,
        project=getattr(args, "project", None),
        thread_key=getattr(args, "thread_key", getattr(args, "thread", None)),
        model=getattr(args, "model", None),
        effort=getattr(args, "effort", None),
    )


def _query_filters(args: argparse.Namespace) -> QueryFilters:
    supplied = _json_object(getattr(args, "filters", "{}"), "filters")
    values = {
        "since": getattr(args, "since", None),
        "until": getattr(args, "until", None),
        "model": getattr(args, "model", None),
        "effort": getattr(args, "effort", None),
        "thread_key": getattr(args, "thread_key", getattr(args, "thread", None)),
        "project": getattr(args, "project", None),
        "origin": getattr(args, "origin", None),
        "service_tier": getattr(args, "service_tier", None),
        "subagent_role": getattr(args, "subagent_role", None),
        "subagent_type": getattr(args, "subagent_type", None),
        "parent_thread_key": getattr(args, "parent_thread_key", None),
    }
    known = set(QueryFilters.__dataclass_fields__)
    unknown = set(supplied) - known
    if unknown:
        raise ValueError(f"unknown filter: {sorted(unknown)[0]}")
    values.update(supplied)
    return QueryFilters(**{key: value for key, value in values.items() if value is not None})


def _comparison(value: str) -> ComparisonWindow | None:
    payload = _json_object(value, "comparison")
    if not payload:
        return None
    if set(payload) != {"since", "until"}:
        raise ValueError("comparison must contain exactly 'since' and 'until'")
    return ComparisonWindow(since=str(payload["since"]), until=str(payload["until"]))


def _json_object(value: str, field_name: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return payload


def _csv_values(values: Sequence[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(item.strip() for value in values for item in value.split(",") if item.strip())


def _default_measures(entity: QueryEntity) -> tuple[QueryMeasure, ...]:
    if entity not in QUERY_ENTITY_CAPABILITIES:
        raise ValueError(f"unsupported query entity: {entity}")
    return ("tokens",)


def _open_target(args: argparse.Namespace, origin: str | None) -> dict[str, object]:
    if args.target_json:
        target = _json_object(args.target_json, "target-json")
        return _normalize_supplied_target(target, origin)
    if args.call_id:
        return build_dashboard_target_v2(
            evidence_kind="call", selector_id=args.call_id, service_origin=origin
        )
    if args.thread_key:
        return build_dashboard_target_v2(
            evidence_kind="thread", selector_id=args.thread_key, service_origin=origin
        )
    if args.target_id:
        return _target_from_id(args.target_id, origin)
    relative = "/react-dashboard.html?view=home"
    return {
        "schema": "codex-usage-tracker-dashboard-target-v2",
        "target_id": "home",
        "surface": "home",
        "evidence_kind": "none",
        "selectors": {},
        "relative_url": relative,
        "absolute_url": f"{origin}{relative}" if origin else None,
        "fallback_instruction": None if origin else "codex-usage-tracker service serve --open",
    }


def _target_from_id(target_id: str, origin: str | None) -> dict[str, object]:
    parts = target_id.split(":")
    if len(parts) < 4 or parts[0] not in {"evidence", "explore"}:
        raise ValueError("target-id must be a dashboard target v2 identifier")
    surface, kind, history = parts[0], parts[1], parts[-1]
    selector = ":".join(parts[2:-1])
    return build_dashboard_target_v2(
        evidence_kind=kind,
        selector_id=selector,
        history=history,
        target_purpose="explore" if surface == "explore" else "evidence",
        service_origin=origin,
    )


def _normalize_supplied_target(
    target: Mapping[str, object], origin: str | None
) -> dict[str, object]:
    if target.get("schema") != "codex-usage-tracker-dashboard-target-v2":
        raise ValueError("target-json must use codex-usage-tracker-dashboard-target-v2")
    relative = target.get("relative_url")
    if not isinstance(relative, str) or not relative.startswith("/react-dashboard.html?"):
        raise ValueError("target-json has an invalid relative_url")
    result = dict(target)
    result["absolute_url"] = (
        f"{origin}{relative}" if origin else _safe_loopback_url(target, relative)
    )
    return result


def _safe_loopback_url(target: Mapping[str, object], relative: str) -> str | None:
    absolute = target.get("absolute_url")
    if not isinstance(absolute, str):
        return None
    parsed = urlsplit(absolute)
    expected = urlsplit(relative)
    is_matching_loopback = (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost"}
        and parsed.path == expected.path
        and parsed.query == expected.query
        and not parsed.fragment
    )
    return absolute if is_matching_loopback else None


def _active_service_origin() -> str | None:
    status = dashboard_service_status(home=Path.home())
    return status.url if status.reachable else None


def _write_json(payload: object, stdout: TextIO | None) -> None:
    stream = sys.stdout if stdout is None else stdout
    if is_dataclass(payload) and not isinstance(payload, type):
        payload = asdict(payload)
    json.dump(payload_mapping(payload), stream, ensure_ascii=False, allow_nan=False, indent=2)
    stream.write("\n")


def _replacement_from_alias(alias: str) -> str:
    if alias.startswith(("init-", "update-", "pin-", "parse-", "allowance-")):
        return "config"
    if alias in {"install-plugin", "upgrade-plugin", "uninstall-plugin"}:
        return "setup"
    return (
        "admin"
        if alias
        in {"inspect-log", "rebuild-index", "reset-db", "source-coverage", "support-bundle"}
        else "analyze"
    )
