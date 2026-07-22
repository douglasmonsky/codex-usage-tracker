"""Stable, bounded status and capability use case."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from codex_usage_tracker.application.context import RequestContext, build_request_context
from codex_usage_tracker.application.requests import StatusRequest
from codex_usage_tracker.core.contracts import FreshnessV1, payload_mapping
from codex_usage_tracker.core.conversational_readiness import conversational_readiness
from codex_usage_tracker.dashboard_service import (
    DashboardServiceStatus,
    dashboard_service_status,
)
from codex_usage_tracker.pricing.config import load_pricing_config

STATUS_SCHEMA = "codex-usage-tracker.status.v2"
CORE_TOOL_NAMES = (
    "usage_status",
    "usage_refresh",
    "usage_analyze",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
)


def get_status(request: StatusRequest) -> dict[str, object]:
    """Return codex-usage-tracker.status.v2 without starting background work."""
    result, _context = _build_status(request)
    return result


def _build_status(request: StatusRequest) -> tuple[dict[str, object], RequestContext]:
    context = build_request_context(
        db_path=request.db_path,
        pricing_path=request.pricing_path,
        scope=request.scope,
    )
    freshness = _freshness_for_threshold(context.freshness, request.freshness_threshold_seconds)
    context = replace(context, freshness=freshness)
    pricing_config = load_pricing_config(request.pricing_path)
    readiness = conversational_readiness(codex_home=request.codex_home)
    service = _service_status(request)
    pricing_state = (
        "malformed"
        if pricing_config.error
        else "available"
        if pricing_config.loaded
        else "unavailable"
    )
    next_action = _next_action(
        freshness_state=freshness.state,
        pricing_state=pricing_state,
        readiness_state=readiness["state"],
    )
    result: dict[str, object] = {
        "schema": STATUS_SCHEMA,
        "index": payload_mapping(freshness),
        "parser": {
            "state": "available" if context.canonical_rows else "empty",
            "indexed_rows": context.canonical_rows,
            "source_revision": context.source_revision,
        },
        "sources": {
            "physical_rows": context.physical_rows,
            "canonical_rows": context.canonical_rows,
            "copied_rows_excluded": context.copied_rows_excluded,
        },
        "pricing": {
            "state": pricing_state,
            "billing_basis": pricing_config.billing_basis,
            "coverage": context.pricing_coverage,
            "credit_coverage": context.credit_coverage,
            "service_tier_coverage": context.service_tier_coverage,
            "error": pricing_config.error,
        },
        "accounting": payload_mapping(context.accounting),
        "conversational_readiness": dict(readiness),
        "mcp": {
            "active_profile": request.mcp_profile,
            "core_tools": list(CORE_TOOL_NAMES),
            "current_task_exposure": "not-verified",
        },
        "persistent_service": _service_payload(service),
        "next_action": next_action,
    }
    return result, context


def _freshness_for_threshold(freshness: FreshnessV1, threshold: float) -> FreshnessV1:
    if freshness.state in {"empty", "unknown"}:
        state = freshness.state
        reason = freshness.reason
    else:
        age = _age_seconds(freshness.refresh_completed_at or freshness.latest_indexed_event_at)
        if age is None:
            state = "unknown"
            reason = "The index has no parseable freshness timestamp."
        elif age <= threshold:
            state = "fresh"
            reason = "The usage index is within the freshness threshold."
        else:
            state = "stale"
            reason = "The usage index is older than the freshness threshold."
    return FreshnessV1(
        latest_indexed_event_at=freshness.latest_indexed_event_at,
        source_revision=freshness.source_revision,
        refresh_completed_at=freshness.refresh_completed_at,
        state=state,
        reason=reason,
        threshold_seconds=int(threshold),
        recommended_refresh_action=None if state == "fresh" else "usage_refresh",
    )


def _age_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _service_status(request: StatusRequest) -> DashboardServiceStatus:
    try:
        return dashboard_service_status(home=request.home)
    except (OSError, RuntimeError, ValueError) as exc:
        return DashboardServiceStatus(False, False, False, 47821, f"unavailable: {exc}")


def _service_payload(service: DashboardServiceStatus) -> dict[str, object]:
    return {
        "installed": service.installed,
        "loaded": service.loaded,
        "reachable": service.reachable,
        "port": service.port,
        "detail": service.detail,
        "url": service.url,
    }


def _next_action(
    *, freshness_state: str, pricing_state: str, readiness_state: str
) -> dict[str, object]:
    if readiness_state == "restart-required":
        return {
            "code": "restart_codex",
            "label": "Restart Codex and open a fresh task.",
            "tool": None,
            "arguments": {},
        }
    if readiness_state == "unavailable":
        return {
            "code": "setup_plugin",
            "label": "Configure the local Codex usage tracker plugin.",
            "tool": None,
            "arguments": {},
        }
    if freshness_state != "fresh":
        return {
            "code": "refresh_index",
            "label": "Refresh the bounded local usage index.",
            "tool": "usage_refresh",
            "arguments": {},
        }
    if pricing_state == "malformed":
        return {
            "code": "fix_pricing_config",
            "label": "Fix the malformed local pricing configuration.",
            "tool": None,
            "arguments": {},
        }
    if pricing_state == "unavailable":
        return {
            "code": "configure_pricing",
            "label": "Configure local pricing for cost coverage.",
            "tool": None,
            "arguments": {},
        }
    return {
        "code": "query_usage",
        "label": "Query the fresh local usage index.",
        "tool": "usage_query",
        "arguments": {},
    }
