#!/usr/bin/env python3
"""Collect synthetic-only CK-08R1 production/independent answer truth."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator  # noqa: E402

from codex_usage_tracker.agent_kernel.domain.plan_operands import PlanEvaluation  # noqa: E402
from codex_usage_tracker.agent_kernel.evidence.cursors import (  # noqa: E402
    CursorCodec,
)
from codex_usage_tracker.agent_kernel.query.contracts import (  # noqa: E402
    EvidenceSelection,
    QueryBatchRequest,
    QueryPage,
    QueryRequest,
)
from codex_usage_tracker.agent_kernel.query.page_executor import (  # noqa: E402
    SUPPORTED_DIRECT_PLAN_IDS,
)
from codex_usage_tracker.agent_kernel.query.registry import (  # noqa: E402
    build_registry,
)
from codex_usage_tracker.agent_kernel.query.service import (  # noqa: E402
    QueryService,
    QueryServiceError,
)
from scripts.ck07r1_prelaunch_recovery import (  # noqa: E402
    AUTHORITY_PATH as CK07R1_RECOVERY_AUTHORITY_PATH,
)
from scripts.ck07r1_prelaunch_recovery import (  # noqa: E402
    load_authority as load_ck07r1_recovery_authority,
)
from scripts.ck07r1_prelaunch_recovery import (  # noqa: E402
    verify_bound_authority_bytes as verify_ck07r1_recovery_authority_bytes,
)
from scripts.ck07r1_prelaunch_recovery import (  # noqa: E402
    verify_exact_authority_delta as verify_ck07r1_recovery_authority_delta,
)
from scripts.ck07r1_prelaunch_recovery import (  # noqa: E402
    verify_prelaunch_recovery,
)
from scripts.ck07r1_shared_successor_overlay import (  # noqa: E402
    PREPARATION_PATH as CK07R1_PREPARATION_PATH,
)
from scripts.ck07r1_shared_successor_overlay import (  # noqa: E402
    verify_shared_successor_overlay,
)
from tests.agent_kernel.fixtures.independent import (  # noqa: E402
    semantic as independent_semantic,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import (  # noqa: E402
    build_question_scenarios,
)
from tests.agent_kernel.fixtures.published_v2 import (  # noqa: E402
    publish_structural_snapshot,
    published_question_case,
)
from tests.agent_kernel.requalification import production as production_replay  # noqa: E402
from tests.agent_kernel.requalification.closure import (  # noqa: E402
    ClosureError,
    compute_closure,
    verify_closure,
)

SCHEMA_NAME = "codex-usage-tracker.answer-truth-requalification.v2"
DEFAULT_OUTPUT = ROOT / "docs/decisions/evidence/ck08r1/answer-truth-requalification-v2.json"
EVIDENCE_SCHEMA = (
    ROOT / "docs/decisions/evidence/ck08r1a" / "answer-truth-requalification-v2.schema.json"
)
JOIN_AUTHORITY = ROOT / "docs/decisions/evidence/ck08r1b" / "answer-semantics-join-authority.json"
ANSWER_SEMANTICS = ROOT / "config/agent-kernel/answer-semantics-v1.json"
CATALOG = ROOT / "config/agent-kernel/question-catalog-v1.json"
PRODUCTION_ROOT = (
    ROOT / "src/codex_usage_tracker/agent_kernel/domain" / "plan_derivations_structural.py"
)
INDEPENDENT_HARNESS = ROOT / "tests/agent_kernel/fixtures/independent/closure.py"
INDEPENDENT_CONSUMER = ROOT / "tests/agent_kernel/fixtures/independent/semantic.py"
PRODUCTION_HARNESS = ROOT / "tests/agent_kernel/requalification/production.py"
PRODUCTION_CONSUMER = ROOT / "tests/agent_kernel/fixtures/oracles/database_replay.py"
PRODUCTION_DATA_SOURCE = ROOT / "tests/agent_kernel/fixtures/oracles/cases_v2.py"
_CURSOR_SECRET = b"ck08r1-synthetic-query-service-secret"
_QUERY_SERVICE_MATRIX: dict[str, Any] | None = None
_GRADING_MATRIX: dict[str, Any] | None = None


class QualificationError(RuntimeError):
    """CK-08R1 must stop before publishing contradictory evidence."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_file(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _json(file_path: Path) -> dict[str, Any]:
    value = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationError(f"{file_path.relative_to(ROOT)} must contain an object")
    return value


