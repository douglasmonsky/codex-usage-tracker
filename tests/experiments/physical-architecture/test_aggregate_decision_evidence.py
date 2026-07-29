from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_EXPERIMENT_ROOT = _REPOSITORY_ROOT / "experiments" / "physical-architecture"
_TEST_ROOT = Path(__file__).resolve().parent
for path in (_EXPERIMENT_ROOT, _TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

aggregate = importlib.import_module("aggregate_decision_evidence")
decision_evidence = importlib.import_module("decision_evidence")
shared = importlib.import_module("shared")
decision_tests = importlib.import_module("test_decision_evidence")


def _canonical(value: object) -> bytes:
    return shared.canonical_json_bytes(value)


def _write_bundle(
    root: Path,
    *,
    candidate_id: str = "A",
    case_id: str = "query.feature.bounded_full_sort",
    profile: str = "standard",
    repetitions: int = 5,
    outcome: str = "passed",
    partial: bool = False,
    code_commit: str = "a" * 40,
    fixture_manifest_digest: str = "b" * 64,
    fixture_oracle_digest: str = "c" * 64,
    oracle_results: dict[str, object] | None = None,
) -> Path:
    root.mkdir()
    environment = decision_tests._environment()["identity"]
    environment_digest = shared.canonical_sha256(environment)
    invocation_base = {
        "schema": "codex-usage-tracker.physical-bakeoff-invocation.v1",
        "run_id": f"{candidate_id.lower()}-{profile}",
        "code_commit": code_commit,
        "fixture": {
            "profile": profile,
            "fixture_revision": shared.FIXTURE_REVISION,
            "manifest_digest": fixture_manifest_digest,
            "oracle_digest": fixture_oracle_digest,
        },
        "workload_matrix_digest": "d" * 64,
        "environment": environment,
        "environment_digest": environment_digest,
        "candidate_ids": [candidate_id],
        "case_ids": [case_id],
        "group_ids": [],
        "repetitions": repetitions,
        "speed_claim": repetitions >= 5,
        "profiled": False,
        "include_research": False,
        "qualification_model": None,
        "retain_run_artifacts": False,
        "completion_marker": "summary.json",
    }
    invocation = {
        **invocation_base,
        "invocation_digest": shared.canonical_sha256(invocation_base),
    }
    measurements: list[dict[str, object]] = []
    details: list[dict[str, object]] = []
    for repetition in range(repetitions):
        identity = {
            "run_id": invocation["run_id"],
            "candidate_id": candidate_id,
            "case_id": case_id,
            "fixture_profile": profile,
            "fixture_manifest_digest": fixture_manifest_digest,
            "fixture_oracle_digest": fixture_oracle_digest,
            "repetition": repetition,
            "profiled": False,
            "code_commit": code_commit,
            "workload_matrix_digest": invocation["workload_matrix_digest"],
            "environment": environment,
            "qualification_model": None,
        }
        values = {
            "answer_correct": True,
            "automatic_index_count": repetition,
            "full_scan_count": repetition + 1,
            "mcp_latency_ns": 100 + repetition,
            "oracle_equivalent": True,
            "response_bytes": 200 + repetition,
            "selector_pages_gap_free": True,
            "sql_latencies_ns": [10 + repetition],
            "sql_statements": 2,
            "temporary_sort_count": repetition + 2,
        }
        measurement = {
            "schema": shared.MEASUREMENT_SCHEMA,
            "identity": identity,
            "wall_time_ns": (
                7_000_000_000 + repetition if outcome == "stopped" else 1_000 + repetition
            ),
            "process_cpu_ns": 900 + repetition,
            "outcome": outcome,
            "partial": partial,
            "stop_decision": (
                {"case_id": case_id, "maximum": 5_000, "metric": "elapsed_ms", "observed": 6_489}
                if outcome == "stopped"
                else None
            ),
            "detail_code": None,
            "values": values,
        }
        projected_identity = {
            **{key: value for key, value in identity.items() if key != "environment"},
            "environment_digest": environment_digest,
        }
        detail_base = {
            "schema": "codex-usage-tracker.physical-bakeoff-detail.v1",
            "invocation_digest": invocation["invocation_digest"],
            "execution_index": repetition,
            "measurement_identity": projected_identity,
            "measurement_identity_digest": shared.canonical_sha256(projected_identity),
            "measurement_record_digest": shared.canonical_sha256(measurement),
            "outcome": outcome,
            "partial": partial,
            "stop_decision": measurement["stop_decision"],
            "detail_code": ("candidate_d.stopped.elapsed_ms" if outcome == "stopped" else None),
            "oracle_results": oracle_results,
        }
        measurements.append(measurement)
        details.append({**detail_base, "detail_digest": shared.canonical_sha256(detail_base)})
    measurement_bytes = b"".join(_canonical(row) for row in measurements)
    detail_bytes = b"".join(_canonical(row) for row in details)
    summary_base = {
        "schema": "codex-usage-tracker.physical-bakeoff-summary.v1",
        "status": "failed" if outcome == "stopped" else "passed",
        "run_id": invocation["run_id"],
        "invocation_digest": invocation["invocation_digest"],
        "code_commit": code_commit,
        "fixture_manifest_digest": fixture_manifest_digest,
        "fixture_oracle_digest": fixture_oracle_digest,
        "workload_matrix_digest": invocation["workload_matrix_digest"],
        "environment_digest": environment_digest,
        "measurement_file": "measurements.jsonl",
        "measurement_sha256": hashlib.sha256(measurement_bytes).hexdigest(),
        "records": repetitions,
        "details_file": "details.jsonl",
        "details_sha256": hashlib.sha256(detail_bytes).hexdigest(),
        "detail_records": repetitions,
        "planned_executions": repetitions,
        "optional_repetitions_skipped": 0,
        "retain_run_artifacts": False,
        "failure": (
            {
                "candidate_id": candidate_id,
                "case_id": case_id,
                "detail_code": "candidate_d.stopped.elapsed_ms",
            }
            if outcome == "stopped"
            else None
        ),
        "cases": [],
    }
    summary = {**summary_base, "summary_digest": shared.canonical_sha256(summary_base)}
    (root / "invocation.json").write_bytes(_canonical(invocation))
    (root / "measurements.jsonl").write_bytes(measurement_bytes)
    (root / "details.jsonl").write_bytes(detail_bytes)
    (root / "summary.json").write_bytes(_canonical(summary))
    return root


def test_authenticates_bundle_and_projects_exact_query_row(tmp_path: Path) -> None:
    bundle = aggregate.authenticate_qualification_bundle(_write_bundle(tmp_path / "run"))
    row = aggregate.project_query_rows([bundle])[0]
    assert row["query_case_id"] == "query.feature.bounded_full_sort"
    assert row["repetitions"] == 5
    assert row["sql_latency_p95_ns"] == 14
    assert row["mcp_latency_p95_ns"] == 104
    assert row["response_bytes_max"] == 204
    assert row["observed_plan_counts"] == {
        "automatic_indexes": 4,
        "full_scans": 5,
        "sql_statements": 2,
        "temporary_sorts": 6,
    }


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda root: (root / "measurements.jsonl").write_bytes(b"{}\n"), "measurement digest"),
        (
            lambda root: (root / "invocation.json").write_text(
                json.dumps(json.loads((root / "invocation.json").read_bytes()), indent=2),
                encoding="utf-8",
            ),
            "canonical",
        ),
        (lambda root: (root / "details.jsonl").unlink(), "missing"),
    ],
)
def test_rejects_stale_hash_noncanonical_or_missing_artifact(
    tmp_path: Path,
    mutation: Any,
    match: str,
) -> None:
    root = _write_bundle(tmp_path / "run")
    mutation(root)
    with pytest.raises(aggregate.AggregateEvidenceError, match=match):
        aggregate.authenticate_qualification_bundle(root)


