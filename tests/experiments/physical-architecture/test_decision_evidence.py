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
if str(_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENT_ROOT))

decision_evidence = importlib.import_module("decision_evidence")
shared = importlib.import_module("shared")
_SCORE_INPUT_CACHE: dict[tuple[object, ...], dict[str, object]] = {}


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
        ("tiny", 102),
        ("standard", 100_000),
        ("production", 1_316_864),
        ("growth", 2_500_000),
    ):
        manifest_id = f"fixture.{scale}.manifest"
        oracle_id = f"fixture.{scale}.oracle"
        manifest_digest = _hash(f"{manifest_id}.semantic")
        oracle_digest = _hash(f"{oracle_id}.semantic")
        digests[scale] = (manifest_digest, oracle_digest)
        rows.append(
            {
                "fixture_id": scale,
                "fixture_revision": shared.FIXTURE_REVISION,
                "manifest_semantic_sha256": manifest_digest,
                "manifest_input_id": manifest_id,
                "model_calls": model_calls,
                "oracle_semantic_sha256": oracle_digest,
                "oracle_input_id": oracle_id,
                "source_bytes": model_calls * 100,
                "source_records": model_calls * 2,
            }
        )
    return rows, digests


def _query_rows() -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    case_ids: list[str] = []
    matrix = shared.build_workload_matrix(physical_cores=10)
    cases = sorted(
        (case for case in matrix.cases if case.group is shared.WorkloadGroup.QUERY),
        key=lambda case: case.case_id,
    )
    for case in cases:
        case_id = case.case_id
        question_id = case.parameter("question_id")
        plan_id = str(case.parameter("plan_id"))
        performance_class = str(case.parameter("performance_class"))
        approved_plan_counts = {
            "automatic_indexes": int(case.parameter("maximum_automatic_indexes") or 0),
            "full_scans": int(case.parameter("maximum_full_scans") or 0),
            "temporary_sorts": int(case.parameter("maximum_temporary_sorts") or 0),
        }
        case_ids.append(case_id)
        rows.append(
            {
                "answer_correct": True,
                "approved_plan_counts": approved_plan_counts,
                "fixture_id": "standard",
                "mcp_latency_p95_ns": 50_000_000,
                "observed_plan_counts": {
                    "automatic_indexes": approved_plan_counts["automatic_indexes"],
                    "full_scans": approved_plan_counts["full_scans"],
                    "sql_statements": 2,
                    "temporary_sorts": approved_plan_counts["temporary_sorts"],
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


def _recovery_evidence(
    *,
    case_id: str,
    observed_stage: str,
) -> dict[str, object]:
    return {
        "abandoned_artifact_disposition": "abandon_candidate",
        "candidate_publication_committed": False,
        "observed_stage": observed_stage,
        "prior_publication_queryable": True,
        "recovery_action": "kept_active_pair",
        "recovery_terminal_sha256": _hash(f"{case_id}.recovery-terminal"),
        "rollback_available": True,
        "sidecar_terminal_state": "failed",
        "subsequent_operation_succeeds": True,
        "subsequent_publication_sha256": _hash(f"{case_id}.subsequent-publication"),
    }


def _crash_rows() -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    case_ids: list[str] = []
    for index, boundary in enumerate(shared.CRASH_BOUNDARIES):
        case_id = f"crash.terminate.{boundary}"
        case_ids.append(case_id)
        lease_missing = boundary == "during_old_artifact_cleanup"
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
                    "actual_return_code": 86,
                    "expected_return_code": 86,
                    "lease_status": "missing" if lease_missing else "valid",
                    "observed_stage": boundary,
                    "pid_lease_agreement": None if lease_missing else True,
                    "requested_boundary": boundary,
                    "status": "observed",
                    "termination_kind": "exit_code",
                    "termination_observed": True,
                    "worker_alive_after_exit": False,
                    "worker_pid": 10_000 + index,
                },
                "qualification_run_id": "run.crash",
                "recovery": _recovery_evidence(
                    case_id=case_id,
                    observed_stage=boundary,
                ),
            }
        )
    for index, fault in enumerate(shared.CRASH_FAULTS):
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
                "qualification_run_id": "run.crash",
                "recovery": _recovery_evidence(
                    case_id=case_id,
                    observed_stage=shared.CRASH_BOUNDARIES[index % len(shared.CRASH_BOUNDARIES)],
                ),
            }
        )
    return sorted(rows, key=lambda row: str(row["observation_id"])), case_ids


