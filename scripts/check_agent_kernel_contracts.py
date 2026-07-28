#!/usr/bin/env python3
"""Validate the agent-kernel question registry against its active authority."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_PATH = _REPO_ROOT / "config" / "agent-kernel" / "question-catalog-v1.json"
_SCHEMA_PATH = (
    _REPO_ROOT / "config" / "agent-kernel" / "question-catalog-v1.schema.json"
)
_GUIDANCE_PATH = (
    _REPO_ROOT / "config" / "agent-kernel" / "question-guidance-v1.json"
)
_MARKDOWN_PATH = (
    _REPO_ROOT / "docs" / "product" / "SUPPORTED_QUESTION_CONTRACTS.md"
)
_FORBIDDEN_REQUIREMENTS = frozenset(
    {
        "arbitrary_sql",
        "free_form_sql",
        "raw_command",
        "raw_content",
        "raw_patch",
        "raw_prompt",
        "raw_reasoning",
        "raw_response",
        "raw_tool_output",
    }
)
_CONCLUSION_SUPPORT_CLASSES = frozenset({"I", "D", "U"})
_NAMED_STAGES = frozenset({"Foundation", "Cutover"})
_ANSWER_FIELD_DEPENDENCIES: dict[str, dict[str, frozenset[str]]] = {
    "following_tokens": {
        "required_capabilities": frozenset({"model_call_usage"}),
        "required_measurements": frozenset(
            {
                "cached_input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "uncached_input_tokens",
            }
        ),
        "logical_primitives": frozenset({"canonical_call"}),
        "coverage_requirements": frozenset(
            {"capability", "history", "measurement"}
        ),
    }
}


def canonical_json_bytes(value: object) -> bytes:
    """Return stable UTF-8 JSON bytes for generated contract artifacts."""

    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.relative_to(_REPO_ROOT)} must contain one object")
    return payload


def _normalize_prose(value: str) -> str:
    return " ".join(value.replace("“", "").replace("”", "").split()).rstrip(".")


def _markdown_map(markdown: str) -> dict[str, dict[str, object]]:
    map_body = markdown.split("## Catalog map", maxsplit=1)[1].split(
        "## Question contracts",
        maxsplit=1,
    )[0]
    records: dict[str, dict[str, object]] = {}
    for line in map_body.splitlines():
        if not line.startswith("| Q-"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if len(cells) != 7:
            raise ValueError(f"invalid catalog-map row: {line}")
        question_id, plan_id, support, stage, evidence, performance, _default = cells
        if question_id in records:
            raise ValueError(f"duplicate Markdown catalog row: {question_id}")
        records[question_id] = {
            "plan_id": plan_id,
            "support_classes": support.split(","),
            "stage": stage,
            "evidence_classes": re.findall(r"E[0-7]", evidence),
            "performance_classes": re.findall(r"P[0-5]", performance),
        }
    return records


def _bullet(section: str, label: str) -> str | None:
    match = re.search(
        rf"^- \*\*{re.escape(label)}:\*\* (?P<body>.*?)(?=\n- \*\*|\n#### |\n### |\n## |\Z)",
        section,
        re.MULTILINE | re.DOTALL,
    )
    return None if match is None else _normalize_prose(match.group("body"))


def _markdown_contracts(markdown: str) -> dict[str, dict[str, str | None]]:
    contracts: dict[str, dict[str, str | None]] = {}
    matches = list(
        re.finditer(
            r"^#### (?P<id>Q-[A-Z]{2,3}-\d{2}): (?P<title>.+)$",
            markdown,
            re.MULTILINE,
        )
    )
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        section = markdown[match.end() : end]
        question_id = match.group("id")
        if question_id in contracts:
            raise ValueError(f"duplicate Markdown detailed contract: {question_id}")
        contracts[question_id] = {
            "title": match.group("title").strip(),
            "intent": _bullet(section, "Intent"),
            "prohibited": _bullet(section, "Must not"),
        }
    return contracts


def build_guidance(catalog: dict[str, Any]) -> dict[str, object]:
    """Project the full registry into compact, model-facing plan guidance."""

    questions = sorted(catalog["questions"], key=lambda item: item["question_id"])
    return {
        "schema": "codex-usage-tracker.question-guidance.v1",
        "catalog_version": catalog["version"],
        "questions": [
            {
                "evidence": question["evidence"]["classes"],
                "hint": question["lower_model_hint"],
                "id": question["question_id"],
                "performance": question["performance_classes"],
                "plan": question["plan_id"],
                "required": question["parameters"]["required"],
                "stage": question["stage"],
                "support": question["support_classes"],
                "when": question["intent_phrases"][0],
            }
            for question in questions
        ],
    }


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _schema_failures(
    catalog: dict[str, Any],
    schema: dict[str, Any],
) -> list[str]:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"question catalog JSON Schema is invalid: {exc.message}"]
    validator = Draft202012Validator(schema)
    return [
        "question catalog schema violation at "
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in sorted(
            validator.iter_errors(catalog),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]


def _reference_failures(catalog: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    reference_fields = {
        "required_capabilities": set(catalog["capabilities"]),
        "required_measurements": set(catalog["measurements"]),
        "coverage_requirements": set(catalog["coverage_dimensions"]),
        "projection_consumers": set(catalog["projection_ids"]),
    }
    parameter_ids = set(catalog["parameter_ids"])
    primitive_ids = set(catalog["logical_primitives"])
    selector_kinds = set(catalog["selector_kinds"])
    evidence_classes = {item["id"] for item in catalog["evidence_classes"]}
    evidence_selectors = {
        item["id"]: set(item["selector_kinds"])
        for item in catalog["evidence_classes"]
    }
    performance_classes = {item["id"] for item in catalog["performance_classes"]}

    for evidence_class in catalog["evidence_classes"]:
        unknown = set(evidence_class["selector_kinds"]) - selector_kinds
        if unknown:
            failures.append(
                f"{evidence_class['id']} names unknown selector kinds: {sorted(unknown)}"
            )

    for question in catalog["questions"]:
        question_id = question["question_id"]
        required = set(question["parameters"]["required"])
        optional = set(question["parameters"]["optional"])
        unknown_parameters = (required | optional) - parameter_ids
        if unknown_parameters:
            failures.append(
                f"{question_id} names unknown parameters: {sorted(unknown_parameters)}"
            )
        if required & optional:
            failures.append(f"{question_id} has required/optional parameter overlap")

        for field, allowed in reference_fields.items():
            unknown = set(question[field]) - allowed
            if unknown:
                failures.append(
                    f"{question_id} {field} contains unknown IDs: {sorted(unknown)}"
                )
        unknown_primitives = set(question["logical_plan"]["primitives"]) - primitive_ids
        if unknown_primitives:
            failures.append(
                f"{question_id} names unknown logical primitives: "
                f"{sorted(unknown_primitives)}"
            )
        unknown_evidence = set(question["evidence"]["classes"]) - evidence_classes
        if unknown_evidence:
            failures.append(
                f"{question_id} names unknown evidence classes: {sorted(unknown_evidence)}"
            )
        unknown_selectors = set(question["evidence"]["selector_kinds"]) - selector_kinds
        if unknown_selectors:
            failures.append(
                f"{question_id} names unknown selector kinds: {sorted(unknown_selectors)}"
            )
        allowed_evidence_selectors = set().union(
            *(
                evidence_selectors[evidence_class]
                for evidence_class in question["evidence"]["classes"]
                if evidence_class in evidence_selectors
            )
        )
        selectors_outside_evidence = (
            set(question["evidence"]["selector_kinds"])
            - allowed_evidence_selectors
        )
        if selectors_outside_evidence:
            failures.append(
                f"{question_id} evidence selectors are outside its evidence-class "
                f"allowlist: {sorted(selectors_outside_evidence)}"
            )
        unknown_performance = set(question["performance_classes"]) - performance_classes
        if unknown_performance:
            failures.append(
                f"{question_id} names unknown performance classes: "
                f"{sorted(unknown_performance)}"
            )
    return failures


def _semantic_failures(
    catalog: dict[str, Any],
    markdown: str,
) -> list[str]:
    failures: list[str] = []
    markdown_map = _markdown_map(markdown)
    markdown_contracts = _markdown_contracts(markdown)
    questions = catalog["questions"]
    question_ids = [question["question_id"] for question in questions]
    duplicate_ids = _duplicates(question_ids)
    if duplicate_ids:
        failures.append(f"duplicate registry question IDs: {sorted(duplicate_ids)}")
    if set(question_ids) != set(markdown_map):
        failures.append(
            "Markdown/registry question IDs differ: "
            f"markdown_only={sorted(set(markdown_map) - set(question_ids))}, "
            f"registry_only={sorted(set(question_ids) - set(markdown_map))}"
        )
    if set(markdown_contracts) != set(markdown_map):
        failures.append("Markdown catalog rows and detailed contracts differ")

    performance = {
        item["id"]: item for item in catalog["performance_classes"]
    }
    parameter_usages = set().union(
        *(
            set(question["parameters"]["required"])
            | set(question["parameters"]["optional"])
            for question in questions
        )
    )
    all_requirement_ids = set().union(
        set(catalog["parameter_ids"]),
        parameter_usages,
        set(catalog["capabilities"]),
        set(catalog["measurements"]),
        set(catalog["logical_primitives"]),
    )
    forbidden = all_requirement_ids & _FORBIDDEN_REQUIREMENTS
    if forbidden:
        failures.append(f"registry requires forbidden raw/SQL inputs: {sorted(forbidden)}")

    for question in questions:
        question_id = question["question_id"]
        markdown_row = markdown_map.get(question_id)
        prose = markdown_contracts.get(question_id)
        if markdown_row is None or prose is None:
            continue
        for field in (
            "plan_id",
            "support_classes",
            "stage",
            "evidence_classes",
            "performance_classes",
        ):
            registry_value: object
            if field == "evidence_classes":
                registry_value = question["evidence"]["classes"]
            else:
                registry_value = question[field]
            if registry_value != markdown_row[field]:
                failures.append(
                    f"{question_id} {field} differs from Markdown: "
                    f"{registry_value!r} != {markdown_row[field]!r}"
                )
        if question["title"] != prose["title"]:
            failures.append(f"{question_id} title differs from Markdown")
        if _normalize_prose(question["intent_phrases"][0]) != prose["intent"]:
            failures.append(f"{question_id} primary intent differs from Markdown")
        if _normalize_prose(question["prohibited_claims"][0]) != prose["prohibited"]:
            failures.append(f"{question_id} primary prohibited claim differs from Markdown")

        if question["stage"] in _NAMED_STAGES and question["support_classes"] != ["N"]:
            failures.append(f"{question_id} {question['stage']} entry must be exactly N")
        if (
            set(question["support_classes"]) & _CONCLUSION_SUPPORT_CLASSES
            and question["answers"]["kernel_conclusion_fields"]
        ):
            failures.append(
                f"{question_id} inference/deferred/unsupported entry names "
                "kernel conclusion fields"
            )
        if question["logical_plan"]["compiler_id"] is not None:
            failures.append(f"{question_id} guesses a physical compiler during CK-01")
        if question["limits"]["default_rows"] > question["limits"]["maximum_rows"]:
            failures.append(f"{question_id} default row limit exceeds maximum")
        if not question["required_capabilities"]:
            failures.append(f"{question_id} has no capability contract")
        if not question["required_measurements"]:
            failures.append(f"{question_id} has no measurement contract")
        if not question["logical_plan"]["primitives"]:
            failures.append(f"{question_id} has no logical primitives")
        if not question["answers"]["fields"]:
            failures.append(f"{question_id} has no graded answer fields")
        for answer_field in question["answers"]["fields"]:
            dependency_rule = _ANSWER_FIELD_DEPENDENCIES.get(answer_field)
            if dependency_rule is None:
                continue
            dependency_sources = {
                "required_capabilities": set(question["required_capabilities"]),
                "required_measurements": set(question["required_measurements"]),
                "logical_primitives": set(
                    question["logical_plan"]["primitives"]
                ),
                "coverage_requirements": set(
                    question["coverage_requirements"]
                ),
            }
            for dependency_kind, required_dependencies in dependency_rule.items():
                missing_dependencies = (
                    required_dependencies - dependency_sources[dependency_kind]
                )
                if missing_dependencies:
                    failures.append(
                        f"{question_id} answer field {answer_field} lacks "
                        f"{dependency_kind}: {sorted(missing_dependencies)}"
                    )
        if "N" in question["support_classes"]:
            for performance_id in question["performance_classes"]:
                budget = performance[performance_id]
                if budget["query_calls"] != 1:
                    failures.append(f"{question_id} named plan is not one query call")
                if budget["response_bytes"] > 16384:
                    failures.append(f"{question_id} named plan exceeds 16 KB")
    return failures


def catalog_failures(
    repo_root: Path = _REPO_ROOT,
    *,
    catalog: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
    guidance_bytes: bytes | None = None,
    markdown: str | None = None,
) -> list[str]:
    """Return all deterministic CK-01 registry failures."""

    catalog_path = repo_root / _CATALOG_PATH.relative_to(_REPO_ROOT)
    schema_path = repo_root / _SCHEMA_PATH.relative_to(_REPO_ROOT)
    guidance_path = repo_root / _GUIDANCE_PATH.relative_to(_REPO_ROOT)
    markdown_path = repo_root / _MARKDOWN_PATH.relative_to(_REPO_ROOT)
    selected_catalog = _load_json(catalog_path) if catalog is None else catalog
    selected_schema = _load_json(schema_path) if schema is None else schema
    selected_guidance_bytes = (
        guidance_path.read_bytes() if guidance_bytes is None else guidance_bytes
    )
    selected_markdown = (
        markdown_path.read_text(encoding="utf-8")
        if markdown is None
        else markdown
    )

    failures = _schema_failures(selected_catalog, selected_schema)
    if failures:
        return failures
    failures.extend(_reference_failures(selected_catalog))
    try:
        failures.extend(_semantic_failures(selected_catalog, selected_markdown))
    except ValueError as exc:
        failures.append(f"Markdown question catalog is invalid: {exc}")

    expected_guidance = canonical_json_bytes(build_guidance(selected_catalog))
    if selected_guidance_bytes != expected_guidance:
        failures.append("question guidance fixture is not the canonical registry projection")
    if len(expected_guidance) > selected_catalog["guidance_budget_bytes"]:
        failures.append(
            "question guidance exceeds byte budget: "
            f"{len(expected_guidance)} > {selected_catalog['guidance_budget_bytes']}"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-guidance",
        action="store_true",
        help="Regenerate the compact guidance fixture from the registry.",
    )
    args = parser.parse_args()

    catalog = _load_json(_CATALOG_PATH)
    if args.write_guidance:
        _GUIDANCE_PATH.write_bytes(canonical_json_bytes(build_guidance(catalog)))

    failures = catalog_failures(catalog=catalog)
    if failures:
        print("\n".join(failures))
        return 1
    guidance_bytes = len(canonical_json_bytes(build_guidance(catalog)))
    print(
        "Agent-kernel question contracts passed: "
        f"questions={len(catalog['questions'])}, guidance_bytes={guidance_bytes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
