from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.storage.database import (
    DatabaseContractError,
    DatabaseIdentityError,
    initialize_analytical,
    initialize_operational,
    measure_database_size,
    open_builder,
    open_read_only,
    open_writer,
    validate_database,
)
from codex_usage_tracker.agent_kernel.storage.paths import (
    ANALYTICAL_CACHE_FILENAME,
    OwnerOnlyPathError,
    agent_kernel_cache_path,
    ensure_owner_only_directory,
)
from codex_usage_tracker.agent_kernel.storage.schema import (
    ANALYTICAL_DDL,
    OPERATIONAL_DDL,
    SCHEMA_CONTRACT_SHA256,
    canonical_schema_digest,
    schema_objects,
)

_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT = _ROOT / "docs" / "architecture" / "AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md"
_PREDECESSOR_SCHEMA_DIGEST = (
    "1a2dcffe778633457bbeb60dd3a41c233a78c15af2a3393bf9cacc1d9e645bb5"
)
_SELECTED_SCHEMA_DIGEST = (
    "e3b8509774987fb4fd9cd09aeee1ab9ee32642932ea6a07726315154409b1e35"
)
_CK08R3A_INDEX_NAMES = (
    "evidence_model_calls_by_session_order",
    "evidence_model_call_tail_by_session_order",
    "evidence_tools_by_session_order",
    "evidence_activities_by_session_order",
    "evidence_state_changes_by_session_order",
    "evidence_compactions_by_session_order",
    "evidence_context_components_by_session_order",
    "evidence_turns_by_session_order",
    "evidence_lifecycle_timeline_order",
    "evidence_source_occurrences_by_logical_order",
    "evidence_tools_by_resource_order",
    "evidence_state_changes_by_resource_order",
    "evidence_allowance_observations_order",
)


