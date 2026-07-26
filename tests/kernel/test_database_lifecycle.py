from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.database import (
    initialize_analytical_database,
    open_read_snapshot,
    open_writer,
    validate_analytical_database,
)


def test_create_reopen_and_writer_connections_enforce_integrity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "codex-usage-kernel-v1.sqlite3"

    initialize_analytical_database(path)

    assert oct(path.stat().st_mode & 0o777) == "0o600"
    with open_writer(path) as writer:
        assert writer.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with open_read_snapshot(path) as reader:
        assert reader.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("DELETE FROM sources")
    assert validate_analytical_database(path) == []


def test_reopen_restores_owner_only_permissions(tmp_path: Path) -> None:
    path = tmp_path / "codex-usage-kernel-v1.sqlite3"
    initialize_analytical_database(path)
    path.chmod(0o644)

    initialize_analytical_database(path)

    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_normal_connections_reject_schema_drift(tmp_path: Path) -> None:
    path = tmp_path / "codex-usage-kernel-v1.sqlite3"
    initialize_analytical_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 2")

    with pytest.raises(ValueError, match="schema identity"), open_writer(path):
        pass
    with pytest.raises(
        ValueError,
        match="schema identity",
    ), open_read_snapshot(path):
        pass


def test_existing_directory_is_rejected_without_permission_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "codex-usage-kernel-v1.sqlite3"
    path.mkdir(mode=0o755)

    with pytest.raises(ValueError, match="regular file"):
        initialize_analytical_database(path)

    assert oct(path.stat().st_mode & 0o777) == "0o755"


def test_interrupted_staging_creation_does_not_replace_active_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "codex-usage-kernel-v1.sqlite3"
    initialize_analytical_database(path)
    before = path.read_bytes()

    def fail_before_replace(_source: Path, _target: Path) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(os, "replace", fail_before_replace)
    with pytest.raises(OSError, match="synthetic replace failure"):
        initialize_analytical_database(path, replace=True)

    assert path.read_bytes() == before
    assert validate_analytical_database(path) == []


def test_kernel_creation_never_opens_legacy_database(tmp_path: Path) -> None:
    legacy = tmp_path / "codex-usage.sqlite3"
    legacy.write_bytes(b"legacy-schema-39-sentinel")
    kernel = tmp_path / "codex-usage-kernel-v1.sqlite3"

    initialize_analytical_database(kernel)

    assert legacy.read_bytes() == b"legacy-schema-39-sentinel"
    assert kernel.is_file()
