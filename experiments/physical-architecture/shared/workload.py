from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import cast

from .canonical import canonical_sha256
from .crash import CRASH_BOUNDARIES, CRASH_FAULTS
from .fixture import REQUIRED_SLICE_QUESTION_IDS
from .stop import MetricLimit, StopMetric


class WorkloadGroup(str, Enum):
    BUILD = "build"
    ORDINARY_CHANGE = "ordinary_change"
    UNSAFE_CHANGE = "unsafe_change"
    QUERY = "query"
    CRASH = "crash"
    DBHUB = "dbhub"
    AGENT_PERF = "agent_perf"


ParameterValue = str | int | bool | None


@dataclass(frozen=True)
class WorkloadCase:
    case_id: str
    group: WorkloadGroup
    parameters: tuple[tuple[str, ParameterValue], ...] = ()
    early_stop_limits: tuple[MetricLimit, ...] = ()
    candidate_capability: str | None = None
    minimum_repetitions: int = 5

    def __post_init__(self) -> None:
        if tuple(sorted(self.parameters)) != self.parameters:
            raise ValueError(f"workload parameters must be sorted: {self.case_id}")
        if len({name for name, _ in self.parameters}) != len(self.parameters):
            raise ValueError(f"workload parameters must be unique: {self.case_id}")
        if self.minimum_repetitions < 1:
            raise ValueError(f"workload repetitions must be positive: {self.case_id}")

    def parameter(self, name: str) -> ParameterValue:
        return dict(self.parameters).get(name)

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "group": self.group.value,
            "parameters": dict(self.parameters),
            "early_stop_limits": [
                {"metric": limit.metric.value, "maximum": limit.maximum}
                for limit in self.early_stop_limits
            ],
            "candidate_capability": self.candidate_capability,
            "minimum_repetitions": self.minimum_repetitions,
        }


@dataclass(frozen=True)
class WorkloadMatrix:
    cases: tuple[WorkloadCase, ...]
    worker_counts: tuple[int, ...]
    digest: str

    def ids(self, group: WorkloadGroup) -> tuple[str, ...]:
        return tuple(case.case_id for case in self.cases if case.group is group)

    def by_id(self, case_id: str) -> WorkloadCase:
        for case in self.cases:
            if case.case_id == case_id:
                return case
        raise KeyError(case_id)


P1_QUESTION_IDS = (
    "Q-ACC-01",
    "Q-ACC-02",
    "Q-ACC-04",
    "Q-ACC-05",
    "Q-ACC-06",
    "Q-ACC-07",
    "Q-ALW-01",
    "Q-CTX-01",
    "Q-DEL-01",
    "Q-OPS-01",
    "Q-WF-01",
    "Q-WF-05",
)

_QUESTION_PLANS = {
    "Q-ACC-01": ("current_usage", "P1"),
    "Q-ACC-02": ("top_sessions", "P1"),
    "Q-ACC-04": ("model_effort_mix", "P1"),
    "Q-ACC-05": ("project_family_usage", "P1"),
    "Q-ACC-06": ("top_valued_entities", "P1"),
    "Q-ACC-07": ("pricing_coverage", "P1"),
    "Q-ALW-01": ("allowance_movement", "P1"),
    "Q-ALW-02": ("allowance_interval_events", "P3"),
    "Q-ALW-03": ("allowance_local_efficiency", "P2"),
    "Q-CTX-01": ("cache_reuse_candidates", "P1"),
    "Q-CTX-02": ("context_pressure_trajectory", "P2"),
    "Q-CTX-04": ("uncached_input_jumps", "P2"),
    "Q-DEL-01": ("parent_subagent_usage", "P1"),
    "Q-OPS-01": ("latest_publication_delta", "P1"),
    "Q-OPS-03": ("dedup_source_audit", "P2"),
    "Q-OPS-04": ("evidence_timeline", "P3"),
    "Q-WF-01": ("turn_completion_efficiency", "P1"),
    "Q-WF-02": ("first_action_mutation", "P2"),
    "Q-WF-03": ("repeated_resource_operations", "P2"),
    "Q-WF-05": ("tool_family_behavior", "P1"),
}
QUESTION_WORKLOAD_CONTRACTS = MappingProxyType(_QUESTION_PLANS)

