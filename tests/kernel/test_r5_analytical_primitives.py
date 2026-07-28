from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.allowance import AllowanceService
from codex_usage_tracker.kernel.application import RuntimePaths
from codex_usage_tracker.kernel.evidence import EvidenceRequest, EvidenceService
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import load_cutover_control
from codex_usage_tracker.kernel.query import QueryService
from codex_usage_tracker.kernel.query.contracts import Operation, QueryRequest
from codex_usage_tracker.kernel.query.plans import compile_plan
from codex_usage_tracker.kernel.thread_labels import load_thread_label_hashes


def test_thread_results_pair_prompt_derived_label_with_stable_selector(
    tmp_path: Path,
) -> None:
    runtime, _source = _refresh_r5_fixture(tmp_path)

    result = QueryService(runtime.kernel.operational).execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.AGGREGATE,
            dimensions=("thread",),
            measures=("total_tokens",),
        )
    )

    assert result.rows == (
        {
            "thread": result.rows[0]["thread"],
            "thread_label": "Investigate fast usage",
            "total_tokens": 28,
        },
    )
    assert result.evidence_selectors == (f"thread:{result.rows[0]['thread']}",)
    assert result.coverage["thread_labels"] == {
        "basis": "prompt_derived_session_index_metadata_when_available",
        "fallback": "bounded_opaque_thread_label",
        "sanitized": True,
        "content_included": False,
    }


def test_thread_dimension_compiles_for_datasets_without_thread_labels() -> None:
    activities = compile_plan(
        QueryRequest(
            "activities",
            Operation.AGGREGATE,
            ("thread",),
            ("activities",),
        ).normalized(),
        generation=1,
        offset=0,
    )
    context = compile_plan(
        QueryRequest(
            "context",
            Operation.AGGREGATE,
            ("thread",),
            ("events",),
        ).normalized(),
        generation=1,
        offset=0,
    )

    assert "AS thread_label" not in activities.sql
    assert "AS thread_label" not in context.sql


def test_turn_and_tool_rows_expose_bounded_inference_facts(
    tmp_path: Path,
) -> None:
    runtime, source = _refresh_r5_fixture(tmp_path)
    query = QueryService(runtime.kernel.operational)

    turns = query.execute(
        QueryRequest(
            dataset="turns",
            operation=Operation.ROWS,
            dimensions=(
                "turn",
                "turn_ordinal",
                "completion_basis",
            ),
            measures=("turns", "duration_ms"),
            descending=False,
        )
    )
    assert turns.rows == (
        {
            "turn": turns.rows[0]["turn"],
            "turn_ordinal": 1,
            "completion_basis": "observed_event",
            "turns": 1,
            "duration_ms": pytest.approx(200.0, abs=0.01),
        },
    )

    tool_identity, tool_semantics, tool_impact = query.execute_batch(
        (
            QueryRequest(
                dataset="tools",
                operation=Operation.ROWS,
                dimensions=("tool_call", "thread", "turn"),
                measures=(),
                descending=False,
            ),
            QueryRequest(
                dataset="tools",
                operation=Operation.ROWS,
                dimensions=("tool_call", "operation", "target"),
                measures=("duration_ms", "output_bytes"),
                descending=False,
            ),
            QueryRequest(
                dataset="tools",
                operation=Operation.ROWS,
                dimensions=("tool_call", "status", "impact_grade"),
                measures=(
                    "adjacent_uncached_input_tokens",
                    "adjacent_cached_input_tokens",
                    "adjacent_reasoning_tokens",
                    "adjacent_output_tokens",
                    "adjacent_total_tokens",
                ),
                descending=False,
            ),
        )
    )
    assert tool_identity.rows == (
        {
            "tool_call": tool_identity.rows[0]["tool_call"],
            "thread": tool_identity.rows[0]["thread"],
            "thread_label": "Investigate fast usage",
            "turn": tool_identity.rows[0]["turn"],
        },
    )
    assert tool_semantics.rows == (
        {
            "tool_call": tool_semantics.rows[0]["tool_call"],
            "operation": "read",
            "target": "src/example.py",
            "duration_ms": pytest.approx(50.0),
            "output_bytes": len(b"synthetic result"),
        },
    )
    assert tool_impact.rows == (
        {
            "tool_call": tool_impact.rows[0]["tool_call"],
            "status": "completed",
            "impact_grade": "deterministic_adjacent_call",
            "adjacent_uncached_input_tokens": 15,
            "adjacent_cached_input_tokens": 5,
            "adjacent_reasoning_tokens": 3,
            "adjacent_output_tokens": 8,
            "adjacent_total_tokens": 28,
        },
    )
    persisted = runtime.kernel.analytical.read_bytes()
    assert b"PRIVATE_SYNTHETIC_ARGUMENT" not in persisted
    assert b"synthetic result" not in persisted
    assert str(source.resolve()).encode() not in persisted


