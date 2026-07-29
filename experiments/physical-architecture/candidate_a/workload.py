from __future__ import annotations

import argparse
from pathlib import Path

import shared

from .ingest import file_sha256
from .publication import publish_artifact


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Candidate A's standard synthetic build workload.",
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = shared.load_agent_perf_workload(
        Path(__file__).with_name("agent-perf-workload.json")
    )
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
    (args.output / "result.json").write_bytes(
        shared.canonical_json_bytes(
            {
                "artifact_sha256": file_sha256(artifact.path),
                "candidate_id": "A",
                "manifest_digest": fixture.manifest_digest,
                "oracle_digest": fixture.oracle_digest,
                "publication_id": artifact.publication_id,
                "workload_id": contract.workload_id,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
