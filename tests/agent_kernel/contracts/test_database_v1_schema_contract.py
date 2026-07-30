from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_PATH = (
    _REPO_ROOT / "docs" / "architecture" / "AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md"
)
_CONTRACT_ID = "codex-usage-tracker.agent-kernel.schema-contract.v1"
_EXPECTED_DIGEST = "1a2dcffe778633457bbeb60dd3a41c233a78c15af2a3393bf9cacc1d9e645bb5"
_COPY_STABILITY_VECTOR_ID = "database-v1.multi-producer-copy-stability.v1"
_COPY_STABILITY_VECTOR_ROWS = (
    "| `sessions` | `session:shared` | `root:a/file:a#1` | `root:b/file:b#1` | 1 | 2 |",
    "| `turns` | `turn:shared` | `root:a/file:a#2` | `root:b/file:b#2` | 1 | 2 |",
    "| `model_calls` | `call:shared` | `root:a/file:a#3` | `root:b/file:b#3` | 1 | 2 |",
    "| `tool_invocations` | `tool:shared` | `root:a/file:a#4` | `root:b/file:b#4` | 1 | 2 |",
    "| `allowance_observations` | `allowance-observation:shared` | `root:a/file:a#5` | `root:b/file:b#5` | 1 | 2 |",
)
_EXPECTED_OBJECT_COUNTS = (42, 44, 6, 6)
_ANALYTICAL_TABLES = (
    "metadata",
    "publications",
    "publication_head",
    "identity_registry",
    "selector_aliases",
    "adapters",
    "source_producers",
    "sources",
    "source_manifestations",
    "source_cursors",
    "source_diagnostics",
    "source_occurrences",
    "selector_anchors",
    "projects",
    "resources",
    "model_profiles",
    "sessions",
    "turns",
    "late_parent_edges",
    "lifecycle_transitions",
    "model_call_locations",
    "model_calls",
    "tool_invocations",
    "tool_resources",
    "activities",
    "compaction_boundaries",
    "context_components",
    "state_changes",
    "allowance_limits",
    "allowance_cycles",
    "allowance_observations",
    "allowance_intervals",
    "rate_card_revisions",
    "active_rate_card",
    "publication_source_coverage",
    "publication_capability_coverage",
    "publication_entity_counts",
    "publication_deltas",
    "publication_delta_entities",
    "publication_delta_samples",
    "model_call_tail_state",
    "model_call_tail",
)
_ANALYTICAL_INDEXES = (
    "sources_by_producer",
    "source_manifestations_by_occurrence_key",
    "source_manifestations_by_identity",
    "source_manifestations_by_technical_path",
    "source_manifestations_by_state",
    "source_diagnostics_by_manifestation",
    "source_occurrences_by_logical_id",
    "selector_anchors_timeline",
    "selector_anchors_by_logical_id",
    "sessions_start_timeline",
    "sessions_terminal_timeline",
    "sessions_by_parent",
    "sessions_by_root",
    "turns_timeline",
    "turns_by_session",
    "late_parent_edges_timeline",
    "late_parent_edges_by_parent",
    "lifecycle_transitions_timeline",
    "lifecycle_transitions_by_entity",
    "model_calls_timeline",
    "model_calls_by_session",
    "tools_start_timeline",
    "tools_pending_start",
    "tools_terminal_timeline",
    "tools_by_session",
    "tools_by_resource",
    "tools_by_family",
    "tool_resources_by_resource",
    "activities_timeline",
    "activities_by_session",
    "state_changes_timeline",
    "state_changes_by_session",
    "state_changes_by_resource",
    "compactions_timeline",
    "compactions_by_session",
    "context_components_timeline",
    "allowance_observations_timeline",
    "allowance_observations_by_compatibility",
    "allowance_intervals_timeline",
    "allowance_intervals_by_cycle",
    "publication_source_coverage_by_source",
    "publication_delta_samples_by_selector",
    "model_call_tail_timeline",
    "model_call_tail_by_session",
)
_OPERATIONAL_TABLES = (
    "operational_metadata",
    "operation_jobs",
    "writer_leases",
    "artifact_pointers",
    "recovery_intents",
    "source_dirty_hints",
)
_OPERATIONAL_INDEXES = (
    "operation_jobs_one_active_compatible",
    "operation_jobs_by_state",
    "operation_jobs_by_parent",
    "artifact_pointers_by_role",
    "recovery_intents_by_state",
    "source_dirty_hints_by_observed",
)