def _score_input(
    candidate_id: str,
    scale: str,
    fixture_digests: dict[str, tuple[str, str]],
    code_commit: str,
) -> dict[str, object]:
    cache_key = (
        candidate_id,
        scale,
        tuple(sorted(fixture_digests.items())),
        code_commit,
    )
    if cache_key not in _SCORE_INPUT_CACHE:
        _SCORE_INPUT_CACHE[cache_key] = decision_evidence.extract_score_input(
            candidate_id=candidate_id,
            scale=scale,
            evidence=_score_evidence(fixture_digests, code_commit),
        )
    return json.loads(json.dumps(_SCORE_INPUT_CACHE[cache_key]))


def _score_evidence_bundle(
    *,
    profile: str,
    case_ids: list[str],
    code_commit: str,
    fixture_digests: dict[str, tuple[str, str]],
    mutate_measurement: Any = None,
    mutate_detail: Any = None,
) -> object:
    run_id = f"score.{profile}"
    repetitions = 1 if all(case_id.startswith("crash.") for case_id in case_ids) else 5
    environment = _environment()["identity"]
    environment_digest = shared.canonical_sha256(environment)
    manifest_digest, oracle_digest = fixture_digests[profile]
    invocation_base = {
        "schema": "codex-usage-tracker.physical-bakeoff-invocation.v1",
        "run_id": run_id,
        "code_commit": code_commit,
        "fixture": {
            "profile": profile,
            "fixture_revision": shared.FIXTURE_REVISION,
            "manifest_digest": manifest_digest,
            "oracle_digest": oracle_digest,
        },
        "workload_matrix_digest": _hash("score.workload"),
        "environment": environment,
        "environment_digest": environment_digest,
        "candidate_ids": ["A"],
        "case_ids": case_ids,
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
    execution_index = 0
    for case_id in case_ids:
        for repetition in range(repetitions):
            identity = {
                "run_id": run_id,
                "candidate_id": "A",
                "case_id": case_id,
                "fixture_profile": profile,
                "fixture_manifest_digest": manifest_digest,
                "fixture_oracle_digest": oracle_digest,
                "repetition": repetition,
                "profiled": False,
                "code_commit": code_commit,
                "workload_matrix_digest": invocation["workload_matrix_digest"],
                "environment": environment,
                "qualification_model": None,
            }
            values = {
                "automatic_index_count": 0,
                "database_bytes": 100,
                "facts_inserted": 1,
                "facts_updated": 0,
                "full_scan_count": 0,
                "index_bytes": 20,
                "mcp_latency_ns": 20,
                "pages_read": 4,
                "pages_written": 2,
                "prior_publication_survived": True,
                "projection_rows_written": 3,
                "response_bytes": 30,
                "selector_pages_gap_free": True,
                "sql_latencies_ns": [10],
                "temporary_sort_count": 0,
                "tracker_batches": 1,
                "tracker_calls": 1,
                "tracker_polls": 0,
                "tracker_retries": 0,
                "refresh_jobs": 0,
                "wal_bytes": 5,
                "writer_transactions": 1,
            }
            measurement: dict[str, object] = {
                "schema": shared.MEASUREMENT_SCHEMA,
                "identity": identity,
                "wall_time_ns": repetition + 1,
                "process_cpu_ns": repetition + 1,
                "outcome": "passed",
                "partial": False,
                "stop_decision": None,
                "detail_code": None,
                "values": values,
            }
            if mutate_measurement is not None:
                mutate_measurement(measurement)
            measurements.append(measurement)
            projected_identity = {
                **{key: value for key, value in identity.items() if key != "environment"},
                "environment_digest": environment_digest,
            }
            detail_base = {
                "schema": "codex-usage-tracker.physical-bakeoff-detail.v1",
                "invocation_digest": invocation["invocation_digest"],
                "execution_index": execution_index,
                "measurement_identity": projected_identity,
                "measurement_identity_digest": shared.canonical_sha256(projected_identity),
                "measurement_record_digest": shared.canonical_sha256(measurement),
                "outcome": "passed",
                "partial": False,
                "stop_decision": None,
                "detail_code": None,
                "oracle_results": None,
            }
            detail = {**detail_base, "detail_digest": shared.canonical_sha256(detail_base)}
            if mutate_detail is not None:
                mutate_detail(detail)
            details.append(detail)
            execution_index += 1
    measurement_bytes = b"".join(shared.canonical_json_bytes(row) for row in measurements)
    detail_bytes = b"".join(shared.canonical_json_bytes(row) for row in details)
    summary_base = {
        "schema": "codex-usage-tracker.physical-bakeoff-summary.v1",
        "status": "passed",
        "run_id": run_id,
        "invocation_digest": invocation["invocation_digest"],
        "code_commit": code_commit,
        "fixture_manifest_digest": manifest_digest,
        "fixture_oracle_digest": oracle_digest,
        "workload_matrix_digest": invocation["workload_matrix_digest"],
        "environment_digest": environment_digest,
        "measurement_file": "measurements.jsonl",
        "measurement_sha256": hashlib.sha256(measurement_bytes).hexdigest(),
        "records": len(measurements),
        "details_file": "details.jsonl",
        "details_sha256": hashlib.sha256(detail_bytes).hexdigest(),
        "detail_records": len(details),
        "planned_executions": len(measurements),
        "optional_repetitions_skipped": 0,
        "retain_run_artifacts": False,
        "failure": None,
        "cases": [],
    }
    summary = {**summary_base, "summary_digest": shared.canonical_sha256(summary_base)}
    return decision_evidence.QualificationScoreEvidence(
        invocation_bytes=shared.canonical_json_bytes(invocation),
        measurement_bytes=measurement_bytes,
        detail_bytes=detail_bytes,
        summary_bytes=shared.canonical_json_bytes(summary),
    )


def _score_evidence(
    fixture_digests: dict[str, tuple[str, str]],
    code_commit: str,
) -> list[object]:
    cases = {
        item
        for scale in ("standard", "production", "growth")
        for item in decision_evidence.score_formula_source_cases(scale)
    }
    return [
        _score_evidence_bundle(
            profile=profile,
            case_ids=sorted(
                {case_id for expected_profile, case_id in cases if expected_profile == profile}
            ),
            code_commit=code_commit,
            fixture_digests=fixture_digests,
        )
        for profile in ("tiny", "standard", "production", "growth")
    ]


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
        eligible = candidate_id == "A"
        score_inputs = (
            [
                _score_input(candidate_id, scale, fixture_digests, code_commit)
                for scale in ("standard", "production", "growth")
            ]
            if eligible
            else []
        )
        score_results: list[dict[str, object]] = []
        for score_input in score_inputs:
            common = {
                "input_sha256": score_input["input_sha256"],
                "output_artifact_id": "score.results",
                "scale": score_input["scale"],
            }
            score_results.append(
                {
                    **common,
                    "rank": 1,
                    "status": "ranked",
                    "weighted_score": "100",
                }
            )
        rows.append(
            {
                "candidate_id": candidate_id,
                "eligible": eligible,
                "evaluation_status": (
                    "eligible_for_scoring" if eligible else "eliminated_before_scoring"
                ),
                "failures": failures[candidate_id],
                "qualification_run_ids": [
                    "run.crash",
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
    route_tools = {
        "generic": "search_objects+execute_sql",
        "named_preset": "top_sessions",
    }
    for route_index, route in enumerate(shared.DBHUB_LOCAL_ROUTES):
        samples = [
            {
                "correct": True,
                "mcp_calls": 2 if route == "generic" else 1,
                "process_cpu_ns": 3_000_000 + repetition,
                "response_bytes": 7_500,
                "result_rows": 25,
                "result_sha256": result_digest,
                "sample_id": f"{route}.{repetition:02d}",
                "scanned_rows": {
                    "reason_code": "tooling_does_not_report",
                    "status": "unavailable",
                },
                "sequence_index": repetition * len(shared.DBHUB_LOCAL_ROUTES) + route_index,
                "sql_statements": {
                    "reason_code": "tooling_does_not_report",
                    "status": "unavailable",
                },
                "wall_time_ns": 4_000_000 + repetition,
            }
            for repetition in range(5)
        ]
        trials.append(
            {
                "executed_route": route,
                "executed_tool": route_tools[route],
                "qualification_run_id": "run.standard",
                "samples": samples,
                "trial_id": route,
            }
        )
    return sorted(trials, key=lambda trial: str(trial["trial_id"]))


def _valid_manifest() -> dict[str, Any]:
    code_commit = "a" * 40
    fixtures, fixture_digests = _fixture_rows()
    query_rows, query_case_ids = _query_rows()
    crash_rows, crash_case_ids = _crash_rows()
    matrix_digest = "4d846d6f7869991117562d7aea9f61cb8fe9d967160415e749010f9704963a94"
    agent_workload = _agent_perf_workload(fixture_digests, matrix_digest)

    standard_cases = sorted(
        {
            "agent_perf.standard_cpu_attribution",
            "build.scale.standard",
            *query_case_ids,
            *(f"dbhub.{route}" for route in shared.DBHUB_LOCAL_ROUTES),
        }
    )
    growth_cases = sorted({"build.scale.growth", *query_case_ids})
    production_cases = sorted(
        {
            "build.scale.production",
            *query_case_ids,
            *(
                case_id
                for profile, case_id in decision_evidence.score_formula_source_cases("production")
                if profile == "production"
            ),
        }
    )
    runs = [
        {
            "candidate_ids": ["A", "C", "D"],
            "case_ids": sorted(crash_case_ids),
            "case_ids_sha256": shared.canonical_sha256(sorted(crash_case_ids)),
            "fixture_id": "tiny",
            "invocation_input_id": "qualification.crash.invocation",
            "measurements_output_id": "qualification.crash.measurements",
            "profiled": False,
            "repetitions": 1,
            "run_id": "run.crash",
            "speed_claim": False,
            "summary_output_id": "qualification.crash.summary",
        },
        {
            "candidate_ids": ["A", "C", "D"],
            "case_ids": growth_cases,
            "case_ids_sha256": shared.canonical_sha256(growth_cases),
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
            "case_ids": production_cases,
            "case_ids_sha256": shared.canonical_sha256(production_cases),
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
                _hash(f"fixture.{scale}.{kind}.file"),
            )
            for scale in ("tiny", "standard", "production", "growth")
            for kind in ("manifest", "oracle")
        ),
        _artifact(
            "agent-perf.a.workload",
            "agent_perf_workload",
            shared.canonical_sha256(agent_workload),
        ),
        _artifact("dbhub.invocation", "dbhub_invocation", _hash("dbhub-invocation")),
        _artifact(
            "qualification.crash.invocation",
            "qualification_invocation",
            _hash("qualification-crash-invocation"),
        ),
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
        _artifact(
            "qualification.crash.measurements",
            "qualification_measurements",
            _hash("qualification-crash-measurements"),
            record_count=75,
        ),
        *(
            _artifact(
                f"qualification.{scale}.measurements",
                "qualification_measurements",
                _hash(f"qualification-{scale}-measurements"),
                record_count=15,
            )
            for scale in ("standard", "production", "growth")
        ),
        _artifact(
            "qualification.crash.summary",
            "qualification_summary",
            _hash("qualification-crash-summary"),
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
                    "process_cpu_ns": {
                        "reason_code": "tooling_does_not_report",
                        "status": "unavailable",
                    },
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
            "model_operability": {
                "owner_packet_id": "CK-11",
                "required_evidence_fields": [
                    "authorization",
                    "exact_model_id",
                    "host_version",
                    "reasoning_effort",
                    "runtime_version",
                    "synthetic_input_artifact_id",
                    "synthetic_input_sha256",
                    "token_source",
                ],
                "status": "deferred",
            },
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
                "area": "agent_perf.process_cpu",
                "category": "telemetry_unavailable",
                "evidence_output_ids": ["agent-perf.measurements"],
                "limitation_id": "agent-perf-process-cpu",
                "owner_packet_ids": ["CK-04"],
                "summary": "Profiler output did not expose process CPU time.",
            },
            {
                "area": "dbhub.model_operability",
                "category": "implementation_seam",
                "evidence_output_ids": ["dbhub.measurements"],
                "limitation_id": "dbhub-model-operability",
                "owner_packet_ids": ["CK-11"],
                "summary": (
                    "Exact installed-model identity and an authorized billed model "
                    "call are deferred to CK-11; this local runner invokes no model."
                ),
            },
            {
                "area": "dbhub.scanned_rows",
                "category": "telemetry_unavailable",
                "evidence_output_ids": ["dbhub.measurements"],
                "limitation_id": "dbhub-scanned-rows",
                "owner_packet_ids": ["CK-04"],
                "summary": "DBHub did not expose rows scanned by SQLite.",
            },
            {
                "area": "dbhub.sql_statements",
                "category": "telemetry_unavailable",
                "evidence_output_ids": ["dbhub.measurements"],
                "limitation_id": "dbhub-sql-statements",
                "owner_packet_ids": ["CK-04"],
                "summary": "DBHub did not expose executed SQL statement counts.",
            },
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
                set(standard_cases)
                | set(crash_case_ids)
                | set(production_cases)
                | set(growth_cases)
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


def test_fixture_file_hashes_and_signed_semantic_digests_are_distinct() -> None:
    manifest = _valid_manifest()
    standard = next(row for row in manifest["fixtures"] if row["fixture_id"] == "standard")
    manifest_artifact = next(
        row
        for row in manifest["canonical_artifacts"]["inputs"]
        if row["artifact_id"] == standard["manifest_input_id"]
    )
    assert manifest_artifact["canonical_sha256"] != standard["manifest_semantic_sha256"]
    decision_evidence.build_manifest(manifest)

    stale_workload = _valid_manifest()
    standard = next(row for row in stale_workload["fixtures"] if row["fixture_id"] == "standard")
    manifest_artifact = next(
        row
        for row in stale_workload["canonical_artifacts"]["inputs"]
        if row["artifact_id"] == standard["manifest_input_id"]
    )
    stale_workload["agent_perf"][0]["workload"]["fixture_manifest_digest"] = manifest_artifact[
        "canonical_sha256"
    ]
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="fixture digests are stale",
    ):
        decision_evidence.build_manifest(stale_workload)


def test_query_evidence_covers_exact_matrix_and_non_question_feature() -> None:
    manifest = _valid_manifest()
    assert len(manifest["query_plans"]) == 69
    bounded = next(
        row
        for row in manifest["query_plans"]
        if row["query_case_id"] == "query.feature.bounded_full_sort"
    )
    assert bounded["question_id"] is None
    decision_evidence.build_manifest(manifest)

    missing_case = _valid_manifest()
    missing_case["query_plans"].pop()
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="exact frozen query matrix",
    ):
        decision_evidence.build_manifest(missing_case)

    invented_question = _valid_manifest()
    bounded = next(
        row
        for row in invented_question["query_plans"]
        if row["query_case_id"] == "query.feature.bounded_full_sort"
    )
    bounded["question_id"] = "Q-OPS-04"
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="must be null",
    ):
        decision_evidence.build_manifest(invented_question)


def test_only_frozen_planner_allowances_are_gated() -> None:
    manifest = _valid_manifest()
    manifest["query_plans"][0]["observed_plan_counts"]["sql_statements"] = 999
    decision_evidence.build_manifest(manifest)

    invented_allowance = _valid_manifest()
    invented_allowance["query_plans"][0]["approved_plan_counts"]["sql_statements"] = 999
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="unsupported=.*sql_statements",
    ):
        decision_evidence.build_manifest(invented_allowance)

    weakened_allowance = _valid_manifest()
    weakened_allowance["query_plans"][0]["approved_plan_counts"]["full_scans"] = 1
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="differs from frozen workload contract",
    ):
        decision_evidence.build_manifest(weakened_allowance)


