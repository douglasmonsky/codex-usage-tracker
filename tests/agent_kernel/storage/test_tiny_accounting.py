from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, make_dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from codex_usage_tracker.agent_kernel.storage.occurrences import (
    SourceOccurrence,
    SourceOccurrenceRepository,
)
from codex_usage_tracker.agent_kernel.storage.repositories import (
    AccountingRepository,
    RepositoryTiming,
    SelectedFactRepository,
)
from codex_usage_tracker.agent_kernel.storage.schema import (
    ANALYTICAL_DDL,
    SCHEMA_CONTRACT_ID,
    SCHEMA_CONTRACT_SHA256,
)

PUBLICATION_ID = "publication:accounting"
_ORACLE_PATH = Path(__file__).parents[1] / "fixtures" / "tiny-v1" / "oracle-bundle.json"
_TINY_ACCOUNTING_INDEX_BY_SCHEMA = {
    "1a2dcffe778633457bbeb60dd3a41c233a78c15af2a3393bf9cacc1d9e645bb5": (
        "source_occurrences_by_logical_id"
    ),
    "e3b8509774987fb4fd9cd09aeee1ab9ee32642932ea6a07726315154409b1e35": (
        "evidence_source_occurrences_by_logical_order"
    ),
    "998343ba4b52bb39decfcb436f8a862d41884fc6f6a6b4e88f7e8f8e42446295": (
        "evidence_source_occurrences_by_logical_order"
    ),
}


def _accounting_oracle() -> dict[str, Any]:
    payload = json.loads(_ORACLE_PATH.read_text(encoding="utf-8"))
    return payload["accounting"]


@dataclass(frozen=True)
class _ModelCall:
    call_id: str
    storage_class: str
    adapter_native_call_key: str
    session_id: str
    turn_id: str
    model_profile_id: str
    lifecycle_state: str
    state_basis: str
    transition_version: int
    event_at_us: int | None
    source_rank: int
    source_order: int
    event_kind_order: int
    transition_rank: int
    context_window_tokens: int | None
    uncached_input_tokens: int | None
    cached_input_tokens: int | None
    reasoning_tokens: int | None
    output_tokens: int | None
    token_basis: str
    finish_category: str | None
    error_category: str | None
    measurement_mask: int
    primary_occurrence_id: str
    first_seen_publication_id: str
    last_seen_publication_id: str