def _git_last_touch(relative: str) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if len(result) != 40 or any(character not in "0123456789abcdef" for character in result):
        raise QualificationError(f"authority git identity is malformed: {relative}")
    return result


def _current_ck07r1_overlay() -> tuple[dict[str, Any], str]:
    """Select the immutable v1 overlay or its exact versioned recovery bridge."""

    recovery_path = ROOT / CK07R1_RECOVERY_AUTHORITY_PATH
    if not recovery_path.is_file():
        return verify_shared_successor_overlay(ROOT)

    recovery = load_ck07r1_recovery_authority(ROOT)
    verify_ck07r1_recovery_authority_bytes(recovery, ROOT)
    verify_ck07r1_recovery_authority_delta(recovery, ROOT)
    overlay = _json(
        ROOT / "docs/decisions/evidence/ck07r1a0/shared-successor-overlay-authority-v1.json"
    )
    predecessor = overlay["states"]["predecessor"]["artifacts"][0]["sha256"]
    successor = next(
        item["sha256"]
        for item in recovery["candidate_cohort"]
        if item["path"] == CK07R1_PREPARATION_PATH
    )
    observed = sha256_file(ROOT / CK07R1_PREPARATION_PATH)
    if observed == predecessor:
        return overlay, "authority_main"
    if observed == successor:
        _, state = verify_prelaunch_recovery(ROOT)
        if state != "prelaunch_recovery_verified":
            raise QualificationError("CK-07R1 recovery state is not verified")
        return overlay, "worker_prequalification"
    raise QualificationError("CK-07R1 preparation state is outside the recovery authority")