def test_query_cost_and_credit_estimates_are_explicit_and_covered(
    tmp_path: Path,
) -> None:
    runtime, _source = _refresh_r5_fixture(tmp_path)
    _write_rate_card(runtime.rate_card)

    result = QueryService(
        runtime.kernel.operational,
        rate_card_path=runtime.rate_card,
    ).execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.AGGREGATE,
            dimensions=(),
            measures=(
                "uncached_input_tokens",
                "cached_input_tokens",
                "reasoning_tokens",
                "output_tokens",
                "total_tokens",
                "configured_cost_usd",
                "estimated_credits",
            ),
        )
    )

    assert result.rows == (
        {
            "uncached_input_tokens": 15,
            "cached_input_tokens": 5,
            "reasoning_tokens": 3,
            "output_tokens": 8,
            "total_tokens": 28,
            "configured_cost_usd": pytest.approx(0.0000335),
            "estimated_credits": pytest.approx(0.000082),
        },
    )
    assert result.coverage["measures"]["configured_cost_usd"] == {
        "basis": "configured_dated_rate_card",
        "observed_count": 1,
        "missing_count": 0,
        "coverage_percent": 100.0,
        "limitations": [
            "configured token cost is a dated local rate-card calculation, not observed billing"
        ],
        "provenance": {
            "name": "Synthetic rates",
            "url": "https://example.invalid/rates",
            "effective_at": "2026-07-01",
            "fetched_at": "2026-07-01T00:00:00Z",
        },
        "confidence": "estimated",
    }
    assert result.coverage["measures"]["estimated_credits"]["basis"] == (
        "explicit_local_credit_rate_card_estimate"
    )
    assert result.grade == "estimated"


def test_allowance_bands_are_time_first_and_keep_four_token_classes(
    tmp_path: Path,
) -> None:
    runtime, _source = _refresh_r5_fixture(tmp_path)
    result = AllowanceService(
        runtime.kernel.operational,
        runtime.rate_card,
    ).read()

    interval = result["rows"][0]
    assert tuple(interval)[:4] == (
        "interval_start",
        "interval_end",
        "window_kind",
        "allowance_observation_id",
    )
    assert interval["interval_start"] is None
    assert interval["interval_end"] == "2026-07-27T12:00:00.150000Z"
    assert interval["local_usage"] == {
        "uncached_input_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "output_tokens": 0,
        "calls": 0,
        "turns": 0,
        "total_tokens": 0,
    }
    assert interval["observed_allowance_drain"] is None
    assert interval["allowance_attribution"] == ("interval_observation_not_revealing_call")


def test_copied_sources_are_excluded_from_every_foundational_aggregate(
    tmp_path: Path,
) -> None:
    runtime, source = _refresh_r5_fixture(tmp_path)
    archived = runtime.codex_home / "archived_sessions" / source.name
    archived.parent.mkdir(parents=True)
    shutil.copyfile(source, archived)
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [archived, source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-copy-contract",
    )
    query = QueryService(runtime.kernel.operational)

    results = query.execute_batch(
        (
            QueryRequest("calls", Operation.AGGREGATE, (), ("calls",)),
            QueryRequest("tools", Operation.AGGREGATE, (), ("tools",)),
            QueryRequest("turns", Operation.AGGREGATE, (), ("turns",)),
            QueryRequest("threads", Operation.AGGREGATE, (), ("threads",)),
            QueryRequest(
                "tools",
                Operation.AGGREGATE,
                ("operation", "target"),
                ("tools",),
            ),
        )
    )

    assert [result.rows[0][result.dataset] for result in results[:4]] == [
        1,
        1,
        1,
        1,
    ]
    assert results[4].rows == ({"operation": "read", "target": "src/example.py", "tools": 1},)


