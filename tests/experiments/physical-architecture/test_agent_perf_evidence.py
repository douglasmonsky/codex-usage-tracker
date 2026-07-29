from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

agent_perf_runner = importlib.import_module("shared.agent_perf_runner")

AgentPerfEvidenceError = agent_perf_runner.AgentPerfEvidenceError
ProcessCapture = agent_perf_runner.ProcessCapture
collect_agent_perf_evidence = agent_perf_runner.collect_agent_perf_evidence

_WORKLOAD_PATH = _EXPERIMENT_ROOT / "candidate_a" / "agent-perf-workload.json"
_SHA_A = "a" * 64
_PROFILE_RUN_ID = "20260729T120000Z-1234abcd"


def _fixture(root: Path, workload: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        root=root.resolve(),
        profile="standard",
        fixture_revision="agent-kernel-structural-v1",
        manifest_digest=workload["fixture_manifest_digest"],
        oracle_digest=workload["fixture_oracle_digest"],
        manifest={
            "format_policy": {"content_bodies": False},
            "schema": "codex-usage-tracker.synthetic-fixture-manifest.v1",
        },
    )


def _result(workload: dict[str, object], *, artifact_sha256: str = _SHA_A) -> dict[str, object]:
    return {
        "artifact_sha256": artifact_sha256,
        "candidate_id": "A",
        "manifest_digest": workload["fixture_manifest_digest"],
        "oracle_digest": workload["fixture_oracle_digest"],
        "parser_workers": 1,
        "physical_cores": 10,
        "publication_id": "publication:v1:synthetic",
        "workload_matrix_digest": workload["workload_matrix_digest"],
        "workload_id": "build.scale.standard",
    }