_SQL_LIMITS_MS = {"P0": 10, "P1": 25, "P2": 100, "P3": 100, "P4": 250, "P5": 100}
_MCP_LIMITS_MS = {"P0": 250, "P1": 500, "P2": 500, "P3": 750, "P4": 750, "P5": 500}
_TRACKER_CALL_LIMITS = {"P0": 1, "P1": 1, "P2": 1, "P3": 2, "P4": 2, "P5": 1}
_HISTORY_SELECTIONS = (
    "current_session",
    "24_hours",
    "7_days",
    "30_days",
    "90_days",
    "one_year",
    "all_time",
)
_SCALES = ("tiny", "small", "standard", "production", "growth")
_EXPANSIONS = (
    ("30_days", "90_days"),
    ("90_days", "one_year"),
    ("one_year", "all_time"),
)
_ORDINARY_CHANGES = (
    "no_source_change",
    "one_model_call",
    "one_tool_start",
    "tool_terminal_transition",
    "tool_plus_state_change",
    "32_call_tail",
    "2000_call_tail",
    "late_event",
    "rate_card_change",
)
_UNSAFE_CHANGES = (
    "source_truncation",
    "source_replacement",
    "canonical_owner_change",
    "identity_normalization_change",
    "projection_schema_change",
    "recanonicalization",
    "database_schema_upgrade",
)
DBHUB_LOCAL_ROUTES = ("generic", "named_preset")


def _parameters(**values: ParameterValue) -> tuple[tuple[str, ParameterValue], ...]:
    return tuple(sorted(values.items()))


def _build_cases(worker_counts: tuple[int, ...]) -> Iterable[WorkloadCase]:
    history_limits = {
        "30_days": 5_000,
        "90_days": 15_000,
        "one_year": 45_000,
        "all_time": 120_000,
    }
    for history in _HISTORY_SELECTIONS:
        maximum = history_limits.get(history)
        limits = (MetricLimit(StopMetric.ELAPSED_MS, maximum),) if maximum is not None else ()
        yield WorkloadCase(
            f"build.empty.{history}",
            WorkloadGroup.BUILD,
            _parameters(history_selection=history, profile="production"),
            limits,
        )
    for start, end in _EXPANSIONS:
        yield WorkloadCase(
            f"build.expand.{start}_to_{end}",
            WorkloadGroup.BUILD,
            _parameters(from_history=start, profile="production", to_history=end),
        )
    for scale in _SCALES:
        limits = (MetricLimit(StopMetric.ELAPSED_MS, 120_000),) if scale == "production" else ()
        yield WorkloadCase(
            f"build.scale.{scale}",
            WorkloadGroup.BUILD,
            _parameters(history_selection="all_time", profile=scale),
            limits,
        )
    for workers in worker_counts:
        yield WorkloadCase(
            f"build.workers.{workers}",
            WorkloadGroup.BUILD,
            _parameters(parser_workers=workers, profile="standard"),
        )
    for writer_mode in ("single", "partitioned_staging"):
        yield WorkloadCase(
            f"build.writer.{writer_mode}",
            WorkloadGroup.BUILD,
            _parameters(profile="standard", writer_mode=writer_mode),
            candidate_capability=(
                "partitioned_staging" if writer_mode == "partitioned_staging" else None
            ),
        )
    for index_mode in ("present", "deferred", "rebuilt"):
        yield WorkloadCase(
            f"build.index.{index_mode}",
            WorkloadGroup.BUILD,
            _parameters(index_mode=index_mode, profile="standard"),
        )
    yield WorkloadCase(
        "build.schema_upgrade.unpublished",
        WorkloadGroup.BUILD,
        _parameters(profile="tiny", publication_state="unpublished"),
    )


