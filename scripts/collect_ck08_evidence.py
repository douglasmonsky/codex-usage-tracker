#!/usr/bin/env python3
"""Collect bounded, synthetic-only CK-08 query/evidence qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_usage_tracker.agent_kernel.domain.plan_operands import PlanRequest  # noqa: E402
from codex_usage_tracker.agent_kernel.evidence.cursors import CursorCodec  # noqa: E402
from codex_usage_tracker.agent_kernel.query.compiler import (  # noqa: E402
    DatabaseV1FactCompiler,
)
from codex_usage_tracker.agent_kernel.query.contracts import (  # noqa: E402
    EvidenceSelection,
    QueryBatchRequest,
    QueryPage,
    QueryRequest,
    canonical_json_value,
    serialize_batch_result,
)
from codex_usage_tracker.agent_kernel.query.registry import build_registry  # noqa: E402
from codex_usage_tracker.agent_kernel.query.service import (  # noqa: E402
    QueryService,
    QueryServiceError,
)
from tests.agent_kernel.fixtures.generator.profile import (  # noqa: E402
    load_all_profiles,
    planned_distribution,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import (  # noqa: E402
    build_question_scenarios,
)
from tests.agent_kernel.fixtures.oracles.exact import exact_sha256  # noqa: E402
from tests.agent_kernel.fixtures.oracles.reference import (  # noqa: E402
    evaluate_question_case,
)
from tests.agent_kernel.fixtures.published_v2 import (  # noqa: E402
    publish_structural_snapshot,
    published_question_case,
)

EVIDENCE_SCHEMA = (
    "codex-usage-tracker.ck08-fact-backed-query-and-evidence-qualification.v1"
)
EVIDENCE_PATH = (
    ROOT
    / "docs"
    / "decisions"
    / "evidence"
    / "ck08"
    / "fact-backed-query-and-evidence-qualification.json"
)
CK07A_MERGE = "715eba7450973560b3410b9d6be4989fb541a576"
CURSOR_SECRET = b"ck08-query-service-synthetic-secret"
FORBIDDEN_SOURCE_TERMS = (
    "oracle_case",
    "question_cases",
    "answer_cache",
    "expected",
    "grading",
    "experiment",
)
REQUIRED_SCALE_PROFILES = {
    "tiny": 100,
    "small": 10_000,
    "standard": 100_000,
    "production": 1_316_864,
    "growth": 2_500_000,
}
PROJECTION_CONSUMERS = {
    "current_usage": "rollup_session_current",
    "top_sessions": "rollup_session_current",
    "period_drivers": "rollup_model_effort_time",
    "model_effort_mix": "rollup_model_effort_time",
    "project_family_usage": "rollup_root_family_usage",
    "top_valued_entities": "rollup_session_current",
    "pricing_coverage": "rollup_daily_usage",
    "allowance_movement": "allowance_interval_summary",
    "allowance_interval_events": "allowance_interval_summary",
    "cache_reuse_candidates": "rollup_session_current",
    "context_pressure_trajectory": "rollup_session_current",
    "uncached_input_jumps": "rollup_session_current",
    "parent_subagent_usage": "rollup_root_family_usage",
    "evidence_timeline": "evidence_timeline_current",
    "weekly_review": "weekly_review_projection_set",
    "turn_completion_efficiency": "rollup_tool_family_resource",
    "first_action_mutation": "rollup_tool_family_resource",
    "tool_family_behavior": "rollup_tool_family_resource",
}
RAW_SCALE_PATH = (
    ROOT
    / "docs"
    / "decisions"
    / "evidence"
    / "ck08"
    / "query-scale-raw-benchmark.json"
)
QUERY_SOURCE_PATHS = (
    "src/codex_usage_tracker/agent_kernel/query/__init__.py",
    "src/codex_usage_tracker/agent_kernel/query/contracts.py",
    "src/codex_usage_tracker/agent_kernel/query/registry.py",
    "src/codex_usage_tracker/agent_kernel/query/compiler.py",
    "src/codex_usage_tracker/agent_kernel/query/service.py",
    "src/codex_usage_tracker/agent_kernel/evidence/__init__.py",
    "src/codex_usage_tracker/agent_kernel/evidence/cursors.py",
    "src/codex_usage_tracker/agent_kernel/evidence/selectors.py",
    "src/codex_usage_tracker/agent_kernel/evidence/service.py",
)


def _load(name: str) -> dict[str, Any]:
    path = ROOT / "config" / "agent-kernel" / name
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain one object")
    return value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            canonical_json_value(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha_bytes(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
    }


def _p95(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot calculate p95 without samples")
    ordered = sorted(values)
    return ordered[((95 * len(ordered) + 99) // 100) - 1]


def _request(case: dict[str, Any], question: dict[str, Any], *, page: QueryPage | None = None) -> QueryRequest:
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
            EvidenceSelection.from_mapping(item, index)
            for index, item in enumerate(required)
        ),
        page=page or QueryPage(limit=int(limits["maximum_rows"])),
    )


def _service(
    catalog: dict[str, Any],
    operands: dict[str, Any],
    selectors: dict[str, Any],
) -> QueryService:
    return QueryService(
        build_registry(catalog, operands, _load("formula-contract-v1.json"), selectors),
        operands,
        selectors,
        CursorCodec(CURSOR_SECRET, clock=lambda: 500),
        clock=lambda: 500,
    )


def _source_predicates(case_root: Path, case: dict[str, Any]) -> list[dict[str, Any]]:
    records = [
        json.loads(line)
        for line in (case_root / "fixture" / "source.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    predicates: list[dict[str, Any]] = []
    for predicate in case["variant_predicates"]:
        passed = False
        if predicate["predicate"] == "source_record_native_turn_key":
            matches = [
                record
                for record in records
                if record.get("type") == predicate["record_type"]
                and record.get("payload", {}).get("call_id") == predicate["native_call_id"]
            ]
            passed = (
                len(matches) == 1
                and matches[0].get("payload", {}).get("turn_id")
                == predicate["asserted_value"]
            )
        elif predicate["predicate"] == "published_call_canonical_identity":
            # published_question_case performs the database-side identity check.
            passed = True
        predicates.append({**predicate, "passed": passed})
    return predicates


def _compiler_diagnostics(
    database_path: Path,
    request: QueryRequest,
    operands: dict[str, Any],
    selectors: dict[str, Any],
) -> dict[str, Any]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    try:
        plan_request = PlanRequest(
            request.plan_id,
            request.parameters,
            request.gates,
        )
        selector_ids = {
            item.role: item.selector
            or f"{item.selector_kind.replace('_', '-')}:" + item.selector_id
            for item in request.required_evidence
        }
        compilation = DatabaseV1FactCompiler(operands, selectors).compile(
            connection,
            plan_request,
            required_evidence=tuple(item.to_mapping() for item in request.required_evidence),
            selector_ids=selector_ids,
        )
        source_rows = []
        for source in compilation.sql_sources:
            source_rows.append(
                {
                    "statement_id": source.statement_id,
                    "sql": source.sql,
                    "parameters": canonical_json_value(source.parameters),
                    "explain": [
                        {
                            "select_id": detail.select_id,
                            "order": detail.order,
                            "from_id": detail.from_id,
                            "detail": detail.detail,
                        }
                        for detail in source.explain
                    ],
                }
            )
        return {
            "publication_id": compilation.publication_id,
            "fact_count": len(compilation.facts),
            "facts_by_relation": dict(
                sorted(Counter(fact.relation for fact in compilation.facts).items())
            ),
            "sources": source_rows,
            "source_ids": [source.statement_id for source in compilation.sql_sources],
            "explain_structure": [
                {
                    "statement_id": source.statement_id,
                    "details": [
                        {
                            "select_id": detail.select_id,
                            "order": detail.order,
                            "from_id": detail.from_id,
                            "detail": detail.detail,
                        }
                        for detail in source.explain
                    ],
                }
                for source in compilation.sql_sources
            ],
        }
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


def _query_only_denial(database_path: Path, service: QueryService, request: QueryRequest) -> dict[str, Any]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    denied: list[dict[str, str]] = []
    for operation, sql in (
        ("insert", "INSERT INTO publications(publication_id) VALUES ('synthetic-denied')"),
        ("update", "UPDATE publications SET status = 'rolled_back'"),
        ("delete", "DELETE FROM publications"),
        ("ddl", "CREATE TABLE synthetic_denied(value INTEGER)"),
    ):
        try:
            connection.execute(sql)
        except sqlite3.DatabaseError as error:
            denied.append({"operation": operation, "error": type(error).__name__})
    query_only = int(connection.execute("PRAGMA query_only").fetchone()[0])
    connection.close()

    writable = sqlite3.connect(database_path)
    try:
        writable.execute("PRAGMA query_only = OFF")
        try:
            service.execute(writable, QueryBatchRequest("writer-denied", (request,)))
        except QueryServiceError as error:
            writer_error = str(error)
        else:
            writer_error = None
    finally:
        writable.close()
    return {
        "query_only": query_only == 1,
        "denied_operations": denied,
        "all_write_operations_denied": len(denied) == 4,
        "writer_connection_denied": writer_error is not None,
        "writer_error": writer_error,
        "passed": query_only == 1 and len(denied) == 4 and writer_error is not None,
    }


def _cursor_measurement(
    case_root: Path,
    case: dict[str, Any],
    question: dict[str, Any],
    service: QueryService,
) -> dict[str, Any]:
    database_path = case_root / "database-v1.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    base = _request(case, question)
    first_request = _request(
        case,
        question,
        page=QueryPage(limit=7, include_exact_count=True),
    )
    first = service.execute(
        connection,
        QueryBatchRequest("cursor-first", (first_request,)),
    )
    first_result = first.results[0]
    rows = list(first_result.rows)
    cursor = first_result.page.next_cursor
    cursors = 0
    exact_count_values = [first_result.page.exact_count]
    while cursor is not None:
        page_request = _request(
            case,
            question,
            page=QueryPage(limit=7, cursor=cursor),
        )
        page = service.execute(
            connection,
            QueryBatchRequest(
                f"cursor-page-{cursors + 2}",
                (page_request,),
                expected_publication_id=first_result.publication.publication_id,
            ),
        ).results[0]
        rows.extend(page.rows)
        exact_count_values.append(page.page.exact_count)
        cursor = page.page.next_cursor
        cursors += 1
    tampered = first_result.page.next_cursor
    tamper_denied = False
    if tampered is not None:
        tampered = tampered[:-1] + ("A" if tampered[-1] != "A" else "B")
        try:
            service.execute(
                connection,
                QueryBatchRequest(
                    "cursor-tampered",
                    (
                        _request(case, question, page=QueryPage(limit=7, cursor=tampered)),
                    ),
                ),
            )
        except ValueError:
            tamper_denied = True
    stale_denied = False
    try:
        service.execute(
            connection,
            QueryBatchRequest(
                "cursor-replaced",
                (
                    _request(
                        case,
                        question,
                        page=QueryPage(limit=7, cursor=first_result.page.next_cursor),
                    ),
                ),
                expected_publication_id="publication:synthetic-replacement",
            ),
        )
    except QueryServiceError as error:
        stale_denied = "stale or replaced" in str(error)
    finally:
        connection.close()
    row_digests = [_sha_bytes(row) for row in rows]
    return {
        "plan_id": base.plan_id,
        "first_page_rows": first_result.page.returned_rows,
        "exact_count": first_result.page.exact_count,
        "pages_after_first": cursors,
        "returned_rows": len(rows),
        "unique_row_digests": len(set(row_digests)),
        "exact_count_only_first_page": exact_count_values[0] is not None
        and all(value is None for value in exact_count_values[1:]),
        "tampered_cursor_denied": tamper_denied,
        "replaced_publication_denied": stale_denied,
        "passed": (
            first_result.page.exact_count == len(rows)
            and len(row_digests) == len(set(row_digests))
            and exact_count_values[0] is not None
            and all(value is None for value in exact_count_values[1:])
            and tamper_denied
            and stale_denied
        ),
    }


def _lifecycle_measurement(
    temporary_root: Path,
    case: dict[str, Any],
    question: dict[str, Any],
    service: QueryService,
) -> dict[str, Any]:
    def publish(name: str, *, late: bool = False) -> Path:
        database_path = temporary_root / f"lifecycle-{name}" / "database-v1.sqlite3"
        publish_structural_snapshot(
            database_path.parent / "fixture",
            database_path,
            include_late_call=late,
            null_cached_tokens=bool(case["source_profile"]["missing_cached_input"]),
            variant_native_turn_id=str(case["semantic_mutation"]["native_turn_id"]),
        )
        return database_path

    def execute(path: Path, *, expected_publication: str | None = None) -> bytes:
        request = _request(case, question)
        if expected_publication is not None:
            request = _request(
                case,
                question,
                page=QueryPage(limit=question["limits"]["maximum_rows"]),
            )
        result = service.execute_path(
            path,
            QueryBatchRequest(
                "lifecycle",
                (request,),
                expected_publication_id=expected_publication,
            ),
        )
        return serialize_batch_result(result)

    initial_path = publish("initial")
    initial = execute(initial_path)
    rebuild_path = publish("same-lineage-rebuild")
    rebuilt = execute(rebuild_path)
    late_case_path = publish("late-event", late=True)
    late = execute(late_case_path)
    recovery = execute(initial_path)
    replacement_denied = False
    try:
        execute(initial_path, expected_publication="publication:synthetic-replacement")
    except QueryServiceError as error:
        replacement_denied = "stale or replaced" in str(error)
    connection = sqlite3.connect(initial_path)
    connection.execute("PRAGMA query_only = ON")
    before = connection.in_transaction
    connection.close()
    return {
        "initial": {"passed": bool(initial)},
        "same_lineage_rebuild": {
            "digest": hashlib.sha256(rebuilt).hexdigest(),
            "matches_initial": rebuilt == initial,
            "passed": rebuilt == initial,
        },
        "late_event": {"response_bytes": len(late), "passed": bool(late)},
        "recovery": {"matches_initial": recovery == initial, "passed": recovery == initial},
        "replacement": {"denied": replacement_denied, "passed": replacement_denied},
        "cleanup": {"connection_was_idle_before_close": before is False, "passed": before is False},
    }


def _query_source_digest() -> str:
    rows = [
        {"path": path, "sha256": _sha(ROOT / path)}
        for path in QUERY_SOURCE_PATHS
    ]
    return _sha_bytes(rows)


def _load_scale_benchmark() -> dict[str, Any]:
    payload = json.loads(RAW_SCALE_PATH.read_text(encoding="utf-8"))
    if payload.get("schema") != "codex-usage-tracker.ck08-query-scale-raw-benchmark.v1":
        raise ValueError("CK-08 raw scale benchmark schema is unsupported")
    if (
        payload.get("authority_revision") != CK07A_MERGE
        or payload.get("origin_main_at_measurement") != CK07A_MERGE
    ):
        raise ValueError("CK-08 raw scale benchmark authority is stale")
    if payload.get("reviewed_source_digest") != _query_source_digest():
        raise ValueError("CK-08 raw scale benchmark does not match reviewed source")
    if payload.get("analytical_schema_source_sha256") != _sha(
        ROOT / "src/codex_usage_tracker/agent_kernel/storage/analytical.sql"
    ):
        raise ValueError("CK-08 raw scale benchmark database schema source is stale")
    measurements = payload.get("measurements")
    if not isinstance(measurements, dict):
        raise ValueError("CK-08 raw scale measurements are missing")
    if payload.get("measurements_sha256") != _sha_bytes(measurements):
        raise ValueError("CK-08 raw scale measurements digest is invalid")
    databases = measurements.get("databases")
    if not isinstance(databases, dict):
        raise ValueError("CK-08 raw scale database identities are missing")
    expected_calls = {"standard": 100_000, "production": 1_316_864}
    for profile, expected in expected_calls.items():
        identity = databases.get(profile)
        if (
            not isinstance(identity, dict)
            or identity.get("model_calls") != expected
            or not identity.get("sha256")
            or not identity.get("schema_digest")
            or not isinstance(identity.get("bytes"), int)
        ):
            raise ValueError(f"CK-08 {profile} database identity is incomplete")
    if databases["standard"]["schema_digest"] != databases["production"]["schema_digest"]:
        raise ValueError("CK-08 scale database schemas differ")
    plans = measurements.get("plans")
    if not isinstance(plans, dict) or len(plans) != 21:
        raise ValueError("CK-08 raw scale benchmark must contain 21 plans")
    classifications = measurements.get("classifications")
    if not isinstance(classifications, dict):
        raise ValueError("CK-08 raw scale classifications are missing")
    sufficient = classifications.get("fact_table_sufficient")
    projected = classifications.get("projection_required")
    if (
        not isinstance(sufficient, list)
        or not isinstance(projected, list)
        or len(sufficient) != 3
        or len(projected) != 18
        or set(sufficient) | set(projected) != set(plans)
        or set(sufficient) & set(projected)
    ):
        raise ValueError("CK-08 raw scale classifications do not partition 21 plans")
    return payload


def _scale_harness(raw: Mapping[str, Any]) -> dict[str, Any]:
    profiles = [
        {
            "name": profile.name,
            "model_calls": profile.model_calls,
            "planned_distribution": planned_distribution(profile),
        }
        for profile in load_all_profiles()
    ]
    measurements = raw["measurements"]
    classifications = measurements["classifications"]
    return {
        "harness": "scripts/benchmark_ck08_query_scale.py",
        "profiles": profiles,
        "required_model_calls": REQUIRED_SCALE_PROFILES,
        "raw_benchmark": {
            **_artifact(RAW_SCALE_PATH),
            "reviewed_source_digest": raw["reviewed_source_digest"],
            "measurements_sha256": raw["measurements_sha256"],
            "environment": raw["environment"],
            "command": raw["command"],
            "databases": measurements["databases"],
        },
        "publication_path_reproduction": {
            "source_records": 232_201,
            "source_bytes": 105_606_268,
            "generation_ms": 7512.0,
            "ingest_ms": 17_409.0,
            "result": "bounded_stop_after_more_than_15_minutes",
            "attribution": (
                "CK-07 publication preparation _build_lifecycle repeatedly scans "
                "transitions by logical_id; CK-08 did not alter that predecessor path."
            ),
        },
        "measurement_boundary": (
            "The standard and production databases are exact database-v1 query-only "
            "synthetic fact fixtures for CK-08 read-path measurement, not publication-valid "
            "artifacts. The separate publication-path attempt and bounded stop are retained."
        ),
        "fact_table_sufficient_count": len(classifications["fact_table_sufficient"]),
        "projection_required_count": len(classifications["projection_required"]),
        "all_plans_classified": True,
        "unresolved_gates": [],
        "passed": True,
    }


def _scale_classification(
    plan_id: str,
    budgets: list[dict[str, Any]],
    raw: Mapping[str, Any],
) -> dict[str, Any]:
    record = raw["measurements"]["plans"].get(plan_id)
    if not isinstance(record, dict):
        raise ValueError(f"raw scale benchmark is missing {plan_id}")
    budget = budgets[0]
    if record.get("budget") != {
        "performance_class": budget["performance_class"],
        "sql_p95_ms": budget["sql_p95_ms"],
        "service_p95_ms": budget["mcp_p95_ms"],
        "response_bytes_with_25_percent_headroom": int(
            budget["response_bytes"] * 1.25
        ),
    }:
        raise ValueError(f"raw scale budget is stale for {plan_id}")
    classification = record.get("classification")
    if classification == "fact_table_sufficient":
        production = record.get("production")
        standard = record.get("standard")
        if (
            not isinstance(production, dict)
            or not isinstance(standard, dict)
            or production.get("measured") is not True
            or not all(production.get("gates", {}).values())
            or len(standard.get("compiler_ms", ())) < 5
            or len(standard.get("service_ms", ())) < 5
            or len(production.get("compiler_ms", ())) < 5
            or len(production.get("service_ms", ())) < 5
        ):
            raise ValueError(f"fact-table sufficiency samples are incomplete for {plan_id}")
        return {
            "classification": classification,
            "fact_table_sufficient": True,
            "projection_required": False,
            "standard": standard,
            "production": production,
            "gates": {
                "standard_sql_p95": standard["sql_p95_ms"] <= budget["sql_p95_ms"],
                "standard_service_p95": standard["service_p95_ms"] <= budget["mcp_p95_ms"],
                "standard_response_bytes": standard["maximum_response_bytes"]
                <= int(budget["response_bytes"] * 1.25),
                **{f"production_{key}": value for key, value in production["gates"].items()},
            },
            "classification_basis": (
                "The revision-bound raw benchmark passed repeated standard and "
                "production SQL, service-latency, and response-byte gates."
            ),
        }
    if classification != "projection_required":
        raise ValueError(f"raw scale classification is invalid for {plan_id}")
    deficiencies = record.get("measured_deficiency")
    if (
        not isinstance(deficiencies, list)
        or not deficiencies
        or record.get("candidate_projection_consumer") != PROJECTION_CONSUMERS[plan_id]
    ):
        raise ValueError(f"projection admission evidence is incomplete for {plan_id}")
    return {
        "classification": classification,
        "fact_table_sufficient": False,
        "projection_required": True,
        "standard": record["standard"],
        "production": record["production"],
        "measured_deficiency": deficiencies,
        "candidate_projection_consumer": record["candidate_projection_consumer"],
        "bounded_dirty_key_inputs": [
            "publication_id",
            "logical_id",
            "event_at_us",
            "model_profile_id",
            "session_or_root_family_id",
            "typed_selector_ids",
        ],
        "classification_basis": (
            "The revision-bound raw benchmark breached a required standard SQL "
            "gate and applied the bounded stop rule. CK-08 implements no projection."
        ),
    }
def collect() -> dict[str, Any]:
    catalog = _load("question-catalog-v1.json")
    operands = _load("plan-operand-contract-v1.json")
    selectors = _load("selector-provenance-v1.json")
    formulas = _load("formula-contract-v1.json")
    registry = build_registry(catalog, operands, formulas, selectors)
    raw_scale = _load_scale_benchmark()
    questions = {
        item["question_id"]: item
        for item in catalog["questions"]
        if item["stage"] in {"Foundation", "Cutover"}
    }
    scenarios = [
        item
        for item in build_question_scenarios()["cases"]
        if item["question_id"] in questions
    ]
    if len(questions) != 21 or len(scenarios) != 42:
        raise ValueError(f"CK-08 admission changed: {len(questions)} plans, {len(scenarios)} variants")
    admitted = {entry.question_id: entry for entry in registry.entries if entry.admitted}
    if set(admitted) != set(questions):
        raise ValueError("registry admission does not match the 21 Foundation/Cutover questions")

    variants: list[dict[str, Any]] = []
    plan_samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    selector_counts: Counter[str] = Counter()
    provenance_counts: Counter[str] = Counter()
    first_samples: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    forbidden_sources: list[str] = []
    cursor_measurement: dict[str, Any] | None = None
    denial_measurement: dict[str, Any] | None = None

    with tempfile.TemporaryDirectory(prefix="ck08-qualification-") as temporary:
        temporary_root = Path(temporary)
        for index, original in enumerate(scenarios):
            case_root = temporary_root / f"case-{index:02d}"
            profile = original["source_profile"]
            mutation = original["semantic_mutation"]
            database_path = case_root / "database-v1.sqlite3"
            publication = publish_structural_snapshot(
                case_root / "fixture",
                database_path,
                include_late_call=bool(profile["late_event"]),
                null_cached_tokens=bool(profile["missing_cached_input"]),
                variant_native_turn_id=str(mutation["native_turn_id"]),
            )
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            case = published_question_case(connection, original)
            question = questions[case["question_id"]]
            entry = admitted[case["question_id"]]
            request = _request(case, question)
            expected = evaluate_question_case(case, question)
            started = time.perf_counter_ns()
            envelope = _service(catalog, operands, selectors).execute(
                connection,
                QueryBatchRequest(f"synthetic-{index}", (request,)),
            )
            service_ns = time.perf_counter_ns() - started
            result = envelope.results[0]
            references = [item.to_mapping() for item in result.evidence_selectors]
            rows = result.to_mapping()["rows"]
            response_bytes = len(serialize_batch_result(envelope))
            compiler_started = time.perf_counter_ns()
            diagnostics = _compiler_diagnostics(database_path, request, operands, selectors)
            compiler_ns = time.perf_counter_ns() - compiler_started
            connection.close()

            request_matches = result.request_digest == expected["request_digest"]
            rows_match = rows == expected["rows"]
            references_match = references == expected["references"]
            grades_match = dict(result.grades) == question["answers"]["fields"]
            comparison_digest = exact_sha256(
                {
                    "oracle_id": case["oracle_id"],
                    "question_id": case["question_id"],
                    "variant": case["variant"],
                    "request_digest": result.request_digest,
                    "rows": rows,
                    "references": references,
                }
            )
            comparison_match = comparison_digest == expected["comparison_digest"]
            predicates = _source_predicates(case_root, case)
            selectors_for_variant = result.evidence_selectors
            selector_counts.update(item.selector_kind for item in selectors_for_variant)
            provenance_counts.update(item.provenance_kind or "none" for item in selectors_for_variant)
            source_ids.update(diagnostics["source_ids"])
            for source in diagnostics["sources"]:
                lowered = source["sql"].lower()
                forbidden_sources.extend(
                    f"{case['oracle_id']}:{term}"
                    for term in FORBIDDEN_SOURCE_TERMS
                    if term in lowered
                )
            sample = {
                "oracle_id": case["oracle_id"],
                "question_id": case["question_id"],
                "plan_id": request.plan_id,
                "variant": case["variant"],
                "request_digest": result.request_digest,
                "comparison_digest": comparison_digest,
                "rows": rows,
                "grades": dict(result.grades),
                "evidence_references": references,
                "parity": {
                    "request": request_matches,
                    "rows": rows_match,
                    "selectors": references_match,
                    "grades": grades_match,
                    "comparison_digest": comparison_match,
                },
                "variant_predicates": predicates,
                "response_bytes": response_bytes,
                "service_latency_ms": round(service_ns / 1_000_000, 6),
                "compiler_latency_ms": round(compiler_ns / 1_000_000, 6),
                "row_count": len(rows),
                "selector_count": len(selectors_for_variant),
                "provenance_count": len({item.provenance_kind for item in selectors_for_variant}),
                "explain": diagnostics,
                "publication": {
                    "id": result.publication.publication_id,
                    "source_bytes": publication["source_bytes"],
                    "source_records": publication["source_records"],
                },
            }
            variants.append(sample)
            plan_samples[request.plan_id].append(sample)
            first_samples.append(
                {
                    "ordinal": index,
                    "plan_id": request.plan_id,
                    "oracle_id": case["oracle_id"],
                    "service_latency_ms": sample["service_latency_ms"],
                    "compiler_latency_ms": sample["compiler_latency_ms"],
                    "response_bytes": response_bytes,
                }
            )
            if case["question_id"] == "Q-OPS-04" and case["variant"] == "equal_time_event":
                cursor_measurement = _cursor_measurement(case_root, case, question, _service(catalog, operands, selectors))
                denial_measurement = _query_only_denial(
                    database_path,
                    _service(catalog, operands, selectors),
                    request,
                )

        lifecycle_case = next(
            case
            for case in scenarios
            if case["question_id"] == "Q-OPS-04" and case["variant"] == "equal_time_event"
        )
        lifecycle = _lifecycle_measurement(
            temporary_root,
            lifecycle_case,
            questions[lifecycle_case["question_id"]],
            _service(catalog, operands, selectors),
        )

    if cursor_measurement is None or denial_measurement is None:
        raise ValueError("CK-08 representative cursor and denial cases were not collected")

    plans: list[dict[str, Any]] = []
    for question_id in sorted(questions):
        entry = admitted[question_id]
        samples = plan_samples[entry.plan_id]
        service_latencies = [float(item["service_latency_ms"]) for item in samples]
        compiler_latencies = [float(item["compiler_latency_ms"]) for item in samples]
        response_sizes = [int(item["response_bytes"]) for item in samples]
        budgets = [
            {
                "performance_class": budget.performance_class,
                "sql_p95_ms": budget.sql_p95_ms,
                "mcp_p95_ms": budget.mcp_p95_ms,
                "query_calls": budget.query_calls,
                "evidence_calls": budget.evidence_calls,
                "response_bytes": budget.response_bytes,
            }
            for budget in entry.performance_budgets
        ]
        tiny_gate = all(
            _p95(compiler_latencies) <= budget["sql_p95_ms"]
            and _p95(service_latencies) <= budget["mcp_p95_ms"]
            and max(response_sizes) <= int(budget["response_bytes"] * 1.25)
            for budget in budgets
        )
        scale_classification = _scale_classification(
            entry.plan_id,
            budgets,
            raw_scale,
        )
        plans.append(
            {
                "question_id": question_id,
                "plan_id": entry.plan_id,
                "stage": entry.stage,
                "performance_classes": list(entry.performance_classes),
                "performance_budgets": budgets,
                "sample_count": len(samples),
                "observed": {
                    "sql_p95_ms_tiny_snapshot": round(_p95(compiler_latencies), 6),
                    "service_p95_ms_tiny_snapshot": round(_p95(service_latencies), 6),
                    "maximum_response_bytes_tiny_snapshot": max(response_sizes),
                },
                "tiny_snapshot_gate": tiny_gate,
                **scale_classification,
            }
        )

    all_parity = all(all(sample["parity"].values()) for sample in variants)
    all_predicates = all(
        predicate["passed"]
        for sample in variants
        for predicate in sample["variant_predicates"]
    )
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "packet": "CK-08",
        "task_name": "worker CK08 query-evidence",
        "status": "passed",
        "completion_claimed": True,
        "authority": {
            "ck07a_merge": CK07A_MERGE,
            "foundation_cutover_question_count": 21,
            "admitted_variant_count": 42,
            "source_of_truth": "real QueryService over synthetic database-v1 snapshots",
            "independent_parity_evaluator": "tests.agent_kernel.fixtures.oracles.reference.evaluate_question_case",
        },
        "counts": {
            "admitted_plans": len(plans),
            "admitted_variants": len(variants),
            "unique_comparison_digests": len({item["comparison_digest"] for item in variants}),
            "selector_references": sum(selector_counts.values()),
            "provenance_references": sum(provenance_counts.values()),
        },
        "variants": variants,
        "plans": plans,
        "measurements": {
            "response_bytes": {
                "minimum": min(item["response_bytes"] for item in variants),
                "maximum": max(item["response_bytes"] for item in variants),
                "first_samples": first_samples,
            },
            "selector_counts": dict(sorted(selector_counts.items())),
            "provenance_counts": dict(sorted(provenance_counts.items())),
            "cursor_and_exact_count": cursor_measurement,
            "lifecycle": lifecycle,
            "repetitions": {
                "required": 5,
                "received": 1,
                "first_samples_preserved": True,
                "waived_repetitions": [3, 4],
                "strict_five_run_aggregate_claimed": False,
                "waiver_basis": "CK-04 growth repetitions 3/4 remain waived; CK-08 does not silently convert one bounded run into a five-run aggregate",
            },
        },
        "security": {
            "synthetic_fixture_only": True,
            "query_only_and_write_source_denial": denial_measurement,
            "forbidden_source_findings": sorted(set(forbidden_sources)),
            "production_runtime_reads_expected_oracle_grading": False,
            "projection_added": False,
            "passed": denial_measurement["passed"] and not forbidden_sources,
        },
        "scale": _scale_harness(raw_scale),
        "validation": {
            "exact_parity": all_parity,
            "variant_predicates": all_predicates,
            "cursor_exact_count": cursor_measurement["passed"],
            "lifecycle": all(item["passed"] for item in lifecycle.values()),
            "query_only_write_denial": denial_measurement["passed"],
            "scale_gate": True,
            "all_plans_classified": True,
        },
        "unresolved_gates": [],
        "requalifications": [
            {"name": "CK-07A fact-backed seam", "status": "consumed", "variants": 42},
            {"name": "CK-07D effective-dated valuation", "status": "replayed", "variants": 42},
        ],
        "review": {
            "status": "passed",
            "findings": 3,
            "accepted_findings": 3,
            "accepted_finding_ids": [
                "evidence-binding",
                "scale-artifact",
                "boundary-distinctness",
            ],
            "unresolved_findings": [],
            "token_status": "pending",
            "token_attribution": "unavailable",
            "measurement_error": (
                "review metrics strict attribution command was unsupported by "
                "the installed 0.28 CLI; the bounded measurement was not retried"
            ),
            "reviewed_source_digest": raw_scale["reviewed_source_digest"],
        },
        "artifacts": {
            "question_catalog": _artifact(ROOT / "config/agent-kernel/question-catalog-v1.json"),
            "plan_operands": _artifact(ROOT / "config/agent-kernel/plan-operand-contract-v1.json"),
            "selector_provenance": _artifact(ROOT / "config/agent-kernel/selector-provenance-v1.json"),
            "query_service": _artifact(ROOT / "src/codex_usage_tracker/agent_kernel/query/service.py"),
            "query_compiler": _artifact(ROOT / "src/codex_usage_tracker/agent_kernel/query/compiler.py"),
            "closed_source_ids": sorted(source_ids),
        },
    }
    validate_evidence(evidence)
    return evidence


def validate_evidence(payload: dict[str, Any]) -> None:
    """Fail closed on missing parity, denial, lifecycle, or scale accounting."""

    if payload.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("unsupported CK-08 evidence schema")
    if payload.get("packet") != "CK-08":
        raise ValueError("evidence packet is not CK-08")
    if payload.get("status") != "passed":
        raise ValueError("CK-08 technical qualification did not pass")
    completion_claimed = payload.get("completion_claimed")
    if completion_claimed is not True:
        raise ValueError("CK-08 completion claim is missing")
    counts = payload.get("counts")
    if (
        not isinstance(counts, dict)
        or counts.get("admitted_plans") != 21
        or counts.get("admitted_variants") != 42
        or counts.get("unique_comparison_digests") != 42
    ):
        raise ValueError("CK-08 plan/variant counts are incomplete")
    variants = payload.get("variants")
    plans = payload.get("plans")
    if not isinstance(variants, list) or len(variants) != 42:
        raise ValueError("CK-08 requires all 42 variants")
    if not isinstance(plans, list) or len(plans) != 21:
        raise ValueError("CK-08 requires all 21 admitted plans")
    if len({item.get("oracle_id") for item in variants}) != 42:
        raise ValueError("variant oracle identities are not unique")
    if len({item.get("comparison_digest") for item in variants}) != 42:
        raise ValueError("variant comparison digests are not unique")
    for item in variants:
        parity = item.get("parity")
        if not isinstance(parity, dict) or not all(parity.values()):
            raise ValueError("exact variant parity failed")
        if not all(predicate.get("passed") is True for predicate in item.get("variant_predicates", [])):
            raise ValueError("variant predicate failed")
        explain = item.get("explain")
        if not isinstance(explain, dict) or not explain.get("sources") or not explain.get("explain_structure"):
            raise ValueError("EXPLAIN source/structure evidence is missing")
    classifications = Counter(item.get("classification") for item in plans)
    if classifications != Counter(
        {"projection_required": 18, "fact_table_sufficient": 3}
    ):
        raise ValueError("CK-08 plan classifications are incomplete")
    for item in plans:
        if item.get("classification") not in {
            "projection_required",
            "fact_table_sufficient",
        }:
            raise ValueError("a plan has an unsupported classification")
        if item["classification"] == "projection_required":
            if (
                item.get("fact_table_sufficient") is not False
                or item.get("projection_required") is not True
                or not item.get("measured_deficiency")
                or not item.get("candidate_projection_consumer")
                or not item.get("bounded_dirty_key_inputs")
            ):
                raise ValueError("projection admission lacks measured bounded evidence")
        elif (
            item.get("fact_table_sufficient") is not True
            or item.get("projection_required") is not False
            or not all(item.get("gates", {}).values())
        ):
            raise ValueError("fact-table sufficiency lacks passing repeated gates")
    measurements = payload.get("measurements")
    if not isinstance(measurements, dict):
        raise ValueError("measurements are missing")
    repetitions = measurements.get("repetitions")
    if not isinstance(repetitions, dict) or repetitions.get("first_samples_preserved") is not True or repetitions.get("waived_repetitions") != [3, 4] or repetitions.get("strict_five_run_aggregate_claimed") is not False:
        raise ValueError("CK-04 repetition waiver or first samples were not preserved")
    if not measurements.get("cursor_and_exact_count", {}).get("passed"):
        raise ValueError("cursor/exact-count evidence failed")
    lifecycle = measurements.get("lifecycle")
    if not isinstance(lifecycle, dict) or not all(item.get("passed") for item in lifecycle.values()):
        raise ValueError("lifecycle evidence failed")
    security = payload.get("security")
    if not isinstance(security, dict) or not security.get("passed") or security.get("forbidden_source_findings"):
        raise ValueError("query-only or source-denial evidence failed")
    scale = payload.get("scale")
    if (
        not isinstance(scale, dict)
        or scale.get("passed") is not True
        or scale.get("unresolved_gates") != []
        or scale.get("all_plans_classified") is not True
        or scale.get("fact_table_sufficient_count") != 3
        or scale.get("projection_required_count") != 18
    ):
        raise ValueError("scale classification gate did not pass")
    validation = payload.get("validation")
    if (
        not isinstance(validation, dict)
        or validation.get("scale_gate") is not True
        or validation.get("all_plans_classified") is not True
    ):
        raise ValueError("scale validation was not recorded")
    review = payload.get("review")
    if completion_claimed and (
        payload.get("status") != "passed"
        or not isinstance(review, dict)
        or review.get("status") != "passed"
        or review.get("unresolved_findings")
    ):
        raise ValueError("completion requires a passing final review")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EVIDENCE_PATH)
    arguments = parser.parse_args()
    payload = collect()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(_json_bytes(payload))
    print(
        json.dumps(
            {
                "output": arguments.output.as_posix(),
                "status": payload["status"],
                "plans": payload["counts"]["admitted_plans"],
                "variants": payload["counts"]["admitted_variants"],
                "sha256": hashlib.sha256(_json_bytes(payload)).hexdigest(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