def test_session_index_label_changes_do_not_require_transcript_reparse(
    tmp_path: Path,
) -> None:
    runtime, _source = _refresh_r5_fixture(tmp_path)
    index = runtime.codex_home / "session_index.jsonl"
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["thread_name"] = "Renamed after refresh"
    index.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    result = QueryService(
        runtime.kernel.operational,
        thread_labels=load_thread_label_hashes(runtime.codex_home),
    ).execute(
        QueryRequest(
            "calls",
            Operation.AGGREGATE,
            ("thread",),
            ("total_tokens",),
        )
    )

    assert result.rows[0]["thread_label"] == "Renamed after refresh"


def test_parser_upgrade_replaces_once_then_returns_to_no_changes(
    tmp_path: Path,
) -> None:
    runtime, source = _refresh_r5_fixture(tmp_path)
    initial = load_cutover_control(runtime.kernel.operational)
    assert initial.active_kernel_path is not None
    with sqlite3.connect(initial.active_kernel_path) as connection:
        connection.execute("UPDATE sources SET parser_version = '1'")

    upgraded = KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-parser-upgrade",
    )
    unchanged = KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-parser-no-change",
    )

    promoted = load_cutover_control(runtime.kernel.operational)
    assert promoted.active_kernel_path is not None
    with sqlite3.connect(promoted.active_kernel_path) as connection:
        assert connection.execute("SELECT parser_version FROM sources").fetchone() == ("2",)
        assert connection.execute("SELECT COUNT(*) FROM tool_calls").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM turns").fetchone() == (1,)
    assert upgraded.planner_reason == "replace_source"
    assert upgraded.generation == 2
    assert unchanged.planner_reason == "no_changes"
    assert unchanged.generation == 2


def test_append_completes_existing_turn_without_double_counting_tool(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    events = _r5_events()
    source = _write_r5_source(runtime, events[:-1])
    ingestor = KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    )
    first = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-open-turn",
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(events[-1], separators=(",", ":")) + "\n")
    completed = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-complete-turn",
    )

    active = load_cutover_control(runtime.kernel.operational).active_kernel_path
    assert active is not None
    with sqlite3.connect(active) as connection:
        assert connection.execute(
            """
            SELECT model_call_count, tool_call_count
            FROM turns
            """
        ).fetchone() == (1, 1)
        assert connection.execute("SELECT COUNT(*) FROM tool_calls").fetchone() == (1,)
    turn = (
        QueryService(runtime.kernel.operational)
        .execute(
            QueryRequest(
                "turns",
                Operation.ROWS,
                ("turn", "status", "completion_basis"),
                ("duration_ms",),
            )
        )
        .rows[0]
    )
    assert turn == {
        "turn": turn["turn"],
        "status": "completed",
        "completion_basis": "observed_event",
        "duration_ms": pytest.approx(200.0, abs=0.02),
    }
    evidence = (
        EvidenceService(runtime.kernel.operational)
        .read(EvidenceRequest(f"turn:{turn['turn']}"))
        .rows[0]
    )
    assert evidence["status"] == "completed"
    assert evidence["completion_basis"] == "observed_event"
    assert evidence["model_call_count"] == 1
    assert evidence["tool_call_count"] == 1
    service = EvidenceService(runtime.kernel.operational)
    for view in ("calls", "tools", "timeline"):
        rows = service.read(EvidenceRequest(f"turn:{turn['turn']}", view=view)).rows
        assert rows
        relevant = (
            [row for row in rows if row["event_kind"] != "activity"]
            if view == "timeline"
            else list(rows)
        )
        assert all(
            row.get("completion_basis") == "observed_event" for row in relevant
        ), (view, rows)
    assert first.inserted_tools == 1
    assert completed.planner_reason == "append_safe"
    assert completed.inserted_tools == 0


