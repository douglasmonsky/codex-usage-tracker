#!/usr/bin/env python3
"""Generate the compact, synthetic-only CK-07A structural-v2 fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.agent_kernel.fact_adapters.support import plan_contract  # noqa: E402
from tests.agent_kernel.fixtures.oracles.cases_v2 import (  # noqa: E402
    FIXTURE_REVISION,
    SCENARIO_SCHEMA,
    build_question_scenarios,
)
from tests.agent_kernel.fixtures.oracles.exact import (  # noqa: E402
    exact_sha256,
    normalize_exact,
)
from tests.agent_kernel.fixtures.oracles.reference import (  # noqa: E402
    evaluate_question_case,
)
from tests.agent_kernel.fixtures.published_v2 import (  # noqa: E402
    publish_structural_snapshot,
    published_question_case,
    structural_records,
)

ORACLE_SCHEMA = "codex-usage-tracker.synthetic-oracle-bundle.v2"


def _bytes(value: Any) -> bytes:
    normalized = normalize_exact(value)
    if isinstance(value, dict):
        normalized = {key: normalize_exact(item) for key, item in value.items()}
    return (
        json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _source_bytes(
    *,
    late: bool,
    null_cached: bool,
    variant_native_turn_id: str,
) -> bytes:
    return b"".join(
        json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
        for record in structural_records(
            include_late_call=late,
            null_cached_tokens=null_cached,
            variant_native_turn_id=variant_native_turn_id,
        )
    )


def _variant_source(case: dict[str, Any]) -> tuple[str, bool, bool, str]:
    profile = case["source_profile"]
    late = bool(profile["late_event"])
    null_cached = bool(profile["missing_cached_input"])
    mutation = case["semantic_mutation"]
    native_turn_id = str(mutation["native_turn_id"])
    name = case["oracle_id"].removeprefix("oracle:").replace(":", "-")
    return name, late, null_cached, native_turn_id


def _manifest_digest(manifest: dict[str, Any]) -> str:
    without_digest = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    return exact_sha256(without_digest)


def _trim_declaration(case: dict[str, Any]) -> None:
    contract = plan_contract()
    plan = next(item for item in contract["plans"] if item["plan_id"] == case["request"]["plan_id"])
    relations = {source["relation"] for source in plan["permitted_sources"]}
    if "valuation_match" in relations:
        # Valuation matches are independently compiled from captured profiles and
        # the effective-dated frontier; profiles are structural inputs, not an
        # extra plan operand.
        relations.add("model_profile")
    declaration = case["declaration"]
    evidence_ids = {item["logical_id"] for item in case["required_evidence"]}
    for item in case["required_evidence"]:
        if item["selector_kind"] == "allowance_interval":
            interval = declaration["allowance_intervals"][item["logical_id"]]
            evidence_ids.update(
                (
                    interval["start_observation_id"],
                    interval["end_observation_id"],
                )
            )
    if "model_profile" in case["required_selector_kinds"]:
        profile_ids = {
            item["logical_id"]
            for item in case["required_evidence"]
            if item["selector_kind"] == "model_profile"
        }
        related_calls = {
            fact["logical_id"]
            for fact in declaration["facts"]
            if fact["relation"] == "canonical_call"
            and fact["values"].get("model_profile_id") in profile_ids
        }
        evidence_ids.update(related_calls)
        relations.add("canonical_call")
    occurrence_coordinate_ids: set[str] = set()
    if "source_occurrence" in relations:
        occurrence_coordinate_ids = {
            fact["values"]["semantic_logical_id"]
            for fact in declaration["facts"]
            if fact["relation"] == "source_occurrence"
        }
    declaration["facts"] = [
        fact
        for fact in declaration["facts"]
        if fact["relation"] in relations
        or fact["logical_id"] in evidence_ids
        or (
            fact["logical_id"] in occurrence_coordinate_ids
            and fact["coordinates"]["event_at_us"] is not None
        )
    ]
    for fact in declaration["facts"]:
        coordinates = fact.get("coordinates")
        if not isinstance(coordinates, dict):
            continue
        for field in (
            "event_at_us",
            "source_rank",
            "source_order",
            "event_kind_order",
            "transition_rank",
        ):
            if coordinates.get(field) in (None, 0):
                coordinates.pop(field, None)
    declaration["occurrences"] = {
        logical_id: occurrences
        for logical_id, occurrences in declaration["occurrences"].items()
        if logical_id in evidence_ids
    }
    required_kinds = set(case["required_selector_kinds"])
    if "allowance_interval" in required_kinds:
        required_kinds.add("allowance_observation")
    declaration["selector_entities"] = {
        kind: entities
        for kind, entities in declaration["selector_entities"].items()
        if kind in required_kinds
    }
    manifestation_ids = {
        occurrence["source_manifestation_id"]
        for occurrences in declaration["occurrences"].values()
        for occurrence in occurrences
    }
    manifestation_ids.update(
        item["logical_id"]
        for item in case["required_evidence"]
        if item["selector_kind"] == "source_manifestation"
    )
    declaration["source_manifestations"] = {
        logical_id: value
        for logical_id, value in declaration["source_manifestations"].items()
        if logical_id in manifestation_ids
    }
    if "allowance_observation" not in relations and "allowance_interval" not in required_kinds:
        declaration["allowance_intervals"] = {}
    if "valuation_match" not in relations and "rate_card" not in required_kinds:
        declaration["rate_card_frontier"] = {
            "head_digest": None,
            "revisions": [],
        }
        declaration["publication_rate_card_digest"] = None


def generate(destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    sources_root = destination / "sources"
    sources_root.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(
        (ROOT / "config/agent-kernel/question-catalog-v1.json").read_text(encoding="utf-8")
    )
    questions = {question["question_id"]: question for question in catalog["questions"]}
    original = build_question_scenarios()
    source_entries = []
    base_paths: dict[tuple[bool, bool], str] = {}
    for late, null_cached, base_name in (
        (False, False, "base"),
        (True, False, "late"),
        (False, True, "missing"),
        (True, True, "late-missing"),
    ):
        payload = _source_bytes(
            late=late,
            null_cached=null_cached,
            variant_native_turn_id="root-turn",
        )
        relative = f"sources/{base_name}.jsonl"
        (destination / relative).write_bytes(payload)
        base_paths[(late, null_cached)] = relative
        source_entries.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
                "records": payload.count(b"\n"),
                "late_event": late,
                "missing_cached_input": null_cached,
            }
        )

    mutation_records = []
    variant_constructions = []
    composed_digests = set()
    for ordinal, case in enumerate(original["cases"]):
        name, late, null_cached, native_turn_id = _variant_source(case)
        composed = _source_bytes(
            late=late,
            null_cached=null_cached,
            variant_native_turn_id=native_turn_id,
        )
        composed_digest = hashlib.sha256(composed).hexdigest()
        composed_digests.add(composed_digest)
        matching = [
            record
            for record in structural_records(
                include_late_call=late,
                null_cached_tokens=null_cached,
                variant_native_turn_id=native_turn_id,
            )
            if record["type"] == "model_call" and record["payload"].get("call_id") == "before"
        ]
        if len(matching) != 1 or matching[0]["payload"]["turn_id"] != native_turn_id:
            raise ValueError(f"{case['oracle_id']} source predicate failed")
        mutation_records.append(matching[0])
        variant_constructions.append(
            {
                "oracle_id": case["oracle_id"],
                "base_path": base_paths[(late, null_cached)],
                "mutation_path": "sources/variant-mutations.jsonl",
                "mutation_record_ordinal": ordinal,
                "operation": "replace_model_call_by_native_call_id",
                "native_call_id": "before",
                "composed_sha256": composed_digest,
                "semantic_mutation": case["semantic_mutation"],
                "variant_predicates": case["variant_predicates"],
            }
        )
    if len(composed_digests) != 80:
        raise ValueError("CK-07A requires 80 distinct semantic source constructions")
    mutation_payload = b"".join(
        json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
        for record in mutation_records
    )
    mutation_path = "sources/variant-mutations.jsonl"
    (destination / mutation_path).write_bytes(mutation_payload)
    source_entries.append(
        {
            "path": mutation_path,
            "sha256": hashlib.sha256(mutation_payload).hexdigest(),
            "bytes": len(mutation_payload),
            "records": len(mutation_records),
            "role": "explicit_semantic_mutations",
        }
    )

    connections: dict[str, sqlite3.Connection] = {}
    temporary = tempfile.TemporaryDirectory(prefix="ck07a-fixture-")
    try:
        scratch = Path(temporary.name)
        for case in original["cases"]:
            name, late, null_cached, native_turn_id = _variant_source(case)
            variant_root = scratch / name
            database_path = variant_root / "database-v1.sqlite3"
            publish_structural_snapshot(
                variant_root / "fixture",
                database_path,
                include_late_call=late,
                null_cached_tokens=null_cached,
                variant_native_turn_id=native_turn_id,
            )
            connections[name] = sqlite3.connect(database_path)

        cases = []
        oracle_questions = {}
        comparison_digests = []
        for case in original["cases"]:
            name, _late, _null_cached, _native_turn_id = _variant_source(case)
            published = published_question_case(
                connections[name], case, preserve_frozen_authority=True
            )
            construction = next(
                item for item in variant_constructions if item["oracle_id"] == case["oracle_id"]
            )
            published["source_path"] = construction["base_path"]
            published["source_mutation"] = {
                "path": construction["mutation_path"],
                "record_ordinal": construction["mutation_record_ordinal"],
                "operation": construction["operation"],
                "composed_sha256": construction["composed_sha256"],
            }
            question = questions[published["question_id"]]
            evaluated = evaluate_question_case(published, question)
            comparison_digests.append(evaluated["comparison_digest"])
            cases.append(published)
            oracle_questions[published["oracle_id"]] = {
                "question_id": published["question_id"],
                "variant": published["variant"],
                "request_digest": evaluated["request_digest"],
                "expected_rows": evaluated["rows"],
                "field_grades": question["answers"]["fields"],
                "references": evaluated["references"],
                "comparison_digest": evaluated["comparison_digest"],
                "source_path": published["source_path"],
            }
    finally:
        for connection in connections.values():
            connection.close()
        temporary.cleanup()

    scenarios = {
        "schema": SCENARIO_SCHEMA,
        "fixture_revision": FIXTURE_REVISION,
        "cases": cases,
    }
    scenario_bytes = _bytes(scenarios)
    (destination / "question-scenarios.json").write_bytes(scenario_bytes)
    oracle = {
        "schema": ORACLE_SCHEMA,
        "fixture_revision": FIXTURE_REVISION,
        "questions": oracle_questions,
        "reconciliation": {
            "catalog_questions": len(questions),
            "declared_variants": len(cases),
            "comparison_digests": comparison_digests,
            "all_unique": len(set(comparison_digests)) == len(cases),
        },
    }
    oracle_bytes = _bytes(oracle)
    (destination / "oracle-bundle.json").write_bytes(oracle_bytes)
    manifest = {
        "fixture_revision": FIXTURE_REVISION,
        "schema": "codex-usage-tracker.synthetic-fixture-manifest.v2",
        "format_policy": {
            "encoding": "canonical_json_utf8_lf",
            "source_records": "adapter_ingestible_structural_events_only",
            "question_intent": "question-scenarios.json_only",
            "expected_answers": "oracle-bundle.json_only",
            "content_bodies": False,
            "absolute_paths": False,
        },
        "catalog": {
            "path": "config/agent-kernel/question-catalog-v1.json",
            "questions": len(questions),
            "variants": len(cases),
            "answer_field_bindings": sum(
                len(question["answers"]["fields"]) for question in questions.values()
            ),
        },
        "sources": source_entries,
        "variant_constructions": variant_constructions,
        "source_totals": {
            "files": len(source_entries),
            "bytes": sum(entry["bytes"] for entry in source_entries),
            "records": sum(entry["records"] for entry in source_entries),
        },
        "question_scenarios": {
            "path": "question-scenarios.json",
            "schema": SCENARIO_SCHEMA,
            "sha256": hashlib.sha256(scenario_bytes).hexdigest(),
        },
        "oracle_bundle": {
            "path": "oracle-bundle.json",
            "schema": ORACLE_SCHEMA,
            "sha256": hashlib.sha256(oracle_bytes).hexdigest(),
        },
    }
    manifest["manifest_digest"] = _manifest_digest(manifest)
    manifest_bytes = _bytes(manifest)
    (destination / "manifest.json").write_bytes(manifest_bytes)
    return {
        "manifest_digest": manifest["manifest_digest"],
        "oracle_sha256": manifest["oracle_bundle"]["sha256"],
        "scenario_sha256": manifest["question_scenarios"]["sha256"],
        "source_bytes": manifest["source_totals"]["bytes"],
        "source_records": manifest["source_totals"]["records"],
        "cases": len(cases),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        type=Path,
        default=ROOT / "tests/agent_kernel/fixtures/tiny-v2",
    )
    arguments = parser.parse_args()
    print(json.dumps(generate(arguments.destination), sort_keys=True))


if __name__ == "__main__":
    main()
