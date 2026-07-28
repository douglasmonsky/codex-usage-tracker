from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from scripts.check_agent_kernel_contracts import (
    build_guidance,
    canonical_json_bytes,
    catalog_failures,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
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


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _catalog() -> dict[str, Any]:
    return _load(_CATALOG_PATH)


def _schema() -> dict[str, Any]:
    return _load(_SCHEMA_PATH)


def _guidance_bytes(catalog: dict[str, Any]) -> bytes:
    return canonical_json_bytes(build_guidance(catalog))


def test_catalog_schema_and_authority_reconcile_exactly() -> None:
    catalog = _catalog()
    schema = _schema()

    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(catalog)) == []
    assert catalog_failures(_REPO_ROOT) == []

    question_ids = [question["question_id"] for question in catalog["questions"]]
    assert len(question_ids) == 40
    assert len(set(question_ids)) == 40
    guidance_ids = [question["id"] for question in build_guidance(catalog)["questions"]]
    assert guidance_ids == sorted(question_ids)


def test_guidance_is_canonical_deterministic_and_bounded() -> None:
    catalog = _catalog()
    expected = _guidance_bytes(catalog)

    assert _guidance_bytes(copy.deepcopy(catalog)) == expected
    assert _GUIDANCE_PATH.read_bytes() == expected
    assert len(expected) <= catalog["guidance_budget_bytes"]


def test_duplicate_question_id_fails_closed() -> None:
    catalog = _catalog()
    catalog["questions"][-1]["question_id"] = catalog["questions"][0]["question_id"]

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
    )

    assert any("duplicate registry question IDs" in failure for failure in failures)


def test_unknown_selector_reference_fails_closed() -> None:
    catalog = _catalog()
    catalog["questions"][0]["evidence"]["selector_kinds"].append("unknown_selector")

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
    )

    assert any("unknown selector kinds" in failure for failure in failures)


def test_selector_outside_evidence_class_allowlist_fails_closed() -> None:
    catalog = _catalog()
    catalog["questions"][0]["evidence"]["selector_kinds"].append("tool")

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
    )

    assert any(
        "evidence selectors are outside its evidence-class allowlist" in failure
        for failure in failures
    )


def test_duplicate_markdown_detailed_heading_fails_closed() -> None:
    catalog = _catalog()
    markdown = _MARKDOWN_PATH.read_text(encoding="utf-8")
    markdown += """

#### Q-ACC-01: Duplicate current usage

- **Intent:** Duplicate detailed contract.
- **Must not:** Hide a duplicate detailed contract.
"""

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
        markdown=markdown,
    )

    assert any(
        "duplicate Markdown detailed contract: Q-ACC-01" in failure
        for failure in failures
    )


def test_inference_entry_cannot_name_kernel_conclusion_field() -> None:
    catalog = _catalog()
    inference = next(
        question
        for question in catalog["questions"]
        if "I" in question["support_classes"]
    )
    inference["answers"]["kernel_conclusion_fields"] = ["waste_conclusion"]

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
    )

    assert any(
        "inference/deferred/unsupported entry names kernel conclusion fields"
        in failure
        for failure in failures
    )


def test_foundation_entry_cannot_be_compositional() -> None:
    catalog = _catalog()
    foundation = next(
        question
        for question in catalog["questions"]
        if question["stage"] == "Foundation"
    )
    foundation["support_classes"] = ["C"]

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
    )

    assert any("Foundation entry must be exactly N" in failure for failure in failures)


def test_raw_or_free_form_requirement_fails_closed() -> None:
    catalog = _catalog()
    catalog["measurements"].append("raw_content")

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
    )

    assert any("forbidden raw/SQL inputs" in failure for failure in failures)


def test_raw_content_parameter_vocabulary_fails_closed() -> None:
    catalog = _catalog()
    catalog["parameter_ids"].append("raw_content")

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
    )

    assert any("forbidden raw/SQL inputs" in failure for failure in failures)


def test_free_form_sql_parameter_usage_fails_closed() -> None:
    catalog = _catalog()
    catalog["parameter_ids"].append("free_form_sql")
    catalog["questions"][0]["parameters"]["optional"].append("free_form_sql")

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
    )

    assert any("forbidden raw/SQL inputs" in failure for failure in failures)


def test_answer_field_dependency_contract_fails_closed() -> None:
    catalog = _catalog()
    question = next(
        item
        for item in catalog["questions"]
        if item["question_id"] == "Q-WF-05"
    )
    question["required_capabilities"].remove("model_call_usage")
    question["required_measurements"].remove("cached_input_tokens")
    question["logical_plan"]["primitives"].remove("canonical_call")
    question["coverage_requirements"].remove("capability")

    failures = catalog_failures(
        _REPO_ROOT,
        catalog=catalog,
        schema=_schema(),
        guidance_bytes=_guidance_bytes(catalog),
    )

    assert any("lacks required_capabilities" in failure for failure in failures)
    assert any("lacks required_measurements" in failure for failure in failures)
    assert any("lacks logical_primitives" in failure for failure in failures)
    assert any("lacks coverage_requirements" in failure for failure in failures)


def test_stale_guidance_fixture_fails_closed() -> None:
    failures = catalog_failures(
        _REPO_ROOT,
        catalog=_catalog(),
        schema=_schema(),
        guidance_bytes=b"{}\n",
    )

    assert "question guidance fixture is not the canonical registry projection" in failures