def _contract_ddl(name: str) -> str:
    markdown = _CONTRACT.read_text(encoding="utf-8")
    match = re.search(
        rf"<!-- {name}-ddl:start -->\n```sql\n(.*?)```\n<!-- {name}-ddl:end -->",
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


def _selected_analytical_ddl() -> str:
    return _contract_ddl("analytical") + "\n" + _contract_ddl("ck08r3a-evidence-indexes")


def _pragma(connection: sqlite3.Connection, name: str) -> object:
    return connection.execute(f"PRAGMA {name}").fetchone()[0]  # noqa: S608


def test_packaged_ddl_is_exact_contract_and_inventory_locked() -> None:
    predecessor = _contract_ddl("analytical")
    selected = _selected_analytical_ddl()
    assert ANALYTICAL_DDL in {predecessor, selected}
    assert OPERATIONAL_DDL == _contract_ddl("operational")
    if ANALYTICAL_DDL == predecessor:
        assert canonical_schema_digest() == SCHEMA_CONTRACT_SHA256 == _PREDECESSOR_SCHEMA_DIGEST
    else:
        assert ANALYTICAL_DDL == selected
        assert canonical_schema_digest() == SCHEMA_CONTRACT_SHA256 == _SELECTED_SCHEMA_DIGEST

    analytical = schema_objects("analytical")
    operational = schema_objects("operational")
    assert sum(item.object_type == "table" for item in analytical) == 42
    expected_index_count = 44 if ANALYTICAL_DDL == predecessor else 57
    assert sum(item.object_type == "index" for item in analytical) == expected_index_count
    assert [item.name for item in analytical if item.object_type == "view"] == [
        "model_calls_visible"
    ]
    assert sum(item.object_type == "table" for item in operational) == 6
    assert sum(item.object_type == "index" for item in operational) == 6


def test_ck08r3a_selected_schema_transition_is_exact_and_fail_closed() -> None:
    predecessor = _contract_ddl("analytical")
    selected = _selected_analytical_ddl()
    assert predecessor != selected
    assert hashlib.sha256(
        (
            "codex-usage-tracker.agent-kernel.schema-contract.v1\n"
            f"analytical\n{selected}"
            f"operational\n{_contract_ddl('operational')}"
        ).encode()
    ).hexdigest() == _SELECTED_SCHEMA_DIGEST

    selected_connection = sqlite3.connect(":memory:")
    try:
        selected_connection.executescript(selected)
        index_names = {
            str(row[0])
            for row in selected_connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
    finally:
        selected_connection.close()
    assert set(_CK08R3A_INDEX_NAMES) <= index_names
    assert len(index_names) == 57


def test_connection_modes_checks_and_database_size(tmp_path: Path) -> None:
    database = tmp_path / "analytical.sqlite3"
    writer = initialize_analytical(database)
    try:
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
        assert _pragma(writer, "page_size") == 4096
        assert str(_pragma(writer, "journal_mode")).lower() == "wal"
        assert _pragma(writer, "synchronous") == 1
        assert _pragma(writer, "foreign_keys") == 1
        assert _pragma(writer, "busy_timeout") == 5000
        assert _pragma(writer, "cache_size") == -20000
        assert _pragma(writer, "mmap_size") == 0
        assert _pragma(writer, "temp_store") == 2
        assert _pragma(writer, "wal_autocheckpoint") == 1000
        validation = validate_database(writer, "analytical", integrity=True)
        assert validation.quick_check == "ok"
        assert validation.integrity_check == "ok"
        assert validation.foreign_key_violations == ()
        size = measure_database_size(database, writer)
        assert size.database_bytes > 0
        assert size.page_size == 4096
        assert size.page_count > 0
        assert size.wal_bytes >= 0
        assert size.shm_bytes >= 0
    finally:
        writer.close()

    reader = open_read_only(database)
    try:
        assert _pragma(reader, "query_only") == 1
        assert _pragma(reader, "foreign_keys") == 1
        assert _pragma(reader, "busy_timeout") == 5000
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("INSERT INTO metadata(key, value) VALUES (?, ?)", ("x", "y"))
    finally:
        reader.close()

    reopened = open_writer(database)
    reopened.close()


def test_builder_mode_is_isolated_and_owner_only(tmp_path: Path) -> None:
    database = tmp_path / "builder.sqlite3"
    builder = open_builder(database)
    try:
        assert _pragma(builder, "journal_mode") == "off"
        assert _pragma(builder, "synchronous") == 0
        assert _pragma(builder, "foreign_keys") == 1
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
    finally:
        builder.close()


def test_old_foreign_and_swapped_database_are_rejected_without_creation(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises((sqlite3.OperationalError, FileNotFoundError)):
        open_writer(missing)
    assert not missing.exists()

    legacy = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(legacy)
    connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
    connection.commit()
    connection.close()
    legacy.chmod(0o600)
    before = legacy.read_bytes()
    with pytest.raises(DatabaseIdentityError):
        open_writer(legacy)
    assert legacy.read_bytes() == before

    operational = tmp_path / "operations.sqlite3"
    initialize_operational(operational).close()
    with pytest.raises(DatabaseIdentityError):
        open_writer(operational, "analytical")


def test_cache_paths_fail_closed_on_unsafe_existing_paths(tmp_path: Path) -> None:
    resolved = agent_kernel_cache_path(tmp_path)
    assert resolved.name == ANALYTICAL_CACHE_FILENAME
    assert stat.S_IMODE(resolved.parent.stat().st_mode) == 0o700

    permissive = tmp_path / "permissive"
    permissive.mkdir(mode=0o755)
    with pytest.raises(OwnerOnlyPathError):
        ensure_owner_only_directory(permissive)

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OwnerOnlyPathError):
        ensure_owner_only_directory(link)

    database = tmp_path / "unsafe.sqlite3"
    database.write_bytes(b"not sqlite")
    database.chmod(0o644)
    with pytest.raises(DatabaseContractError):
        open_writer(database)

    safe_database = tmp_path / "safe.sqlite3"
    initialize_analytical(safe_database).close()
    database_link = tmp_path / "database-link.sqlite3"
    database_link.symlink_to(safe_database)
    with pytest.raises(DatabaseContractError):
        open_writer(database_link)

    sidecar_target = tmp_path / "sidecar-target"
    sidecar_target.write_bytes(b"untouched")
    Path(f"{safe_database}-wal").symlink_to(sidecar_target)
    with pytest.raises(DatabaseContractError):
        open_writer(safe_database)
    assert sidecar_target.read_bytes() == b"untouched"


def test_cache_directory_owner_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "owner"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(os, "getuid", lambda: directory.stat().st_uid + 1)
    with pytest.raises(OwnerOnlyPathError):
        ensure_owner_only_directory(directory)
