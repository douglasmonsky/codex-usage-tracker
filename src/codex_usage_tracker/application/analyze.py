from __future__ import annotations

import hashlib
import secrets
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from codex_usage_tracker.analytics.analysis_catalog import (
    ANALYSIS_CATALOG,
    AnalysisCatalogEntry,
)
from codex_usage_tracker.analytics.analysis_models import (
    AnalysisGoal,
    AnalysisReportV2,
    AnalysisRequest,
)
from codex_usage_tracker.application.context import RequestContext
from codex_usage_tracker.application.errors import RequestContextError, RequestValidationError
from codex_usage_tracker.application.query_validation import normalize_query_filters
from codex_usage_tracker.core.contracts import MessageV1, enforce_payload_budget, payload_mapping
from codex_usage_tracker.core.contracts.claims import validate_findings
from codex_usage_tracker.core.contracts.serialization import serialized_json
from codex_usage_tracker.jobs.adapters import AnalysisJobAdapter
from codex_usage_tracker.jobs.models import JobStatusV1
from codex_usage_tracker.jobs.service import MAX_SEMANTIC_JOBS, JobService

ANALYSIS_RESULT_SCHEMA = "codex-usage-tracker.analysis.v2"
MAX_ANALYSIS_JOB_BYTES = 64 * 1024
ANALYSIS_JOB_ENVELOPE_RESERVE_BYTES = 4 * 1024
MAX_ANALYSIS_REPORT_BYTES = MAX_ANALYSIS_JOB_BYTES - ANALYSIS_JOB_ENVELOPE_RESERVE_BYTES


@dataclass(frozen=True)
class AnalyzeResult:
    completed: AnalysisReportV2 | None = None
    job: JobStatusV1 | None = None

    def __post_init__(self) -> None:
        if (self.completed is None) == (self.job is None):
            raise ValueError("exactly one of completed or job is required")


@dataclass
class _AnalysisRecord:
    job_id: str
    source_revision: str | None
    status: str
    created_at: str
    updated_at: str
    result: dict[str, object] | None = None


class AnalysisRuntime:
    def __init__(
        self,
        *,
        catalog: Mapping[AnalysisGoal, AnalysisCatalogEntry] = ANALYSIS_CATALOG,
        job_service: JobService | None = None,
        pricing_fingerprint: str,
        rate_card_fingerprint: str,
        thresholds_fingerprint: str,
        catalog_version: str,
    ) -> None:
        fingerprints = (
            pricing_fingerprint,
            rate_card_fingerprint,
            thresholds_fingerprint,
            catalog_version,
        )
        if not all(isinstance(value, str) and value for value in fingerprints):
            raise ValueError("analysis semantic fingerprints must be non-empty strings")
        self.catalog = catalog
        self.job_service = job_service or JobService()
        self.pricing_fingerprint = pricing_fingerprint
        self.rate_card_fingerprint = rate_card_fingerprint
        self.thresholds_fingerprint = thresholds_fingerprint
        self.catalog_version = catalog_version
        self._lock = threading.RLock()
        self._records: OrderedDict[str, _AnalysisRecord] = OrderedDict()

    def start(
        self,
        semantic_key: str,
        request: AnalysisRequest,
        context: RequestContext,
        entry: AnalysisCatalogEntry,
    ) -> JobStatusV1:
        with self._lock:
            reusable = self.job_service.reusable(
                semantic_key,
                source_revision=context.source_revision,
                result_schema=ANALYSIS_RESULT_SCHEMA,
            )
            if reusable is not None:
                return reusable
            self._prune_records()
            if len(self._records) >= MAX_SEMANTIC_JOBS:
                raise RequestContextError("analysis job capacity is temporarily full")
            now = _utc_now()
            job_id = f"analysis_{secrets.token_urlsafe(12)}"
            record = _AnalysisRecord(job_id, context.source_revision, "queued", now, now)
            self._records[job_id] = record
            adapter = AnalysisJobAdapter(
                self._read,
                kind="analysis",
                request_hash=semantic_key,
                result_schema=ANALYSIS_RESULT_SCHEMA,
                result_budget=MAX_ANALYSIS_JOB_BYTES,
            )
            self.job_service.register_semantic(
                kind="analysis", job_id=job_id, adapter=adapter, semantic_key=semantic_key
            )
        thread = threading.Thread(
            target=self._run,
            args=(record, request, context, entry, semantic_key),
            name=f"usage-analysis-{job_id[-8:]}",
            daemon=True,
        )
        thread.start()
        return self.job_service.status(job_id)

    def _prune_records(self) -> None:
        for job_id, record in tuple(self._records.items()):
            if len(self._records) < MAX_SEMANTIC_JOBS:
                break
            if record.status in {"completed", "failed", "cancelled"}:
                self._records.pop(job_id, None)
                self.job_service.discard_semantic_job(job_id)

    def _run(
        self,
        record: _AnalysisRecord,
        request: AnalysisRequest,
        context: RequestContext,
        entry: AnalysisCatalogEntry,
        semantic_key: str,
    ) -> None:
        self._update(record, status="running")
        try:
            report = _run_strategy(entry, request, context, semantic_key)
        except Exception:  # noqa: BLE001 - adapters expose only a privacy-safe failed status.
            self._update(record, status="failed")
        else:
            self._update(record, status="completed", result=payload_mapping(report))

    def _update(
        self,
        record: _AnalysisRecord,
        *,
        status: str,
        result: dict[str, object] | None = None,
    ) -> None:
        with self._lock:
            record.status = status
            record.updated_at = _utc_now()
            record.result = result

    def _read(self, job_id: str, *, include_result: bool = False) -> dict[str, object]:
        with self._lock:
            record = self._records[job_id]
            progress = 100 if record.status == "completed" else 0
            return {
                "job_id": job_id,
                "status": record.status,
                "stage": "complete" if record.status == "completed" else record.status,
                "source_revision": record.source_revision,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "completed_at": record.updated_at if record.status == "completed" else None,
                "progress": {"percent": progress},
                "result": record.result if include_result else None,
            }


