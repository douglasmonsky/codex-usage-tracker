"""Application composition root with explicit local dependencies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from codex_usage_tracker.analytics.analysis_catalog import (
    ANALYSIS_CATALOG,
    AnalysisCatalogEntry,
)
from codex_usage_tracker.analytics.analysis_models import AnalysisGoal
from codex_usage_tracker.application.context import RequestContext, build_request_context
from codex_usage_tracker.application.paths import ApplicationPaths
from codex_usage_tracker.application.protocols import (
    Clock,
    DashboardTargetResolver,
    PricingProvider,
    RepositorySet,
)
from codex_usage_tracker.application.requests import RequestScope
from codex_usage_tracker.core.dashboard_targets import build_dashboard_target_v2
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.parser.api import find_session_logs
from codex_usage_tracker.pricing.allowance_rate_card import load_bundled_rate_card
from codex_usage_tracker.pricing.config import PricingConfig, load_pricing_config
from codex_usage_tracker.store.api import (
    query_request_context_facts,
    query_status_context_facts,
)

AnalysisCatalog = Mapping[AnalysisGoal, AnalysisCatalogEntry]


@dataclass(frozen=True)
class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class StoreUsageRepository:
    db_path: Path

    def request_context_facts(
        self,
        *,
        scope: dict[str, object],
        priced_models: set[str],
        credit_models: set[str],
        prefer_materialized_active: bool,
    ) -> dict[str, object]:
        query = (
            query_status_context_facts
            if prefer_materialized_active
            else query_request_context_facts
        )
        return query(
            db_path=self.db_path,
            scope=scope,
            priced_models=priced_models,
            credit_models=credit_models,
        )


@dataclass(frozen=True)
class LocalSourceRepository:
    codex_home: Path

    def session_logs(self, *, include_archived: bool) -> tuple[Path, ...]:
        return tuple(find_session_logs(self.codex_home, include_archived=include_archived))


@dataclass(frozen=True)
class LocalPricingProvider:
    def load(self, path: Path) -> PricingConfig:
        return load_pricing_config(path)

    def credit_rate_card(self) -> dict[str, object]:
        return load_bundled_rate_card()


@dataclass(frozen=True)
class CoreDashboardTargetResolver:
    def resolve(
        self,
        *,
        evidence_kind: str,
        selector_id: str,
        history: str,
        analysis_id: str | None = None,
        target_purpose: str = "evidence",
    ) -> dict[str, object]:
        return build_dashboard_target_v2(
            evidence_kind=evidence_kind,
            selector_id=selector_id,
            history=history,
            analysis_id=analysis_id,
            target_purpose=target_purpose,
        )


@dataclass(frozen=True)
class ApplicationContainer:
    paths: ApplicationPaths
    clock: Clock
    repositories: RepositorySet
    jobs: JobService
    analyses: AnalysisCatalog
    dashboard_targets: DashboardTargetResolver
    pricing: PricingProvider

    def request_context(
        self,
        scope: RequestScope,
        *,
        prefer_materialized_active: bool = False,
    ) -> RequestContext:
        return build_request_context(
            db_path=self.paths.db_path,
            pricing_path=self.paths.pricing_path,
            scope=scope,
            prefer_materialized_active=prefer_materialized_active,
            usage_repository=self.repositories.usage,
            pricing_provider=self.pricing,
            clock=self.clock,
            application_paths=self.paths,
        )


def build_application_container(
    paths: ApplicationPaths,
    *,
    clock: Clock | None = None,
) -> ApplicationContainer:
    jobs = JobService()
    repositories = RepositorySet(
        usage=StoreUsageRepository(paths.db_path),
        sources=LocalSourceRepository(paths.codex_home),
        analysis_results=jobs,
        jobs=jobs,
    )
    return ApplicationContainer(
        paths=paths,
        clock=clock or SystemClock(),
        repositories=repositories,
        jobs=jobs,
        analyses=ANALYSIS_CATALOG,
        dashboard_targets=CoreDashboardTargetResolver(),
        pricing=LocalPricingProvider(),
    )