def test_crash_evidence_uses_tiny_fixture_and_durable_observation_fields() -> None:
    manifest = _valid_manifest()
    crash_run = next(row for row in manifest["qualification_runs"] if row["run_id"] == "run.crash")
    assert crash_run["fixture_id"] == "tiny"
    decision_evidence.build_manifest(manifest)

    wrong_fixture = _valid_manifest()
    crash_run = next(
        row for row in wrong_fixture["qualification_runs"] if row["run_id"] == "run.crash"
    )
    crash_run["fixture_id"] = "standard"
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="must use the tiny fixture",
    ):
        decision_evidence.build_manifest(wrong_fixture)

    missing_process_field = _valid_manifest()
    termination = next(
        row
        for row in missing_process_field["crash_observations"]
        if row["mode"] == "process_termination"
    )
    del termination["process"]["worker_pid"]
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="missing=.*worker_pid",
    ):
        decision_evidence.build_manifest(missing_process_field)

    mismatched_return_code = _valid_manifest()
    termination = next(
        row
        for row in mismatched_return_code["crash_observations"]
        if row["mode"] == "process_termination"
    )
    termination["process"]["actual_return_code"] = 85
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="return codes must both equal 86",
    ):
        decision_evidence.build_manifest(mismatched_return_code)

    mismatched_stage = _valid_manifest()
    termination = next(
        row
        for row in mismatched_stage["crash_observations"]
        if row["mode"] == "process_termination"
    )
    termination["process"]["observed_stage"] = "during_parse"
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="requested boundary and observed stage",
    ):
        decision_evidence.build_manifest(mismatched_stage)

    live_worker = _valid_manifest()
    termination = next(
        row for row in live_worker["crash_observations"] if row["mode"] == "process_termination"
    )
    termination["process"]["worker_alive_after_exit"] = True
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="worker remained alive",
    ):
        decision_evidence.build_manifest(live_worker)

    mismatched_lease = _valid_manifest()
    termination = next(
        row
        for row in mismatched_lease["crash_observations"]
        if row["mode"] == "process_termination" and row["boundary"] != "during_old_artifact_cleanup"
    )
    termination["process"]["pid_lease_agreement"] = False
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="valid agreeing worker lease",
    ):
        decision_evidence.build_manifest(mismatched_lease)

    missing_recovery_hash = _valid_manifest()
    injected_fault = next(
        row
        for row in missing_recovery_hash["crash_observations"]
        if row["mode"] == "injected_fault"
    )
    del injected_fault["recovery"]["recovery_terminal_sha256"]
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="missing=.*recovery_terminal_sha256",
    ):
        decision_evidence.build_manifest(missing_recovery_hash)


