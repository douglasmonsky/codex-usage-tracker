from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import store
from codex_usage_tracker.core.models import DiagnosticFact
from codex_usage_tracker.store.api import connect, upsert_usage_events
from codex_usage_tracker.store.thread_summaries import rebuild_thread_summaries
from tests.store_dashboard_helpers import SESSION_ID, _usage_event


class _LimitedVariableConnection:
    def __init__(self, conn: sqlite3.Connection, *, max_variables: int) -> None:
        self._conn = conn
        self._max_variables = max_variables

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        if _parameter_count(parameters) > self._max_variables:
            raise sqlite3.OperationalError("too many SQL variables")
        return self._conn.execute(sql, parameters)

    def executemany(self, sql: str, parameters: Any, /) -> sqlite3.Cursor:
        return self._conn.executemany(sql, parameters)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def _parameter_count(parameters: Any) -> int:
    if parameters is None:
        return 0
    try:
        return len(parameters)
    except TypeError:
        return 0


def test_upsert_usage_events_batches_diagnostic_fact_deletes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"

    @contextmanager
    def limited_connect(db_path: Path) -> Iterator[_LimitedVariableConnection]:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        with suppress(sqlite3.DatabaseError):
            conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield _LimitedVariableConnection(conn, max_variables=600)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr(store, "connect", limited_connect)

    base_timestamp = datetime(2026, 5, 17, 18, 0, tzinfo=timezone.utc)
    events = [
        _usage_event(
            record_id=f"issue-69-record-{index:04d}",
            session_id=SESSION_ID,
            thread_key="thread:issue-69",
            event_timestamp=(base_timestamp + timedelta(seconds=index))
            .isoformat()
            .replace("+00:00", "Z"),
            cumulative_total_tokens=index + 1,
        )
        for index in range(1200)
    ]
    diagnostic_facts = [
        DiagnosticFact(
            record_id=event.record_id,
            fact_type="function",
            fact_name="exec_command",
            fact_category="function",
        )
        for event in events
    ]

    upsert_usage_events(
        events,
        db_path=db_path,
        refresh_links=False,
        diagnostic_facts=diagnostic_facts,
    )
    assert _diagnostic_fact_row_count(db_path) == 1200

    upsert_usage_events(events, db_path=db_path, refresh_links=False)
    assert _diagnostic_fact_row_count(db_path) == 0


def test_upsert_usage_events_batches_source_file_replacements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"

    @contextmanager
    def limited_connect(db_path: Path) -> Iterator[_LimitedVariableConnection]:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield _LimitedVariableConnection(conn, max_variables=600)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr(store, "connect", limited_connect)
    event = _usage_event(
        record_id="replace-record",
        session_id=SESSION_ID,
        thread_key="thread:replace",
        event_timestamp="2026-05-17T18:00:00Z",
        cumulative_total_tokens=100,
    )
    upsert_usage_events([event], db_path=db_path, refresh_links=False)

    source_files = [Path(f"/tmp/synthetic/missing-{index}.jsonl") for index in range(1200)]
    source_files.append(Path(event.source_file))
    upsert_usage_events(
        [],
        db_path=db_path,
        refresh_links=False,
        replace_source_files=source_files,
    )

    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0


def test_upsert_usage_events_batches_thread_derived_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"

    @contextmanager
    def limited_connect(db_path: Path) -> Iterator[_LimitedVariableConnection]:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield _LimitedVariableConnection(conn, max_variables=600)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr(store, "connect", limited_connect)
    base_timestamp = datetime(2026, 5, 17, 18, 0, tzinfo=timezone.utc)
    events = [
        _usage_event(
            record_id=f"thread-batch-{index:04d}",
            session_id=f"session-{index:04d}",
            thread_key=f"thread:batch-{index:04d}",
            event_timestamp=(base_timestamp + timedelta(seconds=index)).isoformat(),
            cumulative_total_tokens=index + 1,
        )
        for index in range(1200)
    ]

    upsert_usage_events(events, db_path=db_path, refresh_links=False)
    with connect(db_path) as conn:
        rebuild_thread_summaries(conn)
    upsert_usage_events(
        [],
        db_path=db_path,
        refresh_links=True,
        replace_source_files=[Path(event.source_file) for event in events],
    )

    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM thread_summaries").fetchone()[0] == 0


def _diagnostic_fact_row_count(db_path: Path) -> int:
    with connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM call_diagnostic_facts").fetchone()[0])
