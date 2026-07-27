from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.database import short_writer_transaction
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import kernel_paths
from codex_usage_tracker.kernel.query.contracts import (
    ComparisonWindow,
    Filter,
    Operation,
    QueryRequest,
)
from codex_usage_tracker.kernel.query.plans import compile_plan
from codex_usage_tracker.kernel.query.service import QueryService

_ORACLE_ROOT = (
    Path(__file__).parents[1] / "fixtures" / "accounting-oracle-v1"
)


def test_batch_uses_one_generation_and_returns_accounting_rows(
    tmp_path: Path,
) -> None:
    service, analytical = _service(tmp_path)
    before = analytical.read_bytes()

    results = service.execute_batch(
        (
            QueryRequest(
                dataset="calls",
                operation=Operation.AGGREGATE,
                dimensions=("model", "effort"),
                measures=(
                    "calls",
                    "uncached_input_tokens",
                    "cached_input_tokens",
                    "reasoning_tokens",
                    "output_tokens",
                    "total_tokens",
                ),
                limit=25,
            ),
            QueryRequest(
                dataset="calls",
                operation=Operation.SHARE,
                dimensions=("thread",),
                measures=("calls", "total_tokens"),
                limit=25,
            ),
        )
    )

    assert {result.generation for result in results} == {1}
    assert results[0].plan_id == "calls.aggregate.v1"
    assert results[0].rows == (
        {
            "model": "gpt-synthetic",
            "effort": "low",
            "calls": 2,
            "uncached_input_tokens": 22,
            "cached_input_tokens": 8,
            "reasoning_tokens": 3,
            "output_tokens": 5,
            "total_tokens": 35,
        },
    )
    assert results[0].grade == "exact"
    assert results[0].coverage["measures"]["reasoning_tokens"][
        "limitations"
    ] == [
        "reasoning tokens are reported separately; overlap with output "
        "tokens is not inferred"
    ]
    assert results[1].rows[0]["share_total_tokens"] == 1.0
    assert results[1].evidence_selectors == (
        f"thread:{results[1].rows[0]['thread']}",
    )
    assert analytical.read_bytes() == before


def test_cursor_is_generation_and_request_bound(tmp_path: Path) -> None:
    service, _analytical = _service(tmp_path)
    request = QueryRequest(
        dataset="calls",
        operation=Operation.ROWS,
        dimensions=("call", "model"),
        measures=("total_tokens",),
        limit=1,
    )

    first = service.execute(request)
    second = service.execute(
        QueryRequest(
            dataset=request.dataset,
            operation=request.operation,
            dimensions=request.dimensions,
            measures=request.measures,
            limit=request.limit,
            cursor=first.next_cursor,
        )
    )

    assert first.truncated
    assert first.next_cursor
    assert first.rows != second.rows
    assert second.next_cursor is None

    mismatched = QueryRequest(
        dataset="calls",
        operation=Operation.ROWS,
        dimensions=("model",),
        measures=("total_tokens",),
        limit=1,
        cursor=first.next_cursor,
    )
    try:
        service.execute(mismatched)
    except ValueError as exc:
        assert "cursor" in str(exc)
    else:
        raise AssertionError("mismatched cursor was accepted")

    malformed = QueryRequest(
        dataset="calls",
        operation=Operation.ROWS,
        dimensions=("call",),
        measures=("total_tokens",),
        limit=1,
        cursor="%%%not-base64%%%",
    )
    try:
        service.execute(malformed)
    except ValueError as exc:
        assert "cursor" in str(exc)
    else:
        raise AssertionError("malformed cursor was accepted")

    cursor_payload = json.loads(
        base64.urlsafe_b64decode(first.next_cursor + "==")
    )
    cursor_payload["o"] = 2**63
    oversized_cursor = base64.urlsafe_b64encode(
        json.dumps(cursor_payload).encode()
    ).decode()
    with pytest.raises(ValueError, match="cursor"):
        service.execute(
            QueryRequest(
                dataset=request.dataset,
                operation=request.operation,
                dimensions=request.dimensions,
                measures=request.measures,
                limit=request.limit,
                cursor=oversized_cursor,
            )
        )


@pytest.mark.parametrize(
    "attack",
    (
        "gpt-synthetic' OR 1=1 --",
        "gpt-synthetic'; DROP TABLE model_calls; --",
        "%' UNION SELECT 1 --",
    ),
)
def test_filters_are_parameters_not_sql_identifiers(
    tmp_path: Path,
    attack: str,
) -> None:
    service, _analytical = _service(tmp_path)
    result = service.execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.ROWS,
            dimensions=("model",),
            measures=("calls",),
            filters=(Filter("model", "eq", attack),),
            limit=25,
        )
    )
    assert result.matched_count == 0
    assert result.rows == ()


