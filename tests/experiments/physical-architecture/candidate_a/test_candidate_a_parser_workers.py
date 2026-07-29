from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
candidate_a = importlib.import_module("candidate_a")
ingest_module = importlib.import_module("candidate_a.ingest")

_TINY_FIXTURE = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"
_AGENT_PERF_CONTRACT = _EXPERIMENT_ROOT / "candidate_a" / "agent-perf-workload.json"
_QUALIFICATION_PHYSICAL_CORES = 10
_WORKER_COUNTS = (1, 2, 4, 8)


@pytest.fixture
def fixture() -> Any:
    return shared.load_fixture_bundle(_TINY_FIXTURE)


def test_parser_worker_matrix_is_bounded_and_byte_identical(
    fixture: Any,
    tmp_path: Path,
) -> None:
    artifacts = [
        candidate_a.build_artifact(
            fixture,
            tmp_path / f"candidate-a-workers-{workers}.sqlite",
            parser_workers=workers,
        )
        for workers in _WORKER_COUNTS
    ]

    digests = {ingest_module.file_sha256(artifact.path) for artifact in artifacts}
    assert len(digests) == 1
    for workers, artifact in zip(_WORKER_COUNTS, artifacts, strict=True):
        stats = artifact.stats
        assert stats.parser_workers == workers
        assert stats.parser_tasks_submitted == stats.source_files_parsed
        expected_queue_capacity = 1 if workers == 1 else min(stats.source_files_parsed, workers * 2)
        assert stats.parser_queue_capacity == expected_queue_capacity
        assert 0 < stats.parser_peak_pending <= stats.parser_queue_capacity
        assert stats.parser_worker_time_ns > 0
        assert stats.parser_pipeline_time_ns > 0
        assert stats.parser_merge_time_ns > 0
        assert 0 <= stats.parser_parallel_efficiency_ppm <= 1_000_000


@pytest.mark.parametrize("parser_workers", (False, 0, 9))
def test_parser_worker_count_fails_before_creating_sqlite(
    fixture: Any,
    tmp_path: Path,
    parser_workers: int,
) -> None:
    output = tmp_path / f"invalid-workers-{parser_workers}.sqlite"

    with pytest.raises(ValueError, match="parser_workers must be between 1 and 8"):
        candidate_a.build_artifact(
            fixture,
            output,
            parser_workers=parser_workers,
        )

    assert not output.exists()


def test_agent_perf_contract_pins_the_profiled_host_and_worker_count() -> None:
    contract = shared.load_agent_perf_workload(_AGENT_PERF_CONTRACT)
    matrix = shared.build_workload_matrix(physical_cores=_QUALIFICATION_PHYSICAL_CORES)

    assert contract.environment["CANDIDATE_A_PHYSICAL_CORES"] == "10"
    assert contract.environment["CANDIDATE_A_PARSER_WORKERS"] == "1"
    assert contract.workload_matrix_digest == matrix.digest
    assert contract.workload_id == "build.scale.standard"
    assert contract.minimum_unprofiled_runs == 5
    assert contract.profile_is_attribution_only