def recompute_authority_identities() -> dict[str, Any]:
    """Recompute all R1A/B/C identities from committed authority paths."""

    overlay, overlay_state = _current_ck07r1_overlay()
    overlay_predecessor = overlay["states"]["predecessor"]["artifacts"][0]["sha256"]
    overlay_successor = overlay["states"]["successor"]["artifacts"][0]["sha256"]
    authority = _json(JOIN_AUTHORITY)
    producer = authority.get("producer_authority")
    independent = authority.get("independent_truth_authority")
    cohort = authority.get("selected_successor_cohort")
    if not all(isinstance(item, Mapping) for item in (producer, independent, cohort)):
        raise QualificationError("authority sections are missing")

    producer_artifacts = producer.get("artifacts")
    cohort_files = cohort.get("files")
    accepted_roots = independent.get("accepted_roots")
    if not all(
        isinstance(item, list)
        for item in (
            producer_artifacts,
            cohort_files,
            accepted_roots,
        )
    ):
        raise QualificationError("authority path manifests are malformed")

    authority_digests: dict[str, str] = {}
    digest_names = {
        "config/agent-kernel/answer-semantics-v1.json": "answer_semantics",
        "config/agent-kernel/answer-semantics-v1.schema.json": "answer_semantics_schema",
        "tests/agent_kernel/fixtures/contracts/answer-semantics-v1-vectors.json": (
            "answer_semantics_vectors"
        ),
        "docs/decisions/evidence/ck08r1a/answer-truth-requalification-v2.schema.json": (
            "evidence_schema"
        ),
    }
    for record in producer_artifacts:
        if not isinstance(record, Mapping):
            raise QualificationError("R1A authority record is malformed")
        relative = record.get("path")
        expected = record.get("sha256")
        if not isinstance(relative, str) or relative not in digest_names:
            raise QualificationError("R1A authority path is unexpected")
        actual = sha256_file(ROOT / relative)
        if actual != expected:
            raise QualificationError(f"R1A authority digest drift: {relative}")
        authority_digests[digest_names[relative]] = actual
    if set(authority_digests) != set(digest_names.values()):
        raise QualificationError("R1A authority manifest is incomplete")

    selected_by_path: dict[str, Mapping[str, Any]] = {}
    for record in cohort_files:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise QualificationError("R1B cohort record is malformed")
        relative = str(record["path"])
        if relative in selected_by_path:
            raise QualificationError(f"R1B cohort path is duplicated: {relative}")
        actual = sha256_file(ROOT / relative)
        is_exact_ck07_successor = (
            overlay_state == "worker_prequalification"
            and relative == CK07R1_PREPARATION_PATH
            and record.get("sha256") == overlay_predecessor
            and actual == overlay_successor
        )
        if actual != record.get("sha256") and not is_exact_ck07_successor:
            raise QualificationError(f"R1B authority digest drift: {relative}")
        selected_by_path[relative] = record
    if len(selected_by_path) != 23:
        raise QualificationError("R1B selected cohort must contain exactly 23 paths")

    for record in accepted_roots:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise QualificationError("R1C accepted root is malformed")
        relative = str(record["path"])
        accepted_digest = record.get("sha256")
        actual = sha256_file(ROOT / relative)
        if actual == accepted_digest:
            continue
        successor = selected_by_path.get(relative)
        if (
            successor is None
            or successor.get("predecessor_sha256") != accepted_digest
            or (
                successor.get("sha256") != actual
                and not (
                    overlay_state == "worker_prequalification"
                    and relative == CK07R1_PREPARATION_PATH
                    and successor.get("sha256") == overlay_predecessor
                    and actual == overlay_successor
                )
            )
        ):
            raise QualificationError(f"R1C root has unbound successor drift: {relative}")

    dependency_shas = {
        "CK-08R1A": _git_last_touch("config/agent-kernel/answer-semantics-v1.json"),
        "CK-08R1B": _git_last_touch(
            "src/codex_usage_tracker/agent_kernel/domain/plan_derivations_structural.py"
        ),
        "CK-08R1C": _git_last_touch("tests/agent_kernel/fixtures/independent/closure.py"),
    }
    if dependency_shas["CK-08R1C"] != independent.get("accepted_merge_sha"):
        raise QualificationError("R1C accepted merge identity is contradictory")

    return {
        "dependency_shas": dependency_shas,
        "authority_digests": authority_digests,
        "r1b_selected_paths": len(selected_by_path),
        "ck07r1_overlay_state": overlay_state,
    }


