"""Bounded query and analysis adapters for the core MCP profile."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, fields, is_dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.analytics.analysis_catalog import ANALYSIS_CATALOG, AnalysisCatalogEntry
from codex_usage_tracker.analytics.analysis_models import (
    AnalysisGoal,
    AnalysisRequest,
    ComparisonWindow,
)
from codex_usage_tracker.application.analyze import (
    ANALYSIS_RESULT_SCHEMA,
    AnalysisRuntime,
    AnalyzeResult,
    analyze_usage,
)
from codex_usage_tracker.application.context import RequestContext, build_request_context
from codex_usage_tracker.application.query import query_usage
from codex_usage_tracker.application.query_models import QueryFilters, QueryRequest, QueryResult
from codex_usage_tracker.application.query_validation import normalize_query_filters
from codex_usage_tracker.application.requests import HistoryScope, RequestScope
from codex_usage_tracker.core.contracts import (
    NextActionV1,
    enforce_payload_budget,
    envelope_payload,
    payload_mapping,
)
from codex_usage_tracker.core.json_contracts import validate_json_payload_contract
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.pricing.allowance_rate_card import load_bundled_rate_card, load_json_file
from codex_usage_tracker.pricing.config import load_pricing_config
from codex_usage_tracker.reports.recommendations import load_threshold_config

MAX_QUERY_PAYLOAD_BYTES = 256 * 1024
MAX_ANALYSIS_PAYLOAD_BYTES = 64 * 1024
MAX_ANALYSIS_JOB_PAYLOAD_BYTES = 16 * 1024
ANALYSIS_JOB_SCHEMA = "codex-usage-tracker.analysis-job.v1"
QueryService = Callable[..., QueryResult]
AnalysisService = Callable[[AnalysisRequest, RequestContext], AnalyzeResult]
ContextBuilder = Callable[..., RequestContext]


def usage_query(
    entity: str,
    measures: list[str],
    filters: dict[str, object] | None = None,
    group_by: list[str] | None = None,
    order_by: str | None = None,
    order: str = "desc",
    limit: int = 20,
    cursor: str | None = None,
    history: str = "active",
) -> dict[str, object]:
    """Answer exact tabular or grouped usage questions.

    Example: ``entity='model', measures=['tokens'], group_by=['effort']``.
    Use ``usage_analyze`` instead for broad diagnostic or explanatory questions.
    """
    return build_usage_query(
        entity=entity,
        measures=measures,
        filters=filters,
        group_by=group_by,
        order_by=order_by,
        order=order,
        limit=limit,
        cursor=cursor,
        history=history,
    )


def usage_analyze(
    goal: str,
    filters: dict[str, object] | None = None,
    history: str = "active",
    evidence_limit: int = 8,
    comparison: dict[str, object] | None = None,
    execution: str = "auto",
) -> dict[str, object]:
    """Explain a supported usage pattern with bounded aggregate evidence.

    Example: ``goal='token_waste', filters={'since': '2026-07-15T00:00:00Z',
    'until': '2026-07-22T00:00:00Z'}``. Use this for broad diagnostic questions;
    use ``usage_query`` for exact tables and groupings.
    """
    return build_usage_analyze(
        goal=goal,
        filters=filters,
        history=history,
        evidence_limit=evidence_limit,
        comparison=comparison,
        execution=execution,
    )


def build_usage_query(
    *,
    entity: str,
    measures: Sequence[str],
    filters: Mapping[str, object] | None = None,
    group_by: Sequence[str] | None = None,
    order_by: str | None = None,
    order: str = "desc",
    limit: int = 20,
    cursor: str | None = None,
    history: str = "active",
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    query_service: QueryService = query_usage,
    context_builder: ContextBuilder = build_request_context,
) -> dict[str, object]:
    request = _query_request(
        entity, measures, filters, group_by, order_by, order, limit, cursor, history
    )
    normalized = normalize_query_filters(request.filters)
    request = replace(request, filters=normalized)
    context = context_builder(
        db_path=db_path, pricing_path=pricing_path, scope=_request_scope(normalized, history)
    )
    result = query_service(
        request,
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        context=context,
    )
    payload = envelope_payload(
        tool="usage_query",
        result_schema=result.schema,
        result=result,
        scope=context.scope,
        freshness=context.freshness,
        accounting=context.accounting,
        data_class="aggregate",
        dashboard_targets=(
            () if result.dashboard_target is None else (payload_mapping(result.dashboard_target),)
        ),
    )
    enforce_payload_budget(payload, MAX_QUERY_PAYLOAD_BYTES, "usage_query")
    return payload


def build_usage_analyze(
    *,
    goal: str,
    filters: Mapping[str, object] | None = None,
    history: str = "active",
    evidence_limit: int = 8,
    comparison: Mapping[str, object] | None = None,
    execution: str = "auto",
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    runtime: AnalysisRuntime | None = None,
    catalog: Mapping[AnalysisGoal, AnalysisCatalogEntry] = ANALYSIS_CATALOG,
    job_service: JobService | None = None,
    analysis_service: AnalysisService = analyze_usage,
    context_builder: ContextBuilder = build_request_context,
) -> dict[str, object]:
    request = _analysis_request(goal, filters, history, evidence_limit, comparison, execution)
    normalized = normalize_query_filters(request.filters)
    request = replace(request, filters=normalized)
    context = context_builder(
        db_path=db_path, pricing_path=pricing_path, scope=_request_scope(normalized, history)
    )
    runtime = runtime or _analysis_runtime(
        pricing_path, rate_card_path, thresholds_path, catalog, job_service
    )
    outcome = analysis_service(request, replace(context, analysis_runtime=runtime))
    payload = _analysis_envelope(outcome, context)
    enforce_payload_budget(
        payload,
        MAX_ANALYSIS_JOB_PAYLOAD_BYTES if outcome.job else MAX_ANALYSIS_PAYLOAD_BYTES,
        "usage_analyze",
    )
    return payload


def _query_request(
    entity: str,
    measures: Sequence[str],
    filters: Mapping[str, object] | None,
    group_by: Sequence[str] | None,
    order_by: str | None,
    order: str,
    limit: int,
    cursor: str | None,
    history: str,
) -> QueryRequest:
    return QueryRequest(
        entity=cast(Any, entity),
        measures=cast(Any, _strings(measures, "measures", True)),
        filters=_filters(filters),
        group_by=_strings(group_by or (), "group_by"),
        order_by=order_by,
        order=cast(Any, order),
        limit=limit,
        cursor=cursor,
        history=cast(Any, history),
    )


def _analysis_request(
    goal: str,
    filters: Mapping[str, object] | None,
    history: str,
    evidence_limit: int,
    comparison: Mapping[str, object] | None,
    execution: str,
) -> AnalysisRequest:
    return AnalysisRequest(
        goal=cast(Any, goal),
        filters=_filters(filters),
        history=cast(Any, history),
        evidence_limit=evidence_limit,
        comparison=_comparison(comparison),
        execution=cast(Any, execution),
    )


def _filters(value: Mapping[str, object] | None) -> QueryFilters:
    if value is None:
        return QueryFilters()
    if not isinstance(value, Mapping):
        raise ValueError("filters must be an object")
    unknown = set(value) - {item.name for item in fields(QueryFilters)}
    if unknown:
        raise ValueError(f"filters.{sorted(unknown)[0]} is not supported")
    return QueryFilters(**dict(value))  # type: ignore[arg-type]


def _comparison(value: Mapping[str, object] | None) -> ComparisonWindow | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("comparison must be an object")
    unknown = set(value) - {"since", "until"}
    if unknown:
        raise ValueError(f"comparison.{sorted(unknown)[0]} is not supported")
    for name in ("since", "until"):
        if name not in value:
            raise ValueError(f"comparison.{name} is required")
    return ComparisonWindow(cast(str, value["since"]), cast(str, value["until"]))


def _strings(value: Sequence[str], name: str, required: bool = False) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array of strings")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must contain only strings")
    if required and not value:
        raise ValueError(f"{name} must not be empty")
    return tuple(value)


def _request_scope(filters: QueryFilters, history: str) -> RequestScope:
    return RequestScope(
        since=filters.since,
        until=filters.until,
        history=cast(HistoryScope, history),
        project=filters.project,
        thread_key=filters.thread_key,
        model=filters.model,
        effort=filters.effort,
    )


def _analysis_envelope(outcome: AnalyzeResult, context: RequestContext) -> dict[str, object]:
    if outcome.completed is not None:
        result_schema = ANALYSIS_RESULT_SCHEMA
        result: object = outcome.completed
        targets = tuple(
            {"view": item, "arguments": {}} for item in outcome.completed.dashboard_destinations
        )
        actions: tuple[NextActionV1, ...] = ()
    else:
        assert outcome.job is not None
        result_schema = ANALYSIS_JOB_SCHEMA
        result = outcome.job.to_payload()
        result["schema"] = ANALYSIS_JOB_SCHEMA
        errors = validate_json_payload_contract(result)
        if errors:
            raise ValueError(f"analysis job contract invalid: {errors[0]}")
        targets = ()
        actions = (
            NextActionV1(
                code="job.poll",
                label="Poll analysis job",
                tool="usage_job_status",
                arguments={"job_id": outcome.job.job_id},
            ),
        )
    return envelope_payload(
        tool="usage_analyze",
        result_schema=result_schema,
        result=result,
        scope=context.scope,
        freshness=context.freshness,
        accounting=context.accounting,
        data_class="aggregate",
        dashboard_targets=targets,
        next_actions=actions,
    )


def _analysis_runtime(
    pricing_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
    catalog: Mapping[AnalysisGoal, AnalysisCatalogEntry],
    job_service: JobService | None,
) -> AnalysisRuntime:
    fingerprints = _semantic_fingerprints(pricing_path, rate_card_path, thresholds_path, catalog)
    if catalog is ANALYSIS_CATALOG and job_service is None:
        return _cached_default_analysis_runtime(*fingerprints)
    from codex_usage_tracker.application.refresh import default_job_service

    return AnalysisRuntime(
        catalog=catalog,
        job_service=job_service or default_job_service(),
        pricing_fingerprint=fingerprints[0],
        rate_card_fingerprint=fingerprints[1],
        thresholds_fingerprint=fingerprints[2],
        catalog_version=fingerprints[3],
    )


@lru_cache(maxsize=16)
def _cached_default_analysis_runtime(
    pricing_fingerprint: str,
    rate_card_fingerprint: str,
    thresholds_fingerprint: str,
    catalog_version: str,
) -> AnalysisRuntime:
    from codex_usage_tracker.application.refresh import default_job_service

    return AnalysisRuntime(
        job_service=default_job_service(),
        pricing_fingerprint=pricing_fingerprint,
        rate_card_fingerprint=rate_card_fingerprint,
        thresholds_fingerprint=thresholds_fingerprint,
        catalog_version=catalog_version,
    )


def _semantic_fingerprints(
    pricing_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
    catalog: Mapping[AnalysisGoal, AnalysisCatalogEntry],
) -> tuple[str, str, str, str]:
    rate_card = (
        load_json_file(rate_card_path) if rate_card_path.is_file() else load_bundled_rate_card()
    )
    entries = tuple(
        {
            "goal": goal,
            "strategy_id": entry.strategy.strategy_id,
            "strategy_version": entry.strategy.strategy_version,
            "required_facts": entry.required_facts,
            "optional_facts": entry.optional_facts,
            "max_evidence_records": entry.max_evidence_records,
            "sync_work_ceiling": entry.sync_work_ceiling,
            "dashboard_destinations": entry.dashboard_destinations,
            "missing_fact_fallback": entry.missing_fact_fallback,
            "implementation_status": entry.implementation_status,
        }
        for goal, entry in sorted(catalog.items())
    )
    return (
        _fingerprint(_effective_config(load_pricing_config(pricing_path))),
        _fingerprint(rate_card),
        _fingerprint(_effective_config(load_threshold_config(thresholds_path))),
        _fingerprint(entries),
    )


def _effective_config(value: object) -> object:
    raw = asdict(value) if is_dataclass(value) and not isinstance(value, type) else value
    if isinstance(raw, Mapping):
        return {
            key: _effective_config(item)
            for key, item in raw.items()
            if key not in {"path", "error"}
        }
    if isinstance(raw, set | frozenset):
        values = [_effective_config(item) for item in raw]
        return sorted(values, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return [_effective_config(item) for item in raw]
    return raw


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
