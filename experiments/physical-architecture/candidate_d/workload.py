from __future__ import annotations

import argparse
from pathlib import Path
from typing import NoReturn

import shared

from .adapter import Adapter
from .crash import run_crash_worker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the synthetic CK-04 Candidate D workload.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run build.scale.standard once.")
    run.add_argument("--fixture", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--physical-cores", type=int, required=True)

    crash = subparsers.add_parser("crash-worker", help=argparse.SUPPRESS)
    crash.add_argument("--boundary", required=True)
    crash.add_argument("--prior", type=Path, required=True)
    crash.add_argument("--candidate", type=Path, required=True)
    crash.add_argument("--run-root", type=Path, required=True)
    crash.add_argument("--marker", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "crash-worker":
        run_crash_worker(
            boundary=str(arguments.boundary),
            prior=arguments.prior,
            candidate=arguments.candidate,
            run_root=arguments.run_root,
            marker=arguments.marker,
        )
        return 0
    if arguments.command == "run":
        return _run_standard(
            fixture_root=arguments.fixture,
            output_root=arguments.output,
            physical_cores=int(arguments.physical_cores),
        )
    return _unreachable(str(arguments.command))


def _run_standard(
    *,
    fixture_root: Path,
    output_root: Path,
    physical_cores: int,
) -> int:
    fixture = shared.load_fixture_bundle(fixture_root)
    if fixture.profile != "standard":
        raise ValueError("Candidate D agent-perf workload requires the standard fixture")
    matrix = shared.build_workload_matrix(physical_cores=physical_cores)
    case = matrix.by_id("build.scale.standard")
    output_root.mkdir(parents=True, exist_ok=True)
    request = shared.CandidateRequest(
        case=case,
        fixture=fixture,
        run_root=output_root,
        repetition=0,
        stop=shared.EarlyStopController(case.case_id, case.early_stop_limits),
    )
    result = shared.execute_candidate(Adapter(), request)
    (output_root / "candidate-d-standard-result.json").write_bytes(
        shared.canonical_json_bytes(
            {
                "candidate_id": result.candidate_id,
                "case_id": result.case_id,
                "outcome": result.outcome.value,
                "oracle_equivalent": result.measurements.oracle_equivalent,
                "database_bytes": result.measurements.database_bytes,
                "fact_rows": result.measurements.fact_rows,
                "sequence_rows": result.measurements.sequence_rows,
                "workload_matrix_digest": matrix.digest,
            }
        )
    )
    return 0 if result.outcome is shared.RunOutcome.PASSED else 1


def _unreachable(command: str) -> NoReturn:
    raise AssertionError(f"unreachable Candidate D workload command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