def _lane_closures() -> list[dict[str, Any]]:
    contract = _json(ANSWER_SEMANTICS)
    lanes = contract.get("lanes")
    if not isinstance(lanes, Mapping):
        raise QualificationError("answer semantics lane authority is missing")

    production_contract = lanes.get("production")
    independent_contract = lanes.get("independent")
    if not isinstance(production_contract, Mapping) or not isinstance(
        independent_contract, Mapping
    ):
        raise QualificationError("answer semantics lane authority is malformed")

    production = compute_closure(
        roots=(
            (PRODUCTION_HARNESS, "harness"),
            (PRODUCTION_CONSUMER, "consumer"),
            (PRODUCTION_ROOT, "r1b_root"),
            (PRODUCTION_DATA_SOURCE, "r1b_data_source"),
        ),
        root=ROOT,
    )
    production_checks = verify_closure(
        production,
        root=ROOT,
        required_roles=tuple(production_contract["required_root_roles"]),
    )

    independent = compute_closure(
        roots=(
            (INDEPENDENT_HARNESS, "harness"),
            (INDEPENDENT_CONSUMER, "consumer"),
        ),
        root=ROOT,
    )
    independent_checks = verify_closure(
        independent,
        root=ROOT,
        required_roles=tuple(independent_contract["required_root_roles"]),
        forbidden_modules=tuple(independent_contract["forbidden_module_prefixes"]),
        forbidden_roles=tuple(independent_contract["forbidden_overlap_roles"]),
    )

    grading_checks = {
        "sentinel_mutated": "baseline_answers_unchanged",
        "inaccessible": "baseline_answers_unchanged",
    }

    def lane_payload(
        name: str,
        manifest: Mapping[str, Any],
        checks: Mapping[str, bool],
    ) -> dict[str, Any]:
        root_by_role = {str(item["role"]): str(item["path"]) for item in manifest["roots"]}
        return {
            "lane": name,
            "harness": root_by_role["harness"],
            "consumer": root_by_role["consumer"],
            "roots": manifest["roots"],
            "transitive_local_imports": manifest["imports"],
            "closure_digest": manifest["closure_digest"],
            "closure_checks": dict(checks),
            "grading_checks": grading_checks,
        }

    return [
        lane_payload("production", production, production_checks),
        lane_payload("independent", independent, independent_checks),
    ]


def _catalog() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    catalog = _json(CATALOG)
    questions = catalog.get("questions")
    if not isinstance(questions, list):
        raise QualificationError("question catalog is malformed")
    by_id = {
        str(question["question_id"]): question
        for question in questions
        if isinstance(question, dict)
    }
    if len(by_id) != len(questions):
        raise QualificationError("question catalog identities are not unique")
    return catalog, by_id


def _query_service() -> QueryService:
    catalog = _json(CATALOG)
    operands = _json(ROOT / "config/agent-kernel/plan-operand-contract-v1.json")
    formulas = _json(ROOT / "config/agent-kernel/formula-contract-v1.json")
    selectors = _json(ROOT / "config/agent-kernel/selector-provenance-v1.json")
    return QueryService(
        build_registry(catalog, operands, formulas, selectors),
        operands,
        selectors,
        CursorCodec(_CURSOR_SECRET, clock=lambda: 500),
        clock=lambda: 500,
    )


def _query_request(
    case: Mapping[str, Any],
    question: Mapping[str, Any],
) -> QueryRequest:
    request = case["request"]
    limits = question["limits"]
    required = case["required_evidence"]
    return QueryRequest(
        question_id=str(case["question_id"]),
        plan_id=str(request["plan_id"]),
        plan_version=int(question["version"]),
        parameters=request["parameters"],
        gates=request["gates"],
        required_evidence=tuple(
            EvidenceSelection.from_mapping(item, index) for index, item in enumerate(required)
        ),
        page=QueryPage(limit=int(limits["maximum_rows"])),
    )


def _published_connection(
    case_root: Path,
    original: Mapping[str, Any],
) -> tuple[sqlite3.Connection, dict[str, Any]]:
    profile = original["source_profile"]
    mutation = original["semantic_mutation"]
    database_path = case_root / "database-v1.sqlite3"
    publish_structural_snapshot(
        case_root / "fixture",
        database_path,
        include_late_call=bool(profile["late_event"]),
        null_cached_tokens=bool(profile["missing_cached_input"]),
        variant_native_turn_id=str(mutation["native_turn_id"]),
    )
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    case = published_question_case(connection, original)
    connection.execute("PRAGMA query_only = ON")
    return connection, case


def _production_evaluate(
    connection: sqlite3.Connection,
    case: Mapping[str, Any],
    question: Mapping[str, Any],
) -> dict[str, Any]:
    if question.get("question_id") != case.get("question_id"):
        raise QualificationError("production question identity mismatch")
    try:
        return production_replay.evaluate_published_case(connection, case, question)
    except (RuntimeError, ValueError) as exc:
        raise QualificationError(f"production replay failed: {case['oracle_id']}") from exc


