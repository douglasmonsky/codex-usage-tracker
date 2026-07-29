"""Authenticate and aggregate immutable CK-04 decision evidence.

The caller supplies the decision fields that are not measurements (including
the decision date and destination).  This module only authenticates source
artifacts, derives measurement-backed projections, and publishes through the
strict decision-evidence writer.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import decision_evidence
import shared

_MAX_INPUT_BYTES = 32 * 1024 * 1024
_MAX_RECORDS = 20_000
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_EXPECTED_SCORE_FORMULA_SHA256 = "3456939c1b5f5fd015d98ed84b03bafd0b7df99f27b39e4df0187f264c8664fc"
_AGENT_PERF_TOOL_VERSIONS = {
    "agent_perf": "0.1.0",
    "psutil": "7.2.2",
    "scalene": "2.3.0",
}
_FILES = ("invocation.json", "measurements.jsonl", "details.jsonl", "summary.json")


class AggregateEvidenceError(ValueError):
    """An aggregate input is incomplete, stale, unbounded, or unauthenticated."""


@dataclass(frozen=True)
class QualificationBundle:
    root: Path
    invocation: Mapping[str, Any]
    measurements: tuple[Mapping[str, Any], ...]
    details: tuple[Mapping[str, Any], ...]
    summary: Mapping[str, Any]
    canonical_bytes: Mapping[str, bytes]


@dataclass(frozen=True)
class AggregateArtifact:
    root: Path
    manifest_path: Path
    manifest_sha256: str
    complete_path: Path


def _read_bounded(path: Path) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise AggregateEvidenceError(f"artifact is missing or unsafe: {path.name}")
        size = path.stat().st_size
        if size <= 0 or size > _MAX_INPUT_BYTES:
            raise AggregateEvidenceError(f"artifact size is invalid: {path.name}")
        return path.read_bytes()
    except OSError as error:
        raise AggregateEvidenceError(f"artifact cannot be read: {path.name}") from error


def _canonical_object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AggregateEvidenceError(f"{label} is not JSON") from error
    if not isinstance(decoded, dict):
        raise AggregateEvidenceError(f"{label} must be one object")
    if shared.canonical_json_bytes(decoded) != payload:
        raise AggregateEvidenceError(f"{label} is not canonical JSON")
    return decoded


def _canonical_lines(payload: bytes, label: str) -> tuple[dict[str, Any], ...]:
    lines = payload.splitlines(keepends=True)
    if not lines or len(lines) > _MAX_RECORDS:
        raise AggregateEvidenceError(f"{label} record count is invalid")
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        records.append(_canonical_object(line, f"{label}[{index}]"))
    return tuple(records)


def _verify_digest(document: Mapping[str, Any], field: str, label: str) -> None:
    expected = document.get(field)
    base = dict(document)
    base.pop(field, None)
    if expected != shared.canonical_sha256(base):
        raise AggregateEvidenceError(f"{label} {field} is stale")


def _assert_score_formula_contract() -> None:
    if decision_evidence.SCORE_FORMULA_CONTRACT_SHA256 != _EXPECTED_SCORE_FORMULA_SHA256:
        raise AggregateEvidenceError("score formula contract drifted")


def authenticate_qualification_bundle(root: Path) -> QualificationBundle:
    """Authenticate one immutable qualification invocation and its full chain."""

    _assert_score_formula_contract()
    root = root.resolve()
    payloads = {name: _read_bounded(root / name) for name in _FILES}
    invocation = _canonical_object(payloads["invocation.json"], "qualification invocation")
    measurements = _canonical_lines(payloads["measurements.jsonl"], "qualification measurements")
    details = _canonical_lines(payloads["details.jsonl"], "qualification details")
    summary = _canonical_object(payloads["summary.json"], "qualification summary")
    _verify_digest(invocation, "invocation_digest", "qualification invocation")
    _verify_digest(summary, "summary_digest", "qualification summary")

    if summary.get("invocation_digest") != invocation.get("invocation_digest"):
        raise AggregateEvidenceError("qualification summary invocation digest is stale")
    if hashlib.sha256(payloads["measurements.jsonl"]).hexdigest() != summary.get(
        "measurement_sha256"
    ):
        raise AggregateEvidenceError("qualification measurement digest is stale")
    if hashlib.sha256(payloads["details.jsonl"]).hexdigest() != summary.get("details_sha256"):
        raise AggregateEvidenceError("qualification detail digest is stale")
    count = len(measurements)
    if (
        count != len(details)
        or summary.get("records") != count
        or summary.get("detail_records") != count
        or summary.get("planned_executions") != count
    ):
        raise AggregateEvidenceError("qualification record counts are incomplete")
    if summary.get("status") not in {"passed", "failed"}:
        raise AggregateEvidenceError("qualification completion status is unsupported")

    environment = invocation.get("environment")
    fixture = invocation.get("fixture")
    if not isinstance(environment, dict) or not isinstance(fixture, dict):
        raise AggregateEvidenceError("qualification identity is incomplete")
    environment_digest = shared.canonical_sha256(environment)
    if invocation.get("environment_digest") != environment_digest:
        raise AggregateEvidenceError("qualification environment digest is stale")
    expected_identity = {
        "code_commit": invocation.get("code_commit"),
        "workload_matrix_digest": invocation.get("workload_matrix_digest"),
        "fixture_manifest_digest": fixture.get("manifest_digest"),
        "fixture_oracle_digest": fixture.get("oracle_digest"),
        "fixture_profile": fixture.get("profile"),
        "profiled": invocation.get("profiled"),
        "qualification_model": invocation.get("qualification_model"),
        "run_id": invocation.get("run_id"),
    }
    repetitions: dict[tuple[str, str], set[int]] = {}
    for index, (measurement, detail) in enumerate(zip(measurements, details, strict=True)):
        _verify_digest(detail, "detail_digest", f"qualification detail[{index}]")
        identity = measurement.get("identity")
        projected = detail.get("measurement_identity")
        values = measurement.get("values")
        if (
            measurement.get("schema") != shared.MEASUREMENT_SCHEMA
            or not isinstance(identity, dict)
            or not isinstance(projected, dict)
            or not isinstance(values, dict)
        ):
            raise AggregateEvidenceError(f"qualification measurement[{index}] is incomplete")
        for field, expected in expected_identity.items():
            if identity.get(field) != expected:
                raise AggregateEvidenceError(f"qualification measurement[{index}] {field} is stale")
        expected_projection = {
            **{key: value for key, value in identity.items() if key != "environment"},
            "environment_digest": environment_digest,
        }
        if (
            projected != expected_projection
            or detail.get("measurement_identity_digest") != shared.canonical_sha256(projected)
            or detail.get("measurement_record_digest") != shared.canonical_sha256(measurement)
            or detail.get("invocation_digest") != invocation.get("invocation_digest")
        ):
            raise AggregateEvidenceError(
                f"qualification measurement/detail[{index}] digest chain is stale"
            )
        for field in ("outcome", "partial", "stop_decision"):
            if detail.get(field) != measurement.get(field):
                raise AggregateEvidenceError(
                    f"qualification measurement/detail[{index}] {field} differs"
                )
        candidate_id = identity.get("candidate_id")
        case_id = identity.get("case_id")
        repetition = identity.get("repetition")
        if (
            candidate_id not in {"A", "C", "D"}
            or not isinstance(case_id, str)
            or not isinstance(repetition, int)
            or isinstance(repetition, bool)
            or repetition < 0
        ):
            raise AggregateEvidenceError(
                f"qualification measurement[{index}] execution identity is invalid"
            )
        repetitions.setdefault((candidate_id, case_id), set()).add(repetition)
    expected_repetitions = invocation.get("repetitions")
    if not isinstance(expected_repetitions, int) or isinstance(expected_repetitions, bool):
        raise AggregateEvidenceError("qualification repetition count is invalid")
    for key, observed in repetitions.items():
        if observed != set(range(expected_repetitions)):
            raise AggregateEvidenceError(
                f"qualification {key[0]}:{key[1]} repetition coverage is incomplete"
            )
    return QualificationBundle(
        root=root,
        invocation=invocation,
        measurements=measurements,
        details=details,
        summary=summary,
        canonical_bytes=payloads,
    )


def require_common_identity(
    bundles: Sequence[QualificationBundle],
    *,
    code_commit: str,
    fixture_digests: Mapping[str, tuple[str, str]] | None = None,
) -> None:
    if not bundles:
        raise AggregateEvidenceError("qualification evidence is empty")
    matrices = {bundle.invocation.get("workload_matrix_digest") for bundle in bundles}
    environments = {bundle.invocation.get("environment_digest") for bundle in bundles}
    if len(matrices) != 1:
        raise AggregateEvidenceError("qualification workload matrix differs")
    if len(environments) != 1:
        raise AggregateEvidenceError("qualification environment differs")
    for bundle in bundles:
        if bundle.invocation.get("code_commit") != code_commit:
            raise AggregateEvidenceError("qualification code commit differs")
        fixture = bundle.invocation["fixture"]
        profile = fixture["profile"]
        if fixture_digests is not None and (
            profile not in fixture_digests
            or (fixture["manifest_digest"], fixture["oracle_digest"]) != fixture_digests[profile]
        ):
            raise AggregateEvidenceError(f"qualification {profile} fixture differs")


def _nearest_rank_p95(values: Iterable[int]) -> int:
    ordered = sorted(values)
    if not ordered:
        raise AggregateEvidenceError("p95 distribution is empty")
    return ordered[((95 * len(ordered) + 99) // 100) - 1]


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AggregateEvidenceError(f"{field} must be a nonnegative integer")
    return value


def project_query_rows(
    bundles: Sequence[QualificationBundle],
) -> tuple[dict[str, object], ...]:
    """Derive the standard query projection while admitting score-only scales."""

    grouped: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    run_ids: dict[tuple[str, str], str] = {}
    for bundle in bundles:
        for measurement in bundle.measurements:
            identity = measurement["identity"]
            case_id = identity["case_id"]
            if not str(case_id).startswith("query."):
                continue
            profile = identity["fixture_profile"]
            if (
                identity["candidate_id"] != "A"
                or profile not in {"standard", "production", "growth"}
                or identity["profiled"] is not False
                or measurement["outcome"] != "passed"
                or measurement["partial"] is not False
            ):
                raise AggregateEvidenceError(f"query case {case_id} is not passed A evidence")
            grouped.setdefault(profile, {}).setdefault(case_id, []).append(measurement)
            run_ids[(profile, case_id)] = str(bundle.invocation["run_id"])
    matrix = shared.build_workload_matrix(physical_cores=1)
    contracts = {
        case.case_id: case for case in matrix.cases if case.group is shared.WorkloadGroup.QUERY
    }
    for profile, cases in grouped.items():
        for case_id, samples in cases.items():
            if len(samples) != 5:
                raise AggregateEvidenceError(
                    f"query case {case_id} requires exactly five repetitions"
                )
            repetitions = {sample["identity"]["repetition"] for sample in samples}
            if repetitions != set(range(5)):
                raise AggregateEvidenceError(
                    f"query case {case_id} repetition coverage is incomplete"
                )
            if case_id not in contracts:
                raise AggregateEvidenceError(f"query case {case_id} is absent from workload matrix")
            if any(
                sample["values"].get("answer_correct") is not True
                or sample["values"].get("oracle_equivalent") is not True
                or sample["values"].get("selector_pages_gap_free") is not True
                for sample in samples
            ):
                raise AggregateEvidenceError(f"query case {case_id} correctness is not proven")
        if set(cases) != set(contracts):
            raise AggregateEvidenceError(f"{profile} query coverage is incomplete")

    standard = grouped.get("standard")
    if standard is None:
        raise AggregateEvidenceError("standard query coverage is absent")
    rows: list[dict[str, object]] = []
    for case_id in sorted(standard):
        samples = standard[case_id]
        contract = contracts[case_id]
        values = [sample["values"] for sample in samples]
        sql_latencies = [
            _integer(latency, f"{case_id}.sql_latencies_ns")
            for value in values
            for latency in value.get("sql_latencies_ns", [])
        ]
        rows.append(
            {
                "answer_correct": True,
                "approved_plan_counts": {
                    "automatic_indexes": int(contract.parameter("maximum_automatic_indexes") or 0),
                    "full_scans": int(contract.parameter("maximum_full_scans") or 0),
                    "temporary_sorts": int(contract.parameter("maximum_temporary_sorts") or 0),
                },
                "fixture_id": samples[0]["identity"]["fixture_profile"],
                "mcp_latency_p95_ns": _nearest_rank_p95(
                    _integer(value.get("mcp_latency_ns"), f"{case_id}.mcp_latency_ns")
                    for value in values
                ),
                "observed_plan_counts": {
                    "automatic_indexes": max(
                        _integer(value.get("automatic_index_count"), "automatic_index_count")
                        for value in values
                    ),
                    "full_scans": max(
                        _integer(value.get("full_scan_count"), "full_scan_count")
                        for value in values
                    ),
                    "sql_statements": max(
                        _integer(value.get("sql_statements"), "sql_statements") for value in values
                    ),
                    "temporary_sorts": max(
                        _integer(value.get("temporary_sort_count"), "temporary_sort_count")
                        for value in values
                    ),
                },
                "oracle_equivalent": True,
                "performance_class": str(contract.parameter("performance_class")),
                "plan_id": str(contract.parameter("plan_id")),
                "qualification_run_id": run_ids[("standard", case_id)],
                "query_case_id": case_id,
                "question_id": contract.parameter("question_id"),
                "repetitions": 5,
                "response_bytes_max": max(
                    _integer(value.get("response_bytes"), f"{case_id}.response_bytes")
                    for value in values
                ),
                "selector_pages_gap_free": True,
                "sql_latency_p95_ns": _nearest_rank_p95(sql_latencies),
            }
        )
    return tuple(rows)


def project_crash_rows(
    bundles: Sequence[QualificationBundle],
) -> tuple[dict[str, object], ...]:
    """Copy authenticated process and recovery evidence from Candidate A details."""

    rows: list[dict[str, object]] = []
    for bundle in bundles:
        for measurement, detail in zip(bundle.measurements, bundle.details, strict=True):
            identity = measurement["identity"]
            case_id = str(identity["case_id"])
            if identity["candidate_id"] != "A" or not case_id.startswith("crash."):
                continue
            oracle = detail.get("oracle_results")
            if not isinstance(oracle, dict):
                raise AggregateEvidenceError(f"{case_id} has no authenticated recovery evidence")
            if case_id.startswith("crash.terminate."):
                boundary = case_id.removeprefix("crash.terminate.")
                process = oracle.get("process")
                recovery = oracle.get("recovery_evidence")
                if not isinstance(process, dict) or not isinstance(recovery, dict):
                    raise AggregateEvidenceError(
                        f"{case_id} process/recovery evidence is incomplete"
                    )
                fault: str | None = None
                mode = "process_termination"
            else:
                boundary = None
                fault = case_id.removeprefix("crash.fault.")
                process = {"status": "not_applicable"}
                recovery = oracle.get("recovery_evidence")
                if not isinstance(recovery, dict):
                    raise AggregateEvidenceError(f"{case_id} recovery evidence is incomplete")
                mode = "injected_fault"
            rows.append(
                {
                    "boundary": boundary,
                    "candidate_id": "A",
                    "case_id": case_id,
                    "fault": fault,
                    "mode": mode,
                    "observation_id": f"A.{case_id}",
                    "process": process,
                    "qualification_run_id": bundle.invocation["run_id"],
                    "recovery": recovery,
                }
            )
    return tuple(sorted(rows, key=lambda row: str(row["observation_id"])))


def derive_candidate_a_score_inputs(
    bundles: Sequence[QualificationBundle],
) -> tuple[dict[str, object], ...]:
    """Derive all Candidate A score inputs only through the frozen extractor."""

    evidence = [
        decision_evidence.QualificationScoreEvidence(
            invocation_bytes=bundle.canonical_bytes["invocation.json"],
            measurement_bytes=bundle.canonical_bytes["measurements.jsonl"],
            detail_bytes=bundle.canonical_bytes["details.jsonl"],
            summary_bytes=bundle.canonical_bytes["summary.json"],
        )
        for bundle in bundles
        if bundle.invocation.get("candidate_ids") == ["A"]
    ]
    if not evidence:
        raise AggregateEvidenceError("Candidate A score evidence is missing")
    try:
        return tuple(
            decision_evidence.extract_score_input(
                candidate_id="A",
                scale=scale,
                evidence=evidence,
            )
            for scale in ("standard", "production", "growth")
        )
    except decision_evidence.DecisionEvidenceContractError as error:
        raise AggregateEvidenceError(f"Candidate A score evidence is invalid: {error}") from error


def authenticate_agent_perf(path: Path) -> dict[str, Any]:
    """Authenticate the bounded, path-free Agent Perf collector output."""

    payload = _canonical_object(_read_bounded(path.resolve()), "Agent Perf evidence")
    if payload.get("schema") != "codex-usage-tracker.ck04-agent-perf-evidence.v1":
        raise AggregateEvidenceError("Agent Perf evidence schema is unsupported")
    if payload.get("candidate_id") != "A":
        raise AggregateEvidenceError("Agent Perf evidence candidate differs")
    fixture = payload.get("fixture")
    workload = payload.get("workload")
    tool_versions = payload.get("tool_versions")
    unprofiled = payload.get("unprofiled_runs")
    profiled = payload.get("profiled_run")
    if (
        not isinstance(fixture, dict)
        or fixture.get("profile") != "standard"
        or fixture.get("revision") != shared.FIXTURE_REVISION
        or fixture.get("synthetic_only") is not True
        or not isinstance(workload, dict)
        or workload.get("id") != "build.scale.standard"
        or workload.get("minimum_unprofiled_runs") != 5
        or workload.get("profile_is_attribution_only") is not True
        or tool_versions != _AGENT_PERF_TOOL_VERSIONS
        or not isinstance(unprofiled, list)
        or len(unprofiled) != 5
        or not isinstance(profiled, dict)
    ):
        raise AggregateEvidenceError("Agent Perf evidence is incomplete")
    identities = {
        run.get("result_identity_sha256")
        for run in [*unprofiled, profiled]
        if isinstance(run, dict)
    }
    if len(identities) != 1 or None in identities:
        raise AggregateEvidenceError("Agent Perf result identities differ")
    run_ids = [run.get("run_id") for run in [*unprofiled, profiled] if isinstance(run, dict)]
    if len(run_ids) != 6 or len(set(run_ids)) != 6:
        raise AggregateEvidenceError("Agent Perf run identities are incomplete")
    if any(
        _integer(run.get("wall_time_ns"), "Agent Perf wall_time_ns") <= 0
        or _integer(run.get("process_tree_cpu_ns"), "Agent Perf process_tree_cpu_ns") <= 0
        for run in [*unprofiled, profiled]
        if isinstance(run, dict)
    ):
        raise AggregateEvidenceError("Agent Perf measurements are invalid")
    profile = profiled.get("profile")
    if (
        not isinstance(profile, dict)
        or profile.get("profile_is_attribution_only") is not True
        or not isinstance(profile.get("hotspots"), list)
    ):
        raise AggregateEvidenceError("Agent Perf profile attribution is incomplete")
    return payload


def authenticate_dbhub(path: Path) -> dict[str, Any]:
    """Authenticate the exact ten-sample, two-route DBHub evidence."""

    payload = _canonical_object(_read_bounded(path.resolve()), "DBHub evidence")
    if (
        payload.get("package") != shared.DBHUB_PACKAGE
        or payload.get("version") != shared.DBHUB_VERSION
        or payload.get("package_integrity") != shared.DBHUB_NPM_INTEGRITY
        or payload.get("snapshot_sha256_before") != payload.get("snapshot_sha256_after")
        or payload.get("tool_level_read_only") is not True
        or payload.get("engine_level_read_only") is not False
    ):
        raise AggregateEvidenceError("DBHub identity or snapshot authentication failed")
    trials = payload.get("trials")
    if not isinstance(trials, list) or len(trials) != 2:
        raise AggregateEvidenceError("DBHub route evidence is incomplete")
    expected_tools = {
        "generic": ("search_objects+execute_sql", 2, (0, 2, 4, 6, 8)),
        "named_preset": ("top_sessions", 1, (1, 3, 5, 7, 9)),
    }
    result_ids: set[tuple[int, str]] = set()
    for trial in trials:
        if not isinstance(trial, dict):
            raise AggregateEvidenceError("DBHub trial is invalid")
        route = trial.get("executed_route")
        expected = expected_tools.get(str(route))
        samples = trial.get("samples")
        if (
            expected is None
            or trial.get("trial_id") != route
            or trial.get("executed_tool") != expected[0]
            or not isinstance(samples, list)
            or len(samples) != 5
            or tuple(sample.get("sequence_index") for sample in samples) != expected[2]
        ):
            raise AggregateEvidenceError("DBHub route contract differs")
        for sample in samples:
            if (
                not isinstance(sample, dict)
                or sample.get("correct") is not True
                or sample.get("mcp_calls") != expected[1]
            ):
                raise AggregateEvidenceError("DBHub sample contract differs")
            result_ids.add(
                (
                    _integer(sample.get("result_rows"), "DBHub result_rows"),
                    str(sample.get("result_sha256")),
                )
            )
    if len(result_ids) != 1:
        raise AggregateEvidenceError("DBHub routes returned different results")
    return payload


def project_candidate_failure(bundle: QualificationBundle) -> dict[str, object]:
    """Project the one authenticated Candidate C or D hard-gate elimination."""

    if len(bundle.measurements) != 1:
        raise AggregateEvidenceError("candidate elimination must contain exactly one record")
    measurement = bundle.measurements[0]
    detail = bundle.details[0]
    identity = measurement["identity"]
    candidate_id = identity["candidate_id"]
    case_id = identity["case_id"]
    if candidate_id == "C" and case_id == "crash.terminate.before_staging":
        oracle = detail.get("oracle_results")
        if not isinstance(oracle, dict) or oracle.get("process_termination_observed") is not False:
            raise AggregateEvidenceError(
                "Candidate C lacks authenticated process_termination_observed=false"
            )
        return {
            "case_id": case_id,
            "comparison": "eq",
            "detail_code": "process_not_terminated",
            "failure_id": "C.process_termination",
            "gate": "publication_recovery",
            "metric": "process_termination_observed",
            "observed": False,
            "required": True,
        }
    if candidate_id == "D" and case_id == "build.empty.30_days":
        failure = bundle.summary.get("failure")
        stop = measurement.get("stop_decision")
        if (
            not isinstance(failure, dict)
            or not isinstance(stop, dict)
            or failure.get("detail_code") == "suite.watchdog_timeout"
            or str(failure.get("detail_code", "")).startswith("suite.")
        ):
            raise AggregateEvidenceError("Candidate D evidence is censored")
        if (
            measurement.get("outcome") != "stopped"
            or measurement.get("partial") is not True
            or stop.get("metric") != "elapsed_ms"
            or _integer(stop.get("maximum"), "Candidate D elapsed gate") != 5_000
            or _integer(stop.get("observed"), "Candidate D elapsed observation") <= 5_000
        ):
            raise AggregateEvidenceError("Candidate D wall-time failure is not authenticated")
        wall_time = _integer(measurement.get("wall_time_ns"), "Candidate D wall_time")
        if wall_time <= 5_000_000_000:
            raise AggregateEvidenceError("Candidate D wall-time failure is below the hard gate")
        return {
            "case_id": case_id,
            "comparison": "lte",
            "detail_code": str(failure["detail_code"]),
            "failure_id": "D.production_30d",
            "gate": "performance",
            "metric": "wall_time_ns",
            "observed": wall_time,
            "required": 5_000_000_000,
        }
    raise AggregateEvidenceError("candidate elimination artifact is not the frozen C/D case")


def assemble_manifest(
    draft: Mapping[str, object],
    *,
    qualification_bundles: Sequence[QualificationBundle],
    candidate_c: QualificationBundle,
    candidate_d: QualificationBundle,
    agent_perf: Mapping[str, Any],
    dbhub: Mapping[str, Any],
) -> dict[str, object]:
    """Replace every measurement-owned draft field with authenticated projections."""

    manifest = copy.deepcopy(dict(draft))
    query_rows = project_query_rows(qualification_bundles)
    draft_queries = manifest.get("query_plans")
    if not isinstance(draft_queries, list):
        raise AggregateEvidenceError("decision draft query_plans is missing")
    draft_queries_by_id = {
        row.get("query_case_id"): row for row in draft_queries if isinstance(row, dict)
    }
    if set(draft_queries_by_id) != {row["query_case_id"] for row in query_rows}:
        raise AggregateEvidenceError("decision draft query cases differ from evidence")
    for projected in query_rows:
        target = draft_queries_by_id[projected["query_case_id"]]
        target.update(projected)

    crash_rows = project_crash_rows(qualification_bundles)
    draft_crashes = manifest.get("crash_observations")
    if not isinstance(draft_crashes, list):
        raise AggregateEvidenceError("decision draft crash_observations is missing")
    draft_crashes_by_id = {
        row.get("observation_id"): row for row in draft_crashes if isinstance(row, dict)
    }
    if set(draft_crashes_by_id) != {row["observation_id"] for row in crash_rows}:
        raise AggregateEvidenceError("decision draft crash cases differ from evidence")
    for projected in crash_rows:
        draft_crashes_by_id[projected["observation_id"]].update(projected)

    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        raise AggregateEvidenceError("decision draft candidates are missing")
    candidates_by_id = {row.get("candidate_id"): row for row in candidates if isinstance(row, dict)}
    if set(candidates_by_id) != {"A", "C", "D"}:
        raise AggregateEvidenceError("decision draft candidate set differs")
    candidates_by_id["A"]["score_inputs"] = list(
        derive_candidate_a_score_inputs(qualification_bundles)
    )
    for candidate_id, bundle in (("C", candidate_c), ("D", candidate_d)):
        existing = candidates_by_id[candidate_id].get("failures")
        if (
            not isinstance(existing, list)
            or len(existing) != 1
            or not isinstance(existing[0], dict)
        ):
            raise AggregateEvidenceError(
                f"decision draft Candidate {candidate_id} failure slot is invalid"
            )
        output_artifact_id = existing[0].get("output_artifact_id")
        failure = project_candidate_failure(bundle)
        if output_artifact_id is not None:
            failure["output_artifact_id"] = output_artifact_id
        candidates_by_id[candidate_id]["failures"] = [failure]

    draft_dbhub = manifest.get("dbhub")
    if not isinstance(draft_dbhub, dict):
        raise AggregateEvidenceError("decision draft DBHub projection is missing")
    if dbhub.get("input_artifact_id") != draft_dbhub.get("input_artifact_id"):
        raise AggregateEvidenceError("DBHub invocation artifact differs from decision draft")
    manifest["dbhub"] = copy.deepcopy(dict(dbhub))
    _project_agent_perf(
        manifest,
        agent_perf,
        qualification_bundles=qualification_bundles,
    )
    return manifest


def _project_agent_perf(
    manifest: dict[str, object],
    evidence: Mapping[str, Any],
    *,
    qualification_bundles: Sequence[QualificationBundle],
) -> None:
    rows = manifest.get("agent_perf")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise AggregateEvidenceError("decision draft Agent Perf projection is missing")
    projected = rows[0]
    if projected.get("candidate_id") != "A":
        raise AggregateEvidenceError("decision draft Agent Perf candidate differs")
    workload = projected.get("workload")
    if not isinstance(workload, dict):
        raise AggregateEvidenceError("decision draft Agent Perf workload is missing")
    expected_workload = {
        "candidate_id": "A",
        "fixture_profile": "standard",
        "fixture_revision": shared.FIXTURE_REVISION,
        "minimum_unprofiled_runs": 5,
        "profile_is_attribution_only": True,
        "schema": shared.AGENT_PERF_WORKLOAD_SCHEMA,
        "synthetic_only": True,
        "version": 1,
        "workload_id": "build.scale.standard",
    }
    if any(workload.get(key) != value for key, value in expected_workload.items()):
        raise AggregateEvidenceError("decision draft Agent Perf workload contract differs")

    fixture = evidence["fixture"]
    evidence_workload = evidence["workload"]
    if (
        fixture.get("manifest_sha256") != workload.get("fixture_manifest_digest")
        or fixture.get("oracle_sha256") != workload.get("fixture_oracle_digest")
        or fixture.get("profile") != workload.get("fixture_profile")
        or fixture.get("revision") != workload.get("fixture_revision")
        or evidence_workload.get("digest") != shared.canonical_sha256(workload)
        or evidence_workload.get("id") != workload.get("workload_id")
        or evidence_workload.get("matrix_sha256") != workload.get("workload_matrix_digest")
        or evidence_workload.get("minimum_unprofiled_runs")
        != workload.get("minimum_unprofiled_runs")
        or evidence_workload.get("profile_is_attribution_only")
        != workload.get("profile_is_attribution_only")
    ):
        raise AggregateEvidenceError("Agent Perf fixture or workload differs from decision draft")

    profiler = projected.get("profiler")
    if profiler != {
        "name": "agent-perf",
        "version": evidence["tool_versions"]["agent_perf"],
    }:
        raise AggregateEvidenceError("decision draft Agent Perf profiler identity differs")
    _require_agent_perf_artifact_links(manifest, projected, workload, evidence)
    _require_agent_perf_qualification(
        manifest,
        projected,
        workload,
        qualification_bundles=qualification_bundles,
    )

    unprofiled = evidence["unprofiled_runs"]
    profiled = evidence["profiled_run"]
    profile = profiled["profile"]
    projected.update(
        {
            "hotspots": copy.deepcopy(profile["hotspots"]),
            "unprofiled_runs": [
                {"run_id": row["run_id"], "wall_time_ns": row["wall_time_ns"]} for row in unprofiled
            ],
            "profiled_run": {
                "process_cpu_ns": {
                    "status": "observed",
                    "value": profiled["process_tree_cpu_ns"],
                },
                "run_id": profiled["run_id"],
                "wall_time_ns": profiled["wall_time_ns"],
            },
        }
    )


def _require_agent_perf_artifact_links(
    manifest: Mapping[str, object],
    projected: Mapping[str, Any],
    workload: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> None:
    artifacts = manifest.get("canonical_artifacts")
    if not isinstance(artifacts, dict):
        raise AggregateEvidenceError("decision draft canonical artifacts are missing")
    inputs = artifacts.get("inputs")
    outputs = artifacts.get("outputs")
    if not isinstance(inputs, list) or not isinstance(outputs, list):
        raise AggregateEvidenceError("decision draft canonical artifact lists are missing")
    workload_id = projected.get("workload_input_id")
    measurement_id = projected.get("measurements_output_id")
    workload_rows = [
        row for row in inputs if isinstance(row, dict) and row.get("artifact_id") == workload_id
    ]
    measurement_rows = [
        row for row in outputs if isinstance(row, dict) and row.get("artifact_id") == measurement_id
    ]
    if (
        len(workload_rows) != 1
        or workload_rows[0].get("kind") != "agent_perf_workload"
        or workload_rows[0].get("encoding") != "canonical_json"
        or workload_rows[0].get("canonical_sha256") != shared.canonical_sha256(workload)
        or len(measurement_rows) != 1
        or measurement_rows[0].get("kind") != "agent_perf_measurements"
        or measurement_rows[0].get("encoding") != "canonical_json"
        or measurement_rows[0].get("canonical_sha256") != shared.canonical_sha256(evidence)
    ):
        raise AggregateEvidenceError("decision draft Agent Perf artifact links differ")


def _require_agent_perf_qualification(
    manifest: Mapping[str, object],
    projected: Mapping[str, Any],
    workload: Mapping[str, Any],
    *,
    qualification_bundles: Sequence[QualificationBundle],
) -> None:
    run_id = projected.get("qualification_run_id")
    draft_runs = manifest.get("qualification_runs")
    if not isinstance(draft_runs, list):
        raise AggregateEvidenceError("decision draft qualification runs are missing")
    matching_draft = [
        row for row in draft_runs if isinstance(row, dict) and row.get("run_id") == run_id
    ]
    matching_bundles = [
        bundle for bundle in qualification_bundles if bundle.invocation.get("run_id") == run_id
    ]
    if len(matching_draft) != 1 or len(matching_bundles) != 1:
        raise AggregateEvidenceError("Agent Perf qualification run is missing or ambiguous")
    draft_run = matching_draft[0]
    bundle = matching_bundles[0]
    invocation = bundle.invocation
    fixture = invocation.get("fixture")
    case_ids = invocation.get("case_ids")
    agent_perf_measurements = [
        measurement
        for measurement in bundle.measurements
        if measurement["identity"].get("candidate_id") == "A"
        and measurement["identity"].get("case_id") == "agent_perf.standard_cpu_attribution"
    ]
    if (
        draft_run.get("candidate_ids") != ["A"]
        or draft_run.get("case_ids") != case_ids
        or draft_run.get("case_ids_sha256") != shared.canonical_sha256(case_ids)
        or draft_run.get("fixture_id") != "standard"
        or draft_run.get("profiled") is not False
        or draft_run.get("repetitions") != 5
        or draft_run.get("speed_claim") is not True
        or invocation.get("candidate_ids") != ["A"]
        or not isinstance(case_ids, list)
        or "agent_perf.standard_cpu_attribution" not in case_ids
        or invocation.get("profiled") is not False
        or invocation.get("repetitions") != 5
        or not isinstance(fixture, dict)
        or fixture.get("profile") != "standard"
        or fixture.get("fixture_revision") != workload.get("fixture_revision")
        or fixture.get("manifest_digest") != workload.get("fixture_manifest_digest")
        or fixture.get("oracle_digest") != workload.get("fixture_oracle_digest")
        or invocation.get("workload_matrix_digest") != workload.get("workload_matrix_digest")
        or len(agent_perf_measurements) != 5
        or {measurement["identity"].get("repetition") for measurement in agent_perf_measurements}
        != set(range(5))
    ):
        raise AggregateEvidenceError("Agent Perf qualification identity differs")
    _require_qualification_artifact_links(manifest, draft_run, bundle)


def _require_qualification_artifact_links(
    manifest: Mapping[str, object],
    draft_run: Mapping[str, Any],
    bundle: QualificationBundle,
) -> None:
    artifacts = manifest.get("canonical_artifacts")
    if not isinstance(artifacts, dict):
        raise AggregateEvidenceError("decision draft canonical artifacts are missing")
    inputs = artifacts.get("inputs")
    outputs = artifacts.get("outputs")
    if not isinstance(inputs, list) or not isinstance(outputs, list):
        raise AggregateEvidenceError("decision draft canonical artifact lists are missing")

    expected = (
        (
            inputs,
            draft_run.get("invocation_input_id"),
            "qualification_invocation",
            "invocation.json",
            1,
        ),
        (
            outputs,
            draft_run.get("measurements_output_id"),
            "qualification_measurements",
            "measurements.jsonl",
            len(bundle.measurements),
        ),
        (
            outputs,
            draft_run.get("summary_output_id"),
            "qualification_summary",
            "summary.json",
            1,
        ),
    )
    for rows, artifact_id, kind, file_name, record_count in expected:
        matches = [
            row for row in rows if isinstance(row, dict) and row.get("artifact_id") == artifact_id
        ]
        if (
            len(matches) != 1
            or matches[0].get("kind") != kind
            or matches[0].get("canonical_sha256")
            != hashlib.sha256(bundle.canonical_bytes[file_name]).hexdigest()
            or matches[0].get("record_count") != record_count
        ):
            raise AggregateEvidenceError(
                "decision draft Agent Perf qualification artifact links differ"
            )


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise AggregateEvidenceError(f"artifact already exists: {path.name}") from error
    except OSError as error:
        raise AggregateEvidenceError(f"artifact could not be written: {path.name}") from error


def write_aggregate_directory(
    manifest: Mapping[str, object],
    *,
    output_parent: Path,
    aggregate_id: str,
) -> AggregateArtifact:
    """Publish a unique aggregate directory and write ``COMPLETE`` last."""

    if not _SAFE_ID.fullmatch(aggregate_id):
        raise AggregateEvidenceError("aggregate_id is invalid")
    output_parent = output_parent.resolve()
    if output_parent.is_symlink() or not output_parent.is_dir():
        raise AggregateEvidenceError("output parent is missing or unsafe")
    root = output_parent / aggregate_id
    try:
        root.mkdir(mode=0o700)
    except FileExistsError as error:
        raise AggregateEvidenceError("aggregate directory already exists") from error
    except OSError as error:
        raise AggregateEvidenceError("aggregate directory could not be created") from error

    manifest_path = root / "decision-evidence.json"
    try:
        expected = decision_evidence.write_manifest(manifest, manifest_path)
        observed = decision_evidence.validate_manifest_path(manifest_path)
        observed_sha256 = hashlib.sha256(_read_bounded(manifest_path)).hexdigest()
        if observed.sha256 != expected.sha256 or observed_sha256 != expected.sha256:
            raise AggregateEvidenceError("written decision manifest SHA-256 differs")
        complete_path = root / "COMPLETE"
        _write_exclusive(complete_path, f"{observed_sha256}\n".encode("ascii"))
    except Exception:
        # Preserve the incomplete directory as evidence; absence of COMPLETE is
        # the durable indication that publication did not finish.
        raise
    return AggregateArtifact(
        root=root,
        manifest_path=manifest_path,
        manifest_sha256=observed_sha256,
        complete_path=complete_path,
    )


def _parse_fixture(value: str) -> tuple[str, Path]:
    profile, separator, path = value.partition("=")
    if not separator or profile not in {"tiny", "standard", "production", "growth"}:
        raise argparse.ArgumentTypeError("fixture must be PROFILE=PATH")
    return profile, Path(path)


def _load_draft(path: Path) -> dict[str, object]:
    payload = _read_bounded(path.resolve())
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AggregateEvidenceError("decision draft is not JSON") from error
    if not isinstance(value, dict):
        raise AggregateEvidenceError("decision draft must be one object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Authenticate and publish CK-04 aggregate decision evidence."
    )
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--fixture", action="append", type=_parse_fixture, required=True)
    parser.add_argument("--qualification", action="append", type=Path, required=True)
    parser.add_argument("--agent-perf", type=Path, required=True)
    parser.add_argument("--dbhub", type=Path, required=True)
    parser.add_argument("--candidate-c", type=Path, required=True)
    parser.add_argument("--candidate-d", type=Path, required=True)
    parser.add_argument("--output-parent", type=Path, required=True)
    parser.add_argument("--aggregate-id", required=True)
    arguments = parser.parse_args(argv)

    # Authentication is deliberately completed before the destination exists.
    bundles = [authenticate_qualification_bundle(path) for path in arguments.qualification]
    candidate_c = authenticate_qualification_bundle(arguments.candidate_c)
    candidate_d = authenticate_qualification_bundle(arguments.candidate_d)
    agent_perf = authenticate_agent_perf(arguments.agent_perf)
    dbhub = authenticate_dbhub(arguments.dbhub)
    fixture_digests: dict[str, tuple[str, str]] = {}
    for profile, root in arguments.fixture:
        try:
            fixture = shared.load_fixture_bundle(root.resolve())
        except (OSError, ValueError) as error:
            raise AggregateEvidenceError(f"{profile} fixture authentication failed") from error
        if fixture.profile != profile:
            raise AggregateEvidenceError(f"{profile} fixture profile differs")
        fixture_digests[profile] = (fixture.manifest_digest, fixture.oracle_digest)
    draft = _load_draft(arguments.draft)
    require_common_identity(
        [*bundles, candidate_c, candidate_d],
        code_commit=str(draft.get("code_commit")),
        fixture_digests=fixture_digests,
    )
    manifest = assemble_manifest(
        draft,
        qualification_bundles=bundles,
        candidate_c=candidate_c,
        candidate_d=candidate_d,
        agent_perf=agent_perf,
        dbhub=dbhub,
    )
    artifact = write_aggregate_directory(
        manifest,
        output_parent=arguments.output_parent,
        aggregate_id=arguments.aggregate_id,
    )
    print(artifact.manifest_sha256)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