def test_dbhub_local_routes_are_deliberate_and_globally_sequenced() -> None:
    manifest = _valid_manifest()
    trials = manifest["dbhub"]["trials"]
    assert [trial["executed_route"] for trial in trials] == [
        "generic",
        "named_preset",
    ]
    assert [trial["executed_tool"] for trial in trials] == [
        "search_objects+execute_sql",
        "top_sessions",
    ]
    assert [
        (
            sample["sequence_index"],
            trial["executed_route"],
        )
        for trial in trials
        for sample in trial["samples"]
    ] == [
        (0, "generic"),
        (2, "generic"),
        (4, "generic"),
        (6, "generic"),
        (8, "generic"),
        (1, "named_preset"),
        (3, "named_preset"),
        (5, "named_preset"),
        (7, "named_preset"),
        (9, "named_preset"),
    ]
    assert all(
        "model_class" not in trial
        and "model_tokens" not in trial
        and "selected_tool" not in trial
        and "correct_route" not in trial
        for trial in trials
    )
    decision_evidence.build_manifest(manifest)

    nonalternating = _valid_manifest()
    generic, named = nonalternating["dbhub"]["trials"]
    generic["samples"][0]["sequence_index"] = 1
    named["samples"][0]["sequence_index"] = 0
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="must alternate generic and named_preset",
    ):
        decision_evidence.build_manifest(nonalternating)

    wrong_tool = _valid_manifest()
    wrong_tool["dbhub"]["trials"][0]["executed_tool"] = "execute_sql"
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="differs from the local route contract",
    ):
        decision_evidence.build_manifest(wrong_tool)

    wrong_calls = _valid_manifest()
    wrong_calls["dbhub"]["trials"][0]["samples"][0]["mcp_calls"] = 1
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="differs from DBHub route contract",
    ):
        decision_evidence.build_manifest(wrong_calls)

    mismatched_result = _valid_manifest()
    mismatched_result["dbhub"]["trials"][1]["samples"][0]["result_sha256"] = _hash(
        "different-dbhub-result"
    )
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="did not return identical correct result",
    ):
        decision_evidence.build_manifest(mismatched_result)