def _production_grade_fields(question: Mapping[str, Any]) -> dict[str, str]:
    answers = question.get("answers")
    fields = answers.get("fields") if isinstance(answers, Mapping) else None
    if not isinstance(fields, Mapping) or any(
        not isinstance(field, str) or not isinstance(grade, str) for field, grade in fields.items()
    ):
        raise QualificationError("production grading source is unavailable")
    return dict(fields)


def _evidence_projection(references: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "logical_id": item["logical_id"],
            "role": item["role"],
            "selector": item["selector"],
            "selector_kind": item["selector_kind"],
        }
        for item in references
    ]


def _collect_variants() -> list[dict[str, Any]]:
    global _QUERY_SERVICE_MATRIX

    catalog, questions = _catalog()
    scenarios = build_question_scenarios()
    cases = scenarios.get("cases")
    if not isinstance(cases, list) or len(cases) != 80:
        raise QualificationError("exactly 80 synthetic variants are required")
    independent_results = independent_semantic.evaluate_all(cases)

    admitted_plans = {
        str(question["plan_id"])
        for question in catalog["questions"]
        if question["stage"] in {"Foundation", "Cutover"}
    }
    if len(admitted_plans) != 21:
        raise QualificationError("R2 admitted plan frontier must contain 21 plans")

    service = _query_service()
    supported_variants = 0
    failed_closed: set[str] = set()
    variants: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ck08r1-") as temporary:
        temporary_root = Path(temporary)
        for index, (original, independent) in enumerate(
            zip(cases, independent_results, strict=True)
        ):
            if independent["oracle_id"] != original["oracle_id"]:
                raise QualificationError("independent variant order drift")
            connection, case = _published_connection(
                temporary_root / f"case-{index:02d}",
                original,
            )
            try:
                question = questions[str(case["question_id"])]
                production = _production_evaluate(connection, case, question)
                production_grades = _production_grade_fields(question)
                evidence = _evidence_projection(production["references"])
                matches = (
                    independent["rows"] == production["rows"]
                    and independent["field_grades"] == production_grades
                    and independent["ordered_evidence"] == evidence
                    and independent["provenance"] == production["references"]
                )
                if not matches:
                    raise QualificationError(f"answer comparison mismatch: {case['oracle_id']}")

                plan_id = str(case["request"]["plan_id"])
                if plan_id in SUPPORTED_DIRECT_PLAN_IDS:
                    service_result = service.execute(
                        connection,
                        QueryBatchRequest(
                            request_id=f"synthetic-{index}",
                            plans=(_query_request(case, question),),
                        ),
                    ).results[0]
                    if (
                        service_result.to_mapping()["rows"] != independent["rows"]
                        or dict(service_result.grades) != independent["field_grades"]
                        or [item.to_mapping() for item in service_result.evidence_selectors]
                        != independent["provenance"]
                    ):
                        raise QualificationError(
                            f"QueryService comparison mismatch: {case['oracle_id']}"
                        )
                    supported_variants += 1
                elif plan_id in admitted_plans and plan_id not in failed_closed:
                    try:
                        service.execute(
                            connection,
                            QueryBatchRequest(
                                request_id=f"gap-{index}",
                                plans=(_query_request(case, question),),
                            ),
                        )
                    except QueryServiceError as exc:
                        if "projection_added=false" not in str(exc):
                            raise QualificationError(
                                f"R2 gap is not fail closed: {plan_id}"
                            ) from exc
                        failed_closed.add(plan_id)
                    else:
                        raise QualificationError(
                            f"R2 residual plan unexpectedly executed: {plan_id}"
                        )
            finally:
                connection.close()

            variants.append(
                {
                    "oracle_id": independent["oracle_id"],
                    "request": independent["request"],
                    "independent_rows": independent["rows"],
                    "production_rows": production["rows"],
                    "independent_grades": independent["field_grades"],
                    "production_grades": production_grades,
                    "total_order": independent["total_order"],
                    "ordered_evidence": independent["ordered_evidence"],
                    "provenance": independent["provenance"],
                    "matches": True,
                }
            )

    expected_failed = admitted_plans - set(SUPPORTED_DIRECT_PLAN_IDS)
    if supported_variants != 4 or failed_closed != expected_failed:
        raise QualificationError("R2 QueryService support matrix drift")
    _QUERY_SERVICE_MATRIX = {
        "supported_plans": sorted(SUPPORTED_DIRECT_PLAN_IDS),
        "supported_variant_count": supported_variants,
        "failed_closed_plans": sorted(failed_closed),
        "projection_added": False,
        "query_only": True,
    }
    return variants


