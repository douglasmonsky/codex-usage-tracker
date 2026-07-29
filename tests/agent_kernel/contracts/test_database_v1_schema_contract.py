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
_EXPECTED_DIGEST = "eecff68062a8d0cba0619058a6e660f565d9a96c2575ab0dc93d72b987f31543"
_ANALYTICAL_TABLES = (
    "metadata",
    "publications",
    "publication_head",
    "identity_registry",
    "selector_aliases",
    "adapters",
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
    "source_manifestations_by_occurrence_key",
    "source_manifestations_by_identity",
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
    "allowance_observations_timeline",
    "allowance_observations_by_compatibility",
    "allowance_intervals_timeline",
    "allowance_intervals_by_cycle",
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


def test_database_v1_schema_contract_is_executable_exact_and_digest_locked() -> None:
    markdown = _CONTRACT_PATH.read_text(encoding="utf-8")
    analytical = _normalized_ddl(markdown, "analytical")
    operational = _normalized_ddl(markdown, "operational")
    canonical = (f"{_CONTRACT_ID}\nanalytical\n{analytical}operational\n{operational}").encode()

    assert f"**Canonical SHA-256:** `{_EXPECTED_DIGEST}`" in markdown
    assert hashlib.sha256(canonical).hexdigest() == _EXPECTED_DIGEST

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
