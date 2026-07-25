from __future__ import annotations

import sqlite3
from pathlib import Path
from time import monotonic

from codex_usage_tracker.interfaces.mcp.core_tools import (
    build_usage_analyze,
    build_usage_query,
)
from tests.application.test_query import _seed


def test_core_query_and_analysis_read_last_commit_during_refresh_writer(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    _seed(db_path)
    query_args = {
        "entity": "model",
        "measures": ["tokens", "call_count"],
        "history": "all",
        "db_path": db_path,
        "pricing_path": pricing_path,
    }
    analysis_args = {
        "goal": "token_waste",
        "history": "all",
        "execution": "sync",
        "db_path": db_path,
        "pricing_path": pricing_path,
        "rate_card_path": tmp_path / "rate-card.json",
        "thresholds_path": tmp_path / "thresholds.json",
        "projects_path": tmp_path / "projects.json",
    }
    committed_query = build_usage_query(**query_args)
    committed_analysis = build_usage_analyze(**analysis_args)

    writer = sqlite3.connect(db_path, timeout=0.1)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute("BEGIN IMMEDIATE")
    writer.execute(
        "UPDATE usage_events SET total_tokens = total_tokens + 1000000 "
        "WHERE record_id = 'call-0'"
    )
    started_at = monotonic()
    try:
        locked_query = build_usage_query(**query_args)
        locked_analysis = build_usage_analyze(**analysis_args)
    finally:
        writer.rollback()
        writer.close()

    assert monotonic() - started_at < 1
    assert locked_query["result"]["rows"] == committed_query["result"]["rows"]  # type: ignore[index]
    assert locked_query["source_revision"] == committed_query["source_revision"]
    assert locked_analysis["result_schema"] == "codex-usage-tracker.analysis.v2"
    assert locked_analysis["source_revision"] == committed_analysis["source_revision"]
    assert locked_analysis["result"]["summary"] == committed_analysis["result"]["summary"]  # type: ignore[index]