def last_query_service_matrix() -> dict[str, Any]:
    if _QUERY_SERVICE_MATRIX is None:
        raise QualificationError("QueryService matrix has not been collected")
    return copy.deepcopy(_QUERY_SERVICE_MATRIX)


def _grading_checks_all() -> None:
    global _GRADING_MATRIX

    catalog, questions = _catalog()
    cases = [copy.deepcopy(case) for case in independent_semantic.load_cases()]
    if len(cases) != 80:
        raise QualificationError("grading isolation requires all 80 variants")
    plan_ids = {str(case["request"]["plan_id"]) for case in cases}
    catalog_plans = {str(question["plan_id"]) for question in catalog["questions"]}
    if plan_ids != catalog_plans or len(plan_ids) != 40:
        raise QualificationError("grading isolation plan coverage drift")

    baseline_independent = independent_semantic.evaluate_all(cases)
    baseline_by_oracle = {str(item["oracle_id"]): item for item in baseline_independent}
    original_grades = independent_semantic._grades
    try:
        independent_semantic._grades = lambda _case, _rows: {"grading_sentinel": "mutated"}
        sentinel_independent = independent_semantic.evaluate_all(cases)
    finally:
        independent_semantic._grades = original_grades
    for candidate in sentinel_independent:
        baseline = baseline_by_oracle[str(candidate["oracle_id"])]
        candidate_answer = {key: value for key, value in candidate.items() if key != "field_grades"}
        baseline_answer = {key: value for key, value in baseline.items() if key != "field_grades"}
        if candidate_answer != baseline_answer:
            raise QualificationError("independent grading sentinel changed answers")

    class GradingUnavailable(RuntimeError):
        """Synthetic grading boundary is deliberately inaccessible."""

    captured_rows: dict[str, Any] = {}

    def inaccessible_grades(
        case: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
    ) -> dict[str, str]:
        captured_rows[str(case["oracle_id"])] = copy.deepcopy(rows)
        raise GradingUnavailable

    try:
        independent_semantic._grades = inaccessible_grades
        for case in cases:
            try:
                independent_semantic.evaluate_case(case)
            except GradingUnavailable:
                continue
            raise QualificationError("independent grading inaccessibility was not exercised")
    finally:
        independent_semantic._grades = original_grades
    for case in cases:
        oracle_id = str(case["oracle_id"])
        baseline = baseline_by_oracle[oracle_id]
        evidence, provenance = independent_semantic._evidence(case)
        inaccessible_answer = {
            "oracle_id": oracle_id,
            "request": independent_semantic._canonical(case["request"]),
            "rows": captured_rows[oracle_id],
            "total_order": independent_semantic._canonical(independent_semantic._total_order(case)),
            "ordered_evidence": evidence,
            "provenance": provenance,
        }
        baseline_answer = {key: value for key, value in baseline.items() if key != "field_grades"}
        if inaccessible_answer != baseline_answer:
            raise QualificationError("independent inaccessible grading changed answers")

    with tempfile.TemporaryDirectory(prefix="ck08r1-grading-") as temporary:
        temporary_root = Path(temporary)
        for index, original in enumerate(cases):
            connection, case = _published_connection(
                temporary_root / f"case-{index:02d}",
                original,
            )
            try:
                question = questions[str(case["question_id"])]
                baseline_production = _production_evaluate(connection, case, question)
                _production_grade_fields(question)

                mutated_question = copy.deepcopy(question)
                mutated_question["answers"]["fields"] = {
                    field: "mutated-grade" for field in mutated_question["answers"]["fields"]
                }
                sentinel_production = _production_evaluate(
                    connection,
                    case,
                    mutated_question,
                )
                _production_grade_fields(mutated_question)
                if sentinel_production != baseline_production:
                    raise QualificationError("production grading sentinel changed answers")

                inaccessible_question = {
                    key: value for key, value in question.items() if key != "answers"
                }
                inaccessible_production = _production_evaluate(
                    connection,
                    case,
                    inaccessible_question,
                )
                try:
                    _production_grade_fields(inaccessible_question)
                except QualificationError:
                    pass
                else:
                    raise QualificationError("production grading inaccessibility was not exercised")
                if inaccessible_production != baseline_production:
                    raise QualificationError("production inaccessible grading changed answers")
            finally:
                connection.close()

    _GRADING_MATRIX = {
        "independent": {"inaccessible": 80, "sentinel_mutated": 80},
        "production": {"inaccessible": 80, "sentinel_mutated": 80},
        "plan_count": len(plan_ids),
        "variant_count": len(cases),
    }


