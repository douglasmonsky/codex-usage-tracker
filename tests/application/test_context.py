from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.application.context import build_request_context
from codex_usage_tracker.application.errors import RequestContextError
from codex_usage_tracker.application.requests import RequestScope
from codex_usage_tracker.store.api import connect, upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def _write_pricing(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5.5": {
                        "input_per_million": 2.0,
                        "cached_input_per_million": 0.5,
                        "output_per_million": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_context_uses_physical_counts_only_for_copy_accounting(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    original = replace(
        _usage_event(
            record_id="original",
            session_id="session-original",
            thread_key="thread:Alpha",
            event_timestamp="2026-07-21T12:00:00Z",
            cumulative_total_tokens=110,
        ),
        service_tier="priority",
    )
    copied = replace(
        original,
        record_id="copied",
        session_id="session-copied",
        source_file="/tmp/synthetic/copied.jsonl",
        event_timestamp="2026-07-21T12:01:00Z",
        turn_timestamp="2026-07-21T12:01:00Z",
    )
    upsert_usage_events([original, copied], db_path=db_path)
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE usage_events SET is_duplicate = 1, canonical_record_id = ? WHERE record_id = ?",
            ("original", "copied"),
        )

    context = build_request_context(
        db_path=db_path,
        pricing_path=_write_pricing(tmp_path / "pricing.json"),
        scope=RequestScope(history="all"),
    )

    assert context.physical_rows == 2
    assert context.canonical_rows == 1
    assert context.copied_rows_excluded == 1
    assert context.pricing_coverage == 1.0
    assert context.credit_coverage == 1.0
    assert context.service_tier_coverage == 1.0
    assert context.source_revision.startswith("generation:")


def test_missing_database_returns_unknown_context_without_creating_files(tmp_path: Path) -> None:
    db_path = tmp_path / "missing" / "usage.sqlite3"
    pricing_path = tmp_path / "missing-pricing.json"

    context = build_request_context(
        db_path=db_path,
        pricing_path=pricing_path,
        scope=RequestScope(),
    )

    assert context.source_revision is None
    assert context.freshness.state == "empty"
    assert context.physical_rows == 0
    assert context.canonical_rows == 0
    assert context.copied_rows_excluded == 0
    assert context.pricing_coverage is None
    assert context.credit_coverage is None
    assert context.service_tier_coverage is None
    assert not db_path.exists()
    assert not db_path.parent.exists()
    assert not pricing_path.exists()


def test_existing_non_file_database_target_fails_without_side_effects(tmp_path: Path) -> None:
    db_path = tmp_path / "database-target"
    db_path.mkdir()
    pricing_path = tmp_path / "pricing-parent" / "pricing.json"

    with pytest.raises(RequestContextError, match="database path must be a regular file"):
        build_request_context(
            db_path=db_path,
            pricing_path=pricing_path,
            scope=RequestScope(),
        )

    assert db_path.is_dir()
    assert list(db_path.iterdir()) == []
    assert not pricing_path.parent.exists()


def test_plain_text_database_file_fails_without_pricing_side_effects(tmp_path: Path) -> None:
    db_path = tmp_path / "not-a-database.sqlite3"
    db_path.write_text("plain text", encoding="utf-8")
    pricing_path = tmp_path / "pricing-parent" / "pricing.json"

    with pytest.raises(RequestContextError, match="could not be read") as exc_info:
        build_request_context(
            db_path=db_path,
            pricing_path=pricing_path,
            scope=RequestScope(),
        )

    assert exc_info.value.__cause__ is not None
    assert db_path.read_text(encoding="utf-8") == "plain text"
    assert not pricing_path.parent.exists()


def test_broken_database_symlink_is_existing_invalid_state(tmp_path: Path) -> None:
    missing_target = tmp_path / "missing.sqlite3"
    db_path = tmp_path / "database-link.sqlite3"
    try:
        db_path.symlink_to(missing_target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"platform cannot create symlinks: {exc}")
    pricing_path = tmp_path / "pricing-parent" / "pricing.json"

    with pytest.raises(RequestContextError, match="database path must be a regular file"):
        build_request_context(
            db_path=db_path,
            pricing_path=pricing_path,
            scope=RequestScope(),
        )

    assert db_path.is_symlink()
    assert not missing_target.exists()
    assert not pricing_path.parent.exists()
