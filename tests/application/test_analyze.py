import threading
import time
from dataclasses import dataclass, replace
from types import MappingProxyType

import pytest

from codex_usage_tracker.analytics.analysis_catalog import ANALYSIS_CATALOG, AnalysisCatalogEntry
from codex_usage_tracker.analytics.analysis_models import (
    AnalysisGoal,
    AnalysisReportV2,
    AnalysisRequest,
    ComparisonWindow,
    WorkEstimate,
)
from codex_usage_tracker.application import analyze as analyze_module
from codex_usage_tracker.application.analyze import (
    AnalysisRuntime,
    analysis_semantic_key,
    analyze_usage,
)
from codex_usage_tracker.application.context import RequestContext
from codex_usage_tracker.application.errors import RequestContextError, RequestValidationError
from codex_usage_tracker.application.query_models import QueryFilters
from codex_usage_tracker.core.contracts import FreshnessV1, ScopeV1
from codex_usage_tracker.core.contracts.serialization import payload_mapping, serialized_size
from codex_usage_tracker.core.json_contracts import validate_json_payload_contract
from tests.application.fixtures.analysis_cases import ANALYSIS_CASES, synthetic_analysis_report


@dataclass(frozen=True)
class _Strategy:
    goal: AnalysisGoal
    recommended: str = "sync"
    block: threading.Event | None = None
    mode: str = "normal"
    count: int = 1
    version: str = "1.0.0"
    seen: list[AnalysisRequest] | None = None
    summary_size: int = 0

    @property
    def strategy_id(self) -> str:
        return f"synthetic.{self.goal}"

    @property
    def strategy_version(self) -> str:
        return self.version

    def estimate(self, request: AnalysisRequest, _context: RequestContext) -> WorkEstimate:
        if self.seen is not None:
            self.seen.append(request)
        if self.mode == "estimate_fail":
            raise RuntimeError("/private/estimate-path")
        return WorkEstimate(
            self.strategy_id,
            self.strategy_version,
            20 if self.recommended == "async" else 1,
            8,
            request.evidence_limit,
            self.recommended,  # type: ignore[arg-type]
            "synthetic estimate",
        )

    def analyze(self, request: AnalysisRequest, context: RequestContext) -> AnalysisReportV2:
        if self.seen is not None:
            self.seen.append(request)
        if self.block is not None:
            self.block.wait(timeout=2)
        if self.mode == "fail":
            raise RuntimeError("/private/user/path")
        report = synthetic_analysis_report(self.goal, context)
        if self.summary_size:
            report = replace(report, summary="x" * self.summary_size)
        if self.mode == "wrong_goal":
            return replace(report, goal="cache_failure")
        if self.mode == "duplicate":
            return replace(report, findings=report.findings * 2)
        if self.mode == "empty":
            return replace(report, evidence=())
        if self.count == 1:
            return report
        evidence = tuple(
            replace(report.evidence[0], evidence_id=f"evidence-{index}")
            for index in range(self.count)
        )
        findings = tuple(
            replace(
                report.findings[0],
                finding_id=f"finding-{index}",
                evidence_ids=(f"evidence-{index}",),
            )
            for index in range(self.count)
        )
        return replace(report, evidence=evidence, findings=findings)


def _context(
    strategy: _Strategy, *, revision: str = "generation:7", pricing: float = 1.0
) -> RequestContext:
    entry = AnalysisCatalogEntry(
        strategy.goal, strategy, ("canonical_usage",), (), 20, 8, ("overview",), "facts unavailable"
    )
    runtime = AnalysisRuntime(
        catalog=MappingProxyType({strategy.goal: entry}),
        pricing_fingerprint="pricing:v1",
        rate_card_fingerprint="rate-card:v1",
        thresholds_fingerprint="thresholds:v1",
        catalog_version="catalog:v1",
    )
    return RequestContext(
        revision,
        FreshnessV1(None, revision, None, "fresh", None, 300, None),
        ScopeV1(None, None, "active", "strict", {}),
        1,
        1,
        0,
        pricing,
        pricing,
        1.0,
        runtime,
    )