def _identity(connection: sqlite3.Connection, logical_id: str, kind: str) -> None:
    payload = logical_id.encode()
    connection.execute(
        """
        INSERT INTO identity_registry (
          logical_id, entity_kind, identity_version, identity_cbor,
          identity_sha256, first_seen_publication_id, last_seen_publication_id
        ) VALUES (?, ?, 'identity-v1', ?, ?, ?, ?)
        """,
        (
            logical_id,
            kind,
            payload,
            sha256(payload).hexdigest(),
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )


def _tiny_accounting_connection(accounting: dict[str, Any]) -> sqlite3.Connection:
    counts = accounting["canonical_counts"]
    call_count = int(counts["model_calls"])
    occurrence_count = int(accounting["source_reconciliation"]["model_call_occurrences"])
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(ANALYTICAL_DDL)
    connection.execute(
        """
        INSERT INTO publications (
          publication_id, operation_id, schema_contract_id,
          schema_contract_sha256, identity_version, adapter_id,
          adapter_version, normalization_version, history_preset,
          committed_at_us, artifact_manifest_sha256, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            PUBLICATION_ID,
            "operation:accounting",
            SCHEMA_CONTRACT_ID,
            SCHEMA_CONTRACT_SHA256,
            "identity-v1",
            "adapter:accounting",
            "adapter-v1",
            "normalization-v1",
            "all_time",
            1,
            "f" * 64,
            "committed",
        ),
    )
    fixed_identities = (
        ("adapter:accounting", "adapter"),
        ("producer:accounting", "producer"),
        ("source:accounting", "source"),
        ("manifestation:accounting", "source_manifestation"),
        ("project:accounting", "project"),
        ("model-profile:accounting", "model_profile"),
        ("resource:accounting", "resource"),
        ("allowance-limit:accounting", "allowance_limit"),
        ("allowance-cycle:accounting", "allowance_cycle"),
    )
    for logical_id, kind in fixed_identities:
        _identity(connection, logical_id, kind)
    for index in range(int(counts["sessions"])):
        _identity(connection, f"session:{index:02d}", "session")
    for index in range(int(counts["turns"])):
        _identity(connection, f"turn:{index:02d}", "turn")
    for index in range(call_count):
        _identity(connection, f"call:{index:03d}", "model_call")
    for index in range(occurrence_count):
        _identity(connection, f"occurrence:{index:03d}", "source_occurrence")
    for index in range(int(counts["tool_invocations"])):
        _identity(connection, f"tool:{index:02d}", "tool_invocation")
    for index in range(int(counts["activities"])):
        _identity(connection, f"activity:{index:02d}", "activity")
        _identity(connection, f"state-change:{index:02d}", "state_change")
    for index in range(int(counts["allowance_observations"])):
        _identity(connection, f"allowance-observation:{index:02d}", "allowance_observation")

    connection.execute(
        "INSERT INTO adapters VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "adapter:accounting",
            "adapter-v1",
            "synthetic-jsonl",
            15,
            "identity-v1",
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    connection.execute(
        "INSERT INTO source_producers VALUES (?, ?, ?, ?, ?)",
        (
            "producer:accounting",
            "synthetic-local",
            "Synthetic",
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    connection.execute(
        "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "source:accounting",
            "adapter:accounting",
            "producer:accounting",
            "synthetic-jsonl",
            "root",
            "all_time",
            None,
            None,
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    connection.execute(
        "INSERT INTO source_manifestations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "manifestation:accounting",
            1,
            "source:accounting",
            "file",
            "sessions/accounting.jsonl",
            "accounting.jsonl",
            None,
            10_000,
            None,
            None,
            None,
            "revision:1",
            0,
            "active",
            None,
            None,
            "unavailable",
            1,
            PUBLICATION_ID,
            PUBLICATION_ID,
            None,
        ),
    )
    for index in range(occurrence_count):
        semantic_id = f"call:{index:03d}" if index < call_count else "call:000"
        connection.execute(
            "INSERT INTO source_occurrences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"occurrence:{index:03d}",
                semantic_id,
                1,
                "revision:1",
                index,
                index * 10,
                index * 10 + 5,
                "adapter-v1",
                PUBLICATION_ID,
            ),
        )

    connection.execute(
        "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "project:accounting",
            "synthetic-workspace",
            "[]",
            None,
            None,
            "[]",
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    for index in range(int(counts["sessions"])):
        connection.execute(
            """
            INSERT INTO sessions (
              session_id, adapter_native_session_key, identity_version, project_id,
              root_session_id, parent_session_id, relationship_basis,
              delegation_depth, lifecycle_state, state_basis, transition_version,
              start_at_us, end_at_us, observed_duration_us, completion_basis,
              label_candidates_json, primary_occurrence_id,
              first_seen_publication_id, last_seen_publication_id
            ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"session:{index:02d}",
                f"session-native:{index:02d}",
                "identity-v1",
                "project:accounting",
                0,
                "succeeded",
                "synthetic",
                1,
                index,
                index + 1,
                1,
                "synthetic",
                "[]",
                f"occurrence:{index:03d}",
                PUBLICATION_ID,
                PUBLICATION_ID,
            ),
        )
    for index in range(int(counts["turns"])):
        connection.execute(
            """
            INSERT INTO turns (
              turn_id, session_id, ordinal, lifecycle_state, state_basis,
              transition_version, start_at_us, end_at_us, start_source_rank,
              start_source_order,
              end_source_order, completion_basis, membership_json,
              primary_occurrence_id, first_seen_publication_id,
              last_seen_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"turn:{index:02d}",
                f"session:{index // 5:02d}",
                index % 5 + 1,
                "succeeded",
                "synthetic",
                1,
                index,
                index + 1,
                0,
                index,
                index + 1,
                "synthetic",
                "{}",
                f"occurrence:{index:03d}",
                PUBLICATION_ID,
                PUBLICATION_ID,
            ),
        )
    connection.execute(
        "INSERT INTO model_profiles VALUES (?, ?, ?, ?, ?, ?)",
        (
            "model-profile:accounting",
            "synthetic-model",
            "medium",
            None,
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    repository = SelectedFactRepository(
        connection,
        table="model_calls",
        key_column="call_id",
        row_type=_ModelCall,
    )

    def distributed(total: int, count: int, index: int) -> int:
        quotient, remainder = divmod(total, count)
        return quotient + (index < remainder)

    token_sums = accounting["token_observed_sums"]
    cached_observed = int(
        accounting["measurement_coverage"]["cached_input_tokens"]["observed_count"]
    )
    for index in range(call_count):
        call_id = f"call:{index:03d}"
        connection.execute(
            "INSERT INTO model_call_locations(call_id, storage_class) VALUES (?, 'base')",
            (call_id,),
        )
        repository.add(
            _ModelCall(
                call_id,
                "base",
                f"native:{index:03d}",
                "session:00",
                "turn:00",
                "model-profile:accounting",
                "succeeded",
                "synthetic",
                1,
                index,
                0,
                index,
                1,
                1,
                None,
                distributed(int(token_sums["uncached_input_tokens"]), call_count, index),
                (
                    distributed(int(token_sums["cached_input_tokens"]), cached_observed, index)
                    if index < cached_observed
                    else None
                ),
                distributed(int(token_sums["reasoning_tokens"]), call_count, index),
                distributed(int(token_sums["output_tokens"]), call_count, index),
                "exact",
                "stop",
                None,
                15,
                f"occurrence:{index:03d}",
                PUBLICATION_ID,
                PUBLICATION_ID,
            )
        )
    connection.execute(
        "INSERT INTO resources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "resource:accounting",
            "project:accounting",
            "file",
            "synthetic/file",
            "normalization-v1",
            "synthetic file",
            "[]",
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    for index in range(int(counts["tool_invocations"])):
        connection.execute(
            """
            INSERT INTO tool_invocations (
              tool_id, adapter_native_invocation_key, session_id, turn_id,
              transport_name, semantic_operation, tool_family, primary_resource_id,
              write_intent, lifecycle_state, state_basis, transition_version,
              start_at_us, start_source_rank, start_source_order,
              start_event_kind_order, start_transition_rank, start_occurrence_id,
              terminal_at_us, terminal_source_rank, terminal_source_order,
              terminal_event_kind_order, terminal_transition_rank,
              terminal_occurrence_id, observed_duration_us, output_bytes,
              error_category, measurement_mask, first_seen_publication_id,
              last_seen_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"tool:{index:02d}",
                f"tool-native:{index:02d}",
                "session:00",
                "turn:00",
                "synthetic",
                "read",
                "synthetic",
                "resource:accounting",
                0,
                "succeeded",
                "synthetic",
                1,
                index,
                0,
                index,
                1,
                1,
                f"occurrence:{index:03d}",
                index + 1,
                0,
                index,
                1,
                2,
                f"occurrence:{index:03d}",
                1,
                None,
                None,
                1,
                PUBLICATION_ID,
                PUBLICATION_ID,
            ),
        )
    for index in range(int(counts["activities"])):
        connection.execute(
            "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"activity:{index:02d}",
                "session:00",
                "turn:00",
                "synthetic",
                "succeeded",
                "synthetic",
                1,
                index,
                0,
                index,
                1,
                1,
                f"occurrence:{index:03d}",
                PUBLICATION_ID,
                PUBLICATION_ID,
            ),
        )
        connection.execute(
            """
            INSERT INTO state_changes (
              change_id, session_id, turn_id, resource_id, change_kind,
              before_revision, after_revision, causal_attribution, confidence,
              event_at_us, source_rank, source_order, event_kind_order,
              transition_rank, measurement_mask, primary_occurrence_id,
              first_seen_publication_id
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"state-change:{index:02d}",
                "session:00",
                "turn:00",
                "resource:accounting",
                "modified",
                f"revision:{index}",
                "exact",
                index,
                0,
                index,
                1,
                1,
                1,
                f"occurrence:{index:03d}",
                PUBLICATION_ID,
            ),
        )
    connection.execute(
        "INSERT INTO allowance_limits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "allowance-limit:accounting",
            "synthetic",
            "local",
            "test-plan",
            "weekly",
            None,
            "synthetic",
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    connection.execute(
        "INSERT INTO allowance_cycles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "allowance-cycle:accounting",
            "allowance-limit:accounting",
            "reset:synthetic",
            0,
            100,
            "synthetic",
            "complete",
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    for index in range(int(counts["allowance_observations"])):
        connection.execute(
            """
            INSERT INTO allowance_observations (
              observation_id, limit_id, cycle_id, plan_identity, window_kind,
              reset_identity, observation_ordinal, used_percent,
              remaining_percent, absolute_fields_json, reset_time_us,
              observed_at_us, source_rank, source_order, event_kind_order,
              transition_rank, measurement_mask, primary_occurrence_id,
              first_seen_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, '{}', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"allowance-observation:{index:02d}",
                "allowance-limit:accounting",
                "allowance-cycle:accounting",
                "test-plan",
                "weekly",
                "reset:synthetic",
                index + 1,
                str(index),
                100,
                index,
                0,
                index,
                1,
                1,
                1,
                f"occurrence:{index:03d}",
                PUBLICATION_ID,
            ),
        )
    return connection