def test_tool_completion_crosses_parser_batch_without_losing_metadata(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    session_id = "00000000-0000-4000-8000-000000000506"
    lines: list[dict[str, object]] = [
        {
            "timestamp": "2026-07-27T12:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": session_id},
        },
        {
            "timestamp": "2026-07-27T12:00:00.000Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-batch", "model": "gpt-r5"},
        },
    ]
    lines.extend(
        {
            "timestamp": "2026-07-27T12:00:00.010Z",
            "type": "event_msg",
            "payload": {"type": "synthetic_ignored"},
        }
        for _ in range(997)
    )
    lines.extend(
        (
            {
                "timestamp": "2026-07-27T12:00:00.050Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "functions.read_file",
                    "call_id": "call-cross-batch",
                    "arguments": json.dumps({"path": "src/cross_batch.py"}),
                },
            },
            {
                "timestamp": "2026-07-27T12:00:00.100Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-cross-batch",
                    "output": "bounded synthetic output",
                },
            },
        )
    )
    source = _write_r5_source(runtime, tuple(lines))
    result = KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-cross-batch",
    )

    row = (
        QueryService(runtime.kernel.operational)
        .execute(
            QueryRequest(
                "tools",
                Operation.ROWS,
                ("operation", "target", "status"),
                ("duration_ms", "output_bytes"),
            )
        )
        .rows[0]
    )
    assert result.inserted_tools == 1
    assert row == {
        "operation": "read",
        "target": "src/cross_batch.py",
        "status": "completed",
        "duration_ms": pytest.approx(50.0, abs=0.02),
        "output_bytes": len(b"bounded synthetic output"),
    }


def test_tool_completion_appends_without_counting_a_second_tool(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    events = _r5_events()
    source = _write_r5_source(runtime, events[:3])
    ingestor = KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    )
    first = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-tool-start",
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(line, separators=(",", ":")) + "\n" for line in events[3:]))
    completed = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-tool-complete",
    )

    tool = (
        QueryService(runtime.kernel.operational)
        .execute(
            QueryRequest(
                "tools",
                Operation.ROWS,
                ("status",),
                ("duration_ms", "output_bytes"),
            )
        )
        .rows[0]
    )
    assert first.inserted_tools == 1
    assert completed.inserted_tools == 0
    assert tool == {
        "status": "completed",
        "duration_ms": pytest.approx(50.0, abs=0.02),
        "output_bytes": len(b"synthetic result"),
    }


@pytest.mark.parametrize(
    "unsafe_target",
    (
        "/Users/synthetic/private/secret.py",
        "~/.ssh/id_rsa",
        r"C:\Users\synthetic\secret.txt",
        r"\\server\share\secret.txt",
        "file:///Users/synthetic/private/secret.py",
        "https://example.invalid/private",
    ),
)
def test_non_project_relative_tool_target_is_rejected_instead_of_persisted(
    tmp_path: Path,
    unsafe_target: str,
) -> None:
    runtime = _runtime(tmp_path)
    events = list(_r5_events())
    tool_payload = events[2]["payload"]
    assert isinstance(tool_payload, dict)
    tool_payload["arguments"] = json.dumps({"path": unsafe_target})
    source = _write_r5_source(runtime, tuple(events))
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-absolute-target",
    )

    row = (
        QueryService(runtime.kernel.operational)
        .execute(QueryRequest("tools", Operation.ROWS, ("target",), ()))
        .rows[0]
    )
    active = load_cutover_control(runtime.kernel.operational).active_kernel_path
    assert active is not None
    assert row["target"] is None
    assert unsafe_target.encode() not in active.read_bytes()


