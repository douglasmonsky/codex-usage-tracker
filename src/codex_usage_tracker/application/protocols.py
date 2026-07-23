"""Narrow dependency protocols consumed by current application services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from codex_usage_tracker.jobs.models import JobKind, JobStatusV1
from codex_usage_tracker.pricing.config import PricingConfig


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class UsageRepository(Protocol):
    def request_context_facts(
        self,
        *,
        scope: dict[str, object],
        priced_models: set[str],
        credit_models: set[str],
        prefer_materialized_active: bool,
    ) -> dict[str, object]: ...


@runtime_checkable
class SourceRepository(Protocol):
    def session_logs(self, *, include_archived: bool) -> tuple[Path, ...]: ...


@runtime_checkable
class AnalysisResultRepository(Protocol):
    def completed_results(
        self,
        *,
        kind: JobKind,
        result_schema: str,
        source_revision: str | None,
        limit: int,
    ) -> tuple[Mapping[str, object], ...]: ...


@runtime_checkable
class JobRepository(Protocol):
    def status(self, job_id: str, *, include_result: bool = False) -> JobStatusV1: ...


@runtime_checkable
class DashboardTargetResolver(Protocol):
    def resolve(
        self,
        *,
        evidence_kind: str,
        selector_id: str,
        history: str,
        analysis_id: str | None = None,
        target_purpose: str = "evidence",
    ) -> dict[str, object]: ...


@runtime_checkable
class PricingProvider(Protocol):
    def load(self, path: Path) -> PricingConfig: ...

    def credit_rate_card(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class RepositorySet:
    usage: UsageRepository
    sources: SourceRepository
    analysis_results: AnalysisResultRepository
    jobs: JobRepository
