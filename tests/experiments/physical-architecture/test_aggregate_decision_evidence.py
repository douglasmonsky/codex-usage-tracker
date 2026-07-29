from __future__ import annotations

import hashlib
import importlib
import json
import sys
from copy import deepcopy
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
    workload_matrix_digest: str = "d" * 64,
    run_id: str | None = None,
    oracle_results: dict[str, object] | None = None,
) -> Path:
    root.mkdir()
    environment = decision_tests._environment()["identity"]
    environment_digest = shared.canonical_sha256(environment)
    invocation_base = {
        "schema": "codex-usage-tracker.physical-bakeoff-invocation.v1",
        "run_id": run_id or f"{candidate_id.lower()}-{profile}",
        "code_commit": code_commit,
        "fixture": {
            "profile": profile,
            "fixture_revision": shared.FIXTURE_REVISION,
            "manifest_digest": fixture_manifest_digest,
            "oracle_digest": fixture_oracle_digest,
        },
        "workload_matrix_digest": workload_matrix_digest,
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


def _query_bundles(
    root: Path,
    *,
    profiles: tuple[str, ...],
) -> list[Any]:
    case_ids = sorted(
        case.case_id
        for case in shared.build_workload_matrix(physical_cores=1).cases
        if case.group is shared.WorkloadGroup.QUERY
    )
    return [
        aggregate.authenticate_qualification_bundle(
            _write_bundle(
                root / f"{profile}-{index:03d}",
                case_id=case_id,
                profile=profile,
                run_id=f"run.{profile}.{index:03d}",
            )
        )
        for profile in profiles
        for index, case_id in enumerate(case_ids)
    ]


def test_projects_standard_queries_and_accepts_nonstandard_score_evidence(
    tmp_path: Path,
) -> None:
    bundles = _query_bundles(
        tmp_path,
        profiles=("standard", "production", "growth"),
    )
    rows = aggregate.project_query_rows(bundles)
    assert len(rows) == 69
    row = next(row for row in rows if row["query_case_id"] == "query.feature.bounded_full_sort")
    assert row["fixture_id"] == "standard"
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

    with pytest.raises(aggregate.AggregateEvidenceError, match="standard.*coverage"):
        aggregate.project_query_rows(
            [bundle for bundle in bundles if bundle.invocation["fixture"]["profile"] != "standard"]
        )


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


def _agent_perf_run(
    run_id: str,
    *,
    wall_time_ns: int = 20,
    process_cpu_ns: int = 10,
) -> dict[str, object]:
    return {
        "observed_processes": 1,
        "process_tree_cpu_ns": process_cpu_ns,
        "result_identity_sha256": "a" * 64,
        "run_id": run_id,
        "stderr_bytes": 0,
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "stdout_bytes": 0,
        "stdout_sha256": hashlib.sha256(b"").hexdigest(),
        "wall_time_ns": wall_time_ns,
    }


def _agent_perf_evidence(
    workload: dict[str, object] | None = None,
) -> dict[str, object]:
    fixture_manifest_digest = (
        workload["fixture_manifest_digest"] if workload is not None else "b" * 64
    )
    fixture_oracle_digest = workload["fixture_oracle_digest"] if workload is not None else "c" * 64
    workload_matrix_digest = (
        workload["workload_matrix_digest"] if workload is not None else "e" * 64
    )
    evidence = {
        "candidate_id": "A",
        "fixture": {
            "manifest_sha256": fixture_manifest_digest,
            "oracle_sha256": fixture_oracle_digest,
            "profile": "standard",
            "revision": shared.FIXTURE_REVISION,
            "synthetic_only": True,
        },
        "profiled_run": {
            **_agent_perf_run("profiled"),
            "profile": {
                "hotspots": [],
                "profile_is_attribution_only": True,
            },
        },
        "schema": "codex-usage-tracker.ck04-agent-perf-evidence.v1",
        "tool_versions": {
            "agent_perf": "0.1.0",
            "psutil": "7.2.2",
            "scalene": "2.3.0",
        },
        "unprofiled_runs": [_agent_perf_run(f"unprofiled-{index}") for index in range(5)],
        "workload": {
            "digest": (shared.canonical_sha256(workload) if workload is not None else "d" * 64),
            "id": "build.scale.standard",
            "matrix_sha256": workload_matrix_digest,
            "minimum_unprofiled_runs": 5,
            "profile_is_attribution_only": True,
        },
    }
    return evidence


def test_authenticates_agent_perf_and_dbhub_artifacts(tmp_path: Path) -> None:
    agent_perf = _agent_perf_evidence()
    agent_path = tmp_path / "agent.json"
    agent_path.write_bytes(_canonical(agent_perf))
    assert aggregate.authenticate_agent_perf(agent_path)["candidate_id"] == "A"

    dbhub = decision_tests._valid_manifest()["dbhub"]
    dbhub_path = tmp_path / "dbhub.json"
    dbhub_path.write_bytes(_canonical(dbhub))
    assert aggregate.authenticate_dbhub(dbhub_path)["version"] == "0.24.0"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fixture.profile", "growth"),
        ("fixture.revision", "old-revision"),
        ("workload.id", "build.scale.production"),
        ("workload.minimum_unprofiled_runs", 4),
        ("workload.profile_is_attribution_only", False),
        ("tool_versions.agent_perf", "0.2.0"),
        ("tool_versions.psutil", "7.2.1"),
        ("tool_versions.scalene", "2.2.0"),
    ],
)
def test_agent_perf_authentication_rejects_contract_drift(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    evidence = _agent_perf_evidence()
    section, key = field.split(".", 1)
    section_value = evidence[section]
    assert isinstance(section_value, dict)
    section_value[key] = value
    path = tmp_path / "agent.json"
    path.write_bytes(_canonical(evidence))
    with pytest.raises(aggregate.AggregateEvidenceError, match="incomplete"):
        aggregate.authenticate_agent_perf(path)


def test_assemble_derives_agent_perf_telemetry_and_preserves_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = decision_tests._valid_manifest()
    projection = draft["agent_perf"][0]
    projection["profiler"]["version"] = "0.1.0"
    workload = projection["workload"]
    qualification_run = next(
        row
        for row in draft["qualification_runs"]
        if row["run_id"] == projection["qualification_run_id"]
    )
    qualification_run.update(
        {
            "candidate_ids": ["A"],
            "case_ids": ["agent_perf.standard_cpu_attribution"],
            "case_ids_sha256": shared.canonical_sha256(["agent_perf.standard_cpu_attribution"]),
            "repetitions": 5,
        }
    )
    standard = aggregate.authenticate_qualification_bundle(
        _write_bundle(
            tmp_path / "standard",
            case_id="agent_perf.standard_cpu_attribution",
            profile="standard",
            repetitions=5,
            fixture_manifest_digest=workload["fixture_manifest_digest"],
            fixture_oracle_digest=workload["fixture_oracle_digest"],
            workload_matrix_digest=workload["workload_matrix_digest"],
            run_id=projection["qualification_run_id"],
        )
    )
    fresh = _agent_perf_evidence(workload)
    fresh["profiled_run"] = {
        **_agent_perf_run("fresh-profile", wall_time_ns=701, process_cpu_ns=601),
        "profile": {
            "hotspots": [
                {
                    "python_cpu_percent": "42.25",
                    "rank": 1,
                    "source": ("experiments/physical-architecture/candidate_a/publication.py"),
                    "symbol": "publish_artifact",
                }
            ],
            "profile_is_attribution_only": True,
        },
    }
    fresh["unprofiled_runs"] = [
        _agent_perf_run(
            f"fresh-{index}",
            wall_time_ns=100 + index,
            process_cpu_ns=50 + index,
        )
        for index in range(5)
    ]
    artifact_rows = [
        *draft["canonical_artifacts"]["inputs"],
        *draft["canonical_artifacts"]["outputs"],
    ]
    for artifact_id, file_name, record_count in (
        (qualification_run["invocation_input_id"], "invocation.json", 1),
        (
            qualification_run["measurements_output_id"],
            "measurements.jsonl",
            5,
        ),
        (qualification_run["summary_output_id"], "summary.json", 1),
    ):
        artifact = next(row for row in artifact_rows if row["artifact_id"] == artifact_id)
        artifact["canonical_sha256"] = hashlib.sha256(
            standard.canonical_bytes[file_name]
        ).hexdigest()
        artifact["record_count"] = record_count
    agent_measurements = next(
        row
        for row in draft["canonical_artifacts"]["outputs"]
        if row["artifact_id"] == projection["measurements_output_id"]
    )
    agent_measurements["canonical_sha256"] = shared.canonical_sha256(fresh)
    original_links = {
        key: projection[key]
        for key in (
            "candidate_id",
            "measurements_output_id",
            "profiler",
            "qualification_run_id",
            "workload",
            "workload_input_id",
        )
    }
    failures = iter(
        [
            {
                key: value
                for key, value in draft["candidates"][index]["failures"][0].items()
                if key != "output_artifact_id"
            }
            for index in (1, 2)
        ]
    )
    monkeypatch.setattr(aggregate, "project_query_rows", lambda _: tuple(draft["query_plans"]))
    monkeypatch.setattr(
        aggregate,
        "project_crash_rows",
        lambda _: tuple(draft["crash_observations"]),
    )
    monkeypatch.setattr(
        aggregate,
        "derive_candidate_a_score_inputs",
        lambda _: tuple(draft["candidates"][0]["score_inputs"]),
    )
    monkeypatch.setattr(aggregate, "project_candidate_failure", lambda _: next(failures))

    built = aggregate.assemble_manifest(
        draft,
        qualification_bundles=[standard],
        candidate_c=standard,
        candidate_d=standard,
        agent_perf=fresh,
        dbhub=draft["dbhub"],
    )

    built_agent_perf = built["agent_perf"]
    assert isinstance(built_agent_perf, list)
    updated = built_agent_perf[0]
    assert isinstance(updated, dict)
    assert {key: updated[key] for key in original_links} == original_links
    fresh_profiled = fresh["profiled_run"]
    assert isinstance(fresh_profiled, dict)
    fresh_profile = fresh_profiled["profile"]
    assert isinstance(fresh_profile, dict)
    assert updated["hotspots"] == fresh_profile["hotspots"]
    assert updated["unprofiled_runs"] == [
        {"run_id": f"fresh-{index}", "wall_time_ns": 100 + index} for index in range(5)
    ]
    assert updated["profiled_run"] == {
        "process_cpu_ns": {"status": "observed", "value": 601},
        "run_id": "fresh-profile",
        "wall_time_ns": 701,
    }

    for mutation in (
        lambda value: value["agent_perf"][0]["workload"].update(
            {"fixture_manifest_digest": "0" * 64}
        ),
        lambda value: value["agent_perf"][0]["workload"].update(
            {"fixture_oracle_digest": "0" * 64}
        ),
        lambda value: value["agent_perf"][0]["workload"].update(
            {"workload_matrix_digest": "0" * 64}
        ),
        lambda value: value["agent_perf"][0]["profiler"].update({"version": "1.0"}),
        lambda value: next(
            row
            for row in value["qualification_runs"]
            if row["run_id"] == projection["qualification_run_id"]
        ).update({"candidate_ids": ["A", "C"]}),
    ):
        drifted = deepcopy(draft)
        mutation(drifted)
        with pytest.raises(
            aggregate.AggregateEvidenceError,
            match="Agent Perf",
        ):
            aggregate._project_agent_perf(
                drifted,
                fresh,
                qualification_bundles=[standard],
            )


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
    manifest["limitations"][0]["summary"] = "See /" + "Users/alice/private/result.json."
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