def test_period_comparison_returns_exact_current_previous_and_change(
    tmp_path: Path,
) -> None:
    service, _analytical = _service(tmp_path)
    result = service.execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.COMPARISON,
            dimensions=("model",),
            measures=("calls", "total_tokens"),
            comparison=ComparisonWindow(
                current_start="2026-01-01T00:00:02Z",
                current_end="2026-01-02T00:00:00Z",
                previous_start="2026-01-01T00:00:00Z",
                previous_end="2026-01-01T00:00:02Z",
            ),
            limit=25,
        )
    )

    assert result.plan_id == "calls.comparison.v1"
    assert result.rows == (
        {
            "model": "gpt-synthetic",
            "current_calls": 1,
            "previous_calls": 1,
            "change_calls": 0,
            "change_percent_calls": 0.0,
            "current_total_tokens": 23,
            "previous_total_tokens": 12,
            "change_total_tokens": 11,
            "change_percent_total_tokens": 91.66666666666667,
        },
    )
    assert result.scanned_count == 2

    offset_result = service.execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.COMPARISON,
            dimensions=("model",),
            measures=("calls", "total_tokens"),
            comparison=ComparisonWindow(
                current_start="2025-12-31T19:00:02-05:00",
                current_end="2026-01-01T19:00:00-05:00",
                previous_start="2025-12-31T19:00:00-05:00",
                previous_end="2025-12-31T19:00:02-05:00",
            ),
            limit=25,
        )
    )
    assert offset_result.rows == result.rows
    assert offset_result.normalized_scope["comparison"] == {
        "current_start": "2026-01-01T00:00:02Z",
        "current_end": "2026-01-02T00:00:00Z",
        "previous_start": "2026-01-01T00:00:00Z",
        "previous_end": "2026-01-01T00:00:02Z",
    }


def test_query_catalog_supports_every_kernel_dataset(
    tmp_path: Path,
) -> None:
    service, _analytical = _service(tmp_path)
    requests = (
        QueryRequest("calls", Operation.ROWS, ("call",), ("total_tokens",)),
        QueryRequest("turns", Operation.AGGREGATE, (), ("turns",)),
        QueryRequest("threads", Operation.ROWS, ("thread",), ("threads",)),
        QueryRequest("tools", Operation.AGGREGATE, (), ("tools",)),
        QueryRequest(
            "activities",
            Operation.TIMELINE,
            ("activity", "event_at"),
            ("activities",),
        ),
        QueryRequest(
            "phases",
            Operation.TIMELINE,
            ("event_at", "phase", "turn"),
            ("activities", "total_tokens"),
            (Filter("event_at", "gte", "2026-01-01T00:00:00Z"),),
        ),
        QueryRequest(
            "allowance",
            Operation.ROWS,
            ("allowance",),
            (
                "allowance_used_percent",
                "allowance_burn_rate",
                "local_tokens_per_percentage_point",
            ),
        ),
    )

    results = service.execute_batch(requests)

    assert tuple(result.dataset for result in results) == (
        "calls",
        "turns",
        "threads",
        "tools",
        "activities",
        "phases",
        "allowance",
    )
    assert all(result.scanned_count is not None for result in results)
    assert results[5].plan_id == "phases.timeline.v1"
    assert results[5].grade == "deterministic"
    assert results[6].grade == "exact"
    assert any(
        row["local_tokens_per_percentage_point"] == 11.5
        for row in results[6].rows
    )
    assert results[6].coverage["measures"]["allowance_burn_rate"]["basis"] == (
        "deterministic_adjacent_observations"
    )


def test_phase_rows_honor_projection_order_and_actual_wrapper_unknown(
    tmp_path: Path,
) -> None:
    service, _analytical = _service(tmp_path)
    result = service.execute(
        QueryRequest(
            "phases",
            Operation.ROWS,
            ("event_at", "phase"),
            ("activities", "total_tokens"),
            (Filter("event_at", "gte", "2026-01-01T00:00:00Z"),),
            order_by="event_at",
            descending=False,
        )
    )

    assert result.plan_id == "phases.rows.v1"
    assert result.grade == "deterministic"
    assert [row["event_at"] for row in result.rows] == sorted(
        row["event_at"] for row in result.rows
    )
    assert all(
        set(row)
        == {
            "event_at",
            "phase",
            "activities",
            "total_tokens",
            "basis",
            "confidence",
            "segmenter_version",
            "token_attribution",
        }
        for row in result.rows
    )
    assert any(row["phase"] == "unknown" for row in result.rows)
    assert result.coverage["measures"]["total_tokens"]["basis"] == (
        "deterministic_attribution"
    )


def test_missing_tool_observations_are_partial_not_zero(tmp_path: Path) -> None:
    service, _analytical = _service(tmp_path)
    result = service.execute(
        QueryRequest(
            "tools",
            Operation.AGGREGATE,
            (),
            ("duration_ms", "output_bytes", "tools"),
        )
    )

    assert result.rows == (
        {"duration_ms": None, "output_bytes": None, "tools": 1},
    )
    assert result.grade == "exact"
    assert result.coverage["measures"]["duration_ms"] == {
        "basis": "upstream_observed",
        "observed_count": 0,
        "missing_count": 1,
        "coverage_percent": 0.0,
        "limitations": ["null upstream observations are excluded"],
    }