def _ordinary_cases() -> Iterable[WorkloadCase]:
    elapsed_limits = {
        "no_source_change": 100,
        "one_model_call": 500,
        "tool_terminal_transition": 500,
        "2000_call_tail": 50,
    }
    for change in _ORDINARY_CHANGES:
        maximum = elapsed_limits.get(change)
        limits = (MetricLimit(StopMetric.ELAPSED_MS, maximum),) if maximum is not None else ()
        yield WorkloadCase(
            f"ordinary.{change}",
            WorkloadGroup.ORDINARY_CHANGE,
            _parameters(change=change, profile="production"),
            limits,
        )


def _unsafe_cases() -> Iterable[WorkloadCase]:
    for change in _UNSAFE_CHANGES:
        yield WorkloadCase(
            f"unsafe.{change}",
            WorkloadGroup.UNSAFE_CHANGE,
            _parameters(change=change, protocol="isolated_artifact", profile="standard"),
            minimum_repetitions=1,
        )


def _query_limits(
    performance_class: str,
    *,
    maximum_full_scans: int = 0,
    maximum_automatic_indexes: int = 0,
    maximum_temporary_sorts: int = 0,
) -> tuple[MetricLimit, ...]:
    return (
        MetricLimit(StopMetric.SQL_LATENCY_MS, _SQL_LIMITS_MS[performance_class]),
        MetricLimit(StopMetric.MCP_LATENCY_MS, _MCP_LIMITS_MS[performance_class]),
        MetricLimit(StopMetric.FULL_SCAN_COUNT, maximum_full_scans),
        MetricLimit(StopMetric.AUTOMATIC_INDEX_COUNT, maximum_automatic_indexes),
        MetricLimit(StopMetric.TEMPORARY_SORT_COUNT, maximum_temporary_sorts),
        MetricLimit(StopMetric.RESPONSE_BYTES, 16_384),
        MetricLimit(
            StopMetric.TRACKER_CALLS,
            _TRACKER_CALL_LIMITS[performance_class],
        ),
    )


def _query_cases() -> Iterable[WorkloadCase]:
    modes: tuple[tuple[str, dict[str, ParameterValue]], ...] = (
        ("cold_first_page", {"cache": "cold", "page": 1, "repeat": 1}),
        ("warm_first_page", {"cache": "warm", "page": 1, "repeat": 1}),
        ("repeated_identical", {"cache": "warm", "page": 1, "repeat": 2}),
    )
    for question_id in sorted(set(P1_QUESTION_IDS) | set(REQUIRED_SLICE_QUESTION_IDS)):
        plan_id, performance_class = _QUESTION_PLANS[question_id]
        for mode, mode_parameters in modes:
            yield WorkloadCase(
                f"query.{question_id.lower()}.{mode}",
                WorkloadGroup.QUERY,
                _parameters(
                    **mode_parameters,
                    maximum_automatic_indexes=0,
                    maximum_full_scans=0,
                    maximum_temporary_sorts=0,
                    mode=mode,
                    performance_class=performance_class,
                    plan_id=plan_id,
                    question_id=question_id,
                ),
                _query_limits(performance_class),
            )
    feature_parameters: tuple[tuple[str, dict[str, ParameterValue]], ...] = (
        (
            "exact_count",
            {
                "exact_count": True,
                "maximum_automatic_indexes": 0,
                "maximum_full_scans": 13,
                "maximum_temporary_sorts": 0,
                "plan_allowance_reason": ("explicit_exact_count_across_13_evidence_domains"),
                "performance_class": "P3",
                "plan_id": "evidence_timeline",
                "question_id": "Q-OPS-04",
            },
        ),
        (
            "rate_card_replacement",
            {
                "maximum_automatic_indexes": 0,
                "maximum_full_scans": 0,
                "maximum_temporary_sorts": 0,
                "performance_class": "P1",
                "plan_id": "top_valued_entities",
                "question_id": "Q-ACC-06",
                "rate_card": "replacement",
            },
        ),
        (
            "selected_session_timeline",
            {
                "maximum_automatic_indexes": 0,
                "maximum_full_scans": 0,
                "maximum_temporary_sorts": 6,
                "plan_allowance_reason": ("selector_scoped_merge_over_at_most_11_rows_per_stream"),
                "performance_class": "P3",
                "plan_id": "evidence_timeline",
                "question_id": "Q-OPS-04",
                "scope": "selected_session",
            },
        ),
        (
            "top_n_ties",
            {
                "maximum_automatic_indexes": 0,
                "maximum_full_scans": 0,
                "maximum_temporary_sorts": 0,
                "performance_class": "P1",
                "plan_id": "top_sessions",
                "question_id": "Q-ACC-02",
                "ties": "deterministic",
            },
        ),
        (
            "bounded_full_sort",
            {
                "maximum_automatic_indexes": 0,
                "maximum_full_scans": 1,
                "maximum_temporary_sorts": 1,
                "plan_allowance_reason": ("scan_and_complete_sort_over_at_most_100_admitted_rows"),
                "performance_class": "P2",
                "plan_id": "all_admitted_bounded_domains",
                "sort": "complete_server_side",
            },
        ),
    )
    for feature, parameters in feature_parameters:
        performance_class = str(parameters["performance_class"])
        maximum_full_scans = cast(int, parameters["maximum_full_scans"])
        maximum_automatic_indexes = cast(int, parameters["maximum_automatic_indexes"])
        maximum_temporary_sorts = cast(int, parameters["maximum_temporary_sorts"])
        yield WorkloadCase(
            f"query.feature.{feature}",
            WorkloadGroup.QUERY,
            _parameters(**parameters),
            _query_limits(
                performance_class,
                maximum_full_scans=maximum_full_scans,
                maximum_automatic_indexes=maximum_automatic_indexes,
                maximum_temporary_sorts=maximum_temporary_sorts,
            ),
        )
    for position in (10, 100, 1_000, 10_000):
        yield WorkloadCase(
            f"query.deep_keyset.page_{position}",
            WorkloadGroup.QUERY,
            _parameters(
                maximum_automatic_indexes=0,
                maximum_full_scans=0,
                maximum_temporary_sorts=0,
                page_position=position,
                pagination="keyset",
                performance_class="P3",
                plan_id="evidence_timeline",
                question_id="Q-OPS-04",
            ),
            _query_limits("P3"),
        )