@pytest.mark.parametrize(("count", "limit", "expected"), [(10, 8, 8), (25, 20, 20)])
def test_sync_bounds_and_result_exclusivity(count: int, limit: int, expected: int) -> None:
    result = analyze_usage(
        AnalysisRequest("token_waste", QueryFilters(), evidence_limit=limit, execution="sync"),
        _context(_Strategy("token_waste", count=count)),
    )
    assert len(result.completed.findings) == len(result.completed.evidence) == expected  # type: ignore[union-attr]


def test_execution_routing_and_estimate_failures() -> None:
    expensive = _Strategy("token_waste", recommended="async")
    with pytest.raises(RequestValidationError, match="synchronous ceiling"):
        analyze_usage(
            AnalysisRequest("token_waste", QueryFilters(), execution="sync"), _context(expensive)
        )
    for execution in ("async", "auto"):
        result = analyze_usage(
            AnalysisRequest("token_waste", QueryFilters(), execution=execution),  # type: ignore[arg-type]
            _context(expensive),
        )
        assert result.job is not None
    failing = _Strategy("token_waste", mode="estimate_fail")
    assert analyze_usage(
        AnalysisRequest("token_waste", QueryFilters(), execution="async"), _context(failing)
    ).job
    safe = analyze_usage(
        AnalysisRequest("token_waste", QueryFilters()), _context(failing)
    ).completed
    assert safe is not None and safe.findings == ()
    context = _context(_Strategy("token_waste"))
    with pytest.raises(RequestContextError, match="runtime"):
        analyze_usage(
            AnalysisRequest("token_waste", QueryFilters()), replace(context, analysis_runtime=None)
        )
    context.analysis_runtime.catalog = MappingProxyType({})  # type: ignore[union-attr]
    with pytest.raises(RequestValidationError, match="unsupported analysis goal"):
        analyze_usage(AnalysisRequest("token_waste", QueryFilters()), context)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (field, value)
        for field in (
            "pricing_fingerprint",
            "rate_card_fingerprint",
            "thresholds_fingerprint",
            "catalog_version",
        )
        for value in (None, "", 1)
    ],
)
def test_runtime_rejects_invalid_semantic_fingerprints(field: str, value: object) -> None:
    context = _context(_Strategy("token_waste"))
    runtime = context.analysis_runtime
    assert runtime is not None
    kwargs = {
        "catalog": runtime.catalog,
        "pricing_fingerprint": "pricing:v1",
        "rate_card_fingerprint": "rate-card:v1",
        "thresholds_fingerprint": "thresholds:v1",
        "catalog_version": "catalog:v1",
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match="non-empty strings"):
        AnalysisRuntime(**kwargs)  # type: ignore[arg-type]


def test_failed_async_analysis_is_private_not_reused_and_has_no_result() -> None:
    context = _context(_Strategy("token_waste", mode="fail"))
    request = AnalysisRequest("token_waste", QueryFilters(), execution="async")
    first = analyze_usage(request, context).job
    assert first is not None and context.analysis_runtime is not None
    deadline = time.monotonic() + 2
    status = context.analysis_runtime.job_service.status(first.job_id, include_result=True)
    while time.monotonic() < deadline and status.state not in {"failed", "completed"}:
        time.sleep(0.01)
        status = context.analysis_runtime.job_service.status(first.job_id, include_result=True)
    assert status.state == "failed" and status.result is None
    assert status.error is not None and status.error.code == "job.failed"
    assert "/private/" not in status.error.message
    retry = analyze_usage(request, context).job
    assert retry is not None and retry.job_id != first.job_id


