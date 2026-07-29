"""Classify wall-clock performance evidence without blaming a noisy runner."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pytest

_CALIBRATION_ROUNDS = 3
_CALIBRATION_QUORUM = 2
_CPU_ITERATIONS = 5_000
_SQLITE_SAMPLES = 60
_CPU_SCHEDULER_GAP_BUDGET_MS = 50.0
_SQLITE_P95_BUDGET_MS = 10.0
_SQLITE_MAX_BUDGET_MS = 150.0
_LANE_ENV = "CODEX_USAGE_PERFORMANCE_LANE"
_REPORT_ENV = "CODEX_USAGE_PERFORMANCE_REPORT"
_REPORT_SCHEMA = "codex-usage-tracker.ci-performance-qualification.v1"


class PerformanceLane(str, Enum):
    INVARIANTS = "invariants"
    STRICT = "strict"
    GITHUB_HOSTED_QUALIFIED = "github_hosted_qualified"


class PerformanceOutcome(str, Enum):
    INVARIANTS_ONLY = "invariants_only"
    PASS = "pass"
    PRODUCT_REGRESSION = "product_regression"
    RUNNER_UNQUALIFIED = "runner_unqualified"


@dataclass(frozen=True)
class BudgetObservation:
    metric: str
    observed: float
    budget: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "budget": round(self.budget, 6),
            "metric": self.metric,
            "observed": round(self.observed, 6),
        }


@dataclass(frozen=True)
class CalibrationRound:
    cpu_wall_ms: float
    cpu_process_ms: float
    sqlite_p95_ms: float
    sqlite_max_ms: float

    @property
    def scheduler_gap_ms(self) -> float:
        return max(0.0, self.cpu_wall_ms - self.cpu_process_ms)

    @property
    def healthy(self) -> bool:
        return (
            self.scheduler_gap_ms <= _CPU_SCHEDULER_GAP_BUDGET_MS
            and self.sqlite_p95_ms <= _SQLITE_P95_BUDGET_MS
            and self.sqlite_max_ms <= _SQLITE_MAX_BUDGET_MS
        )

    def to_dict(self) -> dict[str, bool | float]:
        return {
            "cpu_process_ms": round(self.cpu_process_ms, 6),
            "cpu_wall_ms": round(self.cpu_wall_ms, 6),
            "healthy": self.healthy,
            "scheduler_gap_ms": round(self.scheduler_gap_ms, 6),
            "sqlite_max_ms": round(self.sqlite_max_ms, 6),
            "sqlite_p95_ms": round(self.sqlite_p95_ms, 6),
        }


@dataclass(frozen=True)
class CalibrationBoundary:
    rounds: tuple[CalibrationRound, ...]

    @property
    def healthy_rounds(self) -> int:
        return sum(item.healthy for item in self.rounds)

    @property
    def qualified(self) -> bool:
        return (
            len(self.rounds) == _CALIBRATION_ROUNDS
            and self.healthy_rounds >= _CALIBRATION_QUORUM
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "healthy_rounds": self.healthy_rounds,
            "qualified": self.qualified,
            "quorum": _CALIBRATION_QUORUM,
            "rounds": [item.to_dict() for item in self.rounds],
        }


@dataclass(frozen=True)
class PerformanceAssessment:
    lane: PerformanceLane
    outcome: PerformanceOutcome
    runner_qualified: bool | None
    observations: tuple[BudgetObservation, ...]
    breaches: tuple[BudgetObservation, ...]
    before: CalibrationBoundary
    after: CalibrationBoundary

    def to_dict(self) -> dict[str, object]:
        return {
            "after": self.after.to_dict(),
            "before": self.before.to_dict(),
            "breaches": [item.to_dict() for item in self.breaches],
            "lane": self.lane.value,
            "observations": [item.to_dict() for item in self.observations],
            "outcome": self.outcome.value,
            "runner_qualified": self.runner_qualified,
            "schema": _REPORT_SCHEMA,
        }


def classify_performance(
    *,
    lane: PerformanceLane,
    before: CalibrationBoundary,
    after: CalibrationBoundary,
    observations: tuple[BudgetObservation, ...],
) -> PerformanceAssessment:
    breaches = tuple(item for item in observations if item.observed > item.budget)
    if lane is PerformanceLane.INVARIANTS:
        return PerformanceAssessment(
            lane=lane,
            outcome=PerformanceOutcome.INVARIANTS_ONLY,
            runner_qualified=None,
            observations=observations,
            breaches=breaches,
            before=before,
            after=after,
        )
    if lane is PerformanceLane.STRICT:
        return PerformanceAssessment(
            lane=lane,
            outcome=(
                PerformanceOutcome.PRODUCT_REGRESSION
                if breaches
                else PerformanceOutcome.PASS
            ),
            runner_qualified=None,
            observations=observations,
            breaches=breaches,
            before=before,
            after=after,
        )

    runner_qualified = before.qualified and after.qualified
    if not runner_qualified:
        outcome = PerformanceOutcome.RUNNER_UNQUALIFIED
    elif breaches:
        outcome = PerformanceOutcome.PRODUCT_REGRESSION
    else:
        outcome = PerformanceOutcome.PASS
    return PerformanceAssessment(
        lane=lane,
        outcome=outcome,
        runner_qualified=runner_qualified,
        observations=observations,
        breaches=breaches,
        before=before,
        after=after,
    )


def record_wall_clock_budget(metric: str, observed: float, budget: float) -> None:
    observation = BudgetObservation(metric, observed, budget)
    _OBSERVATIONS.append(observation)
    if _lane() is PerformanceLane.STRICT and observed > budget:
        raise AssertionError(
            f"{metric} {observed:.3f} ms exceeded {budget:.3f} ms"
        )


def measure_calibration_boundary() -> CalibrationBoundary:
    return CalibrationBoundary(
        tuple(_measure_calibration_round() for _index in range(_CALIBRATION_ROUNDS))
    )


def _measure_calibration_round() -> CalibrationRound:
    payload = b"codex-usage-tracker-runner-calibration" * 128
    cpu_started = time.process_time()
    wall_started = time.perf_counter()
    for _index in range(_CPU_ITERATIONS):
        hashlib.sha256(payload).digest()
    cpu_process_ms = (time.process_time() - cpu_started) * 1_000
    cpu_wall_ms = (time.perf_counter() - wall_started) * 1_000

    with tempfile.TemporaryDirectory(prefix="usage-tracker-perf-") as root:
        path = Path(root) / "calibration.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("CREATE TABLE calibration(value INTEGER NOT NULL)")
            connection.execute("INSERT INTO calibration VALUES (0)")
            connection.commit()
            timings = []
            for _index in range(_SQLITE_SAMPLES):
                started = time.perf_counter()
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE calibration SET value = value + 1"
                )
                connection.commit()
                timings.append((time.perf_counter() - started) * 1_000)
    ordered = sorted(timings)
    p95 = ordered[math.ceil(len(ordered) * 0.95) - 1]
    return CalibrationRound(
        cpu_wall_ms=cpu_wall_ms,
        cpu_process_ms=cpu_process_ms,
        sqlite_p95_ms=p95,
        sqlite_max_ms=ordered[-1],
    )


def _lane() -> PerformanceLane:
    raw = os.environ.get(_LANE_ENV, PerformanceLane.STRICT.value)
    try:
        return PerformanceLane(raw)
    except ValueError as error:
        allowed = ", ".join(item.value for item in PerformanceLane)
        raise RuntimeError(f"{_LANE_ENV} must be one of: {allowed}") from error


def _empty_boundary() -> CalibrationBoundary:
    return CalibrationBoundary(())


_OBSERVATIONS: list[BudgetObservation] = []
_BEFORE = _empty_boundary()


def pytest_sessionstart(session: pytest.Session) -> None:
    global _BEFORE
    del session
    _OBSERVATIONS.clear()
    if _lane() is PerformanceLane.GITHUB_HOSTED_QUALIFIED:
        _BEFORE = measure_calibration_boundary()
    else:
        _BEFORE = _empty_boundary()


def pytest_sessionfinish(
    session: pytest.Session,
    exitstatus: int | pytest.ExitCode,
) -> None:
    lane = _lane()
    after = (
        measure_calibration_boundary()
        if lane is PerformanceLane.GITHUB_HOSTED_QUALIFIED
        else _empty_boundary()
    )
    assessment = classify_performance(
        lane=lane,
        before=_BEFORE,
        after=after,
        observations=tuple(_OBSERVATIONS),
    )
    report = assessment.to_dict()
    report["pytest_exit_status"] = int(exitstatus)
    payload = json.dumps(report, separators=(",", ":"), sort_keys=True)
    print(f"CI_PERFORMANCE_QUALIFICATION={payload}")
    report_path = os.environ.get(_REPORT_ENV)
    if report_path:
        Path(report_path).write_text(payload + "\n", encoding="utf-8")
    if (
        assessment.outcome is PerformanceOutcome.PRODUCT_REGRESSION
        and int(exitstatus) == int(pytest.ExitCode.OK)
    ):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