def test_repeated_same_timestamp_tools_without_upstream_ids_remain_distinct(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    events = (
        _session_event(),
        _turn_event("turn-r5-missing-id"),
        {
            "timestamp": "2026-07-27T12:00:00.050Z",
            "type": "event_msg",
            "payload": {
                "type": "mcp_tool_call_end",
                "tool_name": "usage_query",
                "server_name": "synthetic",
                "result": {"row": 1},
            },
        },
        {
            "timestamp": "2026-07-27T12:00:00.050Z",
            "type": "event_msg",
            "payload": {
                "type": "mcp_tool_call_end",
                "tool_name": "usage_query",
                "server_name": "synthetic",
                "result": {"row": 2},
            },
        },
    )
    source = _write_r5_source(runtime, events)
    KernelIngestor(runtime.kernel.analytical, runtime.kernel.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-missing-tool-id",
    )

    result = QueryService(runtime.kernel.operational).execute(
        QueryRequest("tools", Operation.AGGREGATE, (), ("tools",))
    )

    assert result.rows == ({"tools": 2},)


def test_structured_tool_output_uses_normalized_byte_basis(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    result_payload = {"unicode": "λ", "escaped": "\n", "items": [2, 1]}
    source = _write_r5_source(
        runtime,
        (
            _session_event(),
            _turn_event("turn-r5-structured-output"),
            {
                "timestamp": "2026-07-27T12:00:00.050Z",
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "tool_name": "usage_query",
                    "server_name": "synthetic",
                    "call_id": "structured-output",
                    "result": result_payload,
                },
            },
        ),
    )
    KernelIngestor(runtime.kernel.analytical, runtime.kernel.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-structured-output",
    )

    result = QueryService(runtime.kernel.operational).execute(
        QueryRequest("tools", Operation.ROWS, (), ("output_bytes",))
    )

    expected = len(
        json.dumps(
            result_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    assert result.rows == ({"output_bytes": expected},)
    assert result.coverage["measures"]["output_bytes"]["basis"] == (
        "deterministic_normalized_tool_output_utf8_bytes"
    )


def test_invalid_rate_card_does_not_disable_unpriced_query_or_allowance(
    tmp_path: Path,
) -> None:
    runtime, _source = _refresh_r5_fixture(tmp_path)
    runtime.rate_card.parent.mkdir(parents=True, exist_ok=True)
    runtime.rate_card.write_text("{invalid", encoding="utf-8")
    service = QueryService(
        runtime.kernel.operational,
        rate_card_path=runtime.rate_card,
    )

    tokens = service.execute(
        QueryRequest("calls", Operation.AGGREGATE, (), ("total_tokens",))
    )
    priced = service.execute(
        QueryRequest("calls", Operation.AGGREGATE, (), ("configured_cost_usd",))
    )
    allowance = AllowanceService(
        runtime.kernel.operational,
        runtime.rate_card,
    ).read()

    assert tokens.rows == ({"total_tokens": 28},)
    assert priced.rows == ({"configured_cost_usd": None},)
    assert priced.coverage["rate_card"]["status"] == "invalid"
    assert allowance["rows"]
    assert allowance["coverage"]["pricing"]["status"] == "invalid"


def test_moving_tail_relinks_tool_to_following_model_call(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    source = _write_r5_source(
        runtime,
        (
            _session_event(),
            _turn_event("turn-r5-moving-tail"),
            _token_event(
                "preceding",
                "2026-07-27T12:00:00.010Z",
                input_tokens=10,
                output_tokens=1,
            ),
            {
                "timestamp": "2026-07-27T12:00:00.020Z",
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "tool_name": "usage_query",
                    "server_name": "synthetic",
                    "call_id": "moving-tail-tool",
                    "result": "done",
                },
            },
        ),
    )
    ingestor = KernelIngestor(runtime.kernel.analytical, runtime.kernel.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-moving-tail-first",
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                _token_event(
                    "following",
                    "2026-07-27T12:00:00.030Z",
                    input_tokens=100,
                    output_tokens=2,
                ),
                separators=(",", ":"),
            )
            + "\n"
        )
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-moving-tail-following",
    )

    result = QueryService(runtime.kernel.operational).execute(
        QueryRequest(
            "tools",
            Operation.ROWS,
            (),
            ("adjacent_total_tokens",),
        )
    )

    assert result.rows == ({"adjacent_total_tokens": 102},)
    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path is not None
    assert control.active_generation == 2
    with sqlite3.connect(control.active_kernel_path) as connection:
        persisted = connection.execute(
            """
            SELECT operation, target_label, calls, duration_ms, output_bytes
            FROM rollup_tool_operation
            WHERE generation = 2
            ORDER BY operation, target_label
            """
        ).fetchall()
        exact = connection.execute(
            """
            SELECT profiles.operation, COALESCE(facts.target_label, ''),
                   COUNT(*), COALESCE(SUM(facts.duration_ms), 0.0),
                   COALESCE(SUM(facts.output_bytes), 0)
            FROM tool_call_facts AS facts
            JOIN tool_profiles AS profiles USING (tool_profile_key)
            WHERE facts.generation <= 2
            GROUP BY profiles.operation, COALESCE(facts.target_label, '')
            ORDER BY profiles.operation, COALESCE(facts.target_label, '')
            """
        ).fetchall()
    assert persisted == exact


def test_failed_tool_update_never_mutates_active_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    events = _r5_events()
    source = _write_r5_source(runtime, events[:3])
    ingestor = KernelIngestor(runtime.kernel.analytical, runtime.kernel.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-isolation-first",
    )
    active_before = load_cutover_control(runtime.kernel.operational).active_kernel_path
    assert active_before is not None
    with source.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(events[3], separators=(",", ":")) + "\n")

    def fail_before_promotion(
        candidate: Path,
        generation: int,
        **_kwargs: object,
    ) -> None:
        assert candidate != active_before
        assert generation == 2
        current = QueryService(runtime.kernel.operational).execute(
            QueryRequest("tools", Operation.ROWS, ("status",), ())
        )
        assert current.rows == ({"status": "started"},)
        raise RuntimeError("synthetic promotion failure")

    monkeypatch.setattr(ingestor, "_promote", fail_before_promotion)
    with pytest.raises(RuntimeError, match="synthetic promotion failure"):
        ingestor.refresh(
            [source],
            trigger=RefreshTrigger.CLI_REFRESH,
            owner_id="r5-isolation-failure",
        )

    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path == active_before
    assert control.active_generation == 1
    with sqlite3.connect(active_before) as connection:
        assert connection.execute(
            "SELECT status, generation FROM tool_calls"
        ).fetchone() == ("started", 1)