def test_near_boundary_async_result_remains_retrievable() -> None:
    base_context = _context(_Strategy("token_waste"))
    base = synthetic_analysis_report("token_waste", base_context)
    overhead = serialized_size(payload_mapping(base)) - len(base.summary)
    summary_size = analyze_module.MAX_ANALYSIS_REPORT_BYTES - overhead - 64
    context = _context(_Strategy("token_waste", summary_size=summary_size))
    job = analyze_usage(
        AnalysisRequest("token_waste", QueryFilters(), execution="async"), context
    ).job
    assert job is not None and context.analysis_runtime is not None
    deadline = time.monotonic() + 2
    status = context.analysis_runtime.job_service.status(job.job_id, include_result=True)
    while time.monotonic() < deadline and status.state != "completed":
        time.sleep(0.01)
        status = context.analysis_runtime.job_service.status(job.job_id, include_result=True)
    assert status.result is not None and status.error is None
    assert serialized_size(status.to_payload()) <= analyze_module.MAX_ANALYSIS_JOB_BYTES


def test_facts_unavailable_async_report_remains_completed_and_reusable() -> None:
    context = _context(_Strategy("token_waste"))
    assert context.analysis_runtime is not None
    runtime = AnalysisRuntime(
        catalog=ANALYSIS_CATALOG,
        pricing_fingerprint="pricing:v1",
        rate_card_fingerprint="rate-card:v1",
        thresholds_fingerprint="thresholds:v1",
        catalog_version="catalog:v1",
    )
    context = replace(
        context,
        analysis_runtime=runtime,
        freshness=replace(context.freshness, state="stale"),
    )
    request = AnalysisRequest("token_waste", QueryFilters(), execution="async")
    first = analyze_usage(request, context).job
    assert first is not None
    deadline = time.monotonic() + 2
    status = runtime.job_service.status(first.job_id, include_result=True)
    while time.monotonic() < deadline and status.state != "completed":
        time.sleep(0.01)
        status = runtime.job_service.status(first.job_id, include_result=True)
    assert status.state == "completed" and status.result is not None
    assert analyze_usage(request, context).job.job_id == first.job_id  # type: ignore[union-attr]


def test_active_completed_and_revision_scoped_job_reuse() -> None:
    block = threading.Event()
    context = _context(_Strategy("token_waste", block=block))
    request = AnalysisRequest("token_waste", QueryFilters(), execution="async")
    key = analysis_semantic_key(request, context)
    first = analyze_usage(request, context).job
    second = analyze_usage(request, context).job
    assert first is not None and second is not None and first.job_id == second.job_id
    assert context.analysis_runtime is not None
    context.analysis_runtime.pricing_fingerprint = "pricing:changed"
    block.set()
    deadline = time.monotonic() + 2
    status = context.analysis_runtime.job_service.status(first.job_id, include_result=True)
    while time.monotonic() < deadline and status.state != "completed":
        time.sleep(0.01)
        status = context.analysis_runtime.job_service.status(first.job_id, include_result=True)
    assert status.result["analysis_id"] == f"analysis:{key.removeprefix('sha256:')}"  # type: ignore[index]
    context.analysis_runtime.pricing_fingerprint = "pricing:v1"
    assert analyze_usage(request, context).job.job_id == first.job_id  # type: ignore[union-attr]
    stale = replace(context, source_revision="generation:8")
    assert analyze_usage(request, stale).job.job_id != first.job_id  # type: ignore[union-attr]


@pytest.mark.parametrize("mode", ["fail", "wrong_goal", "duplicate"])
def test_invalid_strategy_output_is_private_structured_and_empty(mode: str) -> None:
    report = analyze_usage(
        AnalysisRequest("token_waste", QueryFilters()),
        _context(_Strategy("token_waste", mode=mode)),
    ).completed
    assert report is not None and report.findings == report.evidence == ()
    assert report.messages[0].code == "analysis.strategy_failed"
    assert "/private/" not in report.messages[0].message


def test_empty_evidence_and_partial_pricing_remain_nonfabricated() -> None:
    empty = analyze_usage(
        AnalysisRequest("token_waste", QueryFilters()),
        _context(_Strategy("token_waste", mode="empty")),
    ).completed
    partial = analyze_usage(
        AnalysisRequest("token_waste", QueryFilters()),
        _context(_Strategy("token_waste"), pricing=0.5),
    ).completed
    assert empty is not None and empty.findings == empty.evidence == ()
    assert partial is not None and "partial" in " ".join(partial.limitations).lower()
    assert partial.findings[0].confidence != "exact"