def test_rejects_wrong_commit_fixture_formula_or_missing_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = aggregate.authenticate_qualification_bundle(_write_bundle(tmp_path / "good"))
    with pytest.raises(aggregate.AggregateEvidenceError, match="code commit"):
        aggregate.require_common_identity([bundle], code_commit="e" * 40)
    with pytest.raises(aggregate.AggregateEvidenceError, match="fixture"):
        aggregate.require_common_identity(
            [bundle],
            code_commit="a" * 40,
            fixture_digests={"standard": ("0" * 64, "c" * 64)},
        )

    drift = _write_bundle(tmp_path / "drift")
    monkeypatch.setattr(decision_evidence, "SCORE_FORMULA_CONTRACT_SHA256", "f" * 64)
    with pytest.raises(aggregate.AggregateEvidenceError, match="score formula"):
        aggregate.authenticate_qualification_bundle(drift)
    monkeypatch.undo()

    short = aggregate.authenticate_qualification_bundle(
        _write_bundle(tmp_path / "short", repetitions=4)
    )
    with pytest.raises(aggregate.AggregateEvidenceError, match="five repetitions"):
        aggregate.project_query_rows([short])


def test_rejects_missing_authenticated_record_count(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "run")
    summary = json.loads((root / "summary.json").read_bytes())
    summary["detail_records"] = 4
    summary.pop("summary_digest")
    summary["summary_digest"] = shared.canonical_sha256(summary)
    (root / "summary.json").write_bytes(_canonical(summary))
    with pytest.raises(aggregate.AggregateEvidenceError, match="record counts"):
        aggregate.authenticate_qualification_bundle(root)


