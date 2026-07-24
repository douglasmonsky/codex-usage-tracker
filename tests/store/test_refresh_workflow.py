from __future__ import annotations

from pathlib import Path

import pytest

from codex_usage_tracker.application.protocols import CacheRepository
from codex_usage_tracker.store import refresh as refresh_module
from codex_usage_tracker.store.cache_repository import SQLiteCacheRepository
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.refresh_metadata import read_refresh_workflow_state
from codex_usage_tracker.store.schema import init_db
from tests.store_dashboard_helpers import _make_codex_home


def test_refresh_cache_writes_have_one_runtime_owner() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src" / "codex_usage_tracker"
    write_owners = {
        source_path.relative_to(source_root).as_posix()
        for source_path in source_root.rglob("*.py")
        if any(
            statement in source_path.read_text(encoding="utf-8")
            for statement in ("INSERT INTO refresh_meta", "DELETE FROM refresh_meta")
        )
    }
    assert write_owners == {"store/cache_repository.py"}


def test_cache_repository_uses_callers_transaction_and_key_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)
        cache = SQLiteCacheRepository(conn)
        assert isinstance(cache, CacheRepository)
        cache.set_many({"refresh": "ready", "home": "cached"})

    with (
        pytest.raises(RuntimeError, match="synthetic rollback"),
        connect(db_path) as conn,
    ):
        cache = SQLiteCacheRepository(conn)
        cache.set_many({"refresh": "pending"})
        cache.delete("home")
        raise RuntimeError("synthetic rollback")

    with connect(db_path) as conn:
        cache = SQLiteCacheRepository(conn)
        assert cache.get("refresh") == "ready"
        assert cache.get("home") == "cached"
        cache.delete("home")

    with connect(db_path) as conn:
        cache = SQLiteCacheRepository(conn)
        assert cache.get("refresh") == "ready"
        assert cache.get("home") is None


def test_interrupted_rebuild_records_resumable_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)
    original_refresh = refresh_module.refresh_usage_index

    def fail_after_clear(**_kwargs: object) -> None:
        raise RuntimeError("synthetic interrupted rebuild")

    monkeypatch.setattr(refresh_module, "refresh_usage_index", fail_after_clear)
    with pytest.raises(RuntimeError, match="synthetic interrupted rebuild"):
        refresh_module.rebuild_usage_index(codex_home=codex_home, db_path=db_path)

    state = read_refresh_workflow_state(db_path)
    assert state is not None
    assert state["kind"] == "rebuild"
    assert state["phase"] == "cleared"
    assert state["status"] == "running"

    monkeypatch.setattr(refresh_module, "refresh_usage_index", original_refresh)
    original_refresh(codex_home=codex_home, db_path=db_path)

    completed = read_refresh_workflow_state(db_path)
    assert completed is not None
    assert completed["kind"] == "rebuild"
    assert completed["phase"] == "complete"
    assert completed["status"] == "completed"
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] > 0


def test_interrupted_otel_phase_is_visible_and_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    original_otel_refresh = refresh_module._refresh_otel_completions

    def fail_otel(**_kwargs: object) -> dict[str, int]:
        raise RuntimeError("synthetic OTel interruption")

    monkeypatch.setattr(refresh_module, "_refresh_otel_completions", fail_otel)
    with pytest.raises(RuntimeError, match="synthetic OTel interruption"):
        refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)

    state = read_refresh_workflow_state(db_path)
    assert state is not None
    assert state["kind"] == "refresh"
    assert state["phase"] == "otel"
    assert state["status"] == "running"

    monkeypatch.setattr(
        refresh_module,
        "_refresh_otel_completions",
        original_otel_refresh,
    )
    refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)

    completed = read_refresh_workflow_state(db_path)
    assert completed is not None
    assert completed["kind"] == "refresh"
    assert completed["phase"] == "complete"
    assert completed["status"] == "completed"
