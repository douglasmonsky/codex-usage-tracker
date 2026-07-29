from __future__ import annotations

import argparse
import os
from pathlib import Path

import shared

from .ingest import file_sha256
from .publication import publish_artifact


def _positive_environment_integer(name: str) -> int:
    value = os.environ.get(name)
    if value is None:
        raise ValueError(f"candidate A profiler workload requires {name}")
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"candidate A profiler workload has invalid {name}") from error
    if parsed < 1:
        raise ValueError(f"candidate A profiler workload requires positive {name}")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Candidate A's standard synthetic build workload.",
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = shared.load_agent_perf_workload(Path(__file__).with_name("agent-perf-workload.json"))
    physical_cores = _positive_environment_integer("CANDIDATE_A_PHYSICAL_CORES")
    parser_workers = _positive_environment_integer("CANDIDATE_A_PARSER_WORKERS")
    if parser_workers != 1:
        raise ValueError(
            "candidate A build.scale.standard profiler workload uses one parser worker"
        )
    matrix = shared.build_workload_matrix(physical_cores=physical_cores)
    if matrix.digest != contract.workload_matrix_digest:
        raise ValueError("candidate A profiler workload matrix differs from the pinned contract")
    fixture = shared.load_fixture_bundle(args.fixture)
    if fixture.profile != contract.fixture_profile:
        raise ValueError("candidate A profiler workload requires the standard fixture")
    if (
        fixture.manifest_digest != contract.fixture_manifest_digest
        or fixture.oracle_digest != contract.fixture_oracle_digest
    ):
        raise ValueError("candidate A profiler fixture digests differ from the pinned contract")
    args.output.mkdir(parents=True, exist_ok=False)
    artifact = publish_artifact(fixture, args.output)
    if artifact.stats.parser_workers != parser_workers:
        raise ValueError("candidate A profiler workload used a different parser-worker count")
    (args.output / "result.json").write_bytes(
        shared.canonical_json_bytes(
            {
                "artifact_sha256": file_sha256(artifact.path),
                "candidate_id": "A",
                "manifest_digest": fixture.manifest_digest,
                "oracle_digest": fixture.oracle_digest,
                "parser_workers": parser_workers,
                "physical_cores": physical_cores,
                "publication_id": artifact.publication_id,
                "workload_matrix_digest": matrix.digest,
                "workload_id": contract.workload_id,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
