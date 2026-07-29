from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.kernel import performance_qualification
from tests.kernel.performance_qualification import (
    BudgetObservation,
    CalibrationBoundary,
    CalibrationRound,
    PerformanceLane,
    PerformanceOutcome,
    classify_performance,
)


def _round(*, healthy: bool) -> CalibrationRound:
    if healthy:
        return CalibrationRound(
            cpu_wall_ms=20.0,
            cpu_process_ms=19.0,
            sqlite_p95_ms=1.0,
            sqlite_max_ms=3.0,
        )
    return CalibrationRound(
        cpu_wall_ms=220.0,
        cpu_process_ms=20.0,
        sqlite_p95_ms=250.0,
        sqlite_max_ms=500.0,
    )


def _boundary(*states: bool) -> CalibrationBoundary:
    return CalibrationBoundary(tuple(_round(healthy=state) for state in states))


def test_qualified_hosted_runner_fails_a_real_regression() -> None:
    assessment = classify_performance(
        lane=PerformanceLane.GITHUB_HOSTED_QUALIFIED,
        before=_boundary(True, True, False),
        after=_boundary(True, False, True),
        observations=(
            BudgetObservation("active_writer_p95_ms", 51.0, 50.0),
            BudgetObservation("active_writer_max_ms", 149.0, 150.0),
        ),
    )

    assert assessment.outcome is PerformanceOutcome.PRODUCT_REGRESSION
    assert assessment.runner_qualified is True
    assert [item.metric for item in assessment.breaches] == [
        "active_writer_p95_ms"
    ]


def test_unqualified_host_reports_telemetry_instead_of_product_regression() -> None:
    assessment = classify_performance(
        lane=PerformanceLane.GITHUB_HOSTED_QUALIFIED,
        before=_boundary(False, True, False),
        after=_boundary(True, True, True),
        observations=(
            BudgetObservation("active_writer_p95_ms", 335.757, 50.0),
            BudgetObservation("active_writer_max_ms", 565.213, 150.0),
        ),
    )

    assert assessment.outcome is PerformanceOutcome.RUNNER_UNQUALIFIED
    assert assessment.runner_qualified is False
    assert {item.metric for item in assessment.breaches} == {
        "active_writer_max_ms",
        "active_writer_p95_ms",
    }
    assert assessment.to_dict()["outcome"] == "runner_unqualified"


def test_strict_lane_enforces_absolute_budgets_without_runner_escape() -> None:
    assessment = classify_performance(
        lane=PerformanceLane.STRICT,
        before=_boundary(False, False, False),
        after=_boundary(False, False, False),
        observations=(
            BudgetObservation("active_writer_p95_ms", 50.001, 50.0),
            BudgetObservation("active_writer_max_ms", 150.0, 150.0),
        ),
    )

    assert assessment.outcome is PerformanceOutcome.PRODUCT_REGRESSION
    assert assessment.runner_qualified is None


def test_healthy_measurements_pass_in_both_lanes() -> None:
    observations = (
        BudgetObservation("active_writer_p95_ms", 30.0, 50.0),
        BudgetObservation("active_writer_max_ms", 80.0, 150.0),
    )
    hosted = classify_performance(
        lane=PerformanceLane.GITHUB_HOSTED_QUALIFIED,
        before=_boundary(True, True, False),
        after=_boundary(True, True, False),
        observations=observations,
    )
    strict = classify_performance(
        lane=PerformanceLane.STRICT,
        before=_boundary(False, False, False),
        after=_boundary(False, False, False),
        observations=observations,
    )

    assert hosted.outcome is PerformanceOutcome.PASS
    assert hosted.runner_qualified is True
    assert strict.outcome is PerformanceOutcome.PASS


class _Session:
    def __init__(self) -> None:
        self.exitstatus: int | pytest.ExitCode = pytest.ExitCode.OK


def test_hosted_hook_keeps_runner_unqualified_machine_readable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    boundaries = iter(
        (
            _boundary(False, True, False),
            _boundary(True, True, True),
        )
    )
    report = tmp_path / "qualification.json"
    monkeypatch.setenv(
        "CODEX_USAGE_PERFORMANCE_LANE",
        PerformanceLane.GITHUB_HOSTED_QUALIFIED.value,
    )
    monkeypatch.setenv("CODEX_USAGE_PERFORMANCE_REPORT", str(report))
    monkeypatch.setattr(
        performance_qualification,
        "measure_calibration_boundary",
        lambda: next(boundaries),
    )
    session = _Session()

    performance_qualification.pytest_sessionstart(session)  # type: ignore[arg-type]
    performance_qualification.record_wall_clock_budget(
        "active_writer_p95_ms",
        335.757,
        50.0,
    )
    performance_qualification.pytest_sessionfinish(  # type: ignore[arg-type]
        session,
        pytest.ExitCode.OK,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert session.exitstatus is pytest.ExitCode.OK
    assert payload["outcome"] == "runner_unqualified"
    assert payload["runner_qualified"] is False


def test_hosted_hook_fails_regression_when_runner_qualifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundaries = iter(
        (
            _boundary(True, True, True),
            _boundary(True, True, True),
        )
    )
    monkeypatch.setenv(
        "CODEX_USAGE_PERFORMANCE_LANE",
        PerformanceLane.GITHUB_HOSTED_QUALIFIED.value,
    )
    monkeypatch.delenv("CODEX_USAGE_PERFORMANCE_REPORT", raising=False)
    monkeypatch.setattr(
        performance_qualification,
        "measure_calibration_boundary",
        lambda: next(boundaries),
    )
    session = _Session()

    performance_qualification.pytest_sessionstart(session)  # type: ignore[arg-type]
    performance_qualification.record_wall_clock_budget(
        "active_writer_p95_ms",
        51.0,
        50.0,
    )
    performance_qualification.pytest_sessionfinish(  # type: ignore[arg-type]
        session,
        pytest.ExitCode.OK,
    )

    assert session.exitstatus is pytest.ExitCode.TESTS_FAILED


def test_runner_unqualified_does_not_suppress_an_existing_test_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    boundaries = iter(
        (
            _boundary(False, True, False),
            _boundary(True, True, True),
        )
    )
    monkeypatch.setenv(
        "CODEX_USAGE_PERFORMANCE_LANE",
        PerformanceLane.GITHUB_HOSTED_QUALIFIED.value,
    )
    monkeypatch.delenv("CODEX_USAGE_PERFORMANCE_REPORT", raising=False)
    monkeypatch.setattr(
        performance_qualification,
        "measure_calibration_boundary",
        lambda: next(boundaries),
    )
    session = _Session()
    session.exitstatus = pytest.ExitCode.TESTS_FAILED

    performance_qualification.pytest_sessionstart(session)  # type: ignore[arg-type]
    performance_qualification.record_wall_clock_budget(
        "active_writer_p95_ms",
        335.757,
        50.0,
    )
    performance_qualification.pytest_sessionfinish(  # type: ignore[arg-type]
        session,
        pytest.ExitCode.TESTS_FAILED,
    )

    output = capsys.readouterr().out
    assert "CI_PERFORMANCE_QUALIFICATION=" in output
    assert '"outcome":"runner_unqualified"' in output
    assert session.exitstatus is pytest.ExitCode.TESTS_FAILED