def analyze_usage(request: AnalysisRequest, context: RequestContext) -> AnalyzeResult:
    runtime = context.analysis_runtime
    if runtime is None:
        raise RequestContextError("analysis runtime is required")
    entry = runtime.catalog.get(request.goal)
    if entry is None:
        raise RequestValidationError(f"unsupported analysis goal: {request.goal}")
    canonical_request = replace(request, filters=normalize_query_filters(request.filters))
    key = analysis_semantic_key(canonical_request, context)
    if request.execution == "async":
        return AnalyzeResult(job=runtime.start(key, canonical_request, context, entry))
    try:
        estimate = entry.strategy.estimate(canonical_request, context)
    except Exception:  # noqa: BLE001 - estimation failures use the safe report boundary.
        return AnalyzeResult(completed=_error_report(entry, context, key))
    if request.execution == "sync" and estimate.estimated_work_units > entry.sync_work_ceiling:
        raise RequestValidationError("analysis estimate exceeds the synchronous ceiling")
    execution = estimate.recommended_execution if request.execution == "auto" else request.execution
    if execution == "async":
        return AnalyzeResult(job=runtime.start(key, canonical_request, context, entry))
    return AnalyzeResult(completed=_execute(entry, canonical_request, context, key))


def analysis_semantic_key(request: AnalysisRequest, context: RequestContext) -> str:
    runtime = context.analysis_runtime
    if runtime is None:
        raise RequestContextError("analysis runtime is required")
    entry = runtime.catalog.get(request.goal)
    if entry is None:
        raise RequestValidationError(f"unsupported analysis goal: {request.goal}")
    semantic = {
        "source_revision": context.source_revision,
        "goal": request.goal,
        "filters": normalize_query_filters(request.filters),
        "history": request.history,
        "evidence_limit": request.evidence_limit,
        "comparison": request.comparison,
        "strategy_id": entry.strategy.strategy_id,
        "strategy_version": entry.strategy.strategy_version,
        "pricing_fingerprint": runtime.pricing_fingerprint,
        "rate_card_fingerprint": runtime.rate_card_fingerprint,
        "thresholds_fingerprint": runtime.thresholds_fingerprint,
        "catalog_version": runtime.catalog_version,
        "accounting": context.accounting,
        "scope": context.scope,
        "freshness_state": context.freshness.state,
    }
    digest = hashlib.sha256(serialized_json(semantic).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _execute(
    entry: AnalysisCatalogEntry,
    request: AnalysisRequest,
    context: RequestContext,
    semantic_key: str,
) -> AnalysisReportV2:
    try:
        return _run_strategy(entry, request, context, semantic_key)
    except Exception:  # noqa: BLE001 - application boundary must remain privacy-safe.
        return _error_report(entry, context, semantic_key)


def _run_strategy(
    entry: AnalysisCatalogEntry,
    request: AnalysisRequest,
    context: RequestContext,
    semantic_key: str,
) -> AnalysisReportV2:
    report = entry.strategy.analyze(request, context)
    if report.goal != entry.goal:
        raise ValueError("strategy report goal does not match catalog goal")
    return _bounded_report(report, entry, request, context, semantic_key)


def _bounded_report(
    report: AnalysisReportV2,
    entry: AnalysisCatalogEntry,
    request: AnalysisRequest,
    context: RequestContext,
    semantic_key: str,
) -> AnalysisReportV2:
    limit = min(request.evidence_limit, entry.max_evidence_records, 20)
    evidence = tuple(report.evidence[:limit])
    evidence_ids = {item.evidence_id for item in evidence}
    if len(evidence_ids) != len(evidence):
        raise ValueError("strategy evidence identifiers must be unique")
    findings = tuple(
        finding
        for finding in report.findings
        if finding.evidence_ids and set(finding.evidence_ids) <= evidence_ids
    )[:limit]
    if len({item.finding_id for item in findings}) != len(findings):
        raise ValueError("strategy finding identifiers must be unique")
    limitations = list(report.limitations)
    partial = context.pricing_coverage is None or context.pricing_coverage < 1
    partial = partial or context.credit_coverage is None or context.credit_coverage < 1
    if partial:
        limitations.append("Pricing or credit coverage is partial; estimates are not exact.")
        findings = tuple(
            replace(
                finding,
                confidence="medium" if finding.confidence == "exact" else finding.confidence,
                caveat_codes=tuple(dict.fromkeys((*finding.caveat_codes, "partial_pricing"))),
            )
            for finding in findings
        )
    validate_findings(findings)
    bounded = replace(
        report,
        analysis_id=f"analysis:{semantic_key.removeprefix('sha256:')}",
        findings=findings,
        evidence=evidence,
        strategy_id=entry.strategy.strategy_id,
        strategy_version=entry.strategy.strategy_version,
        source_revision=context.source_revision,
        accounting=context.accounting,
        limitations=tuple(dict.fromkeys(limitations)),
        dashboard_destinations=entry.dashboard_destinations,
    )
    enforce_payload_budget(payload_mapping(bounded), MAX_ANALYSIS_REPORT_BYTES, "analysis")
    return bounded


def _error_report(
    entry: AnalysisCatalogEntry, context: RequestContext, semantic_key: str
) -> AnalysisReportV2:
    report = AnalysisReportV2(
        analysis_id=f"analysis:{semantic_key.removeprefix('sha256:')}",
        goal=entry.goal,
        summary="Analysis could not be completed; no conclusion was generated.",
        findings=(),
        evidence=(),
        methodology=("The strategy stopped at a privacy-safe application boundary.",),
        suggested_questions=(),
        strategy_id=entry.strategy.strategy_id,
        strategy_version=entry.strategy.strategy_version,
        source_revision=context.source_revision,
        accounting=context.accounting,
        messages=(
            MessageV1(
                code="analysis.strategy_failed",
                severity="blocking",
                message="The analysis strategy could not complete safely.",
            ),
        ),
        limitations=("No analytical conclusion or finding was generated.",),
        dashboard_destinations=entry.dashboard_destinations,
    )
    enforce_payload_budget(payload_mapping(report), MAX_ANALYSIS_REPORT_BYTES, "analysis")
    return report


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
