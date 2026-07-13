from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_usage_tracker.cli import mcp_compression
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.request import prepare_compression_request
from codex_usage_tracker.compression.simulation_api import compression_simulate
from codex_usage_tracker.compression.simulation_payloads import SIMULATION_BUDGET_BYTES
from codex_usage_tracker.store.compression_candidates import replace_compression_candidates
from codex_usage_tracker.store.compression_revisions import touch_compression_revisions
from codex_usage_tracker.store.compression_runs import (
    create_compression_run,
    update_compression_run,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db
from tests.store.test_compression_runs import candidate


def test_simulation_api_returns_compact_content_free_portfolio(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id, candidate_ids = _seed_run(db_path, candidate_count=3)

    payload = compression_simulate(db_path, run_id=run_id, candidate_ids=candidate_ids)

    assert payload["kind"] == "simulation"
    assert payload["run_id"] == run_id
    assert payload["simulation"]["selected_candidate_ids"] == sorted(candidate_ids)
    assert payload["simulation"]["candidate_count"] == 3
    assert payload["calculation_trace"]["total_groups"] == 3
    assert payload["includes_indexed_content"] is False
    assert payload["includes_raw_fragments"] is False
    assert "excerpt" not in json.dumps(payload)
    assert len(json.dumps(payload, separators=(",", ":")).encode()) <= SIMULATION_BUDGET_BYTES


def test_simulation_overrides_indexed_run_privacy_flags(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id, candidate_ids = _seed_run(db_path, candidate_count=1, content_indexed=True)

    payload = compression_simulate(db_path, run_id=run_id, candidate_ids=candidate_ids)

    assert payload["content_mode"] == "aggregate"
    assert payload["includes_indexed_content"] is False
    assert payload["includes_raw_fragments"] is False


def test_api_uses_full_record_capacity_for_disjoint_tool_outputs(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id, candidate_ids = _seed_tool_output_run(db_path)

    payload = compression_simulate(db_path, run_id=run_id, candidate_ids=candidate_ids)

    assert (
        payload["simulation"]["overlap_adjusted_estimate"]
        == payload["simulation"]["gross_estimate"]
    )
    assert payload["calculation_trace"]["rows"][0]["capacity_tokens"] == 200


def test_missing_record_capacity_returns_refresh_error(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id, candidate_ids = _seed_run(db_path, candidate_count=1)
    with connect(db_path) as conn:
        conn.execute("DELETE FROM compression_record_facts")

    payload = compression_simulate(db_path, run_id=run_id, candidate_ids=candidate_ids)

    assert payload["error"]["code"] == "compression_capacity_unavailable"
    assert payload["next"]["tool"] == "usage_compression_start"


def test_mcp_simulation_enforces_budget_and_preserves_totals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id, candidate_ids = _seed_run(db_path, candidate_count=50)
    monkeypatch.setattr(mcp_compression, "DEFAULT_DB_PATH", db_path)

    payload = mcp_compression.usage_compression_simulate(
        run_id=run_id,
        candidate_ids=list(reversed(candidate_ids)),
    )

    assert payload["simulation"]["candidate_count"] == 50
    assert payload["simulation"]["gross_estimate"]["high"] > 0
    assert payload["calculation_trace"]["truncated"] is True
    assert len(json.dumps(payload, separators=(",", ":")).encode()) <= SIMULATION_BUDGET_BYTES


@pytest.mark.parametrize(
    ("candidate_ids", "reason"),
    [
        ([], "empty"),
        (["cmp_000", "cmp_000"], "duplicate"),
        ([f"candidate-{index}" for index in range(51)], "over_limit"),
    ],
)
def test_invalid_candidate_selections_return_structured_errors(
    tmp_path: Path,
    candidate_ids: list[str],
    reason: str,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id, _available = _seed_run(db_path, candidate_count=2)

    payload = compression_simulate(db_path, run_id=run_id, candidate_ids=candidate_ids)

    assert payload["run_id"] == run_id
    assert payload["error"]["code"] == "invalid_candidate_selection"
    assert payload["error"]["reason"] == reason
    assert payload["next"] == {
        "tool": "usage_compression_candidates",
        "arguments": {"run_id": run_id},
    }


def test_unknown_and_foreign_candidates_are_not_silently_dropped(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id, candidate_ids = _seed_run(db_path, run_id="run-one", candidate_count=1)
    _foreign_run, foreign_ids = _seed_run(
        db_path,
        run_id="run-two",
        candidate_count=1,
        candidate_prefix="foreign",
    )

    payload = compression_simulate(
        db_path,
        run_id=run_id,
        candidate_ids=[candidate_ids[0], foreign_ids[0], "missing-candidate"],
    )

    assert payload["error"]["code"] == "invalid_candidate_selection"
    assert payload["error"]["unknown_candidate_ids"] == ["missing-candidate"]
    assert payload["error"]["foreign_candidate_ids"] == [foreign_ids[0]]


def test_incomplete_run_returns_status_poll_guidance(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    prepared = prepare_compression_request(db_path, CompressionScope())
    create_compression_run(
        db_path,
        run_id="run-pending",
        source_revision="",
        scope={"include_archived": False},
        **prepared.cache_lookup(),
    )

    payload = compression_simulate(
        db_path,
        run_id="run-pending",
        candidate_ids=["candidate-1"],
    )

    assert payload["error"]["code"] == "compression_run_not_complete"
    assert payload["next"]["tool"] == "usage_compression_status"


def test_stale_run_returns_equivalent_scope_refresh_guidance(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    scope = CompressionScope(
        since="2026-07-01T00:00:00+00:00",
        until="2026-07-02T00:00:00+00:00",
        thread="thread:selected",
        model="gpt-5.5",
    )
    run_id, candidate_ids = _seed_run(
        db_path,
        candidate_count=1,
        scope=scope,
        detector_families=("stale_context",),
    )
    with connect(db_path) as conn:
        init_db(conn)
        touch_compression_revisions(conn, ("calls",))

    payload = compression_simulate(db_path, run_id=run_id, candidate_ids=candidate_ids)

    assert payload["error"]["code"] == "compression_run_stale"
    assert payload["next"]["tool"] == "usage_compression_start"
    arguments = payload["next"]["arguments"]
    assert arguments["refresh"] is True
    assert arguments["since"] == scope.since
    assert arguments["until"] == scope.until
    assert arguments["thread"] == scope.thread
    assert arguments["model"] == scope.model
    assert arguments["detector_families"] == ["stale_context"]


def test_existing_mcp_lifecycle_can_route_into_simulation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    run_id, candidate_ids = _seed_run(db_path, candidate_count=1)
    monkeypatch.setattr(mcp_compression, "DEFAULT_DB_PATH", db_path)

    started = mcp_compression.usage_compression_start()
    status = mcp_compression.usage_compression_status(started["run_id"])
    profile = mcp_compression.usage_compression_profile(run_id=run_id)
    candidates = mcp_compression.usage_compression_candidates(run_id=run_id, limit=10)
    simulation = mcp_compression.usage_compression_simulate(
        run_id=run_id,
        candidate_ids=candidate_ids,
    )

    assert started["run_id"] == run_id
    assert status["status"] == "completed"
    assert profile["profile"]["candidate_count"] == 1
    assert candidates["pagination"]["total"] == 1
    assert simulation["schema"] == "codex-usage-tracker-compression-api-v1"
    assert simulation["includes_raw_fragments"] is False


def _seed_run(
    db_path: Path,
    *,
    run_id: str = "run-completed",
    candidate_count: int,
    candidate_prefix: str = "cmp",
    scope: CompressionScope | None = None,
    detector_families: tuple[str, ...] | None = None,
    content_indexed: bool = False,
) -> tuple[str, list[str]]:
    normalized_scope = scope or CompressionScope()
    prepared = prepare_compression_request(
        db_path,
        normalized_scope,
        detector_families=detector_families,
    )
    create_compression_run(
        db_path,
        run_id=run_id,
        source_revision="source-revision",
        source_generation=prepared.source_generation,
        scope=normalized_scope.as_dict(),
        **prepared.cache_lookup(),
    )
    candidate_ids = [f"{candidate_prefix}_{index:03d}" for index in range(candidate_count)]
    rows = [
        candidate(candidate_id, likely=max(10, 90 - index)).as_dict()
        for index, candidate_id in enumerate(candidate_ids)
    ]
    _seed_record_capacities(db_path, candidate_ids)
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
            "content_mode": "indexed" if content_indexed else "aggregate",
            "includes_indexed_content": content_indexed,
        },
    )
    return run_id, candidate_ids


def _seed_record_capacities(db_path: Path, candidate_ids: list[str]) -> None:
    with connect(db_path) as conn:
        init_db(conn)
        for candidate_id in candidate_ids:
            record_id = f"record-{candidate_id}"
            _seed_record_capacity(conn, record_id, uncached_input=100)


def _seed_tool_output_run(db_path: Path) -> tuple[str, list[str]]:
    run_id = "run-tool-output"
    prepared = prepare_compression_request(db_path, CompressionScope())
    create_compression_run(
        db_path,
        run_id=run_id,
        source_revision="source-revision",
        source_generation=prepared.source_generation,
        scope=CompressionScope().as_dict(),
        **prepared.cache_lookup(),
    )
    candidate_ids = ["tool-a", "tool-b"]
    rows = [_tool_output_candidate(candidate_id) for candidate_id in candidate_ids]
    with connect(db_path) as conn:
        init_db(conn)
        _seed_record_capacity(conn, "record-shared", tool_output=200)
    replace_compression_candidates(db_path, run_id=run_id, candidates=rows)
    update_compression_run(
        db_path,
        run_id=run_id,
        status="completed",
        progress_percent=100,
        stage="complete",
        public_profile={
            "run_id": run_id,
            "status": "completed",
            "candidate_count": 2,
            "coverage": {"call_count": 1},
        },
    )
    return run_id, candidate_ids


def _tool_output_candidate(candidate_id: str) -> dict:
    row = candidate(candidate_id, likely=60).as_dict()
    row["record_ids"] = ["record-shared"]
    row["observed_exposure"] = {"tool_output": 100}
    row["claims"][0].update(
        record_id="record-shared",
        component="tool_output",
        exposure_tokens=100,
    )
    row["evidence_handles"] = [{"record_id": "record-shared"}]
    return row


def _seed_record_capacity(
    conn,
    record_id: str,
    *,
    uncached_input: int = 0,
    tool_output: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO usage_events (
            record_id, session_id, event_timestamp, source_file, line_number,
            input_tokens, cached_input_tokens, output_tokens,
            reasoning_output_tokens, total_tokens, cumulative_input_tokens,
            cumulative_cached_input_tokens, cumulative_output_tokens,
            cumulative_reasoning_output_tokens, cumulative_total_tokens,
            uncached_input_tokens, cache_ratio, reasoning_output_ratio,
            context_window_percent
        ) VALUES (?, ?, ?, ?, 1, ?, 0, 0, 0, ?, ?, 0, 0, 0, ?, ?, 0, 0, 0)
        """,
        (
            record_id,
            f"session-{record_id}",
            "2026-07-01T00:00:00+00:00",
            f"/synthetic/{record_id}.jsonl",
            uncached_input,
            uncached_input,
            uncached_input,
            uncached_input,
            uncached_input,
        ),
    )
    conn.execute(
        """
        INSERT INTO compression_record_facts (
            record_id, source_file, session_id, thread_key, event_timestamp,
            uncached_input_tokens, tool_output_exposure_tokens, facts_version,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            record_id,
            f"/synthetic/{record_id}.jsonl",
            f"session-{record_id}",
            "thread-1",
            "2026-07-01T00:00:00+00:00",
            uncached_input,
            tool_output,
            "2026-07-01T00:00:00+00:00",
        ),
    )