def test_tiny_accounting_counts_canonical_calls_not_source_copies() -> None:
    accounting = _accounting_oracle()
    connection = _tiny_accounting_connection(accounting)
    repository = AccountingRepository(connection)
    summary = repository.summary()
    assert (
        summary.canonical_model_calls
        == accounting["source_reconciliation"]["canonical_model_calls"]
    )
    assert (
        summary.source_occurrences == accounting["source_reconciliation"]["model_call_occurrences"]
    )
    assert (
        summary.uncached_input_tokens.value
        == accounting["token_observed_sums"]["uncached_input_tokens"]
    )
    assert summary.uncached_input_tokens.complete is True
    assert (
        summary.cached_input_tokens.value
        == accounting["token_observed_sums"]["cached_input_tokens"]
    )
    assert (
        summary.cached_input_tokens.observed_count
        == accounting["measurement_coverage"]["cached_input_tokens"]["observed_count"]
    )
    assert (
        summary.cached_input_tokens.missing_count
        == accounting["measurement_coverage"]["cached_input_tokens"]["missing_count"]
    )
    assert summary.cached_input_tokens.complete is False
    assert summary.reasoning_tokens.value == accounting["token_observed_sums"]["reasoning_tokens"]
    assert summary.output_tokens.value == accounting["token_observed_sums"]["output_tokens"]

    calls = repository.model_call_tokens()
    assert len(calls) == accounting["canonical_counts"]["model_calls"]
    assert (
        calls[
            accounting["measurement_coverage"]["cached_input_tokens"]["observed_count"]
        ].cached_input_tokens
        is None
    )

    for table, expected in accounting["canonical_counts"].items():
        if table == "model_calls":
            continue
        assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == expected

    token_totals = accounting["token_totals"]
    assert token_totals["cached_input_tokens"] is None
    default_total = None
    if summary.cached_input_tokens.complete:
        uncached = summary.uncached_input_tokens.value
        cached = summary.cached_input_tokens.value
        output = summary.output_tokens.value
        assert uncached is not None and cached is not None and output is not None
        default_total = uncached + cached + output
    assert default_total == token_totals["total_tokens"] is None
    assert accounting["token_formula"]["reasoning_in_default_total"] is False
    assert summary.reasoning_tokens.value == token_totals["reasoning_tokens"]

    occurrence_plan = connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT COUNT(*)
        FROM source_occurrences AS occurrence
        JOIN model_call_locations AS call
          ON call.call_id = occurrence.semantic_logical_id
        """
    ).fetchall()
    expected_index = _TINY_ACCOUNTING_INDEX_BY_SCHEMA[SCHEMA_CONTRACT_SHA256]
    assert any(expected_index in str(row[3]) for row in occurrence_plan)


def test_accounting_operation_timing_uses_a_deterministic_observer_seam() -> None:
    clock_values = iter((100, 350, 1_000, 1_400))
    observations: list[RepositoryTiming] = []
    repository = AccountingRepository(
        _tiny_accounting_connection(_accounting_oracle()),
        clock_ns=lambda: next(clock_values),
        observe_timing=observations.append,
    )
    repository.summary()
    repository.model_call_tokens()
    assert observations == [
        RepositoryTiming("accounting_summary", 250),
        RepositoryTiming("model_call_tokens", 400),
    ]


def test_multi_producer_copies_preserve_two_coordinates_and_one_canonical_fact() -> None:
    connection = _tiny_accounting_connection(_accounting_oracle())
    for logical_id, kind in (
        ("producer:copy", "producer"),
        ("source:copy", "source"),
        ("manifestation:copy", "source_manifestation"),
    ):
        _identity(connection, logical_id, kind)
    connection.execute(
        "INSERT INTO source_producers VALUES (?, ?, ?, ?, ?)",
        ("producer:copy", "synthetic-copy", "Copy", PUBLICATION_ID, PUBLICATION_ID),
    )
    connection.execute(
        "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "source:copy",
            "adapter:accounting",
            "producer:copy",
            "synthetic-jsonl",
            "copy-root",
            "all_time",
            None,
            None,
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    connection.execute(
        "INSERT INTO source_manifestations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "manifestation:copy",
            2,
            "source:copy",
            "copy-file",
            "sessions/copy.jsonl",
            "copy.jsonl",
            None,
            1_000,
            None,
            None,
            None,
            "revision:copy",
            1,
            "active",
            None,
            None,
            "unavailable",
            1,
            PUBLICATION_ID,
            PUBLICATION_ID,
            None,
        ),
    )

    vector = (
        ("sessions", "session_id", "session:00", "occurrence:000"),
        ("turns", "turn_id", "turn:00", "occurrence:002"),
        ("model_calls", "call_id", "call:001", "occurrence:001"),
        ("tool_invocations", "tool_id", "tool:00", "occurrence:003"),
        (
            "allowance_observations",
            "observation_id",
            "allowance-observation:00",
            "occurrence:004",
        ),
    )
    repository = SourceOccurrenceRepository(connection)
    for index, (table, key_column, logical_id, original_occurrence_id) in enumerate(vector):
        connection.execute(
            "UPDATE source_occurrences SET semantic_logical_id = ? WHERE occurrence_id = ?",
            (logical_id, original_occurrence_id),
        )
        copy_occurrence_id = f"occurrence:copy:{index}"
        _identity(connection, copy_occurrence_id, "source_occurrence")
        repository.add(
            SourceOccurrence(
                copy_occurrence_id,
                logical_id,
                2,
                "revision:copy",
                index,
                index * 20,
                index * 20 + 10,
                "adapter-v1",
                PUBLICATION_ID,
            )
        )
        columns = tuple(
            str(column[1]) for column in connection.execute(f"PRAGMA table_info({table})")
        )
        row = connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE {key_column} = ?",
            (logical_id,),
        ).fetchone()
        assert row is not None
        row_type = make_dataclass(
            f"Copied{table.title().replace('_', '')}", [(column, Any) for column in columns]
        )
        typed_fact = row_type(*row)
        typed_repository = SelectedFactRepository(
            connection,
            table=table,
            key_column=key_column,
            row_type=row_type,
        )
        # A second producer contributes a new occurrence, while the exact
        # canonical typed fact write coalesces through the production repository.
        assert typed_repository.add(typed_fact) == typed_fact
        assert typed_repository.get(logical_id) == typed_fact
        producers = connection.execute(
            """
            SELECT DISTINCT source.producer_id
            FROM source_occurrences AS occurrence
            JOIN source_manifestations AS manifestation
              ON manifestation.manifestation_key = occurrence.manifestation_key
            JOIN sources AS source ON source.source_id = manifestation.source_id
            WHERE occurrence.semantic_logical_id = ?
            ORDER BY source.producer_id
            """,
            (logical_id,),
        ).fetchall()
        assert producers == [("producer:accounting",), ("producer:copy",)]