def test_projects_authenticated_c_and_uncensored_d_failures(tmp_path: Path) -> None:
    c_oracle: dict[str, object] = {"process_termination_observed": False}
    c = aggregate.authenticate_qualification_bundle(
        _write_bundle(
            tmp_path / "c",
            candidate_id="C",
            case_id="crash.terminate.before_staging",
            profile="tiny",
            repetitions=1,
            oracle_results=c_oracle,
        )
    )
    d = aggregate.authenticate_qualification_bundle(
        _write_bundle(
            tmp_path / "d",
            candidate_id="D",
            case_id="build.empty.30_days",
            profile="production",
            repetitions=1,
            outcome="stopped",
            partial=True,
        )
    )
    assert aggregate.project_candidate_failure(c)["observed"] is False
    assert aggregate.project_candidate_failure(d)["observed"] == 7_000_000_000

    censored_root = _write_bundle(
        tmp_path / "censored",
        candidate_id="D",
        case_id="build.empty.30_days",
        profile="production",
        repetitions=1,
        outcome="stopped",
        partial=True,
    )
    summary = json.loads((censored_root / "summary.json").read_bytes())
    summary["failure"]["detail_code"] = "suite.watchdog_timeout"
    summary.pop("summary_digest")
    summary["summary_digest"] = shared.canonical_sha256(summary)
    (censored_root / "summary.json").write_bytes(_canonical(summary))
    censored = aggregate.authenticate_qualification_bundle(censored_root)
    with pytest.raises(aggregate.AggregateEvidenceError, match="censored"):
        aggregate.project_candidate_failure(censored)


def test_authenticates_agent_perf_and_dbhub_artifacts(tmp_path: Path) -> None:
    run_identity = "a" * 64

    def run(run_id: str) -> dict[str, object]:
        return {
            "observed_processes": 1,
            "process_tree_cpu_ns": 10,
            "result_identity_sha256": run_identity,
            "run_id": run_id,
            "stderr_bytes": 0,
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "stdout_bytes": 0,
            "stdout_sha256": hashlib.sha256(b"").hexdigest(),
            "wall_time_ns": 20,
        }

    agent_perf = {
        "candidate_id": "A",
        "fixture": {"synthetic_only": True},
        "profiled_run": {
            **run("profiled"),
            "profile": {
                "hotspots": [],
                "profile_is_attribution_only": True,
            },
        },
        "schema": "codex-usage-tracker.ck04-agent-perf-evidence.v1",
        "tool_versions": {"agent_perf": "0.1.0"},
        "unprofiled_runs": [run(f"unprofiled-{index}") for index in range(5)],
        "workload": {"profile_is_attribution_only": True},
    }
    agent_path = tmp_path / "agent.json"
    agent_path.write_bytes(_canonical(agent_perf))
    assert aggregate.authenticate_agent_perf(agent_path)["candidate_id"] == "A"

    dbhub = decision_tests._valid_manifest()["dbhub"]
    dbhub_path = tmp_path / "dbhub.json"
    dbhub_path.write_bytes(_canonical(dbhub))
    assert aggregate.authenticate_dbhub(dbhub_path)["version"] == "0.24.0"


def test_writes_unique_directory_validates_sha_and_complete_last(tmp_path: Path) -> None:
    manifest = decision_tests._valid_manifest()
    artifact = aggregate.write_aggregate_directory(
        manifest,
        output_parent=tmp_path,
        aggregate_id="ck04-test",
    )
    assert (
        artifact.manifest_sha256 == hashlib.sha256(artifact.manifest_path.read_bytes()).hexdigest()
    )
    assert artifact.complete_path.read_text(encoding="ascii") == artifact.manifest_sha256 + "\n"
    assert artifact.complete_path.stat().st_mtime_ns >= artifact.manifest_path.stat().st_mtime_ns
    assert str(tmp_path) not in artifact.manifest_path.read_text(encoding="utf-8")
    with pytest.raises(aggregate.AggregateEvidenceError, match="already exists"):
        aggregate.write_aggregate_directory(
            manifest,
            output_parent=tmp_path,
            aggregate_id="ck04-test",
        )


def test_rejects_private_path_without_writing_complete(tmp_path: Path) -> None:
    manifest = decision_tests._valid_manifest()
    manifest["limitations"][0]["summary"] = "See /Users/alice/private/result.json."
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="private path",
    ):
        aggregate.write_aggregate_directory(
            manifest,
            output_parent=tmp_path,
            aggregate_id="ck04-private-path",
        )
    assert not (tmp_path / "ck04-private-path" / "COMPLETE").exists()
