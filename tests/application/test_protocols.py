from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

from codex_usage_tracker.application.protocols import (
    AnalysisResultRepository,
    Clock,
    DashboardTargetResolver,
    JobRepository,
    PricingProvider,
    SourceRepository,
    UsageRepository,
)
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.pricing.config import PricingConfig


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 7, 23, tzinfo=timezone.utc)


class _UsageRepository:
    def request_context_facts(
        self,
        *,
        scope: dict[str, object],
        priced_models: set[str],
        credit_models: set[str],
        prefer_materialized_active: bool,
    ) -> dict[str, object]:
        return {"scope": scope}


class _SourceRepository:
    def session_logs(self, *, include_archived: bool) -> tuple[Path, ...]:
        return ()


class _PricingProvider:
    def load(self, path: Path) -> PricingConfig:
        return PricingConfig(path=path, models={}, loaded=False)

    def credit_rate_card(self) -> dict[str, object]:
        return {}


class _DashboardTargets:
    def resolve(
        self,
        *,
        evidence_kind: str,
        selector_id: str,
        history: str,
        analysis_id: str | None = None,
        target_purpose: str = "evidence",
    ) -> dict[str, object]:
        return {"selector_id": selector_id}


def test_protocols_accept_only_the_current_narrow_service_shapes() -> None:
    assert isinstance(_Clock(), Clock)
    assert isinstance(_UsageRepository(), UsageRepository)
    assert isinstance(_SourceRepository(), SourceRepository)
    assert isinstance(_PricingProvider(), PricingProvider)
    assert isinstance(_DashboardTargets(), DashboardTargetResolver)
    assert isinstance(JobService(), JobRepository)
    assert isinstance(JobService(), AnalysisResultRepository)


def test_application_and_analytics_do_not_import_default_global_paths() -> None:
    package = Path(__file__).parents[2] / "src" / "codex_usage_tracker"
    offenders: list[str] = []
    for root_name in ("application", "analytics"):
        for path in sorted(package.joinpath(root_name).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if any(
                isinstance(node, ast.ImportFrom)
                and node.module == "codex_usage_tracker.core.paths"
                for node in ast.walk(tree)
            ):
                offenders.append(str(path.relative_to(package)))

    assert offenders == []
