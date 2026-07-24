"""Application-owned protocols for analysis runtime composition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from codex_usage_tracker.analytics.analysis_catalog import AnalysisCatalogEntry
from codex_usage_tracker.analytics.analysis_models import AnalysisGoal, AnalysisRequest
from codex_usage_tracker.analytics.context_protocols import AnalysisContext
from codex_usage_tracker.jobs.models import JobStatusV1
from codex_usage_tracker.jobs.service import JobService


class AnalysisRuntimeProtocol(Protocol):
    """Runtime surface consumed by request contexts and analysis orchestration."""

    catalog: Mapping[AnalysisGoal, AnalysisCatalogEntry]
    pricing_fingerprint: str
    rate_card_fingerprint: str
    thresholds_fingerprint: str
    catalog_version: str
    job_service: JobService

    def start(
        self,
        semantic_key: str,
        request: AnalysisRequest,
        context: AnalysisContext,
        entry: AnalysisCatalogEntry,
    ) -> JobStatusV1: ...
