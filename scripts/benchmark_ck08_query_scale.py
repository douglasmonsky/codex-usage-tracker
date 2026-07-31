#!/usr/bin/env python3
"""Measure CK-08 named plans on exact synthetic database-v1 scale fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_usage_tracker.agent_kernel.domain.plan_operands import PlanRequest  # noqa: E402
from codex_usage_tracker.agent_kernel.query.compiler import (  # noqa: E402
    DatabaseV1FactCompiler,
)
from codex_usage_tracker.agent_kernel.query.contracts import (  # noqa: E402
    QueryBatchRequest,
    serialize_batch_result,
)
from codex_usage_tracker.agent_kernel.query.registry import build_registry  # noqa: E402
from scripts.collect_ck08_evidence import (  # noqa: E402
    CK07A_MERGE,
    PROJECTION_CONSUMERS,
    _json_bytes,
    _load,
    _p95,
    _request,
    _service,
    _sha_bytes,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import (  # noqa: E402
    build_question_scenarios,
)

SCHEMA = "codex-usage-tracker.ck08-query-scale-raw-benchmark.v1"
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "decisions"
    / "evidence"
    / "ck08"
    / "query-scale-raw-benchmark.json"
)
SOURCE_PATHS = (
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


def source_digest() -> str:
    rows = [
        {"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
        for path in SOURCE_PATHS
    ]
    return _sha_bytes(rows)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _database_identity(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    try:
        model_calls = int(
            connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
        )
        schema_rows = connection.execute(
            """SELECT type, name, tbl_name, sql
                 FROM sqlite_schema
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name"""
        ).fetchall()
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()
    return {
        "path_basename": path.parent.name + "/" + path.name,
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "model_calls": model_calls,
        "user_version": user_version,
        "schema_digest": _sha_bytes(schema_rows),
    }


def _compile_once(
    connection: sqlite3.Connection,
    compiler: DatabaseV1FactCompiler,
    request: Any,
) -> tuple[float, int, int]:
    selector_ids = {
        item.role: item.selector
        or f"{item.selector_kind.replace('_', '-')}:{item.selector_id}"
        for item in request.required_evidence
    }
    connection.execute("BEGIN")
    started = time.perf_counter_ns()
    try:
        result = compiler.compile(
            connection,
            PlanRequest(request.plan_id, request.parameters, request.gates),
            required_evidence=tuple(
                item.to_mapping() for item in request.required_evidence
            ),
            selector_ids=selector_ids,
        )
    finally:
        connection.rollback()
    return (
        round((time.perf_counter_ns() - started) / 1_000_000, 6),
        len(result.facts),
        len(result.sql_sources),
    )


def _service_once(
    connection: sqlite3.Connection,
    service: Any,
    request: Any,
    request_id: str,
) -> tuple[float, int, int]:
    started = time.perf_counter_ns()
    result = service.execute(
        connection,
        QueryBatchRequest(request_id, (request,)),
    )
    elapsed = round((time.perf_counter_ns() - started) / 1_000_000, 6)
    return elapsed, len(serialize_batch_result(result)), len(result.results[0].rows)


def _measure(
    standard_path: Path,
    production_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = _load("question-catalog-v1.json")
    operands = _load("plan-operand-contract-v1.json")
    formulas = _load("formula-contract-v1.json")
    selectors = _load("selector-provenance-v1.json")
    registry = build_registry(catalog, operands, formulas, selectors)
    entries = {entry.question_id: entry for entry in registry.entries if entry.admitted}
    questions = {
        item["question_id"]: item
        for item in catalog["questions"]
        if item["stage"] in {"Foundation", "Cutover"}
    }
    cases: dict[str, dict[str, Any]] = {}
    for case in build_question_scenarios()["cases"]:
        if case["question_id"] in questions:
            cases.setdefault(case["question_id"], case)
    if set(cases) != set(entries):
        raise ValueError("scale benchmark does not cover the admitted registry")

    compiler = DatabaseV1FactCompiler(operands, selectors)
    service = _service(catalog, operands, selectors)
    standard = sqlite3.connect(standard_path)
    standard.row_factory = sqlite3.Row
    standard.execute("PRAGMA query_only = ON")
    plans: dict[str, dict[str, Any]] = {}
    try:
        for question_id in sorted(entries):
            entry = entries[question_id]
            request = _request(cases[question_id], questions[question_id])
            budget = entry.performance_budgets[0]
            first_ms, fact_count, source_count = _compile_once(
                standard, compiler, request
            )
            compiler_samples = [first_ms]
            irrecoverable = first_ms > max(1000.0, budget.sql_p95_ms * 5.0)
            if not irrecoverable:
                for _ in range(20):
                    sample, _, _ = _compile_once(standard, compiler, request)
                    compiler_samples.append(sample)
            sql_p95 = _p95(compiler_samples)
            record: dict[str, Any] = {
                "question_id": question_id,
                "plan_id": entry.plan_id,
                "budget": {
                    "performance_class": budget.performance_class,
                    "sql_p95_ms": budget.sql_p95_ms,
                    "service_p95_ms": budget.mcp_p95_ms,
                    "response_bytes_with_25_percent_headroom": int(
                        budget.response_bytes * 1.25
                    ),
                },
                "standard": {
                    "compiler_ms": compiler_samples,
                    "sql_p95_ms": round(sql_p95, 6),
                    "fact_count": fact_count,
                    "sql_source_count": source_count,
                    "bounded_stop_after_irrecoverable_sql_breach": irrecoverable,
                },
            }
            if sql_p95 > budget.sql_p95_ms:
                record.update(
                    {
                        "classification": "projection_required",
                        "measured_deficiency": [
                            f"standard SQL p95 {sql_p95:.6f} ms > "
                            f"{budget.sql_p95_ms} ms"
                        ],
                        "candidate_projection_consumer": PROJECTION_CONSUMERS[
                            entry.plan_id
                        ],
                    }
                )
                plans[entry.plan_id] = record
                continue

            service_samples: list[float] = []
            response_sizes: list[int] = []
            row_counts: list[int] = []
            for repetition in range(21):
                elapsed, response_bytes, row_count = _service_once(
                    standard,
                    service,
                    request,
                    f"standard-{question_id}-{repetition:02d}",
                )
                service_samples.append(elapsed)
                response_sizes.append(response_bytes)
                row_counts.append(row_count)
            service_p95 = _p95(service_samples)
            maximum_bytes = max(response_sizes)
            deficiencies = []
            if service_p95 > budget.mcp_p95_ms:
                deficiencies.append(
                    f"standard service p95 {service_p95:.6f} ms > "
                    f"{budget.mcp_p95_ms} ms"
                )
            byte_budget = int(budget.response_bytes * 1.25)
            if maximum_bytes > byte_budget:
                deficiencies.append(
                    f"standard response {maximum_bytes} bytes > {byte_budget} bytes"
                )
            record["standard"].update(
                {
                    "service_ms": service_samples,
                    "service_p95_ms": round(service_p95, 6),
                    "response_bytes": response_sizes,
                    "maximum_response_bytes": maximum_bytes,
                    "row_counts": row_counts,
                }
            )
            if deficiencies:
                record.update(
                    {
                        "classification": "projection_required",
                        "measured_deficiency": deficiencies,
                        "candidate_projection_consumer": PROJECTION_CONSUMERS[
                            entry.plan_id
                        ],
                    }
                )
            else:
                record["classification"] = "fact_table_sufficient"
            plans[entry.plan_id] = record
    finally:
        standard.close()

    production = sqlite3.connect(production_path)
    production.row_factory = sqlite3.Row
    production.execute("PRAGMA query_only = ON")
    try:
        for plan_id, record in plans.items():
            if record["classification"] != "fact_table_sufficient":
                record["production"] = {
                    "measured": False,
                    "reason": "standard required SQL gate already breached",
                }
                continue
            question_id = record["question_id"]
            request = _request(cases[question_id], questions[question_id])
            compiler_samples = []
            service_samples = []
            response_sizes = []
            row_counts = []
            for repetition in range(5):
                elapsed, _, _ = _compile_once(production, compiler, request)
                compiler_samples.append(elapsed)
                elapsed, response_bytes, row_count = _service_once(
                    production,
                    service,
                    request,
                    f"production-{question_id}-{repetition}",
                )
                service_samples.append(elapsed)
                response_sizes.append(response_bytes)
                row_counts.append(row_count)
            budget = record["budget"]
            gates = {
                "sql_p95": _p95(compiler_samples) <= budget["sql_p95_ms"],
                "service_p95": _p95(service_samples)
                <= budget["service_p95_ms"],
                "response_bytes": max(response_sizes)
                <= budget["response_bytes_with_25_percent_headroom"],
            }
            if not all(gates.values()):
                raise ValueError(f"production gate failed for {plan_id}: {gates}")
            record["production"] = {
                "measured": True,
                "compiler_ms": compiler_samples,
                "sql_p95_ms": round(_p95(compiler_samples), 6),
                "service_ms": service_samples,
                "service_p95_ms": round(_p95(service_samples), 6),
                "response_bytes": response_sizes,
                "maximum_response_bytes": max(response_sizes),
                "row_counts": row_counts,
                "gates": gates,
            }
    finally:
        production.close()
    return plans, {
        "fact_table_sufficient": sorted(
            plan_id
            for plan_id, record in plans.items()
            if record["classification"] == "fact_table_sufficient"
        ),
        "projection_required": sorted(
            plan_id
            for plan_id, record in plans.items()
            if record["classification"] == "projection_required"
        ),
    }


def collect(standard_path: Path, production_path: Path) -> dict[str, Any]:
    standard_identity = _database_identity(standard_path)
    production_identity = _database_identity(production_path)
    plans, classifications = _measure(standard_path, production_path)
    measurements = {
        "databases": {
            "standard": standard_identity,
            "production": production_identity,
        },
        "plans": plans,
        "classifications": classifications,
    }
    return {
        "schema": SCHEMA,
        "authority_revision": CK07A_MERGE,
        "origin_main_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "origin/main"],
            cwd=ROOT,
            text=True,
        ).strip(),
        "reviewed_source_digest": source_digest(),
        "analytical_schema_source_sha256": _file_sha256(
            ROOT / "src/codex_usage_tracker/agent_kernel/storage/analytical.sql"
        ),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "clock": "time.perf_counter_ns",
            "profiled": False,
        },
        "command": (
            ".venv/bin/python scripts/benchmark_ck08_query_scale.py "
            "--standard-db <standard-database-v1.sqlite3> "
            "--production-db <production-database-v1.sqlite3>"
        ),
        "measurements": measurements,
        "measurements_sha256": _sha_bytes(measurements),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standard-db", required=True, type=Path)
    parser.add_argument("--production-db", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    payload = collect(arguments.standard_db, arguments.production_db)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(_json_bytes(payload))
    print(
        json.dumps(
            {
                "output": arguments.output.as_posix(),
                "source_digest": payload["reviewed_source_digest"],
                "measurements_sha256": payload["measurements_sha256"],
                "classifications": payload["measurements"]["classifications"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
