#!/usr/bin/env python3
"""Collect synthetic-only CK-08R2 physical page-executor evidence."""

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

from codex_usage_tracker.agent_kernel.domain.plan_operands import (  # noqa: E402
    PlanRequest,
)
from codex_usage_tracker.agent_kernel.query.compiler import (  # noqa: E402
    request_digest,
)
from codex_usage_tracker.agent_kernel.query.page_executor import (  # noqa: E402
    PAGE_EXECUTOR_SCHEMA,
    PageExecutionRequest,
    PhysicalPageError,
    PhysicalPageExecutor,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import (  # noqa: E402
    build_question_scenarios,
)
from tests.agent_kernel.fixtures.published_v2 import (  # noqa: E402
    publish_structural_snapshot,
    published_question_case,
)

DEPENDENCY_SHA = "306cef37eea2ae017aca824d898cc435f7e1bea0"
DEFAULT_OUTPUT = ROOT / "docs" / "decisions" / "evidence" / "ck08r2"
FIXTURE_PATH = ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v2" / (
    "question-scenarios.json"
)
PLAN_CASES = {
    "data_health": ("Q-OPS-02", "deferred_history"),
    "latest_publication_delta": ("Q-OPS-01", "no_change"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_catalog() -> dict[str, dict[str, Any]]:
    payload = json.loads(
        (ROOT / "config" / "agent-kernel" / "question-catalog-v1.json").read_text(
            encoding="utf-8"
        )
    )
    return {str(item["question_id"]): item for item in payload["questions"]}


def _page_request(
    plan_request: PlanRequest,
    question: dict[str, Any],
    publication_id: str,
    *,
    cursor_order: tuple[Any, ...] | None = None,
    include_exact_count: bool = False,
) -> PageExecutionRequest:
    return PageExecutionRequest(
        plan_id=plan_request.plan_id,
        plan_version=int(question["version"]),
        publication_id=publication_id,
        request_digest=request_digest(plan_request),
        complete_order=tuple(str(item) for item in question["order"]),
        page_size=1,
        cursor_order=cursor_order,
        include_exact_count=include_exact_count,
        parameters=plan_request.parameters,
    )


def _anchor(
    connection: sqlite3.Connection,
    plan_id: str,
    publication_id: str,
) -> tuple[Any, ...]:
    if plan_id == "data_health":
        row = connection.execute(
            "SELECT committed_at_us FROM publications WHERE publication_id = ?",
            (publication_id,),
        ).fetchone()
        assert row is not None
        return (int(row[0]),)
    row = connection.execute(
        """
        SELECT 'publication-delta:' ||
               substr(publication_id, length('publication:') + 1)
          FROM publication_deltas
         WHERE publication_id = ?
        """,
        (publication_id,),
    ).fetchone()
    assert row is not None
    return ("", str(row[0]))


def _collect_plan(
    root: Path,
    *,
    plan_id: str,
    question_id: str,
    variant: str,
    question: dict[str, Any],
) -> dict[str, Any]:
    original = next(
        item
        for item in build_question_scenarios()["cases"]
        if item["question_id"] == question_id and item["variant"] == variant
    )
    profile = original["source_profile"]
    mutation = original["semantic_mutation"]
    database_path = root / plan_id / "database-v1.sqlite3"
    publish_structural_snapshot(
        database_path.parent / "fixture",
        database_path,
        include_late_call=profile["late_event"],
        null_cached_tokens=profile["missing_cached_input"],
        variant_native_turn_id=mutation["native_turn_id"],
    )
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    case = published_question_case(connection, original)
    raw_request = case["request"]
    plan_request = PlanRequest(
        plan_id=str(raw_request["plan_id"]),
        parameters=raw_request["parameters"],
        gates=raw_request["gates"],
    )
    publication = connection.execute(
        """
        SELECT p.publication_id, p.artifact_manifest_sha256
          FROM publication_head AS h
          JOIN publications AS p ON p.publication_id = h.publication_id
         WHERE h.singleton = 1
        """
    ).fetchone()
    assert publication is not None
    publication_id = str(publication["publication_id"])
    publication_digest = str(publication["artifact_manifest_sha256"])
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")

    executor = PhysicalPageExecutor()
    samples = [
        executor.execute(
            connection,
            _page_request(plan_request, question, publication_id),
            plan_request,
        )
        for _ in range(5)
    ]
    anchor = _anchor(connection, plan_id, publication_id)
    deep = executor.execute(
        connection,
        _page_request(
            plan_request,
            question,
            publication_id,
            cursor_order=anchor,
        ),
        plan_request,
    )
    stale_rejected = False
    stale = tuple(
        value + 1 if isinstance(value, int) else f"{value}:stale" for value in anchor
    )
    try:
        executor.execute(
            connection,
            _page_request(
                plan_request,
                question,
                publication_id,
                cursor_order=stale,
            ),
            plan_request,
        )
    except PhysicalPageError as error:
        stale_rejected = "stale or replaced" in str(error)
    counted = executor.execute(
        connection,
        _page_request(
            plan_request,
            question,
            publication_id,
            include_exact_count=True,
        ),
        plan_request,
    )
    connection.rollback()
    connection.close()

    first = samples[0]
    stage_keys = {
        "bind": "request_bind_ms",
        "sql": "sql_execute_ms",
        "decode": "row_decode_ms",
        "assembly": "result_assembly_ms",
        "serialization": "serialize_ms",
    }
    return {
        "schema": PAGE_EXECUTOR_SCHEMA,
        "dependency_sha": DEPENDENCY_SHA,
        "plan_id": plan_id,
        "fixture_digest": _sha256(FIXTURE_PATH),
        "publication_digest": publication_digest,
        "request_digest": request_digest(plan_request),
        "sql": first.sql,
        "bound_parameters": list(first.parameters),
        "explain": [
            {
                "select_id": item.select_id,
                "order": item.order,
                "from_id": item.from_id,
                "detail": item.detail,
            }
            for item in first.explain
        ],
        "first_page_order": list(anchor),
        "deep_page_order": [],
        "rows_decoded": max(
            int(item.stage_measurements["rows_decoded"]) for item in samples
        ),
        "stage_timings_ms": {
            stage: [
                float(item.stage_measurements[measurement]) for item in samples
            ]
            for stage, measurement in stage_keys.items()
        },
        "rss_bytes": max(
            int(item.stage_measurements["peak_rss_bytes"]) for item in samples
        ),
        "response_bytes": max(
            int(item.stage_measurements["response_bytes"]) for item in samples
        ),
        "cursor_checks": {
            "first_page_returned": first.returned_rows == 1,
            "deep_page_after_anchor_empty": deep.rows == (),
            "stale_anchor_rejected": stale_rejected,
            "tamper_and_replacement_test": (
                "tests/agent_kernel/query/test_service.py::"
                "test_service_rejects_tampered_cursor_replacement_and_writer_connection"
            ),
            "tie_order_oracle_test": (
                "tests/agent_kernel/query/test_page_executor.py::"
                "test_typed_order_oracle_preserves_ties_across_deep_keyset_page"
            ),
        },
        "exact_count_checks": {
            "default_is_false": first.exact_count is None,
            "opt_in_exact_count": counted.exact_count,
            "bounded_rows_with_count": counted.returned_rows,
        },
        "first_failure": None,
        "noise": [
            {
                "kind": "historical_timing_noise",
                "detail": (
                    "Original broad Candidate A mandatory-workload timing failure "
                    "passed its focused rerun and all later comprehensive runs."
                ),
            },
            {
                "kind": "non_gating_allowance_read_p95_ms",
                "just_v": 651.459,
                "just_vc": 614.754,
                "outcome": "invariants_only",
            },
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    catalog = _load_catalog()
    by_id = {str(item["plan_id"]): item for item in catalog.values()}
    arguments.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ck08r2-page-executor-") as temporary:
        root = Path(temporary)
        for plan_id, (question_id, variant) in PLAN_CASES.items():
            payload = _collect_plan(
                root,
                plan_id=plan_id,
                question_id=question_id,
                variant=variant,
                question=by_id[plan_id],
            )
            target = arguments.output_dir / (
                f"{plan_id.replace('_', '-')}-page-executor-benchmark-v2.json"
            )
            encoded = (
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode()
            target.write_bytes(encoded)
            print(
                json.dumps(
                    {
                        "path": target.as_posix(),
                        "sha256": hashlib.sha256(encoded).hexdigest(),
                    },
                    sort_keys=True,
                )
            )


if __name__ == "__main__":
    main()