def test_optional_telemetry_requires_explicit_provenance_and_limitations() -> None:
    observed_agent_cpu = _valid_manifest()
    observed_agent_cpu["agent_perf"][0]["profiled_run"]["process_cpu_ns"] = {
        "status": "observed",
        "value": 9_000_000_000,
    }
    observed_agent_cpu["limitations"] = [
        row for row in observed_agent_cpu["limitations"] if row["area"] != "agent_perf.process_cpu"
    ]
    decision_evidence.build_manifest(observed_agent_cpu)

    bare_agent_cpu = _valid_manifest()
    bare_agent_cpu["agent_perf"][0]["profiled_run"]["process_cpu_ns"] = 9_000_000_000
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="observed/unavailable provenance object",
    ):
        decision_evidence.build_manifest(bare_agent_cpu)

    observed_scans = _valid_manifest()
    for trial in observed_scans["dbhub"]["trials"]:
        for sample in trial["samples"]:
            sample["scanned_rows"] = {"status": "observed", "value": 25}
    observed_scans["limitations"] = [
        row for row in observed_scans["limitations"] if row["area"] != "dbhub.scanned_rows"
    ]
    decision_evidence.build_manifest(observed_scans)

    bare_scans = _valid_manifest()
    bare_scans["dbhub"]["trials"][0]["samples"][0]["scanned_rows"] = 25
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="observed/unavailable provenance object",
    ):
        decision_evidence.build_manifest(bare_scans)

    observed_statements = _valid_manifest()
    for trial in observed_statements["dbhub"]["trials"]:
        for sample in trial["samples"]:
            sample["sql_statements"] = {"status": "observed", "value": 3}
    observed_statements["limitations"] = [
        row for row in observed_statements["limitations"] if row["area"] != "dbhub.sql_statements"
    ]
    decision_evidence.build_manifest(observed_statements)

    bare_statements = _valid_manifest()
    bare_statements["dbhub"]["trials"][0]["samples"][0]["sql_statements"] = 2
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="observed/unavailable provenance object",
    ):
        decision_evidence.build_manifest(bare_statements)


