"""File-based Agent Perf workload for Candidate C."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import shared

from .database import CandidateCDatabase


def write_agent_perf_workload(
    *,
    fixture: shared.FixtureBundle,
    workload_matrix_digest: str,
    output_path: Path,
) -> Path:
    """Write the exact standard workload wrapped by Agent Perf."""
    if fixture.profile != "standard":
        raise ValueError("Candidate C Agent Perf workload requires the standard fixture")
    payload = {
        "schema": shared.AGENT_PERF_WORKLOAD_SCHEMA,
        "version": 1,
        "candidate_id": "C",
        "fixture_profile": fixture.profile,
        "fixture_revision": fixture.fixture_revision,
        "fixture_manifest_digest": fixture.manifest_digest,
        "fixture_oracle_digest": fixture.oracle_digest,
        "workload_matrix_digest": workload_matrix_digest,
        "synthetic_only": True,
        "workload_id": "build.scale.standard",
        "command_argv": [
            "{python}",
            "-m",
            "candidate_c.workload",
            "--fixture-root",
            "{fixture_root}",
            "--output-root",
            "{output_root}",
        ],
        "environment": {"PYTHONHASHSEED": "0"},
        "minimum_unprofiled_runs": 5,
        "profile_is_attribution_only": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shared.load_agent_perf_workload(output_path)
    return output_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Candidate C's standard synthetic build.")
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    fixture = shared.load_fixture_bundle(arguments.fixture_root)
    if fixture.profile != "standard":
        raise SystemExit("Candidate C Agent Perf workload requires a standard fixture")
    physical_cores = max(1, os.cpu_count() or 1)
    matrix = shared.build_workload_matrix(physical_cores=physical_cores)
    database = CandidateCDatabase(arguments.output_root)
    database.build(
        fixture,
        label=f"agent-perf:{matrix.digest}",
        history_selection="all_time",
        parser_workers=1,
        index_mode="deferred",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