def test_named_plan_has_explainable_static_sql(tmp_path: Path) -> None:
    _service_instance, analytical = _service(tmp_path)
    request = QueryRequest(
        "calls",
        Operation.AGGREGATE,
        ("model",),
        ("calls", "total_tokens"),
        (Filter("event_at", "gte", "2026-01-01T00:00:00Z"),),
    ).normalized()
    plan = compile_plan(request, generation=1, offset=0)

    with sqlite3.connect(analytical) as connection:
        details = [
            str(row[3])
            for row in connection.execute(
                f"EXPLAIN QUERY PLAN {plan.sql}",
                plan.parameters,
            )
        ]

    assert plan.plan_id == "calls.aggregate.v1"
    assert any("model_calls" in detail for detail in details)
    assert all("raw" not in detail.lower() for detail in details)

    row_plan = compile_plan(
        QueryRequest(
            "calls",
            Operation.ROWS,
            ("model",),
            ("calls",),
        ).normalized(),
        generation=1,
        offset=0,
    )
    assert "model_calls.canonical_call_id ASC" in row_plan.sql

    comparison_plan = compile_plan(
        QueryRequest(
            "calls",
            Operation.COMPARISON,
            ("model",),
            ("calls",),
            comparison=ComparisonWindow(
                "2026-01-02T00:00:00Z",
                "2026-01-03T00:00:00Z",
                "2026-01-01T00:00:00Z",
                "2026-01-02T00:00:00Z",
            ),
        ).normalized(),
        generation=1,
        offset=0,
    )
    assert "current_calls DESC, model ASC" in comparison_plan.sql


def test_batch_read_snapshot_is_stable_during_concurrent_commit(
    tmp_path: Path,
) -> None:
    service, analytical = _service(tmp_path)

    class MutatingService(QueryService):
        mutated = False

        def _execute_one(  # type: ignore[override]
            self,
            connection: sqlite3.Connection,
            request: QueryRequest,
            generation: int,
        ):
            result = super()._execute_one(connection, request, generation)
            if not self.mutated:
                with short_writer_transaction(analytical) as writer:
                    writer.execute(
                        "UPDATE threads SET project_label = 'changed-after-snapshot'"
                    )
                self.mutated = True
            return result

    concurrent = MutatingService(service._operational_path)
    request = QueryRequest(
        "threads",
        Operation.ROWS,
        ("project", "thread"),
        ("threads",),
    )
    first, second = concurrent.execute_batch((request, request))
    after = concurrent.execute(request)

    assert first.rows == second.rows
    assert first.rows[0]["project"] is None
    assert after.rows[0]["project"] == "changed-after-snapshot"


def test_query_totals_match_frozen_accounting_oracle(tmp_path: Path) -> None:
    expected = json.loads(
        (_ORACLE_ROOT / "expected.json").read_text(encoding="utf-8")
    )["expected"]["token_totals"]
    sources = sorted((_ORACLE_ROOT / "logs").rglob("*.jsonl"))
    paths = kernel_paths(tmp_path / "oracle-cache")
    KernelIngestor(paths.analytical, paths.operational).refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="query-oracle",
    )
    result = QueryService(paths.operational).execute(
        QueryRequest(
            "calls",
            Operation.AGGREGATE,
            (),
            (
                "calls",
                "input_tokens",
                "cached_input_tokens",
                "uncached_input_tokens",
                "reasoning_tokens",
                "output_tokens",
                "total_tokens",
            ),
        )
    )

    assert result.rows == (
        {
            "calls": 4,
            "input_tokens": expected["input_tokens"],
            "cached_input_tokens": expected["cached_input_tokens"],
            "uncached_input_tokens": expected["uncached_input_tokens"],
            "reasoning_tokens": expected["reasoning_output_tokens"],
            "output_tokens": expected["output_tokens"],
            "total_tokens": expected["total_tokens"],
        },
    )


def _service(tmp_path: Path) -> tuple[QueryService, Path]:
    source = tmp_path / "sessions" / "rollout-query.jsonl"
    source.parent.mkdir()
    rows = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "query-session"},
        },
        {
            "timestamp": "2026-01-01T00:00:00.500Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "functions.exec_command",
            },
        },
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-1",
                "model": "gpt-synthetic",
                "effort": "low",
            },
        },
        _token_row("event-1", 10, 3, 2, 1),
        _token_row("event-2", 20, 5, 3, 2),
    ]
    source.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="query-fixture",
    )
    return QueryService(paths.operational), paths.analytical


def _token_row(
    event_id: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "timestamp": f"2026-01-01T00:00:0{1 if event_id.endswith('1') else 2}Z",
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "plan_type": "synthetic",
                "limit_id": "query-limit",
                "primary": {
                    "used_percent": 10 if event_id.endswith("1") else 12,
                    "window_minutes": 300,
                    "resets_at": 1767243600,
                },
            },
            "info": {
                "last_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_output_tokens": reasoning_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            },
        },
    }
