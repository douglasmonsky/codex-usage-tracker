from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.database import initialize_analytical_database
from codex_usage_tracker.kernel.hydration import (
    HydrationPreset,
    catalog_sources,
    select_hydration_sources,
)
from codex_usage_tracker.kernel.identity import source_id
from codex_usage_tracker.kernel.operational import (
    OPERATIONAL_SCHEMA_VERSION,
    OPERATIONAL_TABLES,
    initialize_operational_database,
    load_cutover_control,
    load_hydration_coverage,
    record_hydration_catalog,
    register_source,
)


def test_full_source_path_exists_only_in_owner_operational_registry(
    tmp_path: Path,
) -> None:
    sensitive = "/Users/alice/Secret Client/codex/sessions/private.jsonl"
    analytical = tmp_path / "codex-usage-kernel-v1.sqlite3"
    operational = tmp_path / "codex-usage-kernel-operational-v1.sqlite3"
    identifier = source_id(
        source_kind="session",
        device_identity="synthetic-device",
        file_identity="synthetic-file",
    )

    initialize_analytical_database(analytical)
    initialize_operational_database(operational)
    register_source(operational, identifier, Path(sensitive))

    assert sensitive.encode() not in analytical.read_bytes()
    assert sensitive.encode() in operational.read_bytes()
    assert oct(operational.stat().st_mode & 0o777) == "0o600"


def test_operational_sidecar_has_only_approved_tables(tmp_path: Path) -> None:
    path = tmp_path / "operational.sqlite3"
    initialize_operational_database(path)

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }

    assert tables == OPERATIONAL_TABLES


def test_owner_only_catalog_records_partial_coverage_without_raw_content(
    tmp_path: Path,
) -> None:
    old = tmp_path / "sessions" / "old.jsonl"
    recent = tmp_path / "sessions" / "recent.jsonl"
    old.parent.mkdir()
    old.write_text(
        '{"timestamp":"2024-01-01T00:00:00Z","type":"synthetic"}\n',
        encoding="utf-8",
    )
    recent.write_text(
        '{"timestamp":"2026-07-20T00:00:00Z","type":"synthetic"}\n',
        encoding="utf-8",
    )
    captured_at = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)
    selection = select_hydration_sources(
        catalog_sources((old, recent)),
        preset=HydrationPreset.RECENT_30D,
        captured_at=captured_at,
    )
    operational = tmp_path / "operational.sqlite3"
    analytical = tmp_path / "analytical.sqlite3"
    initialize_operational_database(operational)
    initialize_analytical_database(analytical)

    coverage = record_hydration_catalog(
        operational,
        selection,
        hydrated_generation=1,
    )

    assert coverage == load_hydration_coverage(operational)
    assert coverage["preset"] == "recent_30d"
    assert coverage["cutoff_at"] == "2026-06-27T12:00:00Z"
    assert coverage["complete_history"] is False
    assert coverage["cataloged_source_count"] == 2
    assert coverage["hydrated_source_count"] == 1
    assert coverage["deferred_source_count"] == 1
    assert coverage["hydrated_bytes"] == recent.stat().st_size
    assert coverage["deferred_bytes"] == old.stat().st_size
    assert isinstance(coverage["coverage_revision"], str)
    assert old.read_bytes() not in operational.read_bytes()
    assert recent.read_bytes() not in operational.read_bytes()
    assert old.read_bytes() not in analytical.read_bytes()
    assert recent.read_bytes() not in analytical.read_bytes()


def test_operational_reopen_validates_version_and_repairs_permissions(
    tmp_path: Path,
) -> None:
    path = tmp_path / "operational.sqlite3"
    initialize_operational_database(path)
    path.chmod(0o644)

    initialize_operational_database(path)

    assert oct(path.stat().st_mode & 0o777) == "0o600"
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"PRAGMA user_version = {OPERATIONAL_SCHEMA_VERSION + 1}"
        )
    with pytest.raises(ValueError, match="schema version"):
        initialize_operational_database(path)


def test_normal_operational_access_repairs_permission_drift(tmp_path: Path) -> None:
    path = tmp_path / "operational.sqlite3"
    initialize_operational_database(path)
    path.chmod(0o644)

    load_cutover_control(path)

    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_operational_directory_is_rejected_without_permission_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "operational.sqlite3"
    path.mkdir(mode=0o755)

    with pytest.raises(ValueError, match="regular file"):
        initialize_operational_database(path)

    assert oct(path.stat().st_mode & 0o777) == "0o755"