class _FakeProcessRunner:
    def __init__(
        self,
        *,
        repository_root: Path,
        python_executable: Path,
        agent_perf_executable: Path,
        workload: dict[str, object],
        mismatched_sample: int | None = None,
        profile_exit_code: int = 0,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.python_executable = python_executable.resolve()
        self.agent_perf_executable = agent_perf_executable.resolve()
        self.workload = workload
        self.mismatched_sample = mismatched_sample
        self.profile_exit_code = profile_exit_code
        self.calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []

    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        environment: dict[str, str],
    ) -> ProcessCapture:
        self.calls.append((argv, cwd, environment))
        is_profile = Path(argv[0]).resolve() == self.agent_perf_executable
        command = argv[argv.index("--") + 1 :] if is_profile else argv
        assert Path(command[0]).resolve() == self.python_executable
        assert tuple(command[1:3]) == ("-m", "candidate_a.workload")
        output_root = Path(command[command.index("--output") + 1])
        output_root.mkdir(parents=True, exist_ok=False)
        sample_index = len(self.calls)
        result = _result(
            self.workload,
            artifact_sha256=("b" * 64 if sample_index == self.mismatched_sample else _SHA_A),
        )
        (output_root / "result.json").write_bytes(agent_perf_runner.canonical_json_bytes(result))

        stdout = b"synthetic command output that must not enter evidence"
        if is_profile:
            state_root = Path(environment["AGENT_PERF_STATE_DIR"])
            run_root = state_root / "runs" / _PROFILE_RUN_ID
            run_root.mkdir(parents=True)
            normalized = {
                "duration_seconds": 1.25,
                "executable": self.python_executable.name,
                "exit_code": 0,
                "hotspots": [
                    {
                        "column": None,
                        "function": "publish_artifact",
                        "inclusive_samples": 42.25,
                        "line": 211,
                        "mapping_confidence": "original",
                        "module": None,
                        "self_samples": 42.25,
                        "source_path": str(
                            self.repository_root
                            / "experiments"
                            / "physical-architecture"
                            / "candidate_a"
                            / "publication.py"
                        ),
                        "total_share": 0.4225,
                    }
                ],
                "label": "ck04-candidate-a-standard",
                "mode": "cpu",
                "profiler": "scalene",
                "profiler_version": "2.3.0",
                "raw_artifacts": [str(run_root / "raw" / "scalene.json")],
                "root": str(self.repository_root),
                "run_id": _PROFILE_RUN_ID,
                "runtime": "python",
                "schema_version": 1,
                "started_at": "2026-07-29T12:00:00+00:00",
                "status": "complete",
                "warnings": ["synthetic warning body that must not enter evidence"],
            }
            (run_root / "normalized.json").write_text(
                json.dumps(normalized, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (run_root / "report.md").write_text("# Local report\n", encoding="utf-8")
            stdout = json.dumps(
                {
                    "report": str(run_root / "report.md"),
                    "run_id": _PROFILE_RUN_ID,
                },
                sort_keys=True,
            ).encode()
        return ProcessCapture(
            exit_code=self.profile_exit_code if is_profile else 0,
            observed_processes=2 if is_profile else 1,
            process_tree_cpu_ns=sample_index * 100_000_000,
            stderr=b"synthetic stderr body that must not enter evidence",
            stdout=stdout,
            wall_time_ns=sample_index * 200_000_000,
        )


def _collect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mismatched_sample: int | None = None,
    profile_exit_code: int = 0,
) -> tuple[dict[str, object], _FakeProcessRunner, Path]:
    workload = json.loads(_WORKLOAD_PATH.read_text(encoding="utf-8"))
    fixture_root = tmp_path / "standard-fixture"
    fixture_root.mkdir()
    python_executable = tmp_path / "python"
    python_executable.touch(mode=0o755)
    agent_perf_executable = tmp_path / "agent-perf"
    agent_perf_executable.touch(mode=0o755)
    fake_process = _FakeProcessRunner(
        repository_root=_REPO_ROOT,
        python_executable=python_executable,
        agent_perf_executable=agent_perf_executable,
        workload=workload,
        mismatched_sample=mismatched_sample,
        profile_exit_code=profile_exit_code,
    )
    monkeypatch.setattr(
        agent_perf_runner,
        "load_fixture_bundle",
        lambda _: _fixture(fixture_root, workload),
    )
    monkeypatch.setattr(
        agent_perf_runner,
        "_pinned_tool_versions",
        lambda _: {
            "agent_perf": "0.1.0",
            "psutil": "7.2.2",
            "scalene": "2.3.0",
        },
    )
    destination = tmp_path / "agent-perf-evidence.json"
    build = collect_agent_perf_evidence(
        repository_root=_REPO_ROOT,
        workload_path=_WORKLOAD_PATH,
        fixture_root=fixture_root,
        destination=destination,
        python_executable=python_executable,
        agent_perf_executable=agent_perf_executable,
        scratch_root=tmp_path / "scratch",
        process_runner=fake_process,
    )
    return build.payload, fake_process, destination


def test_collector_runs_five_exact_unprofiled_commands_then_one_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, fake_process, destination = _collect(tmp_path, monkeypatch)

    assert payload["schema"] == "codex-usage-tracker.ck04-agent-perf-evidence.v1"
    assert payload["candidate_id"] == "A"
    assert len(payload["unprofiled_runs"]) == 5
    assert len(fake_process.calls) == 6
    direct_commands = [call[0] for call in fake_process.calls[:5]]
    assert len({command[-1] for command in direct_commands}) == 5
    assert all(command[:3] == direct_commands[0][:3] for command in direct_commands)
    profiled = fake_process.calls[-1][0]
    assert profiled[:3] == (
        str(fake_process.agent_perf_executable),
        "run",
        "--root",
    )
    assert "--runtime" in profiled
    assert profiled[profiled.index("--runtime") + 1] == "python"
    assert profiled[profiled.index("--label") + 1] == "ck04-candidate-a-standard"
    assert profiled[profiled.index("--include") + 1] == (
        "experiments/physical-architecture/candidate_a"
    )
    assert profiled[profiled.index("--") + 1 :] == payload["profiled_run"]["command_shape"]

    identities = {run["result_identity_sha256"] for run in payload["unprofiled_runs"]}
    assert identities == {payload["profiled_run"]["result_identity_sha256"]}
    assert payload["profiled_run"]["profile"]["hotspots"] == [
        {
            "python_cpu_percent": "42.25",
            "rank": 1,
            "source": "experiments/physical-architecture/candidate_a/publication.py",
            "symbol": "publish_artifact",
        }
    ]
    serialized = destination.read_bytes()
    assert serialized == agent_perf_runner.canonical_json_bytes(payload)
    assert str(tmp_path).encode() not in serialized
    assert b"synthetic command output" not in serialized
    assert b"synthetic stderr body" not in serialized
    assert b"synthetic warning body" not in serialized


def test_collector_fails_closed_on_result_mismatch_without_writing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(AgentPerfEvidenceError, match="result identities differ"):
        _collect(tmp_path, monkeypatch, mismatched_sample=3)
    assert not (tmp_path / "agent-perf-evidence.json").exists()


def test_collector_refuses_an_existing_destination_before_running_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, fake_process, destination = _collect(tmp_path, monkeypatch)
    assert payload
    call_count = len(fake_process.calls)
    with pytest.raises(AgentPerfEvidenceError, match="already exists"):
        collect_agent_perf_evidence(
            repository_root=_REPO_ROOT,
            workload_path=_WORKLOAD_PATH,
            fixture_root=tmp_path / "standard-fixture",
            destination=destination,
            python_executable=fake_process.python_executable,
            agent_perf_executable=fake_process.agent_perf_executable,
            scratch_root=tmp_path / "second-scratch",
            process_runner=fake_process,
        )
    assert len(fake_process.calls) == call_count


def test_collector_rejects_nonstandard_fixture_before_process_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workload = json.loads(_WORKLOAD_PATH.read_text(encoding="utf-8"))
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = _fixture(fixture_root, workload)
    fixture.profile = "tiny"
    monkeypatch.setattr(agent_perf_runner, "load_fixture_bundle", lambda _: fixture)
    monkeypatch.setattr(
        agent_perf_runner,
        "_pinned_tool_versions",
        lambda _: {
            "agent_perf": "0.1.0",
            "psutil": "7.2.2",
            "scalene": "2.3.0",
        },
    )
    calls: list[object] = []

    with pytest.raises(AgentPerfEvidenceError, match="standard synthetic fixture"):
        collect_agent_perf_evidence(
            repository_root=_REPO_ROOT,
            workload_path=_WORKLOAD_PATH,
            fixture_root=fixture_root,
            destination=tmp_path / "evidence.json",
            python_executable=Path(sys.executable),
            agent_perf_executable=tmp_path / "agent-perf",
            scratch_root=tmp_path / "scratch",
            process_runner=lambda *args, **kwargs: calls.append((args, kwargs)),
        )
    assert calls == []


def test_collector_rejects_profile_failure_and_unknown_profiler_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(AgentPerfEvidenceError, match="profile process failed"):
        _collect(tmp_path, monkeypatch, profile_exit_code=2)

    workload = json.loads(_WORKLOAD_PATH.read_text(encoding="utf-8"))
    fixture_root = tmp_path / "other-fixture"
    fixture_root.mkdir()
    monkeypatch.setattr(
        agent_perf_runner,
        "load_fixture_bundle",
        lambda _: _fixture(fixture_root, workload),
    )
    monkeypatch.setattr(
        agent_perf_runner,
        "_pinned_tool_versions",
        lambda _: {
            "agent_perf": "0.1.0",
            "psutil": "7.2.2",
            "scalene": "unknown",
        },
    )
    with pytest.raises(AgentPerfEvidenceError, match="Scalene 2.3.0"):
        collect_agent_perf_evidence(
            repository_root=_REPO_ROOT,
            workload_path=_WORKLOAD_PATH,
            fixture_root=fixture_root,
            destination=tmp_path / "unknown-pin.json",
            python_executable=Path(sys.executable),
            agent_perf_executable=tmp_path / "agent-perf",
            scratch_root=tmp_path / "other-scratch",
        )