def _normalized_ddl(markdown: str, database: str) -> str:
    match = re.search(
        rf"<!-- {database}-ddl:start -->\n```sql\n(.*?)"
        rf"```\n<!-- {database}-ddl:end -->",
        markdown,
        re.DOTALL,
    )
    assert match is not None
    lines = [
        line.rstrip(" \t")
        for line in match.group(1).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def _object_names(connection: sqlite3.Connection, object_type: str) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_schema
        WHERE type = ?
          AND sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
        ORDER BY rowid
        """,
        (object_type,),
    )
    return tuple(str(row[0]) for row in rows)


def _build_database(ddl: str) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(ddl)
    return connection


def _primary_key(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    columns = connection.execute(
        f'PRAGMA table_info("{table}")'  # noqa: S608
    ).fetchall()
    return tuple(
        str(row[1])
        for row in sorted((row for row in columns if int(row[5])), key=lambda row: row[5])
    )


def _indexes(
    connection: sqlite3.Connection,
    table: str,
) -> dict[tuple[str, ...], bool]:
    indexes = connection.execute(
        f'PRAGMA index_list("{table}")'  # noqa: S608
    ).fetchall()
    return {
        tuple(
            str(column[2])
            for column in connection.execute(
                f'PRAGMA index_info("{index[1]}")'  # noqa: S608
            )
        ): bool(index[2])
        for index in indexes
    }


def _foreign_keys(
    connection: sqlite3.Connection,
    table: str,
) -> set[tuple[str, str, str]]:
    return {
        (str(row[2]), str(row[3]), str(row[4]))
        for row in connection.execute(
            f'PRAGMA foreign_key_list("{table}")'  # noqa: S608
        )
    }


def test_database_v1_schema_contract_is_executable_exact_and_digest_locked() -> None:
    markdown = _CONTRACT_PATH.read_text(encoding="utf-8")
    analytical = _normalized_ddl(markdown, "analytical")
    operational = _normalized_ddl(markdown, "operational")
    canonical = (f"{_CONTRACT_ID}\nanalytical\n{analytical}operational\n{operational}").encode()

    assert f"**Canonical SHA-256:** `{_EXPECTED_DIGEST}`" in markdown
    assert hashlib.sha256(canonical).hexdigest() == _EXPECTED_DIGEST
    assert f"**Vector:** `{_COPY_STABILITY_VECTOR_ID}`" in markdown
    assert all(row in markdown for row in _COPY_STABILITY_VECTOR_ROWS)
    assert (
        len(_ANALYTICAL_TABLES),
        len(_ANALYTICAL_INDEXES),
        len(_OPERATIONAL_TABLES),
        len(_OPERATIONAL_INDEXES),
    ) == _EXPECTED_OBJECT_COUNTS

    analytical_db = _build_database(analytical)
    operational_db = _build_database(operational)
    try:
        assert _object_names(analytical_db, "table") == _ANALYTICAL_TABLES
        assert _object_names(analytical_db, "view") == ("model_calls_visible",)
        assert _object_names(analytical_db, "index") == _ANALYTICAL_INDEXES
        assert _object_names(operational_db, "table") == _OPERATIONAL_TABLES
        assert _object_names(operational_db, "view") == ()
        assert _object_names(operational_db, "index") == _OPERATIONAL_INDEXES
        assert analytical_db.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert operational_db.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert analytical_db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert operational_db.execute("PRAGMA foreign_key_check").fetchall() == []

        for connection in (analytical_db, operational_db):
            tables = connection.execute("PRAGMA table_list").fetchall()
            owned_tables = [
                row
                for row in tables
                if row[2] == "table" and row[1] not in {"sqlite_schema", "sqlite_temp_schema"}
            ]
            assert all(row[4] == 1 and row[5] == 1 for row in owned_tables)
    finally:
        analytical_db.close()
        operational_db.close()


def test_database_v1_multi_producer_identity_seams_are_structurally_locked() -> None:
    markdown = _CONTRACT_PATH.read_text(encoding="utf-8")
    analytical_db = _build_database(_normalized_ddl(markdown, "analytical"))
    operational_db = _build_database(_normalized_ddl(markdown, "operational"))
    try:
        producer_indexes = _indexes(analytical_db, "source_producers")
        source_indexes = _indexes(analytical_db, "sources")
        manifestation_indexes = _indexes(analytical_db, "source_manifestations")
        occurrence_indexes = _indexes(analytical_db, "source_occurrences")

        assert producer_indexes[("configured_producer_key",)]
        assert source_indexes[
            (
                "adapter_id",
                "producer_id",
                "source_kind",
                "adapter_native_source_key",
            )
        ]
        assert manifestation_indexes[("source_id", "adapter_native_file_key")]
        assert (
            manifestation_indexes[("source_id", "technical_path_key", "state", "manifestation_id")]
            is False
        )
        assert (
            occurrence_indexes[
                (
                    "semantic_logical_id",
                    "manifestation_key",
                    "source_revision",
                    "record_ordinal",
                    "byte_start",
                    "occurrence_id",
                )
            ]
            is False
        )

        assert (
            "source_producers",
            "producer_id",
            "producer_id",
        ) in _foreign_keys(analytical_db, "sources")
        assert (
            "sources",
            "source_id",
            "source_id",
        ) in _foreign_keys(analytical_db, "source_manifestations")
        assert _primary_key(analytical_db, "publication_source_coverage") == (
            "publication_id",
            "source_id",
        )
        assert {
            ("publications", "publication_id", "publication_id"),
            ("sources", "source_id", "source_id"),
        } <= _foreign_keys(analytical_db, "publication_source_coverage")
        assert _primary_key(operational_db, "source_dirty_hints") == (
            "source_id",
            "technical_path_key",
        )

        semantic_primary_keys = {
            "sessions": ("session_id",),
            "turns": ("turn_id",),
            "model_calls": ("call_id",),
            "tool_invocations": ("tool_id",),
            "allowance_observations": ("observation_id",),
            "context_components": ("component_id",),
            "source_occurrences": ("occurrence_id",),
        }
        assert {
            table: _primary_key(analytical_db, table) for table in semantic_primary_keys
        } == semantic_primary_keys
        context_columns = {
            str(row[1]) for row in analytical_db.execute("PRAGMA table_info(context_components)")
        }
        assert {
            "component_id",
            "session_id",
            "turn_id",
            "call_id",
            "category",
            "observed_utf8_bytes",
            "observed_event_count",
            "total_context_utf8_bytes",
            "estimator",
            "estimated_tokens",
            "inclusion_basis",
            "capability_basis",
            "measurement_basis",
            "event_at_us",
            "source_rank",
            "source_order",
            "event_kind_order",
            "transition_rank",
            "measurement_mask",
            "primary_occurrence_id",
            "first_seen_publication_id",
            "last_seen_publication_id",
        } == context_columns
        assert not context_columns & {
            "body",
            "content",
            "prompt",
            "response",
            "reasoning",
            "tool_output",
        }
    finally:
        analytical_db.close()
        operational_db.close()


def test_rate_card_frontier_schema_is_effective_dated_and_self_linked() -> None:
    markdown = _CONTRACT_PATH.read_text(encoding="utf-8")
    analytical_db = _build_database(_normalized_ddl(markdown, "analytical"))
    try:
        columns = {
            str(row[1]): row
            for row in analytical_db.execute("PRAGMA table_info(rate_card_revisions)")
        }
        assert columns["effective_at_us"][3] == 1
        assert "predecessor_rate_card_id" in columns
        assert (
            "rate_card_revisions",
            "predecessor_rate_card_id",
            "rate_card_id",
        ) in _foreign_keys(analytical_db, "rate_card_revisions")
    finally:
        analytical_db.close()
