"""Transport-independent application facade shared by local interfaces."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.analytics.analysis_catalog import ANALYSIS_CATALOG
from codex_usage_tracker.analytics.analysis_models import ANALYSIS_GOALS, AnalysisRequest
from codex_usage_tracker.application.allowance import get_allowance
from codex_usage_tracker.application.allowance_models import AllowanceRequest
from codex_usage_tracker.application.analyze import AnalysisRuntime, analyze_usage
from codex_usage_tracker.application.container import (
    ApplicationContainer,
)
from codex_usage_tracker.application.evidence import get_evidence
from codex_usage_tracker.application.job_status import get_job_status
from codex_usage_tracker.application.query import query_usage
from codex_usage_tracker.application.query_models import (
    ALL_QUERY_MEASURES,
    QUERY_ENTITY_CAPABILITIES,
    QueryFilters,
    QueryRequest,
)
from codex_usage_tracker.application.query_validation import normalize_query_filters
from codex_usage_tracker.application.refresh import refresh_usage
from codex_usage_tracker.application.requests import (
    JobStatusRequest,
    RefreshRequest,
    RequestScope,
    StatusRequest,
)
from codex_usage_tracker.application.status import (
    ConversationalReadinessProvider,
    DatabaseIntegrityStatusProvider,
    get_status,
)
from codex_usage_tracker.evidence.models import EvidenceRequest


@dataclass
class ApplicationServices:
    """Application-service implementation shared by local transport adapters."""

    container: ApplicationContainer
    readiness_provider: ConversationalReadinessProvider | None = None
    integrity_provider: DatabaseIntegrityStatusProvider | None = None

    def __post_init__(self) -> None:
        self.codex_home = self.container.paths.codex_home
        self.db_path = self.container.paths.db_path
        self.pricing_path = self.container.paths.pricing_path
        self.allowance_path = self.container.paths.allowance_path
        self.rate_card_path = self.container.paths.rate_card_path
        self.thresholds_path = self.container.paths.thresholds_path
        self.projects_path = self.container.paths.projects_path
        self.job_service = self.application.jobs
        self.analysis_runtime = AnalysisRuntime(
            job_service=self.job_service,
            catalog=self.application.analyses,
            pricing_fingerprint=_path_fingerprint(self.pricing_path),
            rate_card_fingerprint=_path_fingerprint(self.rate_card_path),
            thresholds_fingerprint=_path_fingerprint(self.thresholds_path),
            catalog_version=_catalog_fingerprint(),
        )

    @property
    def application(self) -> ApplicationContainer:
        return self.container

    def status(self, request: StatusRequest) -> object:
        context = self.application.request_context(
            request.scope,
            prefer_materialized_active=True,
        )
        return get_status(
            replace(
                request,
                db_path=self.db_path,
                pricing_path=self.pricing_path,
                codex_home=self.codex_home,
                home=self.codex_home.parent,
            ),
            context=context,
            clock=self.application.clock,
            pricing_provider=self.application.pricing,
            readiness_provider=self.readiness_provider,
            integrity_provider=self.integrity_provider,
        )

    def refresh(self, request: RefreshRequest) -> object:
        outcome = refresh_usage(
            request,
            codex_home=self.codex_home,
            db_path=self.db_path,
            pricing_path=self.pricing_path,
            source_repository=self.application.repositories.sources,
            job_service=self.job_service,
        )
        return outcome.result if outcome.result is not None else outcome.job

    def analyze(self, request: AnalysisRequest) -> object:
        normalized = replace(request, filters=normalize_query_filters(request.filters))
        context = self.application.request_context(
            _request_scope(normalized.filters, normalized.history)
        )
        outcome = analyze_usage(
            normalized,
            replace(context, analysis_runtime=self.analysis_runtime),
        )
        return outcome.completed if outcome.completed is not None else outcome.job

    def query(self, request: QueryRequest) -> object:
        normalized = replace(request, filters=normalize_query_filters(request.filters))
        context = self.application.request_context(
            _request_scope(normalized.filters, normalized.history)
        )
        return query_usage(
            normalized,
            db_path=self.db_path,
            pricing_path=self.pricing_path,
            allowance_path=self.allowance_path,
            context=context,
        )

    def evidence(self, request: EvidenceRequest) -> object:
        return get_evidence(
            request,
            db_path=self.db_path,
            pricing_path=self.pricing_path,
            allowance_path=self.allowance_path,
            job_service=self.job_service,
        )

    def allowance(self, request: AllowanceRequest) -> object:
        result = get_allowance(request, db_path=self.db_path, job_service=self.job_service)
        payload = dict(result.payload)
        payload.setdefault("schema", result.result_schema)
        return payload

    def job_status(self, request: JobStatusRequest) -> object:
        return get_job_status(request, job_service=self.job_service)

    def capabilities(self) -> object:
        return {
            "schema": "codex-usage-tracker.capabilities.v2",
            "analysis_goals": list(ANALYSIS_GOALS),
            "query_entities": {
                name: {
                    "identity": capability.identity,
                    "measures": sorted(capability.measures),
                    "group_by": sorted(capability.group_by),
                }
                for name, capability in QUERY_ENTITY_CAPABILITIES.items()
            },
            "query_measures": sorted(ALL_QUERY_MEASURES),
            "allowance_operations": ["status", "series", "evidence", "analysis"],
            "evidence_selector_kinds": ["finding", "call", "thread", "allowance", "analysis"],
        }


def _request_scope(filters: QueryFilters, history: str) -> RequestScope:
    return RequestScope(
        since=filters.since,
        until=filters.until,
        history=cast(Any, history),
        project=filters.project,
        thread_key=filters.thread_key,
        model=filters.model,
        effort=filters.effort,
    )


def _path_fingerprint(path: Path) -> str:
    content = path.read_bytes() if path.is_file() else b"missing"
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _catalog_fingerprint() -> str:
    payload = [
        {
            "goal": goal,
            "strategy_id": entry.strategy.strategy_id,
            "strategy_version": entry.strategy.strategy_version,
        }
        for goal, entry in sorted(ANALYSIS_CATALOG.items())
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
