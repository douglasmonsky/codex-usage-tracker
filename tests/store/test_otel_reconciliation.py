from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.store.api import EVENT_COLUMNS, query_usage_record, upsert_usage_events
from codex_usage_tracker.store.otel_reconciliation import (
    reconcile_otel_completions,
    reset_otel_completion_matches,
)
from tests.otel_helpers import initialized_connection, synthetic_usage_event


def insert_usage_clone_group(
    conn: sqlite3.Connection,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
    *,
    canonical: str = "canonical-a",
    model: str | None = "gpt-5.6-sol",
    effort: str | None = "high",
    service_tier: str | None = None,
    fast: int | None = None,
) -> None:
    events = [
        synthetic_usage_event(
            f"{canonical}-record-{index}",
            conversation_id,
            tokens,
            canonical=canonical,
            model=model or "",
            effort=effort or "",
            service_tier=service_tier,
            fast=fast,
            duplicate=int(index == 1),
        )
        for index in range(2)
    ]
    rows = [event.to_row() for event in events]
    if model is None:
        for row in rows:
            row["model"] = None
    if effort is None:
        for row in rows:
            row["effort"] = None
    placeholders = ", ".join("?" for _column in EVENT_COLUMNS)
    conn.executemany(
        f"INSERT INTO usage_events ({', '.join(EVENT_COLUMNS)}) VALUES ({placeholders})",  # nosec B608
        [[row[column] for column in EVENT_COLUMNS] for row in rows],
    )


def stage_completion(
    conn: sqlite3.Connection,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
    *,
    fast: int,
    model: str | None = "gpt-5.6-sol",
    effort: str | None = "high",
    event_timestamp: str = "2026-07-16T00:00:00Z",
) -> str:
    input_tokens, cached_tokens, output_tokens, reasoning_tokens = tokens
    fingerprint = hashlib.sha256(
        repr((conversation_id, tokens, fast, model, effort, event_timestamp)).encode()
    ).hexdigest()
    conn.execute(
        """
        INSERT INTO otel_completion_events (
            fingerprint, conversation_id, event_timestamp,
            input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens,
            model, effort, service_tier, fast, service_tier_source,
            service_tier_confidence, app_version, source_path, source_line,
            match_status, matched_record_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'otel_response_completed',
                  'exact', '0.143.0', '/synthetic/codex-completions.jsonl', 1, 'pending', NULL)
        """,
        (
            fingerprint,
            conversation_id,
            event_timestamp,
            input_tokens,
            cached_tokens,
            output_tokens,
            reasoning_tokens,
            model,
            effort,
            "fast" if fast == 1 else "standard",
            fast,
        ),
    )
    return fingerprint


def test_unique_token_identity_enriches_every_clone_in_one_canonical_group(
    tmp_path: Path,
) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(
            conn, conversation_id="conversation-a", tokens=(100, 40, 30, 10)
        )
        stage_completion(
            conn, conversation_id="conversation-a", tokens=(100, 40, 30, 10), fast=1
        )
        result = reconcile_otel_completions(conn)
        rows = conn.execute(
            "SELECT service_tier, fast FROM usage_events ORDER BY record_id"
        ).fetchall()

    assert result.matched == 1
    assert [(row["service_tier"], row["fast"]) for row in rows] == [
        ("fast", 1),
        ("fast", 1),
    ]
    assert result.updated_usage_rows == 2


def test_same_tokens_in_two_canonical_groups_remain_ambiguous(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(
            conn, "conversation-a", (100, 40, 30, 10), canonical="canonical-a"
        )
        insert_usage_clone_group(
            conn, "conversation-a", (100, 40, 30, 10), canonical="canonical-b"
        )
        fingerprint = stage_completion(
            conn, "conversation-a", (100, 40, 30, 10), fast=1
        )
        reconcile_otel_completions(conn)
        status = conn.execute(
            "SELECT match_status FROM otel_completion_events WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()[0]
        tiers = conn.execute("SELECT service_tier FROM usage_events").fetchall()

    assert status == "ambiguous"
    assert all(row[0] is None for row in tiers)


def test_timestamp_distance_does_not_affect_matching(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(conn, "conversation-a", (100, 40, 30, 10))
        stage_completion(
            conn,
            "conversation-a",
            (100, 40, 30, 10),
            fast=1,
            event_timestamp="2099-01-01T00:00:00Z",
        )

        assert reconcile_otel_completions(conn).matched == 1


def test_model_or_effort_mismatch_prevents_match_when_both_are_present(
    tmp_path: Path,
) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(
            conn,
            "conversation-a",
            (100, 40, 30, 10),
            model="gpt-5.5",
            effort="medium",
        )
        stage_completion(
            conn,
            "conversation-a",
            (100, 40, 30, 10),
            fast=1,
            model="gpt-5.6",
            effort="high",
        )

        assert reconcile_otel_completions(conn).pending == 1


def test_missing_model_or_effort_does_not_block_exact_token_match(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(
            conn,
            "conversation-a",
            (100, 40, 30, 10),
            model=None,
            effort=None,
        )
        stage_completion(
            conn, "conversation-a", (100, 40, 30, 10), fast=1
        )

        assert reconcile_otel_completions(conn).matched == 1


def test_contradictory_existing_tier_is_preserved_and_marks_conflict(
    tmp_path: Path,
) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(
            conn,
            "conversation-a",
            (100, 40, 30, 10),
            service_tier="standard",
            fast=0,
        )
        fingerprint = stage_completion(
            conn, "conversation-a", (100, 40, 30, 10), fast=1
        )
        assert reconcile_otel_completions(conn).conflicts == 1
        row = conn.execute(
            "SELECT service_tier, fast FROM usage_events LIMIT 1"
        ).fetchone()
        status = conn.execute(
            "SELECT match_status FROM otel_completion_events WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()[0]

    assert tuple(row) == ("standard", 0)
    assert status == "conflict"


def test_usage_upsert_and_source_replacement_preserve_non_null_tier(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    original = synthetic_usage_event(
        "record-a", "conversation-a", (100, 40, 30, 10), fast=1
    )
    upsert_usage_events([original], db_path=db_path)
    reparsed = replace(
        original,
        thread_name="reparsed",
        service_tier=None,
        fast=None,
        service_tier_source=None,
        service_tier_confidence=None,
    )

    upsert_usage_events(
        [reparsed],
        db_path=db_path,
        replace_source_files=[Path(original.source_file)],
    )

    row = query_usage_record(db_path=db_path, record_id="record-a")
    assert row is not None
    assert (row["service_tier"], row["fast"]) == ("fast", 1)
    assert row["service_tier_source"] == "otel_response_completed"
    assert row["service_tier_confidence"] == "exact"


def test_matched_rows_are_idempotent_and_can_be_reset_for_rebuild(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(conn, "conversation-a", (100, 40, 30, 10))
        fingerprint = stage_completion(
            conn, "conversation-a", (100, 40, 30, 10), fast=1
        )
        first = reconcile_otel_completions(conn)
        second = reconcile_otel_completions(conn)
        reset_otel_completion_matches(conn)
        state = conn.execute(
            "SELECT match_status, matched_record_id FROM otel_completion_events WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()

    assert first.matched == 1
    assert second.matched == 1
    assert tuple(state) == ("pending", None)