def last_grading_matrix() -> dict[str, Any]:
    if _GRADING_MATRIX is None:
        raise QualificationError("grading matrix has not been collected")
    return copy.deepcopy(_GRADING_MATRIX)


def _grading_checks() -> None:
    _grading_checks_all()
    return

    """
            mutated_question["answers"]["fields"] = {
                field: "mutated-grade" for field in mutated_question["answers"]["fields"]
            }
            if _production_evaluate(connection, case, mutated_question) != baseline_production:
                raise QualificationError("production grading sentinel changed answers")
            inaccessible_question = {
                key: value for key, value in question.items() if key != "answers"
            }
            if _production_evaluate(connection, case, inaccessible_question) != baseline_production:
                raise QualificationError("production inaccessible grading changed answers")
        finally:
            connection.close()
    """


def _mutate_database_call(
    connection: sqlite3.Connection,
    *,
    call_id: str,
) -> None:
    location = connection.execute(
        "SELECT storage_class FROM model_call_locations WHERE call_id = ?",
        (call_id,),
    ).fetchone()
    if location is None or str(location[0]) not in {"base", "tail"}:
        raise QualificationError("canonical mutation call is not published")
    table = "model_calls" if str(location[0]) == "base" else "model_call_tail"
    connection.execute("PRAGMA query_only = OFF")
    cursor = connection.execute(
        f"UPDATE {table} SET output_tokens = output_tokens + 1 WHERE call_id = ?",
        (call_id,),
    )
    if cursor.rowcount != 1:
        raise QualificationError("canonical mutation did not update exactly one call")
    connection.commit()
    connection.execute("PRAGMA query_only = ON")


