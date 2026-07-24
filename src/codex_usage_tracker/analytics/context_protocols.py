"""Read-only context contracts consumed by analysis strategies."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from codex_usage_tracker.core.contracts import AccountingContextV1, FreshnessV1, ScopeV1


class AnalysisPaths(Protocol):
    @property
    def db_path(self) -> Path: ...

    @property
    def pricing_path(self) -> Path: ...

    @property
    def allowance_path(self) -> Path: ...

    @property
    def projects_path(self) -> Path: ...


class AnalysisContext(Protocol):
    @property
    def source_revision(self) -> str | None: ...

    @property
    def freshness(self) -> FreshnessV1: ...

    @property
    def scope(self) -> ScopeV1: ...

    @property
    def canonical_rows(self) -> int: ...

    @property
    def pricing_coverage(self) -> float | None: ...

    @property
    def credit_coverage(self) -> float | None: ...

    @property
    def service_tier_coverage(self) -> float | None: ...

    @property
    def accounting(self) -> AccountingContextV1: ...

    @property
    def application_paths(self) -> AnalysisPaths | None: ...
