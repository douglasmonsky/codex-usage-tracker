from __future__ import annotations

from pathlib import Path

import pytest

from codex_usage_tracker.store import schema as schema_module
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.integrity import check_database_integrity
from codex_usage_tracker.store.refresh import rebuild_usage_index, refresh_usage_index
from codex_usage_tracker.store.schema import SCHEMA_VERSION, init_db
from tests.store_dashboard_helpers import _make_codex_home

_HISTORICAL_VERSIONS = (13, 15, 16, 17, 20, 21, 24, 26, 27, 30, SCHEMA_VERSION - 1)


def _write_historical_database(db_path: Path, target_version: int) -> None:
    with connect(db_path) as connection:
        schema_module._ensure_migrations_table(connection)
        for version, migrate in schema_module._schema_migrations():
            if version > target_version:
                break
            migrate(connection)
            schema_module._record_migration(connection, version)
        connection.execute(f"PRAGMA user_version = {target_version}")


@pytest.mark.parametrize(
    "historical_version",
    _HISTORICAL_VERSIONS,
)
def test_valid_historical_database_migrates_without_rebuild_and_remains_integral(
    tmp_path: Path,
    historical_version: int,
) -> None:
    db_path = tmp_path / f"usage-v{historical_version}.sqlite3"
    _write_historical_database(db_path, historical_version)

    with connect(db_path) as connection:
        init_db(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    report = check_database_integrity(db_path)
    assert report["state"] == "pass"
    assert report["foreign_key_violation_count"] == 0


@pytest.mark.parametrize("historical_version", _HISTORICAL_VERSIONS)
def test_historical_database_refreshes_and_rebuilds_with_valid_data(
    tmp_path: Path,
    historical_version: int,
) -> None:
    db_path = tmp_path / f"usage-v{historical_version}.sqlite3"
    codex_home = _make_codex_home(tmp_path)
    _write_historical_database(db_path, historical_version)

    refreshed = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    assert refreshed.inserted_or_updated_events > 0

    rebuilt = rebuild_usage_index(codex_home=codex_home, db_path=db_path)
    assert rebuilt.inserted_or_updated_events > 0
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] > 0

    report = check_database_integrity(db_path)
    assert report["state"] == "pass"
    assert report["foreign_key_violation_count"] == 0