def _mutation_checks() -> dict[str, dict[str, bool]]:
    _, questions = _catalog()
    original = next(
        copy.deepcopy(case)
        for case in independent_semantic.load_cases()
        if case["oracle_id"] == "oracle:q-rev-03:differing_coverage"
    )
    question = questions[str(original["question_id"])]
    baseline_independent = independent_semantic.evaluate_case(original)
    left_session = original["request"]["parameters"]["left_session"]
    target = next(
        fact
        for fact in original["declaration"]["facts"]
        if fact["relation"] == "canonical_call" and fact["values"]["session_id"] == left_session
    )
    call_id = str(target["values"]["call_id"])

    with tempfile.TemporaryDirectory(prefix="ck08r1-canonical-") as temporary:
        connection, case = _published_connection(Path(temporary), original)
        try:
            baseline_production = _production_evaluate(connection, case, question)
            mutated_case = copy.deepcopy(original)
            mutated_fact = next(
                fact
                for fact in mutated_case["declaration"]["facts"]
                if fact["relation"] == "canonical_call" and fact["values"]["call_id"] == call_id
            )
            mutated_fact["values"]["output_tokens"] += 1
            mutated_independent = independent_semantic.evaluate_case(mutated_case)
            _mutate_database_call(connection, call_id=call_id)
            mutated_production = _production_evaluate(connection, case, question)
        finally:
            connection.close()
    if (
        mutated_independent["rows"] == baseline_independent["rows"]
        or mutated_production["rows"] == baseline_production["rows"]
        or mutated_independent["rows"] != mutated_production["rows"]
    ):
        raise QualificationError("canonical fact mutation did not move both lanes")

    with tempfile.TemporaryDirectory(prefix="ck08r1-production-") as temporary:
        connection, case = _published_connection(Path(temporary), original)
        try:
            baseline_production = _production_evaluate(connection, case, question)
            original_evaluator = production_replay.database_replay.evaluate_plan

            def mutated_evaluator(*args: Any, **kwargs: Any) -> PlanEvaluation:
                evaluated = original_evaluator(*args, **kwargs)
                return PlanEvaluation(
                    evaluated.plan_id,
                    (*evaluated.rows, {"production_source_sentinel": True}),
                    evaluated.internal_results,
                )

            try:
                production_replay.database_replay.evaluate_plan = mutated_evaluator
                mutated_production = _production_evaluate(connection, case, question)
            finally:
                production_replay.database_replay.evaluate_plan = original_evaluator
        finally:
            connection.close()
    independent_after_production_mutation = independent_semantic.evaluate_case(original)
    if (
        mutated_production["rows"] == baseline_production["rows"]
        or independent_after_production_mutation != baseline_independent
    ):
        raise QualificationError("production source mutation did not remain independent")

    return {
        "canonical_fact": {
            "production_changed": True,
            "independent_changed": True,
        },
        "production_source": {
            "production_changed": True,
            "independent_unchanged": True,
        },
    }


def _validate(payload: Mapping[str, Any]) -> None:
    schema = _json(EVIDENCE_SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def qualify(*, output: Path | None = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Run gates in frozen order and optionally write one deterministic artifact."""

    identities = recompute_authority_identities()
    try:
        lanes = _lane_closures()
    except ClosureError as exc:
        raise QualificationError(f"closure authority failed: {exc}") from exc
    _grading_checks()
    variants = _collect_variants()
    mutation_results = _mutation_checks()

    payload = {
        "schema": SCHEMA_NAME,
        "dependency_shas": identities["dependency_shas"],
        "authority_digests": identities["authority_digests"],
        "gate_order": [
            "closure_membership",
            "closure_digest",
            "closure_accessibility",
            "grading_independence",
            "answer_comparison",
        ],
        "lanes": lanes,
        "variant_results": variants,
        "mutation_results": mutation_results,
        "superseded_evidence_links": [
            "docs/decisions/evidence/ck08/fact-backed-query-and-evidence-qualification.json",
            "docs/decisions/evidence/ck08r1b/answer-semantics-join-authority.json",
        ],
    }
    _validate(payload)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        encoded = canonical_json_bytes(payload)
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_output = Path(stream.name)
            stream.write(encoded)
        temporary_output.replace(output)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed artifact without replacing it",
    )
    args = parser.parse_args(argv)
    if args.check:
        payload = qualify(output=None)
        if not args.output.is_file():
            raise QualificationError(f"evidence artifact is missing: {args.output}")
        if args.output.read_bytes() != canonical_json_bytes(payload):
            raise QualificationError("committed evidence artifact is stale")
    else:
        qualify(output=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
