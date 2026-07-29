from __future__ import annotations

import hashlib
import importlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_EXPERIMENT_ROOT = _REPOSITORY_ROOT / "experiments" / "physical-architecture"
if str(_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENT_ROOT))

decision_evidence = importlib.import_module("decision_evidence")
shared = importlib.import_module("shared")


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _artifact(
    artifact_id: str,
    kind: str,
    digest: str,
    *,
    record_count: int = 1,
) -> dict[str, object]:
    encoding = "canonical_jsonl" if kind == "qualification_measurements" else "canonical_json"
    return {
        "artifact_id": artifact_id,
        "canonical_sha256": digest,
        "encoding": encoding,
        "kind": kind,
        "record_count": record_count,
    }


def _environment() -> dict[str, object]:
    identity = {
        "analyze_state": "candidate-owned",
        "compiler_flags": [
            "compiler=synthetic",
            "implementation=CPython",
            "optimize=0",
        ],
        "cpu_model": "synthetic-cpu",
        "filesystem": "synthetic-fs",
        "filesystem_cache_state": "uncontrolled",
        "logical_cores": 12,
        "memory_bytes": 16 * 1024**3,
        "operating_system": "synthetic-os",
        "physical_cores": 10,
        "python_version": "3.14.6",
        "sqlite_settings": [
            {"name": "cache_size", "value": "-20000"},
            {"name": "journal_mode", "value": "WAL"},
            {"name": "mmap_size", "value": "0"},
            {"name": "page_size", "value": "4096"},
            {"name": "synchronous", "value": "NORMAL"},
            {"name": "temp_store", "value": "MEMORY"},
            {"name": "wal_autocheckpoint", "value": "1000"},
        ],
        "sqlite_version": "3.50.4",
        "storage_model": "synthetic-storage",
    }
    return {
        "environment_id": "qualification-host",
        "fingerprint_sha256": shared.canonical_sha256(identity),
        "identity": identity,
    }


def _fixture_rows() -> tuple[list[dict[str, object]], dict[str, tuple[str, str]]]:
    rows: list[dict[str, object]] = []
    digests: dict[str, tuple[str, str]] = {}
    for scale, model_calls in (
        ("standard", 100_000),
        ("production", 1_316_864),
        ("growth", 2_500_000),
    ):
        manifest_id = f"fixture.{scale}.manifest"
        oracle_id = f"fixture.{scale}.oracle"
        manifest_digest = _hash(manifest_id)
        oracle_digest = _hash(oracle_id)
        digests[scale] = (manifest_digest, oracle_digest)
        rows.append(
            {
                "fixture_id": scale,
                "fixture_revision": shared.FIXTURE_REVISION,
                "manifest_input_id": manifest_id,
                "model_calls": model_calls,
                "oracle_input_id": oracle_id,
                "source_bytes": model_calls * 100,
                "source_records": model_calls * 2,
            }
        )
    return rows, digests


def _query_rows() -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    case_ids: list[str] = []
    questions = sorted(set(shared.P1_QUESTION_IDS) | set(shared.REQUIRED_SLICE_QUESTION_IDS))
    for question_id in questions:
        plan_id, performance_class = shared.QUESTION_WORKLOAD_CONTRACTS[question_id]
        case_id = f"query.{question_id.lower()}.warm_first_page"
        case_ids.append(case_id)
        rows.append(
            {
                "answer_correct": True,
                "approved_plan_counts": {
                    "automatic_indexes": 0,
                    "full_scans": 2,
                    "sql_statements": 4,
                    "temporary_sorts": 6,
                },
                "fixture_id": "standard",
                "mcp_latency_p95_ns": 50_000_000,
                "observed_plan_counts": {
                    "automatic_indexes": 0,
                    "full_scans": 1,
                    "sql_statements": 2,
                    "temporary_sorts": 1,
                },
                "oracle_equivalent": True,
                "output_artifact_id": "query.measurements",
                "performance_class": performance_class,
                "plan_id": plan_id,
                "qualification_run_id": "run.standard",
                "query_case_id": case_id,
                "question_id": question_id,
                "repetitions": 5,
                "response_bytes_max": 9_000,
                "selector_pages_gap_free": True,
                "sql_latency_p95_ns": 45_000_000,
            }
        )
    return sorted(rows, key=lambda row: str(row["query_case_id"])), case_ids


