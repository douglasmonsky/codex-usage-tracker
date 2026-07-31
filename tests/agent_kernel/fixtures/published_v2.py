"""Synthetic structural-v2 source records and real CK-06/CK-07 publication."""

from __future__ import annotations

import copy
import json
import sqlite3
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
)
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    estimate_change_set,
)
from codex_usage_tracker.agent_kernel.publication.rate_cards import (
    attach_rate_card_frontier,
    prepare_rate_card_frontier,
)
from codex_usage_tracker.agent_kernel.publication.writer import (
    PublicationRequest,
    PublicationWriter,
    planned_artifact_manifest_sha256,
    prepare_write_set_from_changes,
)
from codex_usage_tracker.agent_kernel.storage.database import initialize_analytical

PUBLICATION_ID = "publication:ck07a-structural-v2"
OLD_DIGEST = "1" * 64
HEAD_DIGEST = "2" * 64

_EVENT_KIND_ORDER = {
    "session_start": 10,
    "turn_start": 20,
    "model_call": 30,
    "compaction_boundary": 35,
    "context_component": 37,
    "tool_start": 40,
    "tool_terminal": 50,
    "state_change": 60,
    "allowance_observation": 70,
    "session_terminal": 80,
}


def _record(
    record_type: str,
    event_at_us: int,
    source_order: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": record_type,
        "event_at_us": event_at_us,
        "event_kind_order": _EVENT_KIND_ORDER[record_type],
        "source_order": source_order,
        "payload": payload,
    }


