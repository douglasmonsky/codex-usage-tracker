from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from .outcomes import RunOutcome


class StopMetric(str, Enum):
    ELAPSED_MS = "elapsed_ms"
    SQL_LATENCY_MS = "sql_latency_ms"
    MCP_LATENCY_MS = "mcp_latency_ms"
    DATABASE_BYTES = "database_bytes"
    INDEX_BYTES = "index_bytes"
    WAL_BYTES = "wal_bytes"
    PEAK_RSS_BYTES = "peak_rss_bytes"
    FULL_SCAN_COUNT = "full_scan_count"
    AUTOMATIC_INDEX_COUNT = "automatic_index_count"
    TEMPORARY_SORT_COUNT = "temporary_sort_count"
    WRITER_LOCK_MS = "writer_lock_ms"
    PROJECTION_FANOUT = "projection_fanout"
    RESPONSE_BYTES = "response_bytes"
    TRACKER_CALLS = "tracker_calls"


@dataclass(frozen=True)
class MetricLimit:
    metric: StopMetric
    maximum: int

    def __post_init__(self) -> None:
        if self.maximum < 0:
            raise ValueError("early-stop maximum must be nonnegative")


@dataclass(frozen=True)
class StopDecision:
    case_id: str
    metric: StopMetric
    observed: int
    maximum: int
    outcome: RunOutcome = field(default=RunOutcome.STOPPED, init=False)
    partial: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if self.observed < 0 or self.maximum < 0:
            raise ValueError("early-stop decision values must be nonnegative")


class EarlyStopController:
    """Fail a run immediately after a monotonic hard ceiling is exceeded."""

    def __init__(self, case_id: str, limits: tuple[MetricLimit, ...]) -> None:
        if not case_id:
            raise ValueError("early-stop case ID is required")
        self.case_id = case_id
        self._limits = {limit.metric: limit.maximum for limit in limits}
        if len(self._limits) != len(limits):
            raise ValueError("early-stop limits contain duplicate metrics")
        self._observed: dict[StopMetric, int] = {}
        self._decision: StopDecision | None = None

    @property
    def decision(self) -> StopDecision | None:
        return self._decision

    @property
    def limits(self) -> tuple[MetricLimit, ...]:
        return tuple(
            MetricLimit(metric, maximum)
            for metric, maximum in sorted(
                self._limits.items(),
                key=lambda item: item[0].value,
            )
        )

    def observe(self, metric: StopMetric, value: int) -> StopDecision | None:
        if self._decision is not None:
            return self._decision
        if value < 0:
            raise ValueError("early-stop observation must be nonnegative")
        previous = self._observed.get(metric)
        if previous is not None and value < previous:
            raise ValueError(f"{metric.value} observation is not monotonic")
        self._observed[metric] = value
        maximum = self._limits.get(metric)
        if maximum is not None and value > maximum:
            self._decision = StopDecision(
                case_id=self.case_id,
                metric=metric,
                observed=value,
                maximum=maximum,
            )
        return self._decision

    def observe_many(
        self,
        observations: Iterable[tuple[StopMetric, int]],
    ) -> StopDecision | None:
        for metric, value in observations:
            decision = self.observe(metric, value)
            if decision is not None:
                return decision
        return None