def _crash_rows() -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    case_ids: list[str] = []
    prior_digest = _hash("prior-publication")
    for boundary in shared.CRASH_BOUNDARIES:
        case_id = f"crash.terminate.{boundary}"
        case_ids.append(case_id)
        rows.append(
            {
                "boundary": boundary,
                "candidate_id": "A",
                "case_id": case_id,
                "fault": None,
                "mode": "process_termination",
                "observation_id": f"A.{case_id}",
                "output_artifact_id": "crash.measurements",
                "process": {
                    "boundary_reached": True,
                    "exit_kind": "forced_exit",
                    "return_code": 97,
                    "signal": None,
                    "status": "observed",
                    "termination_observed": True,
                    "worker_pid": 1234,
                    "worker_started": True,
                },
                "qualification_run_id": "run.standard",
                "recovery": {
                    "abandoned_artifact_disposition": "abandon_candidate",
                    "candidate_publication_committed": False,
                    "post_recovery_query_sha256": _hash(f"query-{boundary}"),
                    "prior_publication_queryable": True,
                    "prior_publication_sha256": prior_digest,
                    "rollback_available": True,
                    "rollback_publication_sha256": prior_digest,
                    "sidecar_terminal_state": "failed",
                    "subsequent_operation_succeeds": True,
                },
            }
        )
    for fault in shared.CRASH_FAULTS:
        case_id = f"crash.fault.{fault}"
        case_ids.append(case_id)
        rows.append(
            {
                "boundary": None,
                "candidate_id": "A",
                "case_id": case_id,
                "fault": fault,
                "mode": "injected_fault",
                "observation_id": f"A.{case_id}",
                "output_artifact_id": "crash.measurements",
                "process": {"status": "not_applicable"},
                "qualification_run_id": "run.standard",
                "recovery": {
                    "abandoned_artifact_disposition": "abandon_candidate",
                    "candidate_publication_committed": False,
                    "post_recovery_query_sha256": _hash(f"query-{fault}"),
                    "prior_publication_queryable": True,
                    "prior_publication_sha256": prior_digest,
                    "rollback_available": True,
                    "rollback_publication_sha256": prior_digest,
                    "sidecar_terminal_state": "failed",
                    "subsequent_operation_succeeds": True,
                },
            }
        )
    return sorted(rows, key=lambda row: str(row["observation_id"])), case_ids


def _score_input(
    candidate_id: str,
    scale: str,
    fixture_digests: dict[str, tuple[str, str]],
    code_commit: str,
) -> dict[str, object]:
    case_id = f"build.scale.{scale}"
    base_value = {"A": 1, "C": 2, "D": 3}[candidate_id]
    dimensions = [
        {
            "dimension": dimension.value,
            "source_case_ids": [case_id],
            "value": str(base_value),
        }
        for dimension in sorted(shared.ScoreDimension, key=lambda item: item.value)
    ]
    manifest_digest, oracle_digest = fixture_digests[scale]
    score = shared.CandidateScoreInput(
        candidate_id=candidate_id,
        fixture_manifest_digest=manifest_digest,
        fixture_oracle_digest=oracle_digest,
        code_commit=code_commit,
        scale=scale,
        costs=tuple(
            shared.DimensionCost(
                dimension=shared.ScoreDimension(str(dimension["dimension"])),
                value=Decimal(str(dimension["value"])),
                source_case_ids=(case_id,),
            )
            for dimension in dimensions
        ),
    )
    return {
        "dimensions": dimensions,
        "fixture_id": scale,
        "input_sha256": score.digest,
        "scale": scale,
    }


