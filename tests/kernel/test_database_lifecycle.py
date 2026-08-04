from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.kernel import content, database, operational
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


def test_writer_timing_measures_only_the_active_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class FakeConnection:
        def execute(self, statement: str) -> None:
            assert statement == "BEGIN IMMEDIATE"
            events.append("begin")

        def commit(self) -> None:
            events.append("commit")

        def rollback(self) -> None:
            events.append("rollback")

    @contextmanager
    def fake_open_writer(*_args: Any, **_kwargs: Any) -> Any:
        events.append("open")
        yield FakeConnection()
        events.append("close")

    ticks = iter((10.0, 10.005))

    def perf_counter() -> float:
        events.append("timer")
        return next(ticks)

    observed: list[float] = []
    monkeypatch.setattr(database, "open_writer", fake_open_writer)
    monkeypatch.setattr(database.time, "perf_counter", perf_counter)

    with database.short_writer_transaction(
        Path("synthetic.sqlite3"),
        on_transaction_ms=observed.append,
    ):
        events.append("work")

    assert events == ["open", "begin", "timer", "work", "commit", "timer", "close"]
    assert observed == pytest.approx([5.0])


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
        connection.execute("PRAGMA user_version = 999")

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


@pytest.mark.parametrize(
    ("initializer", "name"),
    (
        (initialize_analytical_database, "analytical.sqlite3"),
        (operational.initialize_operational_database, "operational.sqlite3"),
        (content._initialize_content_database, "content.sqlite3"),
    ),
)
def test_database_initializers_close_connections_before_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initializer: Callable[[Path], Any],
    name: str,
) -> None:
    real_connect = sqlite3.connect
    real_replace = os.replace
    connections: list[Any] = []

    class TrackingConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection
            self.closed = False

        def close(self) -> None:
            self.closed = True
            self._connection.close()

        def __getattr__(self, attribute: str) -> Any:
            return getattr(self._connection, attribute)

    def connect(*args: Any, **kwargs: Any) -> TrackingConnection:
        connection = TrackingConnection(real_connect(*args, **kwargs))
        connections.append(connection)
        return connection

    def replace(source: Path, target: Path) -> None:
        assert connections
        assert all(connection.closed for connection in connections)
        real_replace(source, target)

    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr(os, "replace", replace)

    initializer(tmp_path / name)

    assert all(connection.closed for connection in connections)


def test_kernel_creation_never_opens_legacy_database(tmp_path: Path) -> None:
    legacy = tmp_path / "codex-usage.sqlite3"
    legacy.write_bytes(b"legacy-schema-39-sentinel")
    kernel = tmp_path / "codex-usage-kernel-v1.sqlite3"

    initialize_analytical_database(kernel)

    assert legacy.read_bytes() == b"legacy-schema-39-sentinel"
    assert kernel.is_file()
