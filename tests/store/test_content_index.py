from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.core.json_contracts import validate_json_payload_contract
from codex_usage_tracker.reports.api import build_content_search_report
from codex_usage_tracker.store.api import connect, init_db, refresh_usage_index
from tests.store_dashboard_helpers import _make_codex_home


def test_refresh_populates_normalized_content_index_by_default(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with connect(db_path) as conn:
        init_db(conn)
        turn_count = conn.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()
        fragment_rows = conn.execute(
            """
            SELECT fragment_kind, role, safe_label, fragment_text, includes_raw_fragment
            FROM content_fragments
            ORDER BY line_start, safe_label
            """
        ).fetchall()

    assert turn_count is not None
    assert turn_count[0] >= 1
    assert any("SECRET RAW PROMPT" in row["fragment_text"] for row in fragment_rows)
    assert any("AFTER SELECTED CALL" in row["fragment_text"] for row in fragment_rows)
    assert any(row["fragment_kind"] == "reasoning_summary" for row in fragment_rows)
    assert all(row["includes_raw_fragment"] == 1 for row in fragment_rows)
    assert all("SECRET RAW PROMPT" not in row["safe_label"] for row in fragment_rows)


def test_refresh_aggregate_only_skips_content_index(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path, aggregate_only=True)

    with connect(db_path) as conn:
        init_db(conn)
        usage_count = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()
        fragment_count = conn.execute("SELECT COUNT(*) FROM content_fragments").fetchone()

        assert usage_count is not None
        assert fragment_count is not None
        assert usage_count[0] > 0
        assert fragment_count[0] == 0


def test_content_search_returns_explicit_local_snippets(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = build_content_search_report(
        db_path=db_path,
        query="SECRET RAW PROMPT",
        limit=1,
        max_snippet_chars=32,
    ).payload

    assert validate_json_payload_contract(payload) == []
    assert payload["schema"] == "codex-usage-tracker-content-search-v1"
    assert payload["content_mode"] == "local_content_index"
    assert payload["includes_indexed_content"] is True
    assert payload["includes_raw_fragments"] is True
    assert payload["row_count"] == 1
    assert payload["total_matched_rows"] >= 1
    assert payload["rows"][0]["includes_raw_fragment"] is True
    assert "SECRET" in payload["rows"][0]["snippet"]
    assert payload["rows"][0]["snippet_truncated"] is True