def _candidate_rows(
    fixture_digests: dict[str, tuple[str, str]],
    code_commit: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    failures = {
        "A": [],
        "C": [
            {
                "case_id": "crash.terminate.before_staging",
                "comparison": "eq",
                "detail_code": "process_not_terminated",
                "failure_id": "C.process_termination",
                "gate": "publication_recovery",
                "metric": "process_termination_observed",
                "observed": False,
                "output_artifact_id": "crash.measurements",
                "required": True,
            }
        ],
        "D": [
            {
                "case_id": "build.scale.production",
                "comparison": "lte",
                "detail_code": "production_30d_gate_exceeded",
                "failure_id": "D.production_30d",
                "gate": "performance",
                "metric": "wall_time_ns",
                "observed": 6_500_000_000,
                "output_artifact_id": "qualification.production.measurements",
                "required": 5_000_000_000,
            }
        ],
    }
    for candidate_id in ("A", "C", "D"):
        score_inputs = [
            _score_input(candidate_id, scale, fixture_digests, code_commit)
            for scale in ("standard", "production", "growth")
        ]
        score_results: list[dict[str, object]] = []
        for score_input in score_inputs:
            common = {
                "input_sha256": score_input["input_sha256"],
                "output_artifact_id": "score.results",
                "scale": score_input["scale"],
            }
            if candidate_id == "A":
                score_results.append(
                    {
                        **common,
                        "rank": 1,
                        "status": "ranked",
                        "weighted_score": "100",
                    }
                )
            else:
                score_results.append(
                    {
                        **common,
                        "elimination_failure_ids": [str(failures[candidate_id][0]["failure_id"])],
                        "status": "eliminated",
                    }
                )
        rows.append(
            {
                "candidate_id": candidate_id,
                "eligible": candidate_id == "A",
                "failures": failures[candidate_id],
                "qualification_run_ids": [
                    "run.growth",
                    "run.production",
                    "run.standard",
                ],
                "score_inputs": score_inputs,
                "score_results": score_results,
            }
        )
    return rows


def _agent_perf_workload(
    fixture_digests: dict[str, tuple[str, str]],
    matrix_digest: str,
) -> dict[str, object]:
    manifest_digest, oracle_digest = fixture_digests["standard"]
    return {
        "candidate_id": "A",
        "command_argv": [
            "{python}",
            "-m",
            "candidate_a.workload",
            "--fixture",
            "{fixture_root}",
            "--output",
            "{output_root}",
        ],
        "environment": {
            "CANDIDATE_A_PARSER_WORKERS": "1",
            "CANDIDATE_A_PHYSICAL_CORES": "10",
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": "experiments/physical-architecture",
        },
        "fixture_manifest_digest": manifest_digest,
        "fixture_oracle_digest": oracle_digest,
        "fixture_profile": "standard",
        "fixture_revision": shared.FIXTURE_REVISION,
        "minimum_unprofiled_runs": 5,
        "profile_is_attribution_only": True,
        "schema": shared.AGENT_PERF_WORKLOAD_SCHEMA,
        "synthetic_only": True,
        "version": 1,
        "workload_id": "build.scale.standard",
        "workload_matrix_digest": matrix_digest,
    }


def _dbhub_trials() -> list[dict[str, object]]:
    trials: list[dict[str, object]] = []
    result_digest = _hash("dbhub-result")
    for model_class in shared.DBHUB_MODEL_CLASSES:
        for mode in shared.DBHUB_TRIAL_MODES:
            trial_id = f"{model_class}.{mode}"
            samples = [
                {
                    "correct": True,
                    "mcp_calls": 2 if mode == "generic" else 1,
                    "process_cpu_ns": 3_000_000 + index,
                    "response_bytes": 7_500,
                    "result_rows": 25,
                    "result_sha256": result_digest,
                    "sample_id": f"{trial_id}.{index:02d}",
                    "scanned_rows": 25,
                    "sql_statements": 2 if mode == "generic" else 1,
                    "wall_time_ns": 4_000_000 + index,
                }
                for index in range(5)
            ]
            trials.append(
                {
                    "correct_route": True,
                    "mode": mode,
                    "model_class": model_class,
                    "model_tokens": {
                        "reason_code": "telemetry_not_exposed",
                        "status": "unavailable",
                    },
                    "qualification_run_id": "run.standard",
                    "samples": samples,
                    "selected_tool": "execute_sql" if mode == "generic" else "top_sessions",
                    "trial_id": trial_id,
                }
            )
    return sorted(trials, key=lambda trial: str(trial["trial_id"]))


def _valid_manifest() -> dict[str, Any]:
    code_commit = "a" * 40
    fixtures, fixture_digests = _fixture_rows()
    query_rows, query_case_ids = _query_rows()
    crash_rows, crash_case_ids = _crash_rows()
    matrix_digest = "d6059274027d4fb9bfe286ef0932142c49f00e4a6a6e7badb6585ebc44edfb11"
    agent_workload = _agent_perf_workload(fixture_digests, matrix_digest)

    standard_cases = sorted(
        {
            "agent_perf.standard_cpu_attribution",
            "build.scale.standard",
            *query_case_ids,
            *crash_case_ids,
            *(
                f"dbhub.{mode}.{model_class}"
                for model_class in shared.DBHUB_MODEL_CLASSES
                for mode in shared.DBHUB_TRIAL_MODES
            ),
        }
    )
    runs = [
        {
            "candidate_ids": ["A", "C", "D"],
            "case_ids": ["build.scale.growth"],
            "case_ids_sha256": shared.canonical_sha256(["build.scale.growth"]),
            "fixture_id": "growth",
            "invocation_input_id": "qualification.growth.invocation",
            "measurements_output_id": "qualification.growth.measurements",
            "profiled": False,
            "repetitions": 5,
            "run_id": "run.growth",
            "speed_claim": True,
            "summary_output_id": "qualification.growth.summary",
        },
        {
            "candidate_ids": ["A", "C", "D"],
            "case_ids": ["build.scale.production"],
            "case_ids_sha256": shared.canonical_sha256(["build.scale.production"]),
            "fixture_id": "production",
            "invocation_input_id": "qualification.production.invocation",
            "measurements_output_id": "qualification.production.measurements",
            "profiled": False,
            "repetitions": 5,
            "run_id": "run.production",
            "speed_claim": True,
            "summary_output_id": "qualification.production.summary",
        },
        {
            "candidate_ids": ["A", "C", "D"],
            "case_ids": standard_cases,
            "case_ids_sha256": shared.canonical_sha256(standard_cases),
            "fixture_id": "standard",
            "invocation_input_id": "qualification.standard.invocation",
            "measurements_output_id": "qualification.standard.measurements",
            "profiled": False,
            "repetitions": 5,
            "run_id": "run.standard",
            "speed_claim": True,
            "summary_output_id": "qualification.standard.summary",
        },
    ]
    input_artifacts = [
        *(
            _artifact(
                f"fixture.{scale}.{kind}",
                f"fixture_{kind}",
                fixture_digests[scale][0 if kind == "manifest" else 1],
            )
            for scale in ("standard", "production", "growth")
            for kind in ("manifest", "oracle")
        ),
        _artifact(
            "agent-perf.a.workload",
            "agent_perf_workload",
            shared.canonical_sha256(agent_workload),
        ),
        _artifact("dbhub.invocation", "dbhub_invocation", _hash("dbhub-invocation")),
        *(
            _artifact(
                f"qualification.{scale}.invocation",
                "qualification_invocation",
                _hash(f"qualification-{scale}-invocation"),
            )
            for scale in ("standard", "production", "growth")
        ),
        _artifact("workload.matrix", "workload_matrix", matrix_digest),
    ]
    output_artifacts = [
        _artifact(
            "agent-perf.measurements",
            "agent_perf_measurements",
            "fb4d4128ea105c80023d6357aa9157ed1755de5c921486f1752a51af3daa7f23",
        ),
        _artifact("crash.measurements", "crash_measurements", _hash("crash")),
        _artifact("dbhub.measurements", "dbhub_measurements", _hash("dbhub")),
        *(
            _artifact(
                f"qualification.{scale}.measurements",
                "qualification_measurements",
                _hash(f"qualification-{scale}-measurements"),
                record_count=15,
            )
            for scale in ("standard", "production", "growth")
        ),
        *(
            _artifact(
                f"qualification.{scale}.summary",
                "qualification_summary",
                _hash(f"qualification-{scale}-summary"),
            )
            for scale in ("standard", "production", "growth")
        ),
        _artifact(
            "query.measurements",
            "query_plan_measurements",
            "548f93859fa7ca656c5aa860beed7fc9a5de62e11a27f41fe43a7112849f9282",
        ),
        _artifact("score.results", "score_result", _hash("score")),
    ]

    return {
        "agent_perf": [
            {
                "candidate_id": "A",
                "hotspots": [
                    {
                        "python_cpu_percent": "8.3",
                        "rank": 1,
                        "source": "candidate_a/ingest.py",
                        "symbol": "_insert_record",
                    },
                    {
                        "python_cpu_percent": "2.29",
                        "rank": 2,
                        "source": "candidate_a/evidence.py",
                        "symbol": "_merged_rows",
                    },
                ],
                "measurements_output_id": "agent-perf.measurements",
                "profiled_run": {
                    "process_cpu_ns": 9_000_000_000,
                    "run_id": "agent-perf.profiled",
                    "wall_time_ns": 9_746_000_000,
                },
                "profiler": {"name": "agent-perf", "version": "1.0"},
                "qualification_run_id": "run.standard",
                "unprofiled_runs": [
                    {"run_id": f"agent-perf.unprofiled.{index}", "wall_time_ns": wall}
                    for index, wall in enumerate(
                        (
                            7_220_000_000,
                            7_340_000_000,
                            7_330_000_000,
                            7_280_000_000,
                            7_070_000_000,
                        ),
                        start=1,
                    )
                ],
                "workload": agent_workload,
                "workload_input_id": "agent-perf.a.workload",
            }
        ],
        "candidates": _candidate_rows(fixture_digests, code_commit),
        "canonical_artifacts": {
            "inputs": sorted(input_artifacts, key=lambda row: str(row["artifact_id"])),
            "outputs": sorted(output_artifacts, key=lambda row: str(row["artifact_id"])),
        },
        "code_commit": code_commit,
        "crash_observations": crash_rows,
        "dbhub": {
            "engine_level_read_only": False,
            "input_artifact_id": "dbhub.invocation",
            "output_artifact_id": "dbhub.measurements",
            "package": shared.DBHUB_PACKAGE,
            "package_integrity": shared.DBHUB_NPM_INTEGRITY,
            "snapshot_sha256_after": _hash("dbhub-snapshot"),
            "snapshot_sha256_before": _hash("dbhub-snapshot"),
            "tool_level_read_only": True,
            "trials": _dbhub_trials(),
            "version": shared.DBHUB_VERSION,
        },
        "decision_date": "2026-07-29",
        "decision_id": "CK-04",
        "environment": _environment(),
        "fixtures": fixtures,
        "limitations": [
            {
                "area": "dbhub.model_tokens",
                "category": "telemetry_unavailable",
                "evidence_output_ids": ["dbhub.measurements"],
                "limitation_id": "dbhub-model-tokens",
                "owner_packet_ids": ["CK-11"],
                "summary": "Qualification host did not expose per-trial model token telemetry.",
            }
        ],
        "qualification_runs": runs,
        "query_plans": query_rows,
        "schema": decision_evidence.MANIFEST_SCHEMA,
        "schema_identity": {
            "production_contract_id": ("codex-usage-tracker.agent-kernel.schema-contract.v1"),
            "production_contract_sha256": (
                "eecff68062a8d0cba0619058a6e660f565d9a96c2575ab0dc93d72b987f31543"
            ),
            "selected_candidate_schema_id": ("codex-usage-tracker.physical-bakeoff.candidate-a.v1"),
            "selected_candidate_schema_sha256": (
                "31b33e9efe24c458a528f2cc6930379028cd3bf40e9df0b79825290d61d85f09"
            ),
        },
        "selected_candidate": "A",
        "sensitivity": [
            {
                "model_calls": model_calls,
                "ranked_candidate_ids": ["A"],
                "scale": scale,
                "selected_candidate": "A",
                "selection_survives": True,
            }
            for scale, model_calls in (
                ("standard", 100_000),
                ("production", 1_316_864),
                ("growth", 2_500_000),
            )
        ],
        "workload": {
            "case_count": len(
                set(standard_cases) | {"build.scale.production", "build.scale.growth"}
            ),
            "contract_version": shared.CANDIDATE_ADAPTER_CONTRACT_VERSION,
            "matrix_input_id": "workload.matrix",
            "physical_cores": 10,
            "workload_id": "ck04-matrix",
        },
    }


def test_build_validate_write_and_cli_round_trip(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = _valid_manifest()
    build = decision_evidence.build_manifest(manifest)

    assert build.canonical_bytes == shared.canonical_json_bytes(manifest)
    assert build.sha256 == hashlib.sha256(build.canonical_bytes).hexdigest()
    assert decision_evidence.validate_manifest_bytes(build.canonical_bytes) == build

    destination = tmp_path / "aggregate-evidence.json"
    written = decision_evidence.write_manifest(manifest, destination)
    assert written == build
    assert destination.read_bytes() == build.canonical_bytes
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="already exists",
    ):
        decision_evidence.write_manifest(manifest, destination)

    replacement = decision_evidence.write_manifest(manifest, destination, replace=True)
    assert replacement == build

    assert decision_evidence.main(["validate", str(destination)]) == 0
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    cli_output = tmp_path / "cli-output.json"
    assert (
        decision_evidence.main(["write", "--input", str(draft), "--output", str(cli_output)]) == 0
    )
    assert cli_output.read_bytes() == build.canonical_bytes
    assert capsys.readouterr().out.splitlines() == [build.sha256, build.sha256]


def test_validate_rejects_noncanonical_encoding_and_oversized_input() -> None:
    manifest = _valid_manifest()
    pretty = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="not canonical",
    ):
        decision_evidence.validate_manifest_bytes(pretty)

    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="exceeds",
    ):
        decision_evidence.validate_manifest_bytes(b" " * (decision_evidence.MAX_MANIFEST_BYTES + 1))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "summary",
            "Evidence under /" + "Users/alice/private/run.json.",
            "private path",
        ),
        ("summary", "password=correct-horse-battery-staple", "secret-like"),
        ("summary", "raw\ncontent", "raw/control"),
    ],
)
def test_rejects_private_secret_and_raw_strings(
    field: str,
    value: str,
    message: str,
) -> None:
    manifest = _valid_manifest()
    manifest["limitations"][0][field] = value
    with pytest.raises(decision_evidence.DecisionEvidenceContractError, match=message):
        decision_evidence.build_manifest(manifest)