def structural_records(
    *,
    include_late_call: bool = False,
    null_cached_tokens: bool = False,
    variant_native_turn_id: str = "root-turn",
) -> list[dict[str, Any]]:
    """Return body-free adapter-ingestible records spanning every fact family."""

    records = [
        _record(
            "session_start",
            50,
            1,
            {
                "session_id": "root",
                "project_id": "alpha",
                "parent_session_id": None,
                "state": "running",
            },
        ),
        _record(
            "session_start",
            150,
            2,
            {
                "session_id": "child",
                "project_id": "alpha",
                "parent_session_id": "root",
                "relationship_basis": "structural",
                "state": "running",
            },
        ),
        _record(
            "turn_start",
            75,
            20,
            {
                "session_id": "root",
                "turn_id": "root-turn",
                "turn_ordinal": 1,
                "state": "running",
            },
        ),
        _record(
            "turn_start",
            175,
            40,
            {
                "session_id": "child",
                "turn_id": "child-turn",
                "turn_ordinal": 1,
                "state": "running",
            },
        ),
    ]
    calls = [
        ("before", "root", "root-turn", 100, 21, "synthetic-model", "high", 100, 20, 5, 10),
        ("boundary", "child", "child-turn", 250, 41, "synthetic-model", "high", 200, 40, 10, 20),
        ("other", "child", "child-turn", 300, 42, "synthetic-other", "medium", 300, 60, 15, 30),
    ]
    for (
        call_id,
        session_id,
        turn_id,
        event_at_us,
        source_order,
        model,
        effort,
        uncached,
        cached,
        reasoning,
        output,
    ) in calls:
        records.append(
            _record(
                "model_call",
                event_at_us,
                source_order,
                {
                    "call_id": call_id,
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "turn_ordinal": 1,
                    "model": model,
                    "reasoning_effort": effort,
                    "service_tier": "priority" if effort == "high" else "standard",
                    "context_window_tokens": 128_000,
                    "tokens": {
                        "uncached_input_tokens": uncached,
                        "cached_input_tokens": (
                            None if null_cached_tokens and call_id == "before" else cached
                        ),
                        "reasoning_tokens": reasoning,
                        "output_tokens": output,
                    },
                },
            )
        )
    tools = (
        ("inspect", "read", "file", "file", False, "succeeded", 180, 60),
        ("attempt", "execute", "file", "file", True, "failed", 200, 62),
        ("retry", "test", "test", "test_target", True, "succeeded", 220, 64),
    )
    for tool_id, operation, resource_id, resource_kind, write_intent, state, at, order in tools:
        common = {
            "tool_id": tool_id,
            "session_id": "root",
            "turn_id": "root-turn",
            "turn_ordinal": 1,
            "transport_name": "synthetic",
            "semantic_operation": operation,
            "resource_id": resource_id,
            "resource_kind": resource_kind,
            "project_id": "alpha",
            "write_intent": write_intent,
        }
        records.append(_record("tool_start", at, order, {**common, "state": "running"}))
        records.append(
            _record(
                "tool_terminal",
                at + 25,
                order + 1,
                {**common, "state": state, "duration_us": 25, "output_bytes": 64},
            )
        )
    records.extend(
        [
            _record(
                "state_change",
                210,
                70,
                {
                    "change_id": "file-change",
                    "session_id": "root",
                    "turn_id": "root-turn",
                    "turn_ordinal": 1,
                    "resource_id": "file",
                    "resource_kind": "file",
                    "project_id": "alpha",
                    "change_kind": "modified",
                    "preceding_activity_count": 1,
                    "causal_attribution": None,
                },
            ),
            _record(
                "compaction_boundary",
                230,
                71,
                {
                    "compaction_id": "one",
                    "session_id": "root",
                    "before_context_epoch": "before",
                    "after_context_epoch": "after",
                },
            ),
        ]
    )
    for index, category in enumerate(("tool_output", "workspace_context"), start=1):
        records.append(
            _record(
                "context_component",
                235 + index,
                72 + index,
                {
                    "component_id": f"component-{index}",
                    "session_id": "root",
                    "turn_id": "root-turn",
                    "turn_ordinal": 1,
                    "call_id": "before",
                    "category": category,
                    "observed_utf8_bytes": 1000 * index,
                    "observed_event_count": 1,
                    "estimator": "synthetic",
                    "estimated_tokens": 250 * index,
                    "total_context_utf8_bytes": 5000,
                    "inclusion_basis": "observed_in_source",
                    "capability_basis": "structural",
                    "measurement_basis": "synthetic",
                },
            )
        )
    for index, (observed_at_us, remaining_percent) in enumerate(
        ((90, "90"), (190, "80"), (190, "80"), (290, "70"))
    ):
        records.append(
            _record(
                "allowance_observation",
                observed_at_us,
                80 + index,
                {
                    "provider": "synthetic-provider",
                    "account_local_identity": "synthetic-account",
                    "limit_id": "weekly",
                    "cycle_id": "one",
                    "plan_identity": "synthetic-plan",
                    "window_kind": "rolling_week",
                    "reset_identity": "reset:one",
                    "cycle_start_us": 0,
                    "cycle_end_us": 1000,
                    "completion_status": "completed",
                    "observation_ordinal": index,
                    "used_percent": str(100 - int(remaining_percent)),
                    "remaining_percent": remaining_percent,
                    "observed_at_us": observed_at_us,
                },
            )
        )
    records.extend(
        [
            _record(
                "session_terminal",
                450,
                90,
                {
                    "session_id": "child",
                    "project_id": "alpha",
                    "parent_session_id": "root",
                    "relationship_basis": "structural",
                    "state": "succeeded",
                    "completion_basis": "terminal_event",
                },
            ),
            _record(
                "session_terminal",
                500,
                91,
                {
                    "session_id": "root",
                    "project_id": "alpha",
                    "parent_session_id": None,
                    "state": "succeeded",
                    "completion_basis": "terminal_event",
                },
            ),
        ]
    )
    if include_late_call:
        records.append(
            _record(
                "model_call",
                125,
                92,
                {
                    "call_id": "late",
                    "session_id": "root",
                    "turn_id": "root-turn",
                    "turn_ordinal": 1,
                    "model": "synthetic-model",
                    "reasoning_effort": "high",
                    "service_tier": "priority",
                    "context_window_tokens": 128_000,
                    "tokens": {
                        "uncached_input_tokens": 80,
                        "cached_input_tokens": 10,
                        "reasoning_tokens": 2,
                        "output_tokens": 8,
                    },
                },
            )
        )
    matching_variant_records = [
        record
        for record in records
        if record["type"] == "model_call" and record["payload"].get("call_id") == "before"
    ]
    if len(matching_variant_records) != 1:
        raise ValueError("structural source must contain exactly one variant call")
    matching_variant_records[0]["payload"]["turn_id"] = variant_native_turn_id
    return records


def rate_card_frontier() -> RateCardFrontier:
    rates = {
        "uncached_input_tokens": "1",
        "cached_input_tokens": "1",
        "reasoning_tokens": "1",
        "output_tokens": "1",
    }
    revisions = (
        RateCardRevision(
            rate_card_id=semantic_id("rate-card", [OLD_DIGEST]),
            digest=OLD_DIGEST,
            predecessor_digest=None,
            effective_at_us=0,
            fetched_at_us=900,
            source_name="synthetic-old",
            source_url=None,
            currency="USD",
            model_match_rules=(
                {"match_basis": "model_alias", "model_alias": "synthetic-model"},
                {"match_basis": "model_alias", "model_alias": "synthetic-other"},
            ),
            four_class_rates=rates,
            credit_rates=rates,
            reasoning_in_output=False,
            confidence="synthetic",
            validation_status="valid",
        ),
        RateCardRevision(
            rate_card_id=semantic_id("rate-card", [HEAD_DIGEST]),
            digest=HEAD_DIGEST,
            predecessor_digest=OLD_DIGEST,
            effective_at_us=250,
            fetched_at_us=100,
            source_name="synthetic-new",
            source_url=None,
            currency="USD",
            model_match_rules=(
                {"match_basis": "model_alias", "model_alias": "synthetic-model"},
                {"match_basis": "model_alias", "model_alias": "synthetic-other"},
            ),
            four_class_rates={key: "2" for key in rates},
            credit_rates={key: "2" for key in rates},
            reasoning_in_output=False,
            confidence="synthetic",
            validation_status="valid",
        ),
    )
    return RateCardFrontier(HEAD_DIGEST, revisions)


