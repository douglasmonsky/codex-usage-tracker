from __future__ import annotations

from typing import Any

EVIDENCE_SCHEMA = "codex-usage-tracker.ck07a-fact-backed-oracle-and-seam-qualification-evidence.v1"
REQUIRED_TOP_LEVEL_FIELDS = (
    "schema",
    "packet",
    "status",
    "dependency_shas",
    "artifacts",
    "seams",
    "variants",
    "measurements",
    "requalifications",
    "validation",
    "review",
    "privacy",
    "growth_waiver",
    "residual_risks",
)
REQUIRED_SEAMS = (
    "CK-03 truth",
    "CK-04 correctness",
    "CK-05 storage",
    "CK-06 source changes",
    "CK-07 publication",
)


def validate_seam_evidence(payload: dict[str, Any]) -> None:
    if tuple(payload) != REQUIRED_TOP_LEVEL_FIELDS:
        raise ValueError("CK-07A evidence fields canonical order differs")
    if payload["schema"] != EVIDENCE_SCHEMA:
        raise ValueError("CK-07A evidence schema differs")
    if payload["packet"] != "CK-07A":
        raise ValueError("CK-07A evidence packet differs")
    if payload["status"] != "passed":
        raise ValueError("CK-07A completion evidence must be passed")
    if tuple(item["name"] for item in payload["seams"]) != REQUIRED_SEAMS:
        raise ValueError("CK-07A evidence must record all five ordered seam rows")
    for seam in payload["seams"]:
        if (
            seam.get("status") != "passed"
            or seam.get("attempt_count") != 80
            or seam.get("comparison_count") != 80
        ):
            raise ValueError(f"CK-07A seam did not pass exactly: {seam.get('name')}")
    if len(payload["variants"]) != 80:
        raise ValueError("CK-07A evidence must record all 80 variants")
    oracle_ids = [variant.get("oracle_id") for variant in payload["variants"]]
    comparison_digests = [variant.get("comparison_digest") for variant in payload["variants"]]
    if len(set(oracle_ids)) != 80 or len(set(comparison_digests)) != 80:
        raise ValueError("CK-07A variants must have 80 unique IDs and comparisons")
    for variant in payload["variants"]:
        if not all(
            variant.get(field) is True
            for field in (
                "request_matches",
                "rows_match",
                "grades_match",
                "ordered_references_match",
            )
        ):
            raise ValueError(f"CK-07A variant comparison failed: {variant.get('oracle_id')}")
        predicates = variant.get("variant_predicates")
        if (
            not isinstance(predicates, list)
            or len(predicates) != 2
            or not all(item.get("passed") is True for item in predicates)
        ):
            raise ValueError(f"CK-07A variant predicate failed: {variant.get('oracle_id')}")
    if payload["measurements"].get("answer_field_bindings") != 185:
        raise ValueError("CK-07A evidence must record all 185 answer fields")
    if payload["measurements"].get("selector_kind_count") != 14:
        raise ValueError("CK-07A evidence must record all 14 selector kinds")
    if payload["measurements"].get("provenance_kind_count") != 6:
        raise ValueError("CK-07A evidence must record all six provenance kinds")
    if payload["measurements"].get("unique_comparison_digest_count") != 80:
        raise ValueError("CK-07A evidence must record 80 unique comparisons")
    lifecycle = payload["measurements"].get("lifecycle_transitions")
    if (
        not isinstance(lifecycle, list)
        or [item.get("name") for item in lifecycle]
        != ["initial", "same_lineage_rebuild", "replacement", "late_event", "recovery"]
        or not all(item.get("passed") is True for item in lifecycle)
    ):
        raise ValueError("CK-07A lifecycle transitions did not all pass")
    compatibility = payload["measurements"].get("ci_compatibility_followup", {})
    failed_runs = compatibility.get("failed_runs", [])
    passing_run = compatibility.get("passing_run", {})
    correction = compatibility.get("correction", {})
    macos_plan = correction.get("macos_detailed_publication_head_plan")
    ubuntu_plan = correction.get("ubuntu_detailed_publication_head_plan")
    expected_macos_plan = [
        "SEARCH h USING PRIMARY KEY (singleton=?)",
        "SEARCH p USING PRIMARY KEY (publication_id=?)",
        "CORRELATED SCALAR SUBQUERY 1",
        "SEARCH c USING PRIMARY KEY (publication_id=?)",
        "CORRELATED SCALAR SUBQUERY 2",
        "SEARCH e USING PRIMARY KEY (publication_id=?)",
        "CORRELATED SCALAR SUBQUERY 3",
        "SEARCH c USING PRIMARY KEY (publication_id=? AND capability_id=?)",
        "CORRELATED SCALAR SUBQUERY 4",
        "SEARCH c USING PRIMARY KEY (publication_id=? AND capability_id=?)",
    ]
    if (
        compatibility.get("status") != "passed"
        or compatibility.get("timing") != "post_review_deterministic_ci_followup"
        or compatibility.get("reviewer_retried") is not False
        or compatibility.get("numeric_plan_ceilings_changed") is not False
        or [item.get("run_id") for item in failed_runs]
        != [30_604_269_619, 30_604_883_581, 30_605_162_039]
        or [item.get("head_sha") for item in failed_runs]
        != [
            "a04536110b7274920e8727083320bd7f1a394699",
            "4fbec859c626528796db43f873f9c59d5a3336a5",
            "f8df09b656dc8368edc004bd58cdf8ffd0ccec53",
        ]
        or any(item.get("result") != "failed" for item in failed_runs)
        or correction.get("query_only_preserved") is not True
        or correction.get("forbidden_sources_denied_during_execution") is not True
        or correction.get("plan_ceiling_changes") != {}
        or macos_plan != expected_macos_plan
        or ubuntu_plan != [*macos_plan, "USE TEMP B-TREE FOR ORDER BY"]
        or passing_run.get("run_id") != 30_605_461_230
        or passing_run.get("head_sha") != "c97d230de412f6c05dfb469e9838548a09f30766"
        or [item.get("name") for item in passing_run.get("jobs", [])]
        != [
            "Focused Evidence Console",
            "Kernel phase and package isolation (3.10)",
            "Kernel phase and package isolation (3.14)",
        ]
        or any(item.get("status") != "passed" for item in passing_run.get("jobs", []))
    ):
        raise ValueError("CK-07A deterministic CI compatibility follow-up is incomplete")
    response_bytes = payload["measurements"].get("response_bytes", {})
    if response_bytes.get("maximum", 1) > response_bytes.get("ratchet_maximum", 0):
        raise ValueError("CK-07A response byte ratchet failed")
    byte_ratchets = payload["measurements"].get("byte_ratchets")
    if not isinstance(byte_ratchets, dict):
        raise ValueError("CK-07A byte ratchets missing")
    for name in ("candidate_response", "oracle_bundle", "source_jsonl"):
        ratchet = byte_ratchets.get(name, {})
        if ratchet.get("passed") is not True or ratchet.get("observed", 1) > ratchet.get(
            "maximum_with_25_percent_headroom", 0
        ):
            raise ValueError(f"CK-07A byte ratchet failed: {name}")
    complete_tree = byte_ratchets.get("complete_tree", {})
    authority = complete_tree.get("authority", {})
    if (
        complete_tree.get("passed") is not True
        or authority.get("packet") != "CK-07A"
        or authority.get("basis") != "canonical_packet_explicit_complete_tree_authority"
        or complete_tree.get("observed", 1) > authority.get("maximum_authorized_bytes", 0)
    ):
        raise ValueError("CK-07A complete-tree authority is missing or exceeded")
    for item in payload["requalifications"]:
        if item.get("status") != "requalified":
            raise ValueError(f"CK-07A requalification failed: {item.get('packet')}")
    if any(not str(item.get("result", "")).startswith("passed") for item in payload["validation"]):
        raise ValueError("CK-07A validation result did not pass")
    review = payload["review"]
    if (
        review.get("status") != "request_changes_resolved"
        or review.get("unresolved_findings") != []
        or len(review.get("resolved_findings", ())) != 6
    ):
        raise ValueError("CK-07A reviewer findings are not fully resolved")
    if payload["privacy"].get("synthetic_fixture_only") is not True:
        raise ValueError("CK-07A evidence must be synthetic-only")
    if (
        payload["privacy"].get("passed") is not True
        or payload["privacy"].get("real_codex_content") is not False
        or payload["privacy"].get("absolute_paths") is not False
        or payload["privacy"].get("secret_findings") != 0
        or payload["privacy"].get("forbidden_source_findings") != []
    ):
        raise ValueError("CK-07A privacy validation failed")
    if payload["growth_waiver"].get("strict_five_repetition_aggregate_claimed"):
        raise ValueError("CK-07A cannot claim the waived five-repetition aggregate")