def test_scoring_formula_and_eliminate_before_score_are_frozen() -> None:
    manifest = _valid_manifest()
    assert manifest["candidates"][1]["evaluation_status"] == "eliminated_before_scoring"
    assert manifest["candidates"][1]["score_inputs"] == []
    assert manifest["candidates"][1]["score_results"] == []
    decision_evidence.build_manifest(manifest)

    stale_formula = _valid_manifest()
    stale_formula["candidates"][0]["score_inputs"][0]["dimensions"][0]["formula_id"] = (
        "ck04.score.post-hoc.v1"
    )
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="frozen scoring formula",
    ):
        decision_evidence.build_manifest(stale_formula)

    fabricated_scores = _valid_manifest()
    fabricated_scores["candidates"][1]["score_inputs"] = [
        fabricated_scores["candidates"][0]["score_inputs"][0]
    ]
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="between 0 and 0",
    ):
        decision_evidence.build_manifest(fabricated_scores)


def test_extracts_all_score_dimensions_from_authenticated_qualification_evidence() -> None:
    _, fixture_digests = _fixture_rows()
    code_commit = "a" * 40
    evidence = _score_evidence(fixture_digests, code_commit)

    score = decision_evidence.extract_score_input(
        candidate_id="A",
        scale="standard",
        evidence=evidence,
    )

    assert score["formula_contract_sha256"] == decision_evidence.SCORE_FORMULA_CONTRACT_SHA256
    assert score["fixture_id"] == "standard"
    assert score["scale"] == "standard"
    assert [row["dimension"] for row in score["dimensions"]] == sorted(
        dimension.value for dimension in shared.ScoreDimension
    )
    assert {row["dimension"]: row["value"] for row in score["dimensions"]} == {
        "cold_build_expansion_latency": "40",
        "crash_recovery_lifecycle_simplicity": "25000025",
        "database_index_wal_size": "125",
        "evidence_stability_selector_cost": "20050",
        "implementation_complexity_operability": "70",
        "named_query_evidence_mcp_payload_efficiency": "69002072070",
        "ordinary_tail_latency_write_amplification": "54000045",
    }


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (
            lambda bundles: setattr(
                bundles[1],
                "summary_bytes",
                bundles[1].summary_bytes.replace(
                    b'"measurement_sha256":"', b'"measurement_sha256":"0'
                ),
            ),
            "canonical|digest",
        ),
        (
            lambda bundles: setattr(
                bundles[1],
                "detail_bytes",
                bundles[1].detail_bytes.replace(
                    b'"measurement_record_digest":"', b'"measurement_record_digest":"0', 1
                ),
            ),
            "detail.*canonical|digest",
        ),
    ],
)
def test_score_extraction_rejects_stale_or_authentication_independent_evidence(
    mutation: Any,
    match: str,
) -> None:
    _, fixture_digests = _fixture_rows()
    bundles = _score_evidence(fixture_digests, "a" * 40)
    mutation(bundles)

    with pytest.raises(decision_evidence.DecisionEvidenceContractError, match=match):
        decision_evidence.extract_score_input(
            candidate_id="A",
            scale="standard",
            evidence=bundles,
        )


