from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.aggregate_performance_qualification import aggregate_reports
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


def test_invariants_lane_records_breaches_without_claiming_a_regression() -> None:
    assessment = classify_performance(
        lane=PerformanceLane.INVARIANTS,
        before=_boundary(),
        after=_boundary(),
        observations=(
            BudgetObservation("active_writer_p95_ms", 335.757, 50.0),
            BudgetObservation("active_writer_max_ms", 565.213, 150.0),
        ),
    )

    assert assessment.outcome is PerformanceOutcome.INVARIANTS_ONLY
    assert assessment.runner_qualified is None
    assert {item.metric for item in assessment.breaches} == {
        "active_writer_max_ms",
        "active_writer_p95_ms",
    }


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


def test_invariants_hook_never_calibrates_or_fails_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report = tmp_path / "invariants.json"
    monkeypatch.setenv(
        "CODEX_USAGE_PERFORMANCE_LANE",
        PerformanceLane.INVARIANTS.value,
    )
    monkeypatch.setenv("CODEX_USAGE_PERFORMANCE_REPORT", str(report))
    monkeypatch.setattr(
        performance_qualification,
        "measure_calibration_boundary",
        lambda: pytest.fail("invariants lane must not calibrate wall clock"),
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
    assert payload["outcome"] == "invariants_only"
    assert payload["runner_qualified"] is None


def test_strict_helper_still_fails_an_absolute_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CODEX_USAGE_PERFORMANCE_LANE",
        PerformanceLane.STRICT.value,
    )
    session = _Session()
    performance_qualification.pytest_sessionstart(session)  # type: ignore[arg-type]

    with pytest.raises(AssertionError, match="active_writer_p95_ms"):
        performance_qualification.record_wall_clock_budget(
            "active_writer_p95_ms",
            50.001,
            50.0,
        )


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
    assert '"pytest_exit_status":1' in output
    assert session.exitstatus is pytest.ExitCode.TESTS_FAILED


def _run_report(
    writer_p95_ms: float,
    *,
    outcome: str = "pass",
    runner_qualified: bool = True,
    pytest_exit_status: int = 0,
) -> dict[str, object]:
    return {
        "observations": [
            {
                "budget": 50.0,
                "metric": "active_writer_p95_ms",
                "observed": writer_p95_ms,
            },
            {
                "budget": 150.0,
                "metric": "active_writer_max_ms",
                "observed": writer_p95_ms + 5.0,
            },
        ],
        "outcome": outcome,
        "pytest_exit_status": pytest_exit_status,
        "runner_qualified": runner_qualified,
        "schema": "codex-usage-tracker.ci-performance-qualification.v1",
    }


def test_five_run_aggregate_does_not_call_one_host_pause_a_regression() -> None:
    reports = tuple(
        _run_report(value)
        for value in (20.0, 21.0, 335.757, 19.0, 22.0)
    )

    aggregate = aggregate_reports(reports)

    assert aggregate["outcome"] == "pass"
    assert aggregate["breaches"] == []
    writer = next(
        item
        for item in aggregate["metrics"]
        if item["metric"] == "active_writer_p95_ms"
    )
    assert writer["median"] == 21.0
    assert writer["maximum"] == 335.757


def test_five_run_aggregate_fails_a_sustained_median_regression() -> None:
    reports = tuple(
        _run_report(value)
        for value in (20.0, 51.0, 52.0, 53.0, 21.0)
    )

    aggregate = aggregate_reports(reports)

    assert aggregate["outcome"] == "product_regression"
    assert [item["metric"] for item in aggregate["breaches"]] == [
        "active_writer_p95_ms"
    ]


def test_five_run_aggregate_keeps_failure_classes_distinct() -> None:
    healthy = tuple(_run_report(20.0) for _index in range(5))
    unqualified = list(healthy)
    unqualified[2] = _run_report(
        335.757,
        outcome="runner_unqualified",
        runner_qualified=False,
    )
    failed = list(healthy)
    failed[2] = _run_report(20.0, pytest_exit_status=1)
    timed_out = list(healthy)
    timed_out[2] = {
        "outcome": "suite_timeout",
        "schema": "codex-usage-tracker.ci-performance-qualification.v1",
        "timeout_seconds": 300,
    }

    assert aggregate_reports(tuple(unqualified))["outcome"] == "runner_unqualified"
    assert aggregate_reports(tuple(failed))["outcome"] == "test_failure"
    assert aggregate_reports(tuple(timed_out))["outcome"] == "suite_timeout"
    assert aggregate_reports(healthy[:4])["outcome"] == "invalid_report"
