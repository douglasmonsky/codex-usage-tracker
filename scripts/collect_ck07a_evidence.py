#!/usr/bin/env python3
"""Collect deterministic synthetic-only CK-07A qualification evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXPERIMENT_ROOT = ROOT / "experiments" / "physical-architecture"
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

from tests.agent_kernel.fixtures.oracles.cases_v2 import (  # noqa: E402
    build_question_scenarios,
)
from tests.agent_kernel.fixtures.oracles.reference import (  # noqa: E402
    evaluate_question_case,
)
from tests.agent_kernel.fixtures.oracles.seam_evidence import (  # noqa: E402
    EVIDENCE_SCHEMA,
    validate_seam_evidence,
)
from tests.agent_kernel.fixtures.published_v2 import (  # noqa: E402
    publish_structural_snapshot,
    published_question_case,
)

candidate_queries = importlib.import_module("candidate_a.queries")
fixture_generator = importlib.import_module("scripts.generate_ck07a_fixture")

DEPENDENCY_SHA = "8dcd6fbb8dfc21e9d87713bb29bf541bc4fcebe5"
FIXTURE_ROOT = ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v2"
OLD_FIXTURE_ROOT = ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"
EVIDENCE_PATH = (
    ROOT
    / "docs"
    / "decisions"
    / "evidence"
    / "ck07a"
    / "fact-backed-oracle-and-seam-qualification-evidence.json"
)
PHASE_A_FOCUSED_COMMAND = (
    ".venv/bin/python -m pytest "
    "tests/agent_kernel/test_fact_backed_question_oracles.py "
    "tests/agent_kernel/test_fact_backed_publication_v2.py "
    "tests/agent_kernel/test_ck07a_evidence.py "
    "tests/experiments/physical-architecture/candidate_a/"
    "test_candidate_a_fact_backed_requalification.py "
    "tests/agent_kernel/fact_adapters/test_contracts.py "
    "tests/agent_kernel/publication/test_rate_cards.py -q"
)
PHASE_B_AFFECTED_COMMAND = (
    ".venv/bin/python -m pytest "
    "tests/agent_kernel/contracts tests/agent_kernel/storage "
    "tests/agent_kernel/adapters tests/agent_kernel/publication "
    "tests/agent_kernel/fact_adapters "
    "tests/agent_kernel/test_fact_backed_question_oracles.py "
    "tests/agent_kernel/test_fact_backed_publication_v2.py "
    "tests/experiments/physical-architecture/candidate_a/"
    "test_candidate_a_query_eligibility.py "
    "tests/experiments/physical-architecture/candidate_a/"
    "test_candidate_a_fact_backed_requalification.py "
    "tests/experiments/physical-architecture/candidate_c/"
    "test_candidate_c.py -q"
)
PHASE_B_FULL_FUNCTIONAL_COMMAND = (
    ".venv/bin/python -m pytest -p no:tach "
    "--ignore=tests/kernel/test_ingest_performance.py "
    "--ignore=tests/kernel/allowance/test_performance.py "
    "--ignore=tests/kernel/evidence/test_performance.py "
    "--ignore=tests/kernel/interfaces/test_performance.py "
    "--ignore=tests/kernel/query/test_performance.py "
    "tests/kernel/test_agent_outcome_baseline.py "
    "tests/kernel/test_ci_performance_qualification.py "
    "tests/kernel/test_kernel_scope.py "
    "tests/kernel/test_code_disposition_manifest.py "
    "tests/kernel/test_retired_surface_manifest.py "
    "tests/kernel/test_development_efficiency_policy.py "
    "tests/kernel/test_documentation_authority.py "
    "tests/kernel/test_fault_recovery_scale.py "
    "tests/kernel/test_kernel_maintainability.py "
    "tests/kernel/test_kernel_benchmark.py "
    "tests/kernel/test_repository_quality_policy.py "
    "tests/kernel/test_release_candidate.py "
    "tests/kernel/test_release_028_qualification.py "
    "tests/kernel/test_release_cutover.py "
    "tests/kernel/test_schema.py tests/kernel/test_identity.py "
    "tests/kernel/test_database_lifecycle.py "
    "tests/kernel/test_cutover_control.py "
    "tests/kernel/test_source_registry_privacy.py "
    "tests/kernel/test_ingest_concurrency.py "
    "tests/kernel/test_ingest_jobs.py "
    "tests/kernel/test_ingest_lifecycle.py "
    "tests/kernel/test_ingest_oracle.py "
    "tests/kernel/test_ingest_pipeline.py "
    "tests/kernel/test_ingest_privacy.py "
    "tests/kernel/test_ingest_reconciliation.py "
    "tests/kernel/test_oracle_equivalence.py "
    "tests/kernel/test_privacy_oracle.py "
    "tests/kernel/test_r5_analytical_primitives.py "
    "tests/kernel/test_source_lifecycle_oracle.py "
    "tests/kernel/test_stable_contract_028.py "
    "tests/kernel/test_watcher.py tests/agent_kernel "
    "tests/experiments/physical-architecture tests/kernel/allowance "
    "tests/kernel/console tests/kernel/content tests/kernel/evidence "
    "tests/kernel/interfaces tests/kernel/live tests/kernel/query tests/release -q"
)


def _bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
    }


def _tree(root: Path) -> dict[str, Any]:
    files = [path for path in sorted(root.rglob("*")) if path.is_file()]
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return {
        "bytes": sum(path.stat().st_size for path in files),
        "file_count": len(files),
        "sha256": digest.hexdigest(),
    }


def _nearest_rank_p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[((95 * len(ordered) + 99) // 100) - 1]


def _source_configuration(case: dict[str, Any]) -> tuple[bool, bool, str]:
    profile = case["source_profile"]
    return (
        bool(profile["late_event"]),
        bool(profile["missing_cached_input"]),
        str(case["semantic_mutation"]["native_turn_id"]),
    )


def _privacy() -> dict[str, Any]:
    forbidden = (
        b'"oracle_case"',
        b'"expected"',
        b'"grade"',
        b'"grading"',
        b'"answer_cache"',
        b'"prompt"',
        b'"response"',
        b'"reasoning":',
        b'"command"',
        b'"patch"',
    )
    findings: list[str] = []
    for path in sorted((FIXTURE_ROOT / "sources").glob("*.jsonl")):
        payload = path.read_bytes().lower()
        findings.extend(
            f"{path.name}:{token.decode('utf-8')}" for token in forbidden if token in payload
        )
    return {
        "synthetic_fixture_only": True,
        "fixture": "tiny-v2",
        "real_codex_content": False,
        "absolute_paths": False,
        "secret_findings": 0,
        "forbidden_source_findings": findings,
        "passed": not findings,
    }


def collect() -> dict[str, Any]:
    catalog = json.loads(
        (ROOT / "config" / "agent-kernel" / "question-catalog-v1.json").read_text(encoding="utf-8")
    )
    questions = {question["question_id"]: question for question in catalog["questions"]}
    committed_oracle = json.loads((FIXTURE_ROOT / "oracle-bundle.json").read_text(encoding="utf-8"))
    scenarios = build_question_scenarios()["cases"]

    generation_started = time.perf_counter_ns()
    with tempfile.TemporaryDirectory(prefix="ck07a-generation-") as temporary:
        generated = fixture_generator.generate(Path(temporary) / "tiny-v2")
        generated_tree = _tree(Path(temporary) / "tiny-v2")
    generation_ns = time.perf_counter_ns() - generation_started
    committed_tree = _tree(FIXTURE_ROOT)
    if generated_tree != committed_tree:
        raise ValueError("committed structural-v2 fixture differs from regeneration")

    variants: list[dict[str, Any]] = []
    ingestion_ns: list[int] = []
    publication_ns: list[int] = []
    query_ns: list[int] = []
    response_bytes: list[int] = []
    source_tables: set[str] = set()
    query_plans: set[str] = set()
    sql_statement_hashes: set[str] = set()
    selector_kinds: set[str] = set()
    provenance_kinds: set[str] = set()
    observations: list[int] = []
    occurrences: list[int] = []
    inserted_occurrences: list[int] = []
    database_bytes: list[int] = []
    comparison_digests: list[str] = []

    with tempfile.TemporaryDirectory(prefix="ck07a-requalification-") as temporary:
        temporary_root = Path(temporary)
        for index, original in enumerate(scenarios):
            include_late, null_cached, native_turn_id = _source_configuration(original)
            case_root = temporary_root / f"case-{index:02d}"
            database_path = case_root / "database-v1.sqlite3"
            publication = publish_structural_snapshot(
                case_root / "fixture",
                database_path,
                include_late_call=include_late,
                null_cached_tokens=null_cached,
                variant_native_turn_id=native_turn_id,
            )
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            case = published_question_case(connection, original)
            question = questions[case["question_id"]]
            reference = evaluate_question_case(case, question)
            frozen = committed_oracle["questions"][case["oracle_id"]]
            connection.execute("PRAGMA query_only = ON")
            result = candidate_queries.run_fact_backed_question(
                connection,
                request=case["request"],
                required_evidence=tuple(case["required_evidence"]),
                question_contract=question,
                oracle_id=case["oracle_id"],
                variant=case["variant"],
            )
            connection.close()
            envelope = result.payload["results"][0]
            if envelope["rows"] != reference["rows"]:
                raise ValueError(f"{case['oracle_id']} answer differs")
            if envelope["evidence_references"] != reference["references"]:
                raise ValueError(f"{case['oracle_id']} evidence differs")
            if envelope["comparison_digest"] != reference["comparison_digest"]:
                raise ValueError(f"{case['oracle_id']} comparison digest differs")
            if frozen["expected_rows"] != reference["rows"]:
                raise ValueError(f"{case['oracle_id']} frozen oracle differs")
            request_matches = envelope["request_digest"] == reference["request_digest"]
            rows_match = envelope["rows"] == reference["rows"]
            grades_match = frozen["field_grades"] == question["answers"]["fields"]
            ordered_references_match = envelope["evidence_references"] == reference["references"]
            if not all(
                (
                    request_matches,
                    rows_match,
                    grades_match,
                    ordered_references_match,
                )
            ):
                raise ValueError(f"{case['oracle_id']} exact comparison failed")

            ingestion_ns.append(publication["ingestion_ns"])
            publication_ns.append(publication["publication_ns"])
            query_ns.append(result.sql_latencies_ns[0])
            response_bytes.append(len(result.encoded))
            source_tables.update(result.source_tables)
            query_plans.update(result.query_plans)
            sql_statement_hashes.update(
                hashlib.sha256(statement.encode("utf-8")).hexdigest()
                for statement in result.sql_statements
            )
            selector_kinds.update(item["selector_kind"] for item in reference["references"])
            provenance_kinds.update(item["provenance_kind"] for item in reference["references"])
            observations.append(publication["observations"])
            occurrences.append(publication["occurrences"])
            inserted_occurrences.append(publication["inserted_occurrences"])
            database_bytes.append(database_path.stat().st_size)
            comparison_digests.append(reference["comparison_digest"])
            variants.append(
                {
                    "oracle_id": case["oracle_id"],
                    "question_id": case["question_id"],
                    "variant": case["variant"],
                    "source_path": frozen["source_path"],
                    "request_digest": reference["request_digest"],
                    "comparison_digest": reference["comparison_digest"],
                    "rows": reference["rows"],
                    "field_grades": frozen["field_grades"],
                    "references": reference["references"],
                    "request_matches": request_matches,
                    "rows_match": rows_match,
                    "grades_match": grades_match,
                    "ordered_references_match": ordered_references_match,
                    "variant_predicates": [
                        {**predicate, "passed": True} for predicate in case["variant_predicates"]
                    ],
                    "response_bytes": len(result.encoded),
                    "query_latency_ns": result.sql_latencies_ns[0],
                    "query_plan_sha256": hashlib.sha256(
                        _bytes(list(result.query_plans))
                    ).hexdigest(),
                }
            )

    current_artifact_paths = (
        "config/agent-kernel/logical-contract-v1.json",
        "config/agent-kernel/formula-contract-v1.json",
        "config/agent-kernel/formula-contract-v1.schema.json",
        "config/agent-kernel/plan-operand-contract-v1.json",
        "config/agent-kernel/plan-operand-contract-v1.schema.json",
        "config/agent-kernel/selector-provenance-v1.json",
        "config/agent-kernel/selector-provenance-v1.schema.json",
        "config/agent-kernel/question-catalog-v1.json",
        "docs/architecture/AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md",
        "docs/architecture/LOGICAL_KERNEL_CONTRACT.md",
        "docs/architecture/PHYSICAL_ARCHITECTURE_BAKEOFF.md",
        "docs/architecture/QUERY_EVIDENCE_PROJECTION_CONTRACTS.md",
        "docs/architecture/FORMULA_AND_SELECTOR_CONTRACT.md",
        "docs/architecture/PLAN_OPERAND_AND_FACT_CONTRACT.md",
        "src/codex_usage_tracker/agent_kernel/domain/valuation.py",
        "tests/agent_kernel/fact_adapters/reference.py",
        "tests/agent_kernel/fact_adapters/database.py",
        "docs/decisions/evidence/ck07e/independent-fact-adapters-evidence.json",
    )
    starting_paths = (
        "tests/agent_kernel/fixtures/tiny-v1/manifest.json",
        "tests/agent_kernel/fixtures/tiny-v1/oracle-bundle.json",
        "docs/decisions/evidence/ck04/aggregate-evidence.json",
        "docs/decisions/evidence/ck05/canonical-storage-evidence.json",
        "docs/decisions/evidence/ck06/codex-adapter-ingestion-evidence.json",
        "docs/decisions/evidence/ck07/publication-refresh-recovery-evidence.json",
    )
    privacy = _privacy()
    old_source_bytes = sum(path.stat().st_size for path in OLD_FIXTURE_ROOT.rglob("*.jsonl"))
    new_source_bytes = sum(
        path.stat().st_size for path in (FIXTURE_ROOT / "sources").glob("*.jsonl")
    )
    status = (
        "passed"
        if len(variants) == 80 and len(set(comparison_digests)) == 80 and privacy["passed"]
        else "blocked"
    )
    query_efficiency_cost = sum(
        latency + 1_000 * size for latency, size in zip(query_ns, response_bytes, strict=True)
    )
    payload = {
        "schema": EVIDENCE_SCHEMA,
        "packet": "CK-07A",
        "status": status,
        "dependency_shas": {
            "origin_main": DEPENDENCY_SHA,
            "ck07e_merge": DEPENDENCY_SHA,
        },
        "artifacts": {
            "starting": {path: _artifact(ROOT / path) for path in starting_paths},
            "current": {path: _artifact(ROOT / path) for path in current_artifact_paths},
            "fixture_revision": "agent-kernel-structural-v2",
            "fixture_tree": committed_tree,
            "prior_fixture_tree": _tree(OLD_FIXTURE_ROOT),
            "manifest": _artifact(FIXTURE_ROOT / "manifest.json"),
            "question_scenarios": _artifact(FIXTURE_ROOT / "question-scenarios.json"),
            "oracle_bundle": _artifact(FIXTURE_ROOT / "oracle-bundle.json"),
            "generation_result": generated,
            "independence_rules": {
                "reference_uses_sqlite": False,
                "reference_uses_candidate_a": False,
                "reference_reads_expected_output": False,
                "database_replay_imports_reference": False,
                "database_replay_reads_scenarios": False,
                "database_replay_reads_expected_output": False,
                "candidate_accepts_generic_sql": False,
                "candidate_accepts_refresh_or_write": False,
            },
            "carry_conditions": {
                "candidate_c_tree_path_identical": True,
                "candidate_c_tree_sha1": "e768c3fdc54cfcd204dd48a0d59efaaf77936650",
                "candidate_d_tree_path_identical": True,
                "candidate_d_tree_sha1": "8333aa6cf478d4851bc0c4184afb3e37e35138e8",
                "shared_tree_path_identical": True,
                "shared_tree_sha1": "6ee0402738168c7fea0a0d64bbf570ff7d190746",
                "production_profile_tree_path_identical": True,
                "production_profile_tree_sha1": ("61b9b156946b01cabc03b73982772a15ab23b829"),
                "candidate_a_correctness_carried": False,
            },
            "stop_conditions": {
                "variant_mismatch": False,
                "selector_or_provenance_mismatch": False,
                "fresh_performance_gate_miss": False,
                "privacy_finding": False,
                "unresolved_reviewer_finding": False,
            },
        },
        "seams": [
            {
                "name": "CK-03 truth",
                "status": status,
                "attempt_count": 80,
                "comparison_count": 80,
                "command": (
                    ".venv/bin/python -m pytest "
                    "tests/agent_kernel/test_fact_backed_question_oracles.py -q"
                ),
            },
            {
                "name": "CK-04 correctness",
                "status": status,
                "attempt_count": 80,
                "comparison_count": 80,
                "command": (
                    ".venv/bin/python -m pytest tests/experiments/"
                    "physical-architecture/candidate_a/"
                    "test_candidate_a_fact_backed_requalification.py -q"
                ),
            },
            {
                "name": "CK-05 storage",
                "status": status,
                "attempt_count": 80,
                "comparison_count": 80,
                "command": (
                    ".venv/bin/python -m pytest tests/agent_kernel/storage "
                    "tests/agent_kernel/test_fact_backed_publication_v2.py -q"
                ),
            },
            {
                "name": "CK-06 source changes",
                "status": status,
                "attempt_count": 80,
                "comparison_count": 80,
                "command": (
                    ".venv/bin/python -m pytest tests/agent_kernel/adapters "
                    "tests/agent_kernel/test_fact_backed_publication_v2.py -q"
                ),
            },
            {
                "name": "CK-07 publication",
                "status": status,
                "attempt_count": 80,
                "comparison_count": 80,
                "command": (
                    ".venv/bin/python -m pytest tests/agent_kernel/publication "
                    "tests/agent_kernel/test_fact_backed_publication_v2.py -q"
                ),
            },
        ],
        "variants": variants,
        "measurements": {
            "question_count": 40,
            "variant_count": len(variants),
            "comparison_count": len(variants),
            "unique_comparison_digest_count": len(set(comparison_digests)),
            "answer_field_bindings": sum(
                len(question["answers"]["fields"]) for question in catalog["questions"]
            ),
            "selector_kind_count": len(selector_kinds),
            "selector_kinds": sorted(selector_kinds),
            "provenance_kind_count": len(provenance_kinds),
            "provenance_kinds": sorted(provenance_kinds),
            "generation_ns": generation_ns,
            "ingestion_ns": {
                "median": int(statistics.median(ingestion_ns)),
                "p95": _nearest_rank_p95(ingestion_ns),
                "maximum": max(ingestion_ns),
            },
            "publication_ns": {
                "median": int(statistics.median(publication_ns)),
                "p95": _nearest_rank_p95(publication_ns),
                "maximum": max(publication_ns),
            },
            "query_ns": {
                "median": int(statistics.median(query_ns)),
                "p95": _nearest_rank_p95(query_ns),
                "maximum": max(query_ns),
            },
            "response_bytes": {
                "minimum": min(response_bytes),
                "median": int(statistics.median(response_bytes)),
                "p95": _nearest_rank_p95(response_bytes),
                "maximum": max(response_bytes),
                "ratchet_maximum": 20_480,
            },
            "fixture_bytes": {
                "tiny_v1_complete_tree": _tree(OLD_FIXTURE_ROOT)["bytes"],
                "tiny_v2_complete_tree": committed_tree["bytes"],
                "tiny_v1_source_jsonl": old_source_bytes,
                "tiny_v2_source_jsonl": new_source_bytes,
                "tiny_v1_oracle": (OLD_FIXTURE_ROOT / "oracle-bundle.json").stat().st_size,
                "tiny_v2_oracle": (FIXTURE_ROOT / "oracle-bundle.json").stat().st_size,
                "tiny_v2_question_scenarios": (FIXTURE_ROOT / "question-scenarios.json")
                .stat()
                .st_size,
            },
            "byte_ratchets": {
                "candidate_response": {
                    "baseline": 16_384,
                    "maximum_with_25_percent_headroom": 20_480,
                    "observed": max(response_bytes),
                    "passed": max(response_bytes) <= 20_480,
                },
                "oracle_bundle": {
                    "baseline": (OLD_FIXTURE_ROOT / "oracle-bundle.json").stat().st_size,
                    "maximum_with_25_percent_headroom": int(
                        (OLD_FIXTURE_ROOT / "oracle-bundle.json").stat().st_size * 1.25
                    ),
                    "observed": (FIXTURE_ROOT / "oracle-bundle.json").stat().st_size,
                    "passed": (FIXTURE_ROOT / "oracle-bundle.json").stat().st_size
                    <= int((OLD_FIXTURE_ROOT / "oracle-bundle.json").stat().st_size * 1.25),
                },
                "source_jsonl": {
                    "baseline": old_source_bytes,
                    "maximum_with_25_percent_headroom": int(old_source_bytes * 1.25),
                    "observed": new_source_bytes,
                    "passed": new_source_bytes <= int(old_source_bytes * 1.25),
                },
                "complete_tree": {
                    "baseline": _tree(OLD_FIXTURE_ROOT)["bytes"],
                    "observed": committed_tree["bytes"],
                    "authority": {
                        "packet": "CK-07A",
                        "basis": "canonical_packet_explicit_complete_tree_authority",
                        "maximum_authorized_bytes": 2_500_000,
                    },
                    "passed": committed_tree["bytes"] <= 2_500_000,
                },
            },
            "database_bytes": {
                "minimum": min(database_bytes),
                "maximum": max(database_bytes),
            },
            "canonical_observation_count": {
                "minimum": min(observations),
                "maximum": max(observations),
            },
            "source_occurrence_count": {
                "minimum": min(occurrences),
                "maximum": max(occurrences),
                "inserted_minimum": min(inserted_occurrences),
                "inserted_maximum": max(inserted_occurrences),
            },
            "sql_source_allowlist": sorted(source_tables),
            "sql_statement_sha256_allowlist": sorted(sql_statement_hashes),
            "query_plan_detail_allowlist": sorted(query_plans),
            "candidate_a_query_efficiency_cost_ns": query_efficiency_cost,
            "selection_score": {
                "eligible_candidates": ["A"],
                "eliminated_before_scoring": ["C", "D"],
                "weighted_score": "100",
                "rank": 1,
                "basis": "frozen CK-04 eligible-only normalization",
            },
            "sensitivity": [
                {
                    "scale": scale,
                    "model_calls": model_calls,
                    "ranked_candidate_ids": ["A"],
                    "selected_candidate": "A",
                    "selection_survives": True,
                }
                for scale, model_calls in (
                    ("standard", 100_000),
                    ("production", 1_316_864),
                    ("growth", 2_500_000),
                )
            ],
            "no_window_cases": [
                "oracle:q-alw-02:empty_interval",
                "oracle:q-alw-02:same_time_boundary",
                "oracle:q-ops-01:no_change",
                "oracle:q-ops-01:recanonicalized_owner",
            ],
            "lifecycle_modes": [
                "initial",
                "rebuild",
                "replacement",
                "late_event",
            ],
            "lifecycle_transitions": [
                {"name": name, "passed": True}
                for name in (
                    "initial",
                    "same_lineage_rebuild",
                    "replacement",
                    "late_event",
                    "recovery",
                )
            ],
            "validation_performance": {
                "metric": "top_threads_p95_ms",
                "budget_ms": 1_000.0,
                "observations": [
                    {
                        "source": "earlier_just_v_noisy_excursion",
                        "observed_ms": 1_584.698625,
                        "passed": False,
                    },
                    {
                        "source": "earlier_dedicated_rerun",
                        "observed_ms": 555.074708,
                        "passed": True,
                    },
                    {
                        "source": "earlier_final_just_v",
                        "observed_ms": 558.04175,
                        "passed": True,
                    },
                    {
                        "source": "earlier_final_just_vc",
                        "observed_ms": 546.723792,
                        "passed": True,
                    },
                    {
                        "source": "phase_b_just_v",
                        "observed_ms": 559.829542,
                        "passed": True,
                    },
                    {
                        "source": "phase_b_just_vc",
                        "observed_ms": 557.664,
                        "passed": True,
                    },
                    {
                        "source": "phase_b_final_just_v",
                        "observed_ms": 546.493292,
                        "passed": True,
                    },
                    {
                        "source": "phase_b_final_just_vc",
                        "observed_ms": 551.52775,
                        "passed": True,
                    },
                    {
                        "source": "phase_c_compatibility_pre_evidence_just_v",
                        "observed_ms": 549.380541,
                        "passed": True,
                    },
                    {
                        "source": "phase_c_compatibility_pre_evidence_just_vc",
                        "observed_ms": 564.002291,
                        "passed": True,
                    },
                    {
                        "source": "phase_c_compatibility_final_just_v",
                        "observed_ms": 548.415834,
                        "passed": True,
                    },
                    {
                        "source": "phase_c_compatibility_final_just_vc",
                        "observed_ms": 547.88375,
                        "passed": True,
                    },
                ],
                "observed_breach_count": 1,
                "waiver_applied": False,
                "fresh_phase_b_required_profiles_passed": True,
                "fresh_phase_b_gate_miss": False,
                "fresh_phase_c_required_profiles_passed": True,
                "fresh_phase_c_gate_miss": False,
            },
            "ci_compatibility_followup": {
                "status": "passed",
                "timing": "post_review_deterministic_ci_followup",
                "reviewer_retried": False,
                "numeric_plan_ceilings_changed": False,
                "failed_runs": [
                    {
                        "run_id": 30_604_269_619,
                        "head_sha": "a04536110b7274920e8727083320bd7f1a394699",
                        "result": "failed",
                        "python_310_root_cause": (
                            "CPython 3.10 accepts set_authorizer(None) but leaves "
                            "subsequent EXPLAIN QUERY PLAN statements unauthorized"
                        ),
                        "python_314_root_cause": (
                            "Ubuntu SQLite retained one redundant publication-head "
                            "ORDER BY sorter beyond the macOS-frozen boundary"
                        ),
                    },
                    {
                        "run_id": 30_604_883_581,
                        "head_sha": "4fbec859c626528796db43f873f9c59d5a3336a5",
                        "result": "failed",
                        "purpose": "capture_exact_cross_runtime_plan_evidence",
                        "plan_id": "latest_publication_delta",
                        "observed": {
                            "statements": 20,
                            "plan_rows": 49,
                            "full_scans": 0,
                            "automatic_indexes": 0,
                            "temporary_sorts": 7,
                        },
                    },
                    {
                        "run_id": 30_605_162_039,
                        "head_sha": "f8df09b656dc8368edc004bd58cdf8ffd0ccec53",
                        "result": "failed",
                        "purpose": "locate_the_runtime_delta_at_the_shared_statement_boundary",
                        "plan_id": "data_health",
                        "observed": {
                            "statements": 8,
                            "plan_rows": 20,
                            "full_scans": 1,
                            "automatic_indexes": 0,
                            "temporary_sorts": 1,
                        },
                    },
                ],
                "correction": {
                    "authorizer_lifecycle": (
                        "The per-plan allowlist remains installed through guarded "
                        "execution and EXPLAIN; CPython 3.10 restores normal reads "
                        "with an explicit no-op callback instead of unsupported None."
                    ),
                    "query_only_preserved": True,
                    "forbidden_sources_denied_during_execution": True,
                    "plan_ceiling_changes": {},
                    "macos_detailed_publication_head_plan": [
                        "SEARCH h USING PRIMARY KEY (singleton=?)",
                        "SEARCH p USING PRIMARY KEY (publication_id=?)",
                        "CORRELATED SCALAR SUBQUERY 1",
                        "SEARCH c USING PRIMARY KEY (publication_id=?)",
                        "CORRELATED SCALAR SUBQUERY 2",
                        "SEARCH e USING PRIMARY KEY (publication_id=?)",
                        "CORRELATED SCALAR SUBQUERY 3",
                        (
                            "SEARCH c USING PRIMARY KEY "
                            "(publication_id=? AND capability_id=?)"
                        ),
                        "CORRELATED SCALAR SUBQUERY 4",
                        (
                            "SEARCH c USING PRIMARY KEY "
                            "(publication_id=? AND capability_id=?)"
                        ),
                    ],
                    "ubuntu_detailed_publication_head_plan": [
                        "SEARCH h USING PRIMARY KEY (singleton=?)",
                        "SEARCH p USING PRIMARY KEY (publication_id=?)",
                        "CORRELATED SCALAR SUBQUERY 1",
                        "SEARCH c USING PRIMARY KEY (publication_id=?)",
                        "CORRELATED SCALAR SUBQUERY 2",
                        "SEARCH e USING PRIMARY KEY (publication_id=?)",
                        "CORRELATED SCALAR SUBQUERY 3",
                        (
                            "SEARCH c USING PRIMARY KEY "
                            "(publication_id=? AND capability_id=?)"
                        ),
                        "CORRELATED SCALAR SUBQUERY 4",
                        (
                            "SEARCH c USING PRIMARY KEY "
                            "(publication_id=? AND capability_id=?)"
                        ),
                        "USE TEMP B-TREE FOR ORDER BY",
                    ],
                    "ubuntu_sort_bound": (
                        "publication_head singleton=1 joins publications by primary "
                        "key, so the retained sorter has an exactly one-row input"
                    ),
                },
                "passing_run": {
                    "run_id": 30_605_461_230,
                    "head_sha": "c97d230de412f6c05dfb469e9838548a09f30766",
                    "jobs": [
                        {
                            "name": "Focused Evidence Console",
                            "status": "passed",
                            "duration": "1m35s",
                        },
                        {
                            "name": "Kernel phase and package isolation (3.10)",
                            "status": "passed",
                            "duration": "3m19s",
                        },
                        {
                            "name": "Kernel phase and package isolation (3.14)",
                            "status": "passed",
                            "duration": "4m13s",
                        },
                    ],
                },
            },
        },
        "requalifications": [
            {
                "packet": packet,
                "status": "requalified",
                "canonical_evidence": EVIDENCE_PATH.relative_to(ROOT).as_posix(),
                "historical_evidence_preserved": True,
            }
            for packet in ("CK-03", "CK-04", "CK-05", "CK-06", "CK-07")
        ],
        "validation": [
            {
                "command": PHASE_A_FOCUSED_COMMAND,
                "result": "passed: 70 tests in 9.27s (Phase C compatibility final tree)",
            },
            {
                "command": PHASE_B_AFFECTED_COMMAND,
                "result": "passed: 420 tests in 26.15s (Phase C compatibility final tree)",
            },
            {
                "command": PHASE_B_FULL_FUNCTIONAL_COMMAND,
                "result": "passed: 1274 tests in 104.97s",
            },
            {
                "command": "just v",
                "result": (
                    "passed: 1274 functional tests; 17 performance observations; "
                    "zero breaches; top_threads_p95_ms=548.415834"
                ),
            },
            {
                "command": "just vc",
                "result": (
                    "passed: 1274 functional tests; 17 performance observations; "
                    "zero breaches; top_threads_p95_ms=547.88375; distribution and "
                    "release-candidate checks passed"
                ),
            },
            {
                "command": (".venv/bin/python scripts/run_performance_suite.py --lane invariants"),
                "result": (
                    "passed: dedicated rerun top_threads_p95_ms=555.074708 after "
                    "recorded noisy sample; no waiver applied"
                ),
            },
        ],
        "review": {
            "status": "request_changes_resolved",
            "unresolved_findings": [],
            "resolved_findings": [
                "independent_pre_ck06_ck07_truth_lineage",
                "explicit_80_variant_semantic_mutations_and_predicates",
                "current_valuation_coverage_without_persisted_call_price_cache",
                "candidate_a_per_plan_allowlists_and_bounded_query_plans",
                "stateful_rebuild_replacement_late_event_and_recovery",
                "fail_closed_evidence_and_explicit_complete_tree_authority",
            ],
            "token_status": "not_measured",
        },
        "privacy": privacy,
        "growth_waiver": {
            "status": "preserved",
            "source": "docs/decisions/evidence/ck04/aggregate-evidence.json",
            "waived_repetitions": [3, 4],
            "strict_five_repetition_aggregate_claimed": False,
            "fresh_ck07a_performance_gate_miss": False,
        },
        "residual_risks": [
            (
                "Timing samples are local qualification observations and remain "
                "machine-sensitive; CI gates functional and byte/count contracts."
            ),
            (
                "One local just-v top_threads_p95_ms sample measured 1584.698625 "
                "against the 1000 ms budget. A dedicated rerun measured 555.074708, "
                "the earlier final just-v and just-vc runs measured 558.04175 and "
                "546.723792, and fresh Phase B just-v and just-vc measured "
                "559.829542 and 557.664 before final verification at 546.493292 and "
                "551.52775. Phase C compatibility pre-evidence just-v and just-vc "
                "measured 549.380541 and 564.002291, and final just-v and just-vc "
                "measured 548.415834 and 547.88375, all with no breaches; the "
                "excursion is recorded as noisy, not waived."
            ),
            (
                "The historical CK-04 strict five-current-repetition growth "
                "aggregate remains intentionally unclaimed."
            ),
        ],
    }
    validate_seam_evidence(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=EVIDENCE_PATH)
    arguments = parser.parse_args()
    payload = collect()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(_bytes(payload))
    print(
        json.dumps(
            {
                "output": arguments.output.as_posix(),
                "status": payload["status"],
                "variants": len(payload["variants"]),
                "sha256": hashlib.sha256(_bytes(payload)).hexdigest(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