def test_score_extraction_fails_closed_on_missing_wrong_case_profile_or_unit() -> None:
    _, fixture_digests = _fixture_rows()
    code_commit = "a" * 40
    cases = decision_evidence.score_formula_source_cases("standard")

    missing = _score_evidence(fixture_digests, code_commit)
    missing[1] = _score_evidence_bundle(
        profile="standard",
        case_ids=[
            case_id
            for profile, case_id in cases
            if profile == "standard" and case_id != "build.scale.standard"
        ],
        code_commit=code_commit,
        fixture_digests=fixture_digests,
    )
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError, match="missing.*build.scale.standard"
    ):
        decision_evidence.extract_score_input(candidate_id="A", scale="standard", evidence=missing)

    wrong_profile = _score_evidence(fixture_digests, code_commit)
    wrong_profile[1] = _score_evidence_bundle(
        profile="standard",
        case_ids=["ordinary.no_source_change"],
        code_commit=code_commit,
        fixture_digests=fixture_digests,
    )
    with pytest.raises(decision_evidence.DecisionEvidenceContractError, match="profile"):
        decision_evidence.extract_score_input(
            candidate_id="A",
            scale="standard",
            evidence=wrong_profile,
        )

    wrong_unit = _score_evidence(fixture_digests, code_commit)
    wrong_unit[1] = _score_evidence_bundle(
        profile="standard",
        case_ids=[case_id for profile, case_id in cases if profile == "standard"],
        code_commit=code_commit,
        fixture_digests=fixture_digests,
        mutate_measurement=lambda row: row["values"].update({"response_bytes": "30"}),
    )
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError, match="response_bytes.*integer"
    ):
        decision_evidence.extract_score_input(
            candidate_id="A",
            scale="standard",
            evidence=wrong_unit,
        )


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


def test_deferred_model_operability_requires_explicit_ck11_limitation() -> None:
    manifest = _valid_manifest()
    manifest["limitations"] = [
        row for row in manifest["limitations"] if row["area"] != "dbhub.model_operability"
    ]
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="explicit limitations",
    ):
        decision_evidence.build_manifest(manifest)

    incomplete_prerequisites = _valid_manifest()
    incomplete_prerequisites["dbhub"]["model_operability"]["required_evidence_fields"].remove(
        "exact_model_id"
    )
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="between 8 and 8",
    ):
        decision_evidence.build_manifest(incomplete_prerequisites)

    wrong_owner = _valid_manifest()
    wrong_owner["dbhub"]["model_operability"]["owner_packet_id"] = "CK-04"
    with pytest.raises(
        decision_evidence.DecisionEvidenceContractError,
        match="owner_packet_id must be CK-11",
    ):
        decision_evidence.build_manifest(wrong_owner)