def test_structural_only_copies_have_one_canonical_owner_and_evidence_row(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    source = _write_r5_source(
        runtime,
        (
            _session_event(),
            _turn_event("turn-r5-structural-copy"),
            {
                "timestamp": "2026-07-27T12:00:00.100Z",
                "type": "event_msg",
                "payload": {"type": "task_complete"},
            },
        ),
    )
    archived = runtime.codex_home / "archived_sessions" / source.name
    archived.parent.mkdir(parents=True)
    shutil.copyfile(source, archived)
    KernelIngestor(runtime.kernel.analytical, runtime.kernel.operational).refresh(
        [archived, source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-structural-copy",
    )
    query = QueryService(runtime.kernel.operational)

    threads, turns = query.execute_batch(
        (
            QueryRequest("threads", Operation.ROWS, ("thread",), ("threads",)),
            QueryRequest("turns", Operation.ROWS, ("turn",), ("turns",)),
        )
    )

    assert len(threads.rows) == 1
    assert len(turns.rows) == 1
    thread_evidence = EvidenceService(runtime.kernel.operational).read(
        EvidenceRequest(f"thread:{threads.rows[0]['thread']}")
    )
    turn_evidence = EvidenceService(runtime.kernel.operational).read(
        EvidenceRequest(f"turn:{turns.rows[0]['turn']}")
    )
    assert thread_evidence.matched_count == 1
    assert turn_evidence.matched_count == 1


def test_partial_rate_coverage_keeps_unrated_usage_visible(
    tmp_path: Path,
) -> None:
    runtime, source = _refresh_r5_fixture(tmp_path)
    _write_rate_card(runtime.rate_card)
    extra = (
        {
            "timestamp": "2026-07-27T12:01:00.000Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-r5-unrated",
                "model": "gpt-unrated",
                "effort": "low",
            },
        },
        {
            "event_id": "event-r5-unrated",
            "timestamp": "2026-07-27T12:01:00.100Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 0,
                        "reasoning_output_tokens": 1,
                        "output_tokens": 2,
                        "total_tokens": 13,
                    }
                },
            },
        },
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(line, separators=(",", ":")) + "\n" for line in extra))
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-partial-rates",
    )

    result = QueryService(
        runtime.kernel.operational,
        rate_card_path=runtime.rate_card,
    ).execute(
        QueryRequest(
            "calls",
            Operation.AGGREGATE,
            (),
            ("calls", "total_tokens", "configured_cost_usd"),
        )
    )

    assert result.rows == (
        {
            "calls": 2,
            "total_tokens": 40,
            "configured_cost_usd": pytest.approx(0.0000335),
        },
    )
    assert result.coverage["measures"]["configured_cost_usd"]["observed_count"] == 1
    assert result.coverage["measures"]["configured_cost_usd"]["missing_count"] == 1
    assert result.coverage["measures"]["configured_cost_usd"]["coverage_percent"] == 50.0


