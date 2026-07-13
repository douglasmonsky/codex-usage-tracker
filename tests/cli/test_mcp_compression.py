from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from codex_usage_tracker.cli import mcp_compression
from codex_usage_tracker.compression.api import (
    compression_candidate_detail,
    compression_candidates,
    compression_profile,
)
from codex_usage_tracker.compression.payloads import (
    CANDIDATE_DETAIL_BUDGET_BYTES,
    CANDIDATE_PAGE_BUDGET_BYTES,
    PROFILE_BUDGET_BYTES,
    STATUS_BUDGET_BYTES,
    compression_candidate_detail_payload,
    compression_candidate_page_payload,
    compression_status_payload,
)
from codex_usage_tracker.store.compression_candidates import replace_compression_candidates
from codex_usage_tracker.store.compression_runs import (
    create_compression_run,
    update_compression_run,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db
from tests.store.test_compression_runs import candidate


def test_status_payload_is_compact_and_omits_private_profiles() -> None:
    payload = compression_status_payload(
        {
            "run_id": "run-1",
            "status": "running",
            "stage": "detectors",
            "progress_percent": 45,
            "current_detector": "stale_context",
            "completed_detectors": 2,
            "total_detectors": 6,
            "records_examined": 1000,
            "candidate_count": 12,
            "source_revision": "revision-1",
            "scope": {"include_archived": False, "thread": "x" * 20_000},
            "filters": {"question": "x" * 20_000},
            "coverage": {"call_count": 1000},
            "timing": {},
            "error_summary": {},
            "aggregate_profile": {"private": "x" * 20_000},
            "public_profile": {"also_too_large": "x" * 20_000},
            "detector_set_version": "detectors-v1",
            "estimator_version": "estimator-v1",
            "compression_schema_version": 1,
            "cache_reused": False,
            "request_reused": "none",
            "next_poll_ms": 250,
        }
    )

    encoded = json.dumps(payload, separators=(",", ":")).encode()
    assert len(encoded) <= STATUS_BUDGET_BYTES
    assert "aggregate_profile" not in payload
    assert "public_profile" not in payload
    assert payload["next"]["tool"] == "usage_compression_status"
    assert payload["progress"]["percent"] == 45
    assert payload["includes_raw_fragments"] is False
    assert payload["payload_truncated"] is True


def test_detail_payload_falls_back_to_core_candidate_when_metadata_exceeds_budget() -> None:
    run = {
        "run_id": "run-1",
        "status": "completed",
        "scope": {},
        "filters": {},
        "coverage": {},
    }
    payload = compression_candidate_detail_payload(
        run,
        {
            "candidate_id": "candidate-1",
            "run_id": "run-1",
            "family": "stale_context",
            "pattern": "x" * 40_000,
            "adjusted_estimate": {"low": 1, "likely": 2, "high": 3},
            "estimator": {"assumptions": ["x" * 40_000]},
        },
        evidence_mode="handles",
        claims=[],
        evidence=[],
    )

    assert len(json.dumps(payload, separators=(",", ":")).encode()) <= CANDIDATE_DETAIL_BUDGET_BYTES
    assert payload["candidate"]["candidate_id"] == "candidate-1"
    assert payload["payload_truncated"] is True


def test_candidate_filters_are_sql_backed_and_local_limit_zero_is_unbounded(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id = _seed_completed_run(
        db_path,
        candidate_count=40,
        record_metadata={
            "record-cmp_005": (
                "gpt-filtered",
                "thread:filtered",
                "2026-07-12T12:00:00+00:00",
            )
        },
    )

    unbounded = compression_candidates(db_path, run_id=run_id, limit=0)
    filtered = compression_candidates(
        db_path,
        run_id=run_id,
        model="gpt-filtered",
        thread="thread:filtered",
        since="2026-07-12T00:00:00+00:00",
        until="2026-07-12T23:59:59+00:00",
        limit=None,
    )

    assert len(unbounded["candidates"]) == 40
    assert unbounded["pagination"]["requested_limit"] is None
    assert filtered["pagination"]["total"] == 1
    assert [row["candidate_id"] for row in filtered["candidates"]] == ["cmp_005"]
    with connect(db_path) as conn:
        conn.execute("DELETE FROM usage_events WHERE record_id = ?", ("record-cmp_005",))
    stable = compression_candidates(
        db_path,
        run_id=run_id,
        model="gpt-filtered",
        thread="thread:filtered",
        since="2026-07-12T00:00:00+00:00",
        until="2026-07-12T23:59:59+00:00",
        limit=None,
    )
    assert [row["candidate_id"] for row in stable["candidates"]] == ["cmp_005"]


def test_mcp_candidate_page_enforces_budget_and_returns_next_offset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id = _seed_completed_run(db_path, candidate_count=200)
    monkeypatch.setattr(mcp_compression, "DEFAULT_DB_PATH", db_path)

    payload = mcp_compression.usage_compression_candidates(run_id=run_id, limit=0)

    assert len(json.dumps(payload, separators=(",", ":")).encode()) <= CANDIDATE_PAGE_BUDGET_BYTES
    assert payload["pagination"]["total"] == 200
    assert payload["pagination"]["truncated"] is True
    assert payload["pagination"]["next_offset"] == len(payload["candidates"])
    assert all("claims" not in row for row in payload["candidates"])


def test_candidate_page_compacts_oversized_first_row_and_advances_cursor() -> None:
    payload = compression_candidate_page_payload(
        {"run_id": "run-1", "status": "completed", "scope": {}, "filters": {}},
        {
            "rows": [
                {
                    "candidate_id": "candidate-1",
                    "run_id": "run-1",
                    "family": "stale_context",
                    "pattern": "x" * (CANDIDATE_PAGE_BUDGET_BYTES * 2),
                    "adjusted_estimate": {"low": 1, "likely": 2, "high": 3},
                }
            ],
            "total": 2,
            "offset": 0,
            "limit": 1,
            "truncated": True,
        },
        max_bytes=CANDIDATE_PAGE_BUDGET_BYTES,
    )

    assert payload["candidates"] == [
        {
            "candidate_id": "candidate-1",
            "run_id": "run-1",
            "family": "stale_context",
            "adjusted_estimate": {"low": 1, "likely": 2, "high": 3},
        }
    ]
    assert payload["pagination"]["returned"] == 1
    assert payload["pagination"]["next_offset"] == 1
    assert len(json.dumps(payload, separators=(",", ":")).encode()) <= CANDIDATE_PAGE_BUDGET_BYTES


def test_candidate_detail_modes_are_explicit_and_excerpt_is_bounded(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed_completed_run(db_path, candidate_count=1)
    _seed_usage_row(
        db_path,
        record_id="record-cmp_000",
        model="gpt-5.5",
        thread="thread:one",
        timestamp="2026-07-12T12:00:00+00:00",
    )
    _seed_fragment(db_path, record_id="record-cmp_000", text="private local excerpt " * 100)

    handles = compression_candidate_detail(db_path, candidate_id="cmp_000")
    summaries = compression_candidate_detail(
        db_path,
        candidate_id="cmp_000",
        evidence_mode="summaries",
    )
    excerpts = compression_candidate_detail(
        db_path,
        candidate_id="cmp_000",
        evidence_mode="excerpts",
        evidence_limit=1,
        max_excerpt_chars=80,
    )

    assert handles["evidence_mode"] == "handles"
    assert handles["includes_raw_fragments"] is False
    assert "excerpt" not in json.dumps(handles)
    assert summaries["evidence_mode"] == "summaries"
    assert summaries["includes_raw_fragments"] is False
    assert excerpts["evidence_mode"] == "excerpts"
    assert excerpts["includes_indexed_content"] is True
    assert excerpts["includes_raw_fragments"] is True
    assert len(excerpts["evidence"][0]["excerpt"]) <= 80
    assert (
        len(json.dumps(excerpts, separators=(",", ":")).encode()) <= CANDIDATE_DETAIL_BUDGET_BYTES
    )


def test_profile_never_launches_and_returns_actionable_missing_result(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    missing = compression_profile(db_path, run_id="missing")
    run_id = _seed_completed_run(db_path, candidate_count=1)
    completed = compression_profile(db_path, run_id=run_id)

    assert missing["error"]["code"] == "compression_run_not_found"
    assert missing["next"]["tool"] == "usage_compression_start"
    assert completed["run_id"] == run_id
    assert completed["profile"]["candidate_count"] == 1
    assert len(json.dumps(completed, separators=(",", ":")).encode()) <= PROFILE_BUDGET_BYTES


def test_incomplete_run_errors_preserve_common_envelope_and_run_identity(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id = "run-pending"
    create_compression_run(
        db_path,
        run_id=run_id,
        source_revision="source-revision",
        scope_hash="scope-hash",
        detector_set_version="detectors-v1",
        estimator_version="estimator-v1",
        compression_schema_version=1,
        scope={"include_archived": False},
    )

    required_keys = {
        "schema",
        "kind",
        "versions",
        "run_id",
        "status",
        "source_revision",
        "scope",
        "filters",
        "include_archived",
        "coverage",
        "timing",
        "cache",
        "content_mode",
        "includes_indexed_content",
        "includes_raw_fragments",
        "warnings",
        "caveats",
        "payload_truncated",
        "error",
        "next",
    }
    for payload in (
        compression_profile(db_path, run_id=run_id),
        compression_candidates(db_path, run_id=run_id),
    ):
        assert required_keys <= payload.keys()
        assert payload["run_id"] == run_id
        assert payload["status"] == "error"


def test_warm_profile_and_candidate_page_complete_below_half_second(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id = _seed_completed_run(db_path, candidate_count=40)

    began = time.perf_counter()
    compression_profile(db_path, run_id=run_id)
    profile_duration = time.perf_counter() - began
    began = time.perf_counter()
    compression_candidates(db_path, run_id=run_id, limit=20)
    candidate_duration = time.perf_counter() - began

    assert profile_duration < 0.5
    assert candidate_duration < 0.5


def _seed_completed_run(
    db_path: Path,
    *,
    candidate_count: int,
    record_metadata: dict[str, tuple[str, str, str]] | None = None,
) -> str:
    run_id = "run-completed"
    create_compression_run(
        db_path,
        run_id=run_id,
        source_revision="source-revision",
        scope_hash="scope-hash",
        detector_set_version="detectors-v1",
        estimator_version="estimator-v1",
        compression_schema_version=1,
        scope={"include_archived": False},
    )
    rows = [
        candidate(f"cmp_{index:03d}", likely=max(10, 90 - index)).as_dict()
        for index in range(candidate_count)
    ]
    for record_id, (model, thread, timestamp) in (record_metadata or {}).items():
        _seed_usage_row(
            db_path,
            record_id=record_id,
            model=model,
            thread=thread,
            timestamp=timestamp,
        )
    replace_compression_candidates(db_path, run_id=run_id, candidates=rows)
    update_compression_run(
        db_path,
        run_id=run_id,
        status="completed",
        progress_percent=100,
        stage="complete",
        public_profile={
            "schema": "codex-usage-compression-profile-v1",
            "run_id": run_id,
            "status": "completed",
            "candidate_count": candidate_count,
            "coverage": {"call_count": candidate_count},
            "cache": {"mode": "cold", "reused": False},
            "warnings": [],
            "caveats": [],
        },
    )
    return run_id


def _seed_usage_row(
    db_path: Path,
    *,
    record_id: str,
    model: str,
    thread: str,
    timestamp: str,
) -> None:
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO usage_events (
                record_id, session_id, thread_name, event_timestamp, source_file,
                line_number, model, effort, thread_key,
                input_tokens, cached_input_tokens, output_tokens,
                reasoning_output_tokens, total_tokens,
                cumulative_input_tokens, cumulative_cached_input_tokens,
                cumulative_output_tokens, cumulative_reasoning_output_tokens,
                cumulative_total_tokens, uncached_input_tokens, cache_ratio,
                reasoning_output_ratio, context_window_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            """,
            (
                record_id,
                f"session-{record_id}",
                thread,
                timestamp,
                f"/synthetic/{record_id}.jsonl",
                1,
                model,
                "high",
                thread,
            ),
        )


def _seed_fragment(db_path: Path, *, record_id: str, text: str) -> None:
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO content_fragments (
                fragment_id, record_id, turn_key, fragment_kind, role, safe_label,
                content_hash, content_size_bytes, fragment_text, includes_raw_fragment,
                line_start, line_end, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "fragment-1",
                record_id,
                None,
                "message",
                "user",
                "user message",
                "hash-1",
                len(text.encode()),
                text,
                1,
                10,
                10,
                "2026-07-12T12:00:00+00:00",
            ),
        )
