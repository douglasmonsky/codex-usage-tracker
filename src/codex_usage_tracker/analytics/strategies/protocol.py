from __future__ import annotations

from typing import Protocol, runtime_checkable

from codex_usage_tracker.analytics.analysis_models import (
    AnalysisGoal,
    AnalysisReportV2,
    AnalysisRequest,
    WorkEstimate,
)
from codex_usage_tracker.application.context import RequestContext


@runtime_checkable
class AnalysisStrategy(Protocol):
    @property
    def goal(self) -> AnalysisGoal: ...

    @property
    def strategy_id(self) -> str: ...

    @property
    def strategy_version(self) -> str: ...

    def estimate(self, request: AnalysisRequest, context: RequestContext) -> WorkEstimate: ...

    def analyze(self, request: AnalysisRequest, context: RequestContext) -> AnalysisReportV2: ...
