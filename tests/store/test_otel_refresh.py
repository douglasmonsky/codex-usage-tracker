from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.store.api import (
    query_usage_record,
    rebuild_usage_index,
    refresh_metadata,
    refresh_usage_index,
)
from codex_usage_tracker.store.connection import connect
from tests.otel_helpers import (
    completion_attributes,
    synthetic_otlp_line,
    write_lines,
    write_otel_directory,
    write_usage_session,
)


def test_refresh_ingests_session_rows_before_reconciling_otel(tmp_path: Path) -> None:
    codex_home = write_usage_session(
        tmp_path, conversation_id="conversation-a", tokens=(100, 40, 30, 10)
    )
    otel_dir = tmp_path / "otel"
    write_lines(
        otel_dir / "codex-completions.jsonl",
        [
            synthetic_otlp_line(
                attributes=completion_attributes(
                    conversation_id="conversation-a",
                    tokens=(100, 40, 30, 10),
                    service_tier="priority",
                )
            )
        ],
    )
    db_path = tmp_path / "usage.sqlite3"

    result = refresh_usage_index(
        codex_home=codex_home, db_path=db_path, otel_dir=otel_dir
    )

    with connect(db_path) as conn:
        record_id = str(conn.execute("SELECT record_id FROM usage_events").fetchone()[0])
    row = query_usage_record(db_path=db_path, record_id=record_id)
    assert row is not None
    assert row["service_tier"] == "fast"
    assert result.parser_diagnostics["otel_matched"] == 1


def test_absent_otel_directory_is_a_supported_noop(tmp_path: Path) -> None:
    result = refresh_usage_index(
        codex_home=tmp_path / "codex",
        db_path=tmp_path / "usage.sqlite3",
        otel_dir=tmp_path / "missing",
    )

    assert result.parser_diagnostics.get("otel_files_scanned", 0) == 0


def test_refresh_records_protocol_confirmed_standard(tmp_path: Path) -> None:
    codex_home = write_usage_session(
        tmp_path, "conversation-standard", (100, 40, 30, 10)
    )
    otel_dir = tmp_path / "otel"
    write_lines(
        otel_dir / "codex-completions.jsonl",
        [
            synthetic_otlp_line(
                attributes=completion_attributes(
                    conversation_id="conversation-standard",
                    tokens=(100, 40, 30, 10),
                    service_tier=None,
                    app_version="0.143.0",
                )
            )
        ],
    )
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT service_tier, fast, service_tier_confidence FROM usage_events"
        ).fetchone()
    assert tuple(row) == ("standard", 0, "protocol")


def test_refresh_keeps_older_omitted_tier_unknown(tmp_path: Path) -> None:
    codex_home = write_usage_session(
        tmp_path, "conversation-legacy", (100, 40, 30, 10)
    )
    otel_dir = tmp_path / "otel"
    write_lines(
        otel_dir / "codex-completions.jsonl",
        [
            synthetic_otlp_line(
                attributes=completion_attributes(
                    conversation_id="conversation-legacy",
                    tokens=(100, 40, 30, 10),
                    service_tier=None,
                    app_version="0.142.9",
                )
            )
        ],
    )
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)

    with connect(db_path) as conn:
        row = conn.execute("SELECT service_tier, fast FROM usage_events").fetchone()
    assert tuple(row) == (None, None)


def test_otel_before_jsonl_matches_on_a_later_refresh(tmp_path: Path) -> None:
    otel_dir = write_otel_directory(
        tmp_path, "conversation-a", (100, 40, 30, 10)
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(
        codex_home=tmp_path / "empty", db_path=db_path, otel_dir=otel_dir
    )
    codex_home = write_usage_session(
        tmp_path, "conversation-a", (100, 40, 30, 10)
    )

    refresh_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)

    with connect(db_path) as conn:
        assert conn.execute("SELECT service_tier FROM usage_events").fetchone()[0] == "fast"


def test_rebuild_retains_staging_resets_match_pointer_and_reapplies_tier(
    tmp_path: Path,
) -> None:
    codex_home = write_usage_session(
        tmp_path, "conversation-a", (100, 40, 30, 10)
    )
    otel_dir = write_otel_directory(
        tmp_path, "conversation-a", (100, 40, 30, 10)
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)

    rebuild_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)

    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM otel_completion_events").fetchone()[0] == 1
        assert conn.execute("SELECT service_tier FROM usage_events").fetchone()[0] == "fast"
        state = conn.execute(
            "SELECT match_status, matched_record_id FROM otel_completion_events"
        ).fetchone()
    assert state["match_status"] == "matched"
    assert state["matched_record_id"] is not None


def test_refresh_persists_all_bounded_otel_metadata_counters(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(
        codex_home=tmp_path / "codex",
        db_path=db_path,
        otel_dir=tmp_path / "missing",
    )

    metadata = refresh_metadata(db_path)
    assert metadata["otel_files_scanned"] == "0"
    assert metadata["otel_invalid_json"] == "0"
