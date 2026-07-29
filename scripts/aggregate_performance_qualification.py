#!/usr/bin/env python3
"""Aggregate repeated performance qualification reports."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

_RUN_SCHEMA = "codex-usage-tracker.ci-performance-qualification.v1"
_AGGREGATE_SCHEMA = "codex-usage-tracker.ci-performance-qualification.aggregate.v1"
_REQUIRED_REPETITIONS = 5
_COMPLETED_OUTCOMES = {"pass", "product_regression", "runner_unqualified"}
_BLOCKING_OUTCOMES = {
    "invalid_report",
    "product_regression",
    "suite_timeout",
    "test_failure",
}


class MetricSummary(TypedDict):
    budget: float
    coefficient_of_variation: float
    maximum: float
    median: float
    metric: str
    p95: float
    samples: list[float]


def _base_report(
    reports: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "breaches": [],
        "metrics": [],
        "repetitions_expected": _REQUIRED_REPETITIONS,
        "repetitions_received": len(reports),
        "run_outcomes": [str(report.get("outcome", "missing")) for report in reports],
        "schema": _AGGREGATE_SCHEMA,
    }


def _terminal_report(
    reports: Sequence[Mapping[str, object]],
    outcome: str,
    reason: str,
) -> dict[str, object]:
    result = _base_report(reports)
    result.update({"outcome": outcome, "reason": reason})
    return result


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _observation_map(
    report: Mapping[str, object],
) -> dict[str, tuple[float, float]] | None:
    raw_observations = report.get("observations")
    if not isinstance(raw_observations, list) or not raw_observations:
        return None
    observations: dict[str, tuple[float, float]] = {}
    for raw in raw_observations:
        if not isinstance(raw, Mapping):
            return None
        metric = raw.get("metric")
        observed = _number(raw.get("observed"))
        budget = _number(raw.get("budget"))
        if (
            not isinstance(metric, str)
            or not metric
            or observed is None
            or budget is None
            or metric in observations
        ):
            return None
        observations[metric] = (observed, budget)
    return observations


def _aggregate_metrics(
    reports: Sequence[Mapping[str, object]],
) -> list[MetricSummary] | None:
    run_maps = [_observation_map(report) for report in reports]
    if any(item is None for item in run_maps):
        return None
    observations = [item for item in run_maps if item is not None]
    metric_names = set(observations[0])
    if any(set(item) != metric_names for item in observations[1:]):
        return None

    metrics: list[MetricSummary] = []
    for metric in sorted(metric_names):
        samples = [item[metric][0] for item in observations]
        budgets = {item[metric][1] for item in observations}
        if len(budgets) != 1:
            return None
        budget = budgets.pop()
        ordered = sorted(samples)
        mean = statistics.fmean(samples)
        coefficient_of_variation = (
            statistics.pstdev(samples) / mean if mean else 0.0
        )
        metrics.append(
            {
                "budget": round(budget, 6),
                "coefficient_of_variation": round(coefficient_of_variation, 6),
                "maximum": round(ordered[-1], 6),
                "median": round(statistics.median(samples), 6),
                "metric": metric,
                "p95": round(
                    ordered[math.ceil(len(ordered) * 0.95) - 1],
                    6,
                ),
                "samples": [round(sample, 6) for sample in samples],
            }
        )
    return metrics


def aggregate_reports(
    reports: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Classify five fresh-process qualification reports."""

    if len(reports) != _REQUIRED_REPETITIONS:
        return _terminal_report(
            reports,
            "invalid_report",
            "exactly five qualification reports are required",
        )
    if any(report.get("schema") != _RUN_SCHEMA for report in reports):
        return _terminal_report(
            reports,
            "invalid_report",
            "one or more reports use an unsupported schema",
        )

    outcomes = [report.get("outcome") for report in reports]
    if any(outcome == "suite_timeout" for outcome in outcomes):
        return _terminal_report(
            reports,
            "suite_timeout",
            "at least one qualification repetition exceeded its host deadline",
        )
    if any(outcome not in _COMPLETED_OUTCOMES for outcome in outcomes):
        return _terminal_report(
            reports,
            "invalid_report",
            "one or more reports use an unsupported outcome",
        )

    exit_statuses = [report.get("pytest_exit_status") for report in reports]
    if any(
        isinstance(status, bool) or not isinstance(status, int)
        for status in exit_statuses
    ):
        return _terminal_report(
            reports,
            "invalid_report",
            "completed reports must include an integer pytest_exit_status",
        )
    if any(status != 0 for status in exit_statuses):
        return _terminal_report(
            reports,
            "test_failure",
            "at least one repetition had a deterministic pytest failure",
        )

    qualifications = [report.get("runner_qualified") for report in reports]
    if any(not isinstance(value, bool) for value in qualifications):
        return _terminal_report(
            reports,
            "invalid_report",
            "completed reports must declare runner_qualified",
        )
    if not all(qualifications):
        return _terminal_report(
            reports,
            "runner_unqualified",
            "all five repetitions must qualify the shared runner",
        )

    metrics = _aggregate_metrics(reports)
    if metrics is None:
        return _terminal_report(
            reports,
            "invalid_report",
            "metric names and budgets must match across all repetitions",
        )
    breaches = [
        metric
        for metric in metrics
        if metric["median"] > metric["budget"]
    ]
    result = _base_report(reports)
    result.update(
        {
            "breaches": breaches,
            "metrics": metrics,
            "outcome": "product_regression" if breaches else "pass",
            "runner_qualified_repetitions": len(reports),
        }
    )
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate five performance qualification JSON reports.",
    )
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports: list[Mapping[str, object]] = []
    read_error: str | None = None
    for path in args.reports:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            read_error = f"{path}: {error}"
            break
        if not isinstance(payload, dict):
            read_error = f"{path}: report root must be an object"
            break
        reports.append(payload)

    if read_error is None:
        result = aggregate_reports(tuple(reports))
    else:
        result = _terminal_report(
            tuple(reports),
            "invalid_report",
            read_error,
        )
    encoded = json.dumps(result, separators=(",", ":"), sort_keys=True)
    args.output.write_text(encoded + "\n", encoding="utf-8")
    print(f"CI_PERFORMANCE_QUALIFICATION_AGGREGATE={encoded}")
    return 1 if result["outcome"] in _BLOCKING_OUTCOMES else 0


if __name__ == "__main__":
    raise SystemExit(main())