def test_semantic_key_covers_payload_dimensions_and_ignores_runtime_identity() -> None:
    strategy = _Strategy("token_waste")
    context = _context(strategy)
    request = AnalysisRequest("token_waste", QueryFilters(model="gpt-5.5"))
    baseline = analysis_semantic_key(request, context)
    requests = (
        replace(request, filters=QueryFilters(model="gpt-5.6")),
        replace(request, history="all"),
        replace(request, evidence_limit=9),
        replace(
            request, comparison=ComparisonWindow("2026-07-01T00:00:00Z", "2026-07-02T00:00:00Z")
        ),
    )
    contexts = (
        replace(context, source_revision="generation:8"),
        replace(context, canonical_rows=2),
        replace(context, freshness=replace(context.freshness, state="stale")),
        replace(context, scope=replace(context.scope, privacy_mode="normal")),
        _context(replace(strategy, version="2.0.0")),
        _context(_Strategy("cache_failure")),
    )
    assert all(analysis_semantic_key(item, context) != baseline for item in requests)
    assert all(
        analysis_semantic_key(
            request
            if item.analysis_runtime.catalog.get("token_waste")
            else AnalysisRequest("cache_failure", QueryFilters()),
            item,
        )
        != baseline
        for item in contexts
    )  # type: ignore[union-attr]
    assert analysis_semantic_key(replace(request, execution="async"), context) == baseline
    for field in (
        "pricing_fingerprint",
        "rate_card_fingerprint",
        "thresholds_fingerprint",
        "catalog_version",
    ):
        changed = _context(strategy)
        setattr(changed.analysis_runtime, field, f"changed:{field}")  # type: ignore[union-attr]
        assert analysis_semantic_key(request, changed) != baseline
    other = _context(strategy)
    other.analysis_runtime.local_path = "/private/b"  # type: ignore[union-attr,attr-defined]
    assert analysis_semantic_key(request, other) == baseline


def test_request_normalization_validation_and_analysis_identity() -> None:
    seen: list[AnalysisRequest] = []
    context = _context(_Strategy("token_waste", seen=seen))
    raw = AnalysisRequest(
        "token_waste", QueryFilters(model=" gpt-5.5 ", since="2026-07-01T01:00:00+01:00")
    )
    canonical = AnalysisRequest(
        "token_waste", QueryFilters(model="gpt-5.5", since="2026-07-01T00:00:00Z")
    )
    first = analyze_usage(raw, context).completed
    second = analyze_usage(
        replace(canonical, filters=replace(canonical.filters, model="gpt-5.6")), context
    ).completed
    assert seen and all(item.filters.model == "gpt-5.5" for item in seen[:2])
    assert analysis_semantic_key(raw, context) == analysis_semantic_key(canonical, context)
    assert first is not None and second is not None and first.analysis_id != second.analysis_id
    with pytest.raises(ValueError, match="model must be a string"):
        analysis_semantic_key(AnalysisRequest("token_waste", QueryFilters(model=1)), context)  # type: ignore[arg-type]


@pytest.mark.parametrize(("goal", "record_id"), ANALYSIS_CASES)
def test_exact_contract_fixture_for_every_goal(goal: AnalysisGoal, record_id: str) -> None:
    request = AnalysisRequest(goal, QueryFilters())
    context = _context(_Strategy(goal))
    result = analyze_usage(request, context).completed
    expected = replace(
        synthetic_analysis_report(goal, context),
        analysis_id=f"analysis:{analysis_semantic_key(request, context).removeprefix('sha256:')}",
    )
    assert result == expected and result.evidence[0].selectors["record_id"] == record_id  # type: ignore[union-attr]
    assert validate_json_payload_contract(payload_mapping(result)) == []