def test_rejects_unknown_telemetry_duplicate_ids_and_noncanonical_order() -> None:
    unsupported = _valid_manifest()
    unsupported["dbhub"]["trials"][0]["samples"][0]["estimated_cpu_ns"] = 1
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="unsupported",
    ):
        decision_evidence.build_manifest(unsupported)

    duplicated = _valid_manifest()
    duplicated["dbhub"]["trials"][1]["samples"][0]["sample_id"] = duplicated["dbhub"]["trials"][0][
        "samples"
    ][0]["sample_id"]
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="sample ID duplicated",
    ):
        decision_evidence.build_manifest(duplicated)

    unordered = _valid_manifest()
    unordered["query_plans"] = list(reversed(unordered["query_plans"]))
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="canonically ordered",
    ):
        decision_evidence.build_manifest(unordered)


def test_rejects_stale_score_hash_and_sensitivity_result() -> None:
    stale_hash = _valid_manifest()
    stale_hash["candidates"][0]["score_inputs"][0]["input_sha256"] = "0" * 64
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="input_sha256 is stale",
    ):
        decision_evidence.build_manifest(stale_hash)

    stale_sensitivity = _valid_manifest()
    stale_sensitivity["sensitivity"][1]["ranked_candidate_ids"] = ["A", "C"]
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="ranked_candidate_ids is stale",
    ):
        decision_evidence.build_manifest(stale_sensitivity)


