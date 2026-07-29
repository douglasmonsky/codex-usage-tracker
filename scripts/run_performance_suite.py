#!/usr/bin/env python3
"""Run the fixed synthetic performance suite under a host-owned deadline."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_REPORT_SCHEMA = "codex-usage-tracker.ci-performance-qualification.v1"
_DEFAULT_TIMEOUT_SECONDS = 300
_TERMINATION_GRACE_SECONDS = 30
_PERFORMANCE_TESTS = (
    "tests/kernel/test_ingest_performance.py",
    "tests/kernel/allowance/test_performance.py",
    "tests/kernel/evidence/test_performance.py",
    "tests/kernel/interfaces/test_performance.py",
    "tests/kernel/query/test_performance.py",
)
_LANES = ("github_hosted_qualified", "invariants", "strict")


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=_TERMINATION_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGKILL)
    else:
        process.kill()
    process.wait()


def _write_timeout_report(
    path: Path,
    timeout_seconds: float,
    lane: str,
) -> None:
    payload = {
        "lane": lane,
        "outcome": "suite_timeout",
        "schema": _REPORT_SCHEMA,
        "timeout_seconds": timeout_seconds,
    }
    path.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_bounded_command(
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
    timeout_seconds: float,
    report_path: Path | None,
) -> int:
    """Run one process and classify only an observed host deadline as timeout."""

    if timeout_seconds <= 0:
        raise ValueError("performance timeout must be positive")
    process = subprocess.Popen(
        tuple(command),
        env=dict(environment),
        start_new_session=os.name == "posix",
    )
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process(process)
        if report_path is not None:
            _write_timeout_report(
                report_path,
                timeout_seconds,
                environment.get(
                    "CODEX_USAGE_PERFORMANCE_LANE",
                    "unknown",
                ),
            )
        print(
            "performance suite deadline exceeded; "
            "bounded non-completion is not a product regression",
            file=sys.stderr,
        )
        return 124


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the fixed synthetic performance suite with a deadline.",
    )
    parser.add_argument("--lane", required=True, choices=_LANES)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=_DEFAULT_TIMEOUT_SECONDS,
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    environment = dict(os.environ)
    environment["CODEX_USAGE_PERFORMANCE_LANE"] = args.lane
    if args.report is not None:
        environment["CODEX_USAGE_PERFORMANCE_REPORT"] = str(args.report)
    else:
        environment.pop("CODEX_USAGE_PERFORMANCE_REPORT", None)
    command = (
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:tach",
        "-p",
        "tests.kernel.performance_qualification",
        *_PERFORMANCE_TESTS,
    )
    return run_bounded_command(
        command,
        environment=environment,
        timeout_seconds=args.timeout_seconds,
        report_path=args.report,
    )


if __name__ == "__main__":
    raise SystemExit(main())