def _refresh_r5_fixture(tmp_path: Path) -> tuple[RuntimePaths, Path]:
    runtime = _runtime(tmp_path)
    source = _write_r5_source(runtime, _r5_events())
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r5-contract",
    )
    return runtime, source


def _runtime(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths(
        codex_home=tmp_path / "codex-home",
        cache_root=tmp_path / "cache",
    )


def _write_r5_source(
    runtime: RuntimePaths,
    lines: tuple[dict[str, object], ...],
) -> Path:
    _write_session_index(runtime)
    source = runtime.codex_home / "sessions" / "2026" / "07" / "27" / "rollout-r5-session.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        "".join(json.dumps(line, separators=(",", ":")) + "\n" for line in lines),
        encoding="utf-8",
    )
    return source


def _r5_events() -> tuple[dict[str, object], ...]:
    session_id = "00000000-0000-4000-8000-000000000505"
    return (
        {
            "timestamp": "2026-07-27T12:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": session_id},
        },
        {
            "timestamp": "2026-07-27T12:00:00.000Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-r5-1",
                "model": "gpt-r5",
                "effort": "high",
            },
        },
        {
            "timestamp": "2026-07-27T12:00:00.050Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "functions.read_file",
                "call_id": "call-r5-tool",
                "arguments": json.dumps(
                    {
                        "path": "src/example.py",
                        "private": "PRIVATE_SYNTHETIC_ARGUMENT",
                    }
                ),
            },
        },
        {
            "timestamp": "2026-07-27T12:00:00.100Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-r5-tool",
                "output": "synthetic result",
            },
        },
        {
            "event_id": "event-r5-call",
            "timestamp": "2026-07-27T12:00:00.150Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 20,
                        "cached_input_tokens": 5,
                        "reasoning_output_tokens": 3,
                        "output_tokens": 8,
                        "total_tokens": 28,
                    },
                    "model_context_window": 200_000,
                },
                "rate_limits": {
                    "plan_type": "synthetic",
                    "limit_id": "synthetic-limit",
                    "primary": {
                        "used_percent": 10.0,
                        "window_minutes": 300,
                        "resets_at": 1_785_170_000,
                    },
                },
            },
        },
        {
            "timestamp": "2026-07-27T12:00:00.200Z",
            "type": "event_msg",
            "payload": {"type": "task_complete"},
        },
    )


def _session_event() -> dict[str, object]:
    return {
        "timestamp": "2026-07-27T12:00:00.000Z",
        "type": "session_meta",
        "payload": {"id": "00000000-0000-4000-8000-000000000505"},
    }


def _turn_event(turn_id: str) -> dict[str, object]:
    return {
        "timestamp": "2026-07-27T12:00:00.000Z",
        "type": "turn_context",
        "payload": {"turn_id": turn_id, "model": "gpt-r5"},
    }


def _token_event(
    event_id: str,
    timestamp: str,
    *,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "last_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": 0,
                    "reasoning_output_tokens": 0,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            },
        },
    }


def _write_session_index(runtime: RuntimePaths) -> None:
    runtime.codex_home.mkdir(parents=True, exist_ok=True)
    runtime.codex_home.joinpath("session_index.jsonl").write_text(
        json.dumps(
            {
                "id": "00000000-0000-4000-8000-000000000505",
                "thread_name": "  Investigate\n\tfast   usage  ",
                "updated_at": "2026-07-27T12:00:00.300Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_rate_card(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "codex-usage-tracker.kernel-rate-card.v1",
                "source": {
                    "name": "Synthetic rates",
                    "url": "https://example.invalid/rates",
                    "effective_at": "2026-07-01",
                    "fetched_at": "2026-07-01T00:00:00Z",
                },
                "models": {
                    "gpt-r5": {
                        "input_per_million": 1.0,
                        "cached_input_per_million": 0.5,
                        "output_per_million": 2.0,
                        "credits_input_per_million": 3.0,
                        "credits_cached_input_per_million": 1.0,
                        "credits_output_per_million": 4.0,
                        "confidence": "estimated",
                    }
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
