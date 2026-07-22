"""Evidence-record contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

from codex_usage_tracker.core.contracts.common import MetricValue, immutable_snapshot

EvidenceKind = Literal[
    "call",
    "thread",
    "subagent",
    "time_bucket",
    "allowance_cycle",
    "diagnostic_fact",
    "aggregate_comparison",
]


@dataclass(frozen=True)
class EvidenceV1:
    """Deterministic evidence selector and bounded metrics."""

    schema: Literal["codex-usage-tracker.evidence.v1"] = field(
        default="codex-usage-tracker.evidence.v1", init=False
    )
    evidence_id: str
    kind: EvidenceKind
    label: str
    selectors: Mapping[str, str]
    metrics: Mapping[str, MetricValue]
    source_schema: str
    dashboard_target: Mapping[str, object] | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selectors",
            cast(Mapping[str, str], immutable_snapshot(self.selectors)),
        )
        object.__setattr__(
            self,
            "metrics",
            cast(Mapping[str, MetricValue], immutable_snapshot(self.metrics)),
        )
        if self.dashboard_target is not None:
            object.__setattr__(
                self,
                "dashboard_target",
                cast(
                    Mapping[str, object],
                    immutable_snapshot(self.dashboard_target),
                ),
            )