def _crash_cases() -> Iterable[WorkloadCase]:
    for boundary in CRASH_BOUNDARIES:
        yield WorkloadCase(
            f"crash.terminate.{boundary}",
            WorkloadGroup.CRASH,
            _parameters(boundary=boundary, injection="process_termination"),
            minimum_repetitions=1,
        )
    for fault in CRASH_FAULTS:
        yield WorkloadCase(
            f"crash.fault.{fault}",
            WorkloadGroup.CRASH,
            _parameters(fault=fault, injection="fault"),
            minimum_repetitions=1,
        )


def build_workload_matrix(*, physical_cores: int) -> WorkloadMatrix:
    if physical_cores < 1:
        raise ValueError("physical_cores must be positive")
    worker_counts = tuple(sorted({1, 2, 4, min(physical_cores, 8)}))
    cases = tuple(
        [
            *_build_cases(worker_counts),
            *_ordinary_cases(),
            *_unsafe_cases(),
            *_query_cases(),
            *_crash_cases(),
            *(
                WorkloadCase(
                    f"dbhub.{route}",
                    WorkloadGroup.DBHUB,
                    _parameters(
                        profile="standard",
                        route=route,
                        transport="stdio",
                        version="0.24.0",
                    ),
                )
                for route in DBHUB_LOCAL_ROUTES
            ),
            WorkloadCase(
                "agent_perf.standard_cpu_attribution",
                WorkloadGroup.AGENT_PERF,
                _parameters(profile="standard", speed_claim=False),
            ),
        ]
    )
    if len(cases) != len({case.case_id for case in cases}):
        raise AssertionError("workload matrix contains duplicate case IDs")
    digest = canonical_sha256(
        {
            "schema": "codex-usage-tracker.physical-bakeoff-workload.v1",
            "physical_cores": physical_cores,
            "worker_counts": worker_counts,
            "cases": [case.as_dict() for case in cases],
        }
    )
    return WorkloadMatrix(cases=cases, worker_counts=worker_counts, digest=digest)
