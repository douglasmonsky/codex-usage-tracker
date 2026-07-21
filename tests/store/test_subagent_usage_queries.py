from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.store.api import refresh_usage_index
from codex_usage_tracker.store.subagent_usage_queries import query_subagent_usage_buckets
from tests.store_dashboard_helpers import (
    AUTO_REVIEW_SESSION_ID,
    SESSION_ID,
    _make_codex_home,
    _write_archived_log,
)


def _indexed_fixture(tmp_path: Path) -> Path:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    return db_path


def test_query_counts_one_spawn_for_multiple_subagent_calls(tmp_path: Path) -> None:
    db_path = _indexed_fixture(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE usage_events
            SET session_id = (
                    SELECT session_id FROM usage_events WHERE agent_role = 'test_runner'
                ),
                agent_role = 'test_runner',
                subagent_type = 'thread_spawn',
                parent_session_id = ?,
                parent_thread_name = 'Add Codex token tracking'
            WHERE session_id = ?
            """,
            (SESSION_ID, AUTO_REVIEW_SESSION_ID),
        )

    result = query_subagent_usage_buckets(db_path)

    assert result["cohorts"]["subagent"]["metrics"]["observed_spawns"] == 1
    assert result["cohorts"]["subagent"]["metrics"]["calls"] == 2
    assert result["breakdowns"]["role"][0]["group_key"] == "test_runner"
    assert result["breakdowns"]["type"][0]["group_key"] == "thread_spawn"
    assert result["breakdowns"]["parent"][0]["role_mix"] == [
        {
            "agent_role": "test_runner",
            "observed_spawns": 1,
            "calls": 2,
            "total_tokens": 100,
        }
    ]
    assert all("session_id" not in row for row in result["cohorts"]["subagent"]["model_buckets"])


def test_query_excludes_duplicate_subagent_rows_from_canonical_totals(tmp_path: Path) -> None:
    db_path = _indexed_fixture(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE usage_events SET is_duplicate = 1 WHERE agent_role = 'test_runner'")

    result = query_subagent_usage_buckets(db_path, agent_role="test_runner")

    assert result["cohorts"]["subagent"]["metrics"]["calls"] == 0
    assert result["cohorts"]["subagent"]["metrics"]["total_tokens"] == 0
    assert result["breakdowns"]["role"] == []
    assert result["coverage"]["missing_session_rows"] == 0


def test_role_filter_keeps_direct_baseline_in_base_scope(tmp_path: Path) -> None:
    result = query_subagent_usage_buckets(_indexed_fixture(tmp_path), agent_role="unknown-role")

    assert result["cohorts"]["direct"]["metrics"]["calls"] > 0
    assert result["cohorts"]["subagent"]["metrics"]["calls"] == 0


def test_parent_filter_matches_parent_direct_rows_and_attached_children(
    tmp_path: Path,
) -> None:
    result = query_subagent_usage_buckets(
        _indexed_fixture(tmp_path), parent_thread="Add Codex token tracking"
    )

    assert result["cohorts"]["direct"]["metrics"]["calls"] == 2
    assert result["cohorts"]["subagent"]["metrics"]["calls"] == 1
    assert result["breakdowns"]["parent"][0]["group_key"] == ("Add Codex token tracking")


def test_missing_session_metadata_is_coverage_not_a_spawn(tmp_path: Path) -> None:
    db_path = _indexed_fixture(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE usage_events SET session_id = '' WHERE agent_role = 'test_runner'")

    result = query_subagent_usage_buckets(db_path, agent_role="test_runner")

    assert result["cohorts"]["subagent"]["metrics"]["calls"] == 1
    assert result["cohorts"]["subagent"]["metrics"]["observed_spawns"] == 0
    assert result["cohorts"]["attributable_subagent"]["metrics"]["calls"] == 0
    assert result["coverage"]["missing_session_rows"] == 1
    assert result["coverage"]["missing_session_tokens"] == 50


def test_archived_rows_require_explicit_opt_in(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    _write_archived_log(codex_home)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path, include_archived=True)

    current = query_subagent_usage_buckets(db_path)
    with_archived = query_subagent_usage_buckets(db_path, include_archived=True)

    assert current["cohorts"]["direct"]["metrics"]["calls"] == 2
    assert with_archived["cohorts"]["direct"]["metrics"]["calls"] == 3


@pytest.mark.parametrize("limit", [0, 101, 1.5, True])
def test_breakdown_limit_is_validated_before_sql(tmp_path: Path, limit: object) -> None:
    db_path = tmp_path / "must-not-be-created.sqlite3"

    with pytest.raises(ValueError, match="limit must be an integer from 1 through 100"):
        query_subagent_usage_buckets(db_path, limit=limit)  # type: ignore[arg-type]

    assert not db_path.exists()