def test_rejects_stale_schema_and_agent_perf_workload_identity() -> None:
    stale_schema = _valid_manifest()
    stale_schema["schema_identity"]["production_contract_sha256"] = "0" * 64
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="schema contract SHA-256 is stale",
    ):
        decision_evidence.build_manifest(stale_schema)

    stale_workload = _valid_manifest()
    stale_workload["agent_perf"][0]["workload"]["workload_matrix_digest"] = "0" * 64
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="differs from decision workload",
    ):
        decision_evidence.build_manifest(stale_workload)


def test_rejects_elimination_without_failure_and_plan_overage() -> None:
    no_failure = _valid_manifest()
    no_failure["candidates"][1]["failures"] = []
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="must name why eliminated",
    ):
        decision_evidence.build_manifest(no_failure)

    plan_overage = _valid_manifest()
    plan_overage["query_plans"][0]["observed_plan_counts"]["full_scans"] = 3
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="exceeds approval",
    ):
        decision_evidence.build_manifest(plan_overage)


def test_rejects_asserted_crash_agent_perf_shortcut_and_dbhub_gap() -> None:
    asserted_crash = _valid_manifest()
    termination = next(
        row for row in asserted_crash["crash_observations"] if row["mode"] == "process_termination"
    )
    termination["process"]["termination_observed"] = False
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="asserted rather than observed",
    ):
        decision_evidence.build_manifest(asserted_crash)

    too_few_runs = _valid_manifest()
    too_few_runs["agent_perf"][0]["unprofiled_runs"].pop()
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="between 5 and 100",
    ):
        decision_evidence.build_manifest(too_few_runs)

    missing_cpu = _valid_manifest()
    del missing_cpu["dbhub"]["trials"][0]["samples"][0]["process_cpu_ns"]
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="missing=.*process_cpu_ns",
    ):
        decision_evidence.build_manifest(missing_cpu)


def test_unavailable_model_tokens_require_explicit_limitation() -> None:
    manifest = _valid_manifest()
    manifest["limitations"][0]["area"] = "other.measurement"
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="require explicit limitation",
    ):
        decision_evidence.build_manifest(manifest)
