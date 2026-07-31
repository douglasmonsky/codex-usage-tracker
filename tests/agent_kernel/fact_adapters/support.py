"""Synthetic, body-free CK-07E declarations and database-v1 snapshots.

This module is test setup only.  Neither adapter imports it: the reference
adapter receives the structural declaration value, while the database adapter
receives only the sealed query-only connection produced here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.domain.plan_operands import PlanRequest
from codex_usage_tracker.agent_kernel.storage.schema import schema_ddl

ROOT = Path(__file__).resolve().parents[3]
PLAN_CONTRACT_PATH = ROOT / "config/agent-kernel/plan-operand-contract-v1.json"
SELECTOR_CONTRACT_PATH = ROOT / "config/agent-kernel/selector-provenance-v1.json"

OLD_DIGEST = "1" * 64
HEAD_DIGEST = "2" * 64
PUBLICATION_ID = "publication:ck07e"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain one object")
    return value


def plan_contract() -> dict[str, Any]:
    return load_json(PLAN_CONTRACT_PATH)


def selector_contract() -> dict[str, Any]:
    return load_json(SELECTOR_CONTRACT_PATH)


def _request_digest(request: PlanRequest) -> str:
    def normalize(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, Mapping):
            return {
                str(key): normalize(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        return value

    payload = json.dumps(
        normalize(
            {
                "gates": request.gates,
                "parameters": request.parameters,
                "plan_id": request.plan_id,
            }
        ),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _coordinates(
    event_at_us: int | None,
    source_order: int,
    event_kind_order: int = 10,
    transition_rank: int = 0,
) -> dict[str, int | None]:
    return {
        "event_at_us": event_at_us,
        "source_rank": 1,
        "source_order": source_order,
        "event_kind_order": event_kind_order,
        "transition_rank": transition_rank,
    }


def _fact(
    relation: str,
    logical_id: str,
    values: Mapping[str, Any],
    coordinates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "relation": relation,
        "logical_id": logical_id,
        "values": dict(values),
        "coordinates": None if coordinates is None else dict(coordinates),
    }


def _occurrence(logical_id: str, ordinal: int, *, revision: str) -> dict[str, Any]:
    manifestation = (
        "source-manifestation:replacement"
        if revision == "replacement"
        else "source-manifestation:active"
    )
    return {
        "occurrence_id": f"occurrence:{revision}:{ordinal}",
        "semantic_logical_id": logical_id,
        "source_manifestation_id": manifestation,
        "source_revision": f"{revision}-v1",
        "record_ordinal": ordinal,
        "byte_start": ordinal * 100,
        "byte_end": ordinal * 100 + 80,
        "adapter_version": "codex-jsonl.synthetic-v2",
    }


def build_structural_v2(
    *,
    lifecycle: str = "initial",
    include_late_call: bool = False,
    null_cached_tokens: bool = False,
) -> dict[str, Any]:
    """Return one rich structural-v2 declaration spanning all fact families."""

    if lifecycle not in {"initial", "rebuild", "replacement", "late_event"}:
        raise ValueError(f"unsupported lifecycle: {lifecycle}")
    revision = "replacement" if lifecycle == "replacement" else "active"
    facts: list[dict[str, Any]] = []
    order = 1

    def add(
        relation: str,
        logical_id: str,
        values: Mapping[str, Any],
        event_at_us: int | None = None,
        *,
        event_kind_order: int = 10,
        transition_rank: int = 0,
    ) -> None:
        nonlocal order
        facts.append(
            _fact(
                relation,
                logical_id,
                values,
                _coordinates(event_at_us, order, event_kind_order, transition_rank),
            )
        )
        order += 1

    add("project", "project:alpha", {"project_id": "project:alpha", "parent_project_id": None})
    add(
        "session",
        "session:root",
        {
            "session_id": "session:root",
            "project_id": "project:alpha",
            "root_session_id": "session:root",
            "parent_session_id": None,
            "delegation_depth": 0,
            "start_at_us": 50,
            "end_at_us": 500,
            "lifecycle_state": "succeeded",
            "completion_basis": "terminal_event",
        },
        50,
    )
    add(
        "session",
        "session:child",
        {
            "session_id": "session:child",
            "project_id": "project:alpha",
            "root_session_id": "session:root",
            "parent_session_id": "session:root",
            "delegation_depth": 1,
            "start_at_us": 150,
            "end_at_us": 450,
            "lifecycle_state": "succeeded",
            "completion_basis": "terminal_event",
        },
        150,
    )
    for ordinal, (turn_id, session_id, start, end) in enumerate(
        (
            ("turn:root", "session:root", 75, 240),
            ("turn:child", "session:child", 175, 440),
        ),
        start=1,
    ):
        add(
            "turn",
            turn_id,
            {
                "turn_id": turn_id,
                "session_id": session_id,
                "ordinal": ordinal,
                "lifecycle": "succeeded",
                "lifecycle_state": "succeeded",
                "start_at_us": start,
                "end_at_us": end,
                "completion_basis": "terminal_event",
                "first_boundary_coordinates": {
                    "event_at_us": start,
                    "source_rank": 1,
                    "source_order": order,
                },
            },
            start,
        )
    add(
        "model_profile",
        "profile:alpha",
        {
            "model_profile_id": "profile:alpha",
            "model": "synthetic-model",
            "effort": "high",
            "tier": "priority",
        },
    )
    add(
        "model_profile",
        "profile:beta",
        {
            "model_profile_id": "profile:beta",
            "model": "synthetic-other",
            "effort": "medium",
            "tier": "standard",
        },
    )
    call_rows = [
        ("call:before", "session:root", "turn:root", "profile:alpha", 100, 100, 20, 5, 10),
        ("call:boundary", "session:child", "turn:child", "profile:alpha", 250, 200, 40, 10, 20),
        ("call:other", "session:child", "turn:child", "profile:beta", 300, 300, 60, 15, 30),
    ]
    if include_late_call:
        call_rows.append(
            ("call:late", "session:root", "turn:root", "profile:alpha", 125, 80, 10, 2, 8)
        )
    priced_call_count = sum(
        1 for row in call_rows if not (null_cached_tokens and row[0] == "call:before")
    )
    for (
        call_id,
        session_id,
        turn_id,
        profile_id,
        at,
        uncached,
        cached,
        reasoning,
        output,
    ) in call_rows:
        add(
            "canonical_call",
            call_id,
            {
                "call_id": call_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "model_profile_id": profile_id,
                "project_id": "project:alpha",
                "tool_id": None,
                "context_window_tokens": 128_000,
                "uncached_input_tokens": uncached,
                "cached_input_tokens": None
                if null_cached_tokens and call_id == "call:before"
                else cached,
                "reasoning_tokens": reasoning,
                "output_tokens": output,
                "lifecycle": "succeeded",
            },
            at,
        )
    add("resource", "resource:file", {"resource_id": "resource:file", "resource_kind": "file"})
    add(
        "resource",
        "resource:test",
        {"resource_id": "resource:test", "resource_kind": "test_target"},
    )
    tool_rows = (
        ("tool:inspect", "read", "read", "resource:file", False, "succeeded", 180),
        ("tool:attempt", "execute", "write", "resource:file", True, "failed", 200),
        ("tool:retry", "test", "test", "resource:test", True, "succeeded", 220),
    )
    for tool_id, operation, family, resource_id, write_intent, lifecycle_state, at in tool_rows:
        resource_links = (
            ["resource:file", "resource:test"] if tool_id == "tool:inspect" else [resource_id]
        )
        add(
            "tool_invocation",
            tool_id,
            {
                "tool_id": tool_id,
                "session_id": "session:root",
                "turn_id": "turn:root",
                "transport_name": "synthetic",
                "semantic_operation": operation,
                "tool_family": family,
                "resource_id": resource_id,
                "resource_links": resource_links,
                "resource_kind": "file" if resource_id == "resource:file" else "test_target",
                "write_intent": write_intent,
                "lifecycle": lifecycle_state,
                "duration_us": 25,
                "output_bytes": 64,
                "error_category": "synthetic_failure" if lifecycle_state == "failed" else None,
            },
            at,
        )
    add(
        "state_change",
        "state-change:file",
        {
            "state_change_id": "state-change:file",
            "session_id": "session:root",
            "turn_id": "turn:root",
            "resource_id": "resource:file",
            "mutation_kind": "modified",
        },
        210,
    )
    add(
        "compaction_boundary",
        "compaction:one",
        {"compaction_id": "compaction:one", "session_id": "session:root"},
        230,
    )
    for index, category in enumerate(("tool_output", "workspace_context"), start=1):
        add(
            "context_component",
            f"context-component:{index}",
            {
                "component_id": f"context-component:{index}",
                "session_id": "session:root",
                "turn_id": "turn:root",
                "call_id": "call:boundary",
                "category": category,
                "observed_utf8_bytes": 1000 * index,
                "estimated_tokens": 250 * index,
                "total_context_utf8_bytes": 5000,
            },
            235 + index,
        )
    for index, (observed_at_us, allowance_percent) in enumerate(
        (
            (90, Decimal("90")),
            (190, Decimal("80")),
            (190, Decimal("80")),
            (290, Decimal("70")),
        ),
        start=1,
    ):
        add(
            "allowance_observation",
            f"allowance-observation:{index}",
            {
                "observation_id": f"allowance-observation:{index}",
                "limit_id": "allowance-limit:weekly",
                "provider": "synthetic-provider",
                "plan": "synthetic-plan",
                "window_kind": "rolling_week",
                "reset_identity": "reset:one",
                "observed_at_us": observed_at_us,
                "allowance_percent": allowance_percent,
                "compatibility_basis": "same_cycle_adjacent",
                "completion_status": "completed",
            },
            observed_at_us,
            event_kind_order=30,
            transition_rank=index,
        )
    add(
        "publication",
        PUBLICATION_ID,
        {
            "publication_id": PUBLICATION_ID,
            "operation_id": "operation:ck07e",
            "artifact_manifest_sha256": "b" * 64,
            "committed_at_us": 600,
            "observed_through_us": 500,
            "indexed_from_us": 50,
            "guaranteed_complete_from_us": 50,
            "capabilities": {"context_components": True, "valuation": True},
            "measurements": {"calls": len(call_rows), "sources": 2},
            "valuation_coverage": {
                "basis": "configured_estimate",
                "priced_calls": priced_call_count,
            },
        },
        None,
    )
    add(
        "publication_delta",
        "publication-delta:ck07e",
        {
            "inserted_count": len(facts),
            "removed_count": 0,
            "corrected_count": 1 if lifecycle == "replacement" else 0,
            "recanonicalized_count": 0,
            "terminalized_count": 1,
            "token_delta": sum(
                int(row[5]) + int(row[6]) + int(row[7]) + int(row[8]) for row in call_rows
            ),
            "publication_id": PUBLICATION_ID,
        },
        None,
    )
    for manifestation_id, state in (
        ("source-manifestation:active", "active"),
        ("source-manifestation:replacement", "replaced"),
    ):
        add(
            "source_manifestation",
            manifestation_id,
            {
                "source_manifestation_id": manifestation_id,
                "lifecycle_state": state,
                "canonical_basis": "source_inventory",
            },
            None,
        )

    for fact in facts:
        relation = fact["relation"]
        if relation == "model_profile":
            fact["coordinates"] = {
                "event_at_us": None,
                "source_rank": 0,
                "source_order": 0,
                "event_kind_order": 0,
                "transition_rank": 0,
            }
        elif relation == "publication":
            fact["coordinates"] = {
                "event_at_us": 600,
                "source_rank": 0,
                "source_order": 0,
                "event_kind_order": 0,
                "transition_rank": 0,
            }
        elif relation == "source_manifestation":
            manifestation_order = 1 if fact["logical_id"] == "source-manifestation:active" else 2
            fact["coordinates"] = {
                "event_at_us": None,
                "source_rank": manifestation_order,
                "source_order": manifestation_order,
                "event_kind_order": 10,
                "transition_rank": 0,
            }
        elif relation == "publication_delta":
            fact["coordinates"] = {
                "event_at_us": None,
                "source_rank": 0,
                "source_order": 0,
                "event_kind_order": 0,
                "transition_rank": 0,
            }
        elif lifecycle == "replacement":
            fact["coordinates"]["source_rank"] = 2

    occurrences: dict[str, list[dict[str, Any]]] = {}
    for ordinal, fact in enumerate(facts, start=1):
        if fact["relation"] == "model_profile":
            continue
        occurrence = _occurrence(fact["logical_id"], ordinal, revision=revision)
        occurrences.setdefault(fact["logical_id"], []).append(occurrence)
        if lifecycle == "rebuild":
            occurrences[fact["logical_id"]][0] = {
                **occurrence,
                "occurrence_id": f"occurrence:rebuild:{ordinal}",
            }
        if lifecycle == "late_event" and fact["logical_id"] == "call:before":
            occurrences[fact["logical_id"]].append(
                _occurrence(fact["logical_id"], ordinal + 10_000, revision=revision)
            )
    occurrence_facts: list[dict[str, Any]] = []
    for logical_occurrences in occurrences.values():
        for occurrence in logical_occurrences:
            occurrence_facts.append(
                _fact(
                    "source_occurrence",
                    occurrence["occurrence_id"],
                    {
                        "occurrence_id": occurrence["occurrence_id"],
                        "semantic_logical_id": occurrence["semantic_logical_id"],
                        "source_manifestation_id": occurrence["source_manifestation_id"],
                        "occurrence_coordinates": {
                            "source_revision": occurrence["source_revision"],
                            "record_ordinal": occurrence["record_ordinal"],
                            "byte_start": occurrence["byte_start"],
                            "byte_end": occurrence["byte_end"],
                            "adapter_version": occurrence["adapter_version"],
                        },
                    },
                    {
                        **_coordinates(None, occurrence["record_ordinal"]),
                        "source_rank": (
                            2
                            if occurrence["source_manifestation_id"]
                            == "source-manifestation:replacement"
                            else 1
                        ),
                    },
                )
            )
    facts.extend(occurrence_facts)

    selector_entities = {
        "allowance_interval": [
            "allowance-interval:one",
            "allowance-interval:two",
        ],
        "allowance_observation": [
            "allowance-observation:1",
            "allowance-observation:2",
            "allowance-observation:3",
            "allowance-observation:4",
        ],
        "call": [row[0] for row in call_rows],
        "model_profile": ["profile:alpha", "profile:beta"],
        "project": ["project:alpha"],
        "publication": [PUBLICATION_ID],
        "rate_card": [HEAD_DIGEST],
        "resource": ["resource:file", "resource:test"],
        "session": ["session:root", "session:child"],
        "source_manifestation": [
            "source-manifestation:active",
            "source-manifestation:replacement",
        ],
        "state_change": ["state-change:file"],
        "tool": ["tool:inspect", "tool:attempt", "tool:retry"],
        "turn": ["turn:root", "turn:child"],
    }
    frontier = {
        "head_digest": HEAD_DIGEST,
        "revisions": [
            {
                "rate_card_id": "rate-card:old",
                "digest": OLD_DIGEST,
                "predecessor_digest": None,
                "effective_at_us": 0,
                "fetched_at_us": 900,
                "source_name": "synthetic-old",
                "source_url": None,
                "currency": "USD",
                "model_match_rules": [
                    {
                        "model_profile_id": "profile:alpha",
                        "match_basis": "exact_model_profile",
                    },
                    {
                        "model_profile_id": "profile:beta",
                        "match_basis": "exact_model_profile",
                    },
                ],
                "four_class_rates": {
                    "uncached_input_tokens": "1",
                    "cached_input_tokens": "1",
                    "reasoning_tokens": "1",
                    "output_tokens": "1",
                },
                "credit_rates": {
                    "uncached_input_tokens": "1",
                    "cached_input_tokens": "1",
                    "reasoning_tokens": "1",
                    "output_tokens": "1",
                },
                "reasoning_in_output": False,
                "confidence": "synthetic",
                "validation_status": "valid",
            },
            {
                "rate_card_id": "rate-card:new",
                "digest": HEAD_DIGEST,
                "predecessor_digest": OLD_DIGEST,
                "effective_at_us": 250,
                "fetched_at_us": 100,
                "source_name": "synthetic-new",
                "source_url": None,
                "currency": "USD",
                "model_match_rules": [
                    {
                        "model_alias": "synthetic-model",
                        "match_basis": "model_alias",
                    }
                ],
                "four_class_rates": {
                    "uncached_input_tokens": "2",
                    "cached_input_tokens": "2",
                    "reasoning_tokens": "2",
                    "output_tokens": "2",
                },
                "credit_rates": {
                    "uncached_input_tokens": "2",
                    "cached_input_tokens": "2",
                    "reasoning_tokens": "2",
                    "output_tokens": "2",
                },
                "reasoning_in_output": False,
                "confidence": "synthetic",
                "validation_status": "valid",
            },
        ],
    }
    source_manifestations = {
        "source-manifestation:active": {
            "source_id": "source:active",
            "content_revision": f"{revision}-v1",
            "state": "active",
            "selected_publication_id": PUBLICATION_ID,
        },
        "source-manifestation:replacement": {
            "source_id": "source:replacement",
            "content_revision": "replacement-v1",
            "state": "replaced",
            "selected_publication_id": PUBLICATION_ID,
        },
    }
    declaration = {
        "schema": "codex-usage-tracker.synthetic-structural-v2.v1",
        "scenario_id": f"ck07e:{lifecycle}",
        "facts": facts,
        "occurrences": occurrences,
        "selector_entities": selector_entities,
        "allowance_intervals": {
            "allowance-interval:one": {
                "start_observation_id": "allowance-observation:1",
                "end_observation_id": "allowance-observation:2",
            },
            "allowance-interval:two": {
                "start_observation_id": "allowance-observation:3",
                "end_observation_id": "allowance-observation:4",
            },
        },
        "source_manifestations": source_manifestations,
        "rate_card_frontier": frontier,
        "publication_rate_card_digest": HEAD_DIGEST,
    }
    return copy.deepcopy(declaration)


def required_references(
    *,
    request: PlanRequest | None = None,
    include_window: bool = True,
) -> tuple[dict[str, str], ...]:
    """Return one exact ordered selection covering every admitted selector kind."""

    rows = [
        (
            "interval",
            "allowance_interval",
            "allowance-interval:allowance-interval:one",
            "allowance-interval:one",
        ),
        (
            "observation",
            "allowance_observation",
            "allowance-observation:allowance-observation:1",
            "allowance-observation:1",
        ),
        ("call", "call", "call:call:before", "call:before"),
        ("profile", "model_profile", "model-profile:profile:alpha", "profile:alpha"),
        ("project", "project", "project:project:alpha", "project:alpha"),
        ("publication", "publication", f"publication:{PUBLICATION_ID}", PUBLICATION_ID),
        ("rate_card", "rate_card", f"rate-card:{HEAD_DIGEST}", HEAD_DIGEST),
        ("resource", "resource", "resource:resource:file", "resource:file"),
        ("session", "session", "session:session:root", "session:root"),
        (
            "source",
            "source_manifestation",
            "source-manifestation:source-manifestation:active",
            "source-manifestation:active",
        ),
        ("state", "state_change", "state-change:state-change:file", "state-change:file"),
        ("tool", "tool", "tool:tool:inspect", "tool:inspect"),
        ("turn", "turn", "turn:turn:root", "turn:root"),
    ]
    if include_window:
        if request is None:
            request = adapter_request()
        request_digest = _request_digest(request)
        for role, value in request.parameters.items():
            if role != "window" and not role.endswith("_window"):
                continue
            if not isinstance(value, Mapping):
                raise TypeError(f"{role} must be a typed request window")
            start = value.get("start_us")
            end = value.get("end_us")
            timezone = value.get("timezone", "UTC")
            if (
                isinstance(start, bool)
                or not isinstance(start, int)
                or isinstance(end, bool)
                or not isinstance(end, int)
                or not isinstance(timezone, str)
            ):
                raise TypeError(f"{role} must contain typed window bounds")
            logical_id = semantic_id(
                "window",
                [request_digest, role, start, end, timezone],
            )
            rows.append((role, "window", f"window:{logical_id}", logical_id))
    return tuple(
        {
            "role": role,
            "selector_kind": kind,
            "selector": selector,
            "logical_id": logical_id,
        }
        for role, kind, selector, logical_id in rows
    )


def adapter_request(plan_id: str = "current_usage", *, with_window: bool = True) -> PlanRequest:
    parameters: dict[str, Any] = {}
    plan = next(item for item in plan_contract()["plans"] if item["plan_id"] == plan_id)
    declared_parameters = {
        *plan["request_schema"]["required"],
        *plan["request_schema"].get("optional", {}),
    }
    if with_window and "window" in declared_parameters:
        parameters["window"] = {
            "start_us": 0,
            "end_us": 1_000,
            "timezone": "UTC",
        }
    for name, declaration in plan["request_schema"]["required"].items():
        if name in parameters:
            continue
        declared_type = declaration["type"]
        if name in {"start_observation_id", "end_observation_id"}:
            parameters[name] = (
                "allowance-observation:1" if name.startswith("start") else "allowance-observation:2"
            )
        elif name == "as_of_us":
            parameters[name] = 1_000
        elif name == "cohorts":
            parameters[name] = {
                "left": ["session:root"],
                "right": ["session:child"],
            }
        elif name == "family_mode":
            parameters[name] = "root" if plan_id == "parent_subagent_usage" else "project"
        elif declared_type == "integer":
            parameters[name] = 10
        elif declared_type == "array":
            parameters[name] = ["session:root"]
        elif declared_type == "object":
            parameters[name] = {
                "start_us": 0,
                "end_us": 1_000,
                "timezone": "UTC",
            }
        else:
            parameters[name] = f"synthetic-{name}"
    return PlanRequest(
        plan_id=plan_id,
        parameters=parameters,
        gates={gate: True for gate in plan["gates"]},
    )


def emitted_structural_jsonl(declaration: Mapping[str, Any]) -> bytes:
    def normalize(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, Mapping):
            return {str(key): normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        return value

    return b"".join(
        json.dumps(
            normalize(
                {
                    "type": "structural_fact",
                    "relation": fact["relation"],
                    "logical_id": fact["logical_id"],
                    "values": fact["values"],
                    "coordinates": fact["coordinates"],
                }
            ),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
        for fact in declaration["facts"]
    )


def _sql_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    if isinstance(value, bool):
        return int(value)
    return value


def build_query_only_database(declaration: Mapping[str, Any]) -> sqlite3.Connection:
    """Populate one database-v1 analytical snapshot, then seal it query-only."""

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(schema_ddl("analytical"))
    connection.execute("PRAGMA foreign_keys = OFF")

    def insert(table: str, values: Mapping[str, Any]) -> None:
        columns = tuple(values)
        connection.execute(
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            tuple(_sql_value(values[column]) for column in columns),
        )

    facts = declaration["facts"]
    by_relation: dict[str, list[Mapping[str, Any]]] = {}
    for fact in facts:
        by_relation.setdefault(fact["relation"], []).append(fact)
    publication_fact = by_relation["publication"][0]
    insert(
        "publications",
        {
            "publication_id": PUBLICATION_ID,
            "parent_publication_id": None,
            "operation_id": "operation:ck07e",
            "schema_contract_id": "codex-usage-tracker.agent-kernel.schema-contract.v1",
            "schema_contract_sha256": "a" * 64,
            "identity_version": "v1",
            "adapter_id": "adapter:synthetic",
            "adapter_version": "structural-v2",
            "normalization_version": "v1",
            "projection_registry_sha256": None,
            "rate_card_digest": HEAD_DIGEST,
            "history_preset": "all_time",
            "requested_cutoff_us": None,
            "committed_at_us": 600,
            "observed_through_us": publication_fact["values"]["observed_through_us"],
            "indexed_from_us": publication_fact["values"]["indexed_from_us"],
            "indexed_through_us": 600,
            "guaranteed_complete_from_us": publication_fact["values"][
                "guaranteed_complete_from_us"
            ],
            "artifact_manifest_sha256": "b" * 64,
            "status": "committed",
        },
    )
    insert(
        "publication_head",
        {"singleton": 1, "publication_id": PUBLICATION_ID, "activated_at_us": 601},
    )
    for source_id in ("source:active", "source:replacement"):
        insert(
            "publication_source_coverage",
            {
                "publication_id": PUBLICATION_ID,
                "source_id": source_id,
                "selected_manifestation_count": 1,
                "selected_manifestation_bytes": 10_000,
                "deferred_manifestation_count": 0,
                "deferred_manifestation_bytes": 0,
                "malformed_manifestation_count": 0,
                "malformed_manifestation_bytes": 0,
                "missing_manifestation_count": 0,
                "missing_manifestation_bytes": 0,
                "uncertain_manifestation_count": 0,
                "uncertain_manifestation_bytes": 0,
                "malformed_range_count": 0,
                "malformed_range_bytes": 0,
                "selected_complete_record_count": 1,
                "tail_pending": 0,
                "indexed_from_us": publication_fact["values"]["indexed_from_us"],
                "indexed_through_us": 600,
                "guaranteed_complete_from_us": publication_fact["values"][
                    "guaranteed_complete_from_us"
                ],
                "guaranteed_complete_through_us": 600,
                "clock_quality": "bounded",
                "clock_uncertainty_us": 0,
                "inventory_started_at_us": 590,
                "inventory_completed_at_us": 600,
            },
        )
    publication_call_count = publication_fact["values"]["measurements"].get("calls")
    if publication_call_count is None:
        publication_call_count = publication_fact["values"]["measurements"]["model_calls"]
    for capability_id, eligible, observed, unavailable, grade in (
        ("context_components", 2, 2, 0, "exact"),
        (
            "valuation",
            publication_call_count,
            publication_fact["values"]["valuation_coverage"]["priced_calls"],
            publication_call_count
            - publication_fact["values"]["valuation_coverage"]["priced_calls"],
            "configured_estimate",
        ),
    ):
        insert(
            "publication_capability_coverage",
            {
                "publication_id": PUBLICATION_ID,
                "capability_id": capability_id,
                "eligible_entity_count": eligible,
                "observed_entity_count": observed,
                "unavailable_entity_count": unavailable,
                "measurement_mask": 0,
                "grade": grade,
                "basis": "structural-v2",
            },
        )
    for entity_kind, entity_count in publication_fact["values"]["measurements"].items():
        insert(
            "publication_entity_counts",
            {
                "publication_id": PUBLICATION_ID,
                "entity_kind": entity_kind,
                "entity_count": entity_count,
            },
        )
    manifestation_keys: dict[str, int] = {}
    for index, (manifestation_id, manifest) in enumerate(
        declaration["source_manifestations"].items(),
        start=1,
    ):
        manifestation_keys[manifestation_id] = index
        insert(
            "source_manifestations",
            {
                "manifestation_id": manifestation_id,
                "manifestation_key": index,
                "source_id": manifest["source_id"],
                "adapter_native_file_key": f"file-{index}",
                "technical_path_key": f"synthetic/file-{index}.jsonl",
                "display_label": f"synthetic-{index}",
                "filesystem_identity_json": None,
                "size_bytes": 10_000,
                "modified_at_us": 500,
                "prefix_sha256": "c" * 64,
                "suffix_sha256": "d" * 64,
                "content_revision": manifest["content_revision"],
                "source_rank": index,
                "state": manifest["state"],
                "time_range_start_us": 0,
                "time_range_end_us": 600,
                "time_range_confidence": "trusted",
                "selected": 1,
                "first_seen_publication_id": PUBLICATION_ID,
                "last_seen_publication_id": PUBLICATION_ID,
                "ended_publication_id": None,
            },
        )
    for logical_occurrences in declaration["occurrences"].values():
        for occurrence in logical_occurrences:
            insert(
                "source_occurrences",
                {
                    "occurrence_id": occurrence["occurrence_id"],
                    "semantic_logical_id": occurrence["semantic_logical_id"],
                    "manifestation_key": manifestation_keys[occurrence["source_manifestation_id"]],
                    "source_revision": occurrence["source_revision"],
                    "record_ordinal": occurrence["record_ordinal"],
                    "byte_start": occurrence["byte_start"],
                    "byte_end": occurrence["byte_end"],
                    "adapter_version": occurrence["adapter_version"],
                    "first_seen_publication_id": PUBLICATION_ID,
                },
            )
    insert(
        "projects",
        {
            "project_id": "project:alpha",
            "workspace_key": "synthetic-workspace",
            "first_event_at_us": 50,
            "last_event_at_us": 500,
            "provenance_json": "[]",
            "first_seen_publication_id": PUBLICATION_ID,
            "last_seen_publication_id": PUBLICATION_ID,
        },
    )

    fallback_occurrence_id = next(
        (
            occurrence["occurrence_id"]
            for occurrences in declaration["occurrences"].values()
            for occurrence in occurrences
        ),
        None,
    )

    def occurrence_id(logical_id: str) -> str:
        occurrences = declaration["occurrences"].get(logical_id, ())
        if occurrences:
            return occurrences[0]["occurrence_id"]
        return fallback_occurrence_id or semantic_id(
            "source-occurrence",
            ["query-only-coordinate-anchor"],
        )

    for fact in by_relation["model_profile"]:
        values = fact["values"]
        insert(
            "model_profiles",
            {
                "model_profile_id": fact["logical_id"],
                "model": values["model"],
                "reasoning_effort": values.get("effort"),
                "service_tier": values.get("tier"),
                "first_seen_publication_id": PUBLICATION_ID,
                "last_seen_publication_id": PUBLICATION_ID,
            },
        )
    for fact in by_relation["session"]:
        values = fact["values"]
        insert(
            "sessions",
            {
                "session_id": fact["logical_id"],
                "adapter_native_session_key": fact["logical_id"],
                "identity_version": "v1",
                "project_id": values["project_id"],
                "root_session_id": values.get("root_session_id"),
                "parent_session_id": values.get("parent_session_id"),
                "relationship_basis": "structural",
                "delegation_depth": values.get("delegation_depth"),
                "lifecycle_state": values["lifecycle_state"],
                "state_basis": "structural",
                "transition_version": 1,
                "start_at_us": values.get("start_at_us"),
                "end_at_us": values.get("end_at_us"),
                "observed_duration_us": 450,
                "completion_basis": values.get("completion_basis"),
                "label_candidates_json": "[]",
                "primary_occurrence_id": occurrence_id(fact["logical_id"]),
                "first_seen_publication_id": PUBLICATION_ID,
                "last_seen_publication_id": PUBLICATION_ID,
            },
        )
    for fact in by_relation["turn"]:
        values = fact["values"]
        insert(
            "turns",
            {
                "turn_id": fact["logical_id"],
                "session_id": values["session_id"],
                "ordinal": values["ordinal"],
                "lifecycle_state": values["lifecycle_state"],
                "state_basis": "structural",
                "transition_version": 1,
                "start_at_us": values["start_at_us"],
                "end_at_us": values["end_at_us"],
                "start_source_order": 1,
                "end_source_order": 2,
                "completion_basis": values["completion_basis"],
                "membership_json": "{}",
                "primary_occurrence_id": occurrence_id(fact["logical_id"]),
                "first_seen_publication_id": PUBLICATION_ID,
                "last_seen_publication_id": PUBLICATION_ID,
            },
        )
    for fact in by_relation["canonical_call"]:
        values = fact["values"]
        coordinates = fact["coordinates"]
        insert(
            "model_call_locations",
            {"call_id": fact["logical_id"], "storage_class": "base"},
        )
        insert(
            "model_calls",
            {
                "call_id": fact["logical_id"],
                "storage_class": "base",
                "adapter_native_call_key": fact["logical_id"],
                "session_id": values["session_id"],
                "turn_id": values["turn_id"],
                "model_profile_id": values["model_profile_id"],
                "lifecycle_state": values["lifecycle"],
                "state_basis": "structural",
                "transition_version": 1,
                "event_at_us": coordinates["event_at_us"],
                "source_rank": coordinates["source_rank"],
                "source_order": coordinates["source_order"],
                "event_kind_order": coordinates["event_kind_order"],
                "transition_rank": coordinates["transition_rank"],
                "context_window_tokens": values["context_window_tokens"],
                "uncached_input_tokens": values["uncached_input_tokens"],
                "cached_input_tokens": values["cached_input_tokens"],
                "reasoning_tokens": values["reasoning_tokens"],
                "output_tokens": values["output_tokens"],
                "token_basis": "structural",
                "finish_category": None,
                "error_category": None,
                "measurement_mask": 0,
                "primary_occurrence_id": occurrence_id(fact["logical_id"]),
                "first_seen_publication_id": PUBLICATION_ID,
                "last_seen_publication_id": PUBLICATION_ID,
            },
        )
    for fact in by_relation["resource"]:
        values = fact["values"]
        insert(
            "resources",
            {
                "resource_id": fact["logical_id"],
                "project_id": "project:alpha",
                "resource_kind": values["resource_kind"],
                "normalized_key": fact["logical_id"],
                "normalization_version": "v1",
                "display_label": fact["logical_id"],
                "provenance_json": "[]",
                "first_seen_publication_id": PUBLICATION_ID,
                "last_seen_publication_id": PUBLICATION_ID,
            },
        )
    for fact in by_relation["tool_invocation"]:
        values = fact["values"]
        coordinates = fact["coordinates"]
        insert(
            "tool_invocations",
            {
                "tool_id": fact["logical_id"],
                "adapter_native_invocation_key": fact["logical_id"],
                "session_id": values["session_id"],
                "turn_id": values["turn_id"],
                "transport_name": values["transport_name"],
                "semantic_operation": values["semantic_operation"],
                "tool_family": values["tool_family"],
                "primary_resource_id": values["resource_id"],
                "write_intent": values["write_intent"],
                "lifecycle_state": values["lifecycle"],
                "state_basis": "structural",
                "transition_version": 1,
                "start_at_us": coordinates["event_at_us"],
                "start_source_rank": coordinates["source_rank"],
                "start_source_order": coordinates["source_order"],
                "start_event_kind_order": coordinates["event_kind_order"],
                "start_transition_rank": coordinates["transition_rank"],
                "start_occurrence_id": occurrence_id(fact["logical_id"]),
                "terminal_at_us": coordinates["event_at_us"] + values["duration_us"],
                "terminal_source_rank": coordinates["source_rank"],
                "terminal_source_order": coordinates["source_order"] + 1,
                "terminal_event_kind_order": coordinates["event_kind_order"],
                "terminal_transition_rank": 1,
                "terminal_occurrence_id": occurrence_id(fact["logical_id"]),
                "observed_duration_us": values["duration_us"],
                "output_bytes": values["output_bytes"],
                "error_category": values["error_category"],
                "measurement_mask": 0,
                "first_seen_publication_id": PUBLICATION_ID,
                "last_seen_publication_id": PUBLICATION_ID,
            },
        )
        for resource_id in dict.fromkeys(values["resource_links"]):
            insert(
                "tool_resources",
                {
                    "tool_id": fact["logical_id"],
                    "resource_id": resource_id,
                    "relationship_role": (
                        "tested"
                        if values["semantic_operation"] == "test"
                        else "read"
                        if values["semantic_operation"] == "read"
                        else "executed"
                    ),
                    "occurrence_id": occurrence_id(fact["logical_id"]),
                },
            )
    for fact in by_relation["state_change"]:
        values = fact["values"]
        coordinates = fact["coordinates"]
        insert(
            "state_changes",
            {
                "change_id": fact["logical_id"],
                "session_id": values["session_id"],
                "turn_id": values["turn_id"],
                "resource_id": values["resource_id"],
                "change_kind": values["mutation_kind"],
                "before_revision": None,
                "after_revision": "revision:after",
                "confidence": "synthetic",
                "event_at_us": coordinates["event_at_us"],
                "source_rank": coordinates["source_rank"],
                "source_order": coordinates["source_order"],
                "event_kind_order": coordinates["event_kind_order"],
                "transition_rank": coordinates["transition_rank"],
                "measurement_mask": 0,
                "primary_occurrence_id": occurrence_id(fact["logical_id"]),
                "first_seen_publication_id": PUBLICATION_ID,
            },
        )
    for fact in by_relation["compaction_boundary"]:
        coordinates = fact["coordinates"]
        insert(
            "compaction_boundaries",
            {
                "compaction_id": fact["logical_id"],
                "session_id": fact["values"]["session_id"],
                "before_context_epoch": "epoch:before",
                "after_context_epoch": "epoch:after",
                "event_at_us": coordinates["event_at_us"],
                "source_rank": coordinates["source_rank"],
                "source_order": coordinates["source_order"],
                "event_kind_order": coordinates["event_kind_order"],
                "transition_rank": coordinates["transition_rank"],
                "primary_occurrence_id": occurrence_id(fact["logical_id"]),
                "first_seen_publication_id": PUBLICATION_ID,
            },
        )
    for fact in by_relation["context_component"]:
        values = fact["values"]
        coordinates = fact["coordinates"]
        insert(
            "context_components",
            {
                "component_id": fact["logical_id"],
                "session_id": values["session_id"],
                "turn_id": values["turn_id"],
                "call_id": values["call_id"],
                "category": values["category"],
                "observed_utf8_bytes": values["observed_utf8_bytes"],
                "observed_event_count": 1,
                "estimator": "synthetic",
                "estimated_tokens": values["estimated_tokens"],
                "total_context_utf8_bytes": values["total_context_utf8_bytes"],
                "inclusion_basis": "observed_in_source",
                "capability_basis": "structural",
                "measurement_basis": "synthetic",
                "event_at_us": coordinates["event_at_us"],
                "source_rank": coordinates["source_rank"],
                "source_order": coordinates["source_order"],
                "event_kind_order": coordinates["event_kind_order"],
                "transition_rank": coordinates["transition_rank"],
                "measurement_mask": 0,
                "primary_occurrence_id": occurrence_id(fact["logical_id"]),
                "first_seen_publication_id": PUBLICATION_ID,
                "last_seen_publication_id": PUBLICATION_ID,
            },
        )
    insert(
        "allowance_limits",
        {
            "limit_id": "allowance-limit:weekly",
            "provider": "synthetic-provider",
            "account_local_identity": "synthetic-account",
            "plan_identity": "synthetic-plan",
            "window_kind": "rolling_week",
            "configured_duration_us": 604_800_000_000,
            "capability_basis": "structural",
            "first_seen_publication_id": PUBLICATION_ID,
            "last_seen_publication_id": PUBLICATION_ID,
        },
    )
    insert(
        "allowance_cycles",
        {
            "cycle_id": "allowance-cycle:one",
            "limit_id": "allowance-limit:weekly",
            "reset_identity": "reset:one",
            "start_at_us": 0,
            "end_at_us": 1_000,
            "reset_basis": "structural",
            "completion_status": "completed",
            "first_seen_publication_id": PUBLICATION_ID,
            "last_seen_publication_id": PUBLICATION_ID,
        },
    )
    for index, fact in enumerate(by_relation["allowance_observation"], start=1):
        values = fact["values"]
        coordinates = fact["coordinates"]
        insert(
            "allowance_observations",
            {
                "observation_id": fact["logical_id"],
                "limit_id": values["limit_id"],
                "cycle_id": "allowance-cycle:one",
                "plan_identity": values["plan"],
                "window_kind": values["window_kind"],
                "reset_identity": values["reset_identity"],
                "observation_ordinal": index,
                "used_percent": (
                    Decimal("10")
                    if index == 1
                    else Decimal("20")
                    if index == 3
                    else Decimal("30")
                    if index == 4
                    else None
                ),
                "remaining_percent": (Decimal("80") if index in {2, 3} else None),
                "absolute_fields_json": "{}",
                "reset_time_us": None,
                "observed_at_us": values["observed_at_us"],
                "source_rank": coordinates["source_rank"],
                "source_order": coordinates["source_order"],
                "event_kind_order": coordinates["event_kind_order"],
                "transition_rank": coordinates["transition_rank"],
                "measurement_mask": 0,
                "primary_occurrence_id": occurrence_id(fact["logical_id"]),
                "first_seen_publication_id": PUBLICATION_ID,
            },
        )
    allowance_facts = {fact["logical_id"]: fact for fact in by_relation["allowance_observation"]}
    for interval_id, interval in declaration["allowance_intervals"].items():
        start_fact = allowance_facts[interval["start_observation_id"]]
        end_fact = allowance_facts[interval["end_observation_id"]]
        start_percent = Decimal(str(start_fact["values"]["allowance_percent"]))
        end_percent = Decimal(str(end_fact["values"]["allowance_percent"]))
        insert(
            "allowance_intervals",
            {
                "interval_id": interval_id,
                "limit_id": "allowance-limit:weekly",
                "cycle_id": "allowance-cycle:one",
                "start_observation_id": start_fact["logical_id"],
                "end_observation_id": end_fact["logical_id"],
                "start_us": start_fact["values"]["observed_at_us"],
                "end_us": end_fact["values"]["observed_at_us"],
                "percent_delta": start_percent - end_percent,
                "compatibility_basis": "allowance-compatibility-v1",
                "ratio_eligible": int(start_percent > end_percent),
                "coverage_json": "{}",
                "first_seen_publication_id": PUBLICATION_ID,
            },
        )
    delta = by_relation["publication_delta"][0]["values"]
    insert(
        "publication_deltas",
        {
            "publication_id": PUBLICATION_ID,
            "parent_publication_id": None,
            "inserted_count": delta["inserted_count"],
            "corrected_count": delta["corrected_count"],
            "terminalized_count": delta["terminalized_count"],
            "recanonicalized_count": delta["recanonicalized_count"],
            "removed_count": delta["removed_count"],
            "uncached_input_token_delta": delta["token_delta"],
            "cached_input_token_delta": 0,
            "reasoning_token_delta": 0,
            "output_token_delta": 0,
            "affected_session_count": 2,
            "affected_turn_count": 2,
            "affected_tool_count": 3,
            "affected_resource_count": 2,
            "affected_state_change_count": 1,
            "affected_allowance_observation_count": 4,
            "source_coverage_changed": 0,
            "sample_truncated": 0,
        },
    )
    revisions = declaration["rate_card_frontier"]["revisions"]
    predecessor_id: str | None = None
    for revision in revisions:
        insert(
            "rate_card_revisions",
            {
                "rate_card_id": revision["rate_card_id"],
                "digest": revision["digest"],
                "predecessor_rate_card_id": predecessor_id,
                "source_name": revision["source_name"],
                "source_url": revision["source_url"],
                "effective_at_us": revision["effective_at_us"],
                "fetched_at_us": revision["fetched_at_us"],
                "currency": revision["currency"],
                "model_match_rules_json": revision["model_match_rules"],
                "four_class_rates_json": revision["four_class_rates"],
                "credit_rates_json": revision["credit_rates"],
                "reasoning_in_output": revision["reasoning_in_output"],
                "confidence": revision["confidence"],
                "validation_status": revision["validation_status"],
                "first_seen_publication_id": PUBLICATION_ID,
            },
        )
        predecessor_id = revision["rate_card_id"]
    insert(
        "active_rate_card",
        {
            "singleton": 1,
            "rate_card_id": "rate-card:new",
            "selected_at_us": 600,
            "publication_id": PUBLICATION_ID,
        },
    )
    connection.commit()
    connection.execute("PRAGMA query_only = ON")
    return connection


def normalize_materialization(materialization: Any) -> tuple[Any, ...]:
    """Cross-adapter comparison that depends on neither adapter's result type."""

    def normalized(value: Any) -> Any:
        if isinstance(value, Decimal):
            return ("decimal", str(value))
        if isinstance(value, Mapping):
            return tuple(
                (str(key), normalized(item))
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            )
        if isinstance(value, (list, tuple)):
            return tuple(normalized(item) for item in value)
        if hasattr(value, "value") and isinstance(value.value, str):
            return value.value
        return value

    def normalized_provenance(value: Any) -> Any:
        if isinstance(value, Mapping):
            mapped = dict(value)
            if "occurrence_id" in mapped:
                if "source_manifestation_id" in mapped:
                    mapped["manifestation_id"] = mapped.pop("source_manifestation_id")
                if "source_revision" in mapped:
                    mapped["revision"] = mapped.pop("source_revision")
                mapped.pop("semantic_logical_id", None)
            return tuple(
                (str(key), normalized_provenance(item))
                for key, item in sorted(mapped.items(), key=lambda pair: str(pair[0]))
            )
        if isinstance(value, (list, tuple)):
            return tuple(normalized_provenance(item) for item in value)
        return normalized(value)

    facts = tuple(
        sorted(
            (
                fact.relation,
                fact.logical_id,
                normalized(fact.values),
                None
                if fact.coordinates is None
                else (
                    fact.coordinates.event_at_us,
                    fact.coordinates.source_rank,
                    fact.coordinates.source_order,
                    fact.coordinates.event_kind_order,
                    fact.coordinates.transition_rank,
                ),
            )
            for fact in materialization.facts
        )
    )
    references = tuple(
        (
            reference.role,
            reference.selector_kind,
            reference.selector,
            reference.logical_id,
            reference.provenance_kind,
            normalized_provenance(reference.provenance),
        )
        for reference in materialization.evidence_references
    )
    request = (
        materialization.request.plan_id,
        normalized(materialization.request.parameters),
        normalized(materialization.request.gates),
    )
    return request, facts, references


__all__ = [
    "HEAD_DIGEST",
    "OLD_DIGEST",
    "PLAN_CONTRACT_PATH",
    "PUBLICATION_ID",
    "SELECTOR_CONTRACT_PATH",
    "adapter_request",
    "build_query_only_database",
    "build_structural_v2",
    "emitted_structural_jsonl",
    "normalize_materialization",
    "plan_contract",
    "required_references",
    "selector_contract",
]
