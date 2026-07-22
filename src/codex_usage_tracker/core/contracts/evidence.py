"""Evidence-record contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from codex_usage_tracker.core.contracts.common import MetricValue

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