def publish_structural_snapshot(
    fixture_root: Path,
    database_path: Path,
    *,
    include_late_call: bool = False,
    null_cached_tokens: bool = False,
    variant_native_turn_id: str = "root-turn",
) -> dict[str, int]:
    """Run real CK-06 ingestion and CK-07 publication into database-v1."""

    fixture_root.mkdir(parents=True, exist_ok=True)
    payload = b"".join(
        json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
        for record in structural_records(
            include_late_call=include_late_call,
            null_cached_tokens=null_cached_tokens,
            variant_native_turn_id=variant_native_turn_id,
        )
    )
    (fixture_root / "source.jsonl").write_bytes(payload)
    ingestion_started_ns = time.perf_counter_ns()
    ingested = ingest(fixture_root, workers=2, batch_size=32)
    ingestion_ns = time.perf_counter_ns() - ingestion_started_ns
    frontier = rate_card_frontier()
    request = PublicationRequest(
        publication_id=PUBLICATION_ID,
        operation_id="operation:ck07a-structural-v2",
        committed_at_us=600,
        history_preset="all_time",
        artifact_manifest_sha256="0" * 64,
        observed_through_us=500,
        indexed_from_us=50,
        indexed_through_us=500,
        guaranteed_complete_from_us=50,
        rate_card_digest=frontier.head_digest,
    )
    prepared = prepare_rate_card_frontier(
        frontier,
        publication_id=request.publication_id,
    )
    write_set = attach_rate_card_frontier(
        prepare_write_set_from_changes(ingested.changes, request),
        request,
        prepared,
    )
    plan = PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        None,
        estimate_change_set(
            ingested.changes,
            dirty_keys=len(prepared.dirty_intervals),
        ),
        ("ck07a_structural_v2",),
        True,
        prepared.dirty_intervals,
    )
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            plan,
            request,
            write_set,
        ),
    )
    publication_started_ns = time.perf_counter_ns()
    connection = initialize_analytical(database_path)
    try:
        published = PublicationWriter(connection).publish(plan, request, write_set)
    finally:
        connection.close()
    publication_ns = time.perf_counter_ns() - publication_started_ns
    return {
        "artifact_manifest_sha256": request.artifact_manifest_sha256,
        "source_bytes": len(payload),
        "source_records": len(
            structural_records(
                include_late_call=include_late_call,
                null_cached_tokens=null_cached_tokens,
                variant_native_turn_id=variant_native_turn_id,
            )
        ),
        "observations": len(ingested.changes.observations),
        "occurrences": len(ingested.changes.occurrences),
        "inserted_occurrences": published.inserted_occurrences,
        "ingestion_ns": ingestion_ns,
        "publication_ns": publication_ns,
    }


def published_question_case(
    connection: sqlite3.Connection,
    case: dict[str, Any],
) -> dict[str, Any]:
    """Verify a publication against, but never derive, frozen structural truth."""

    result = copy.deepcopy(case)
    publication = connection.execute(
        """
        SELECT publication_id
        FROM publication_head
        WHERE singleton = 1
        """
    ).fetchone()
    if publication is None or str(publication[0]) != PUBLICATION_ID:
        raise ValueError("published CK-07A snapshot is missing")
    artifact = connection.execute(
        """
        SELECT artifact_manifest_sha256
        FROM publications
        WHERE publication_id = ?
        """,
        (PUBLICATION_ID,),
    ).fetchone()
    expected_artifact = result["semantic_mutation"]["expected_artifact_manifest_sha256"]
    if artifact is None or str(artifact[0]) != expected_artifact:
        raise ValueError("published artifact manifest differs from frozen authority")
    for predicate in result.get("variant_predicates", ()):
        if predicate.get("predicate") != "published_call_canonical_identity":
            continue
        row = connection.execute(
            """
            SELECT call_id
            FROM model_calls_visible
            WHERE adapter_native_call_key = ?
            """,
            (predicate["native_call_id"],),
        ).fetchone()
        if row is None or str(row[0]) != str(predicate["asserted_value"]):
            raise ValueError("published variant predicate failed")
    return result


__all__ = [
    "HEAD_DIGEST",
    "OLD_DIGEST",
    "PUBLICATION_ID",
    "publish_structural_snapshot",
    "published_question_case",
    "rate_card_frontier",
    "structural_records",
]
