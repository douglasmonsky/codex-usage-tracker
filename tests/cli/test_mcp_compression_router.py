from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def test_usage_investigate_token_waste_routes_through_compression_lab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_usage_tracker.cli import mcp_compression_router

    calls: list[tuple[str, Any]] = []

    def start(db_path: Path, scope: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(("start", {"scope": scope, **kwargs}))
        return _compression_status("completed")

    def profile(db_path: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(("profile", kwargs))
        return _compression_profile()

    def candidates(db_path: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(("candidates", kwargs))
        return _compression_candidates()

    def detail(db_path: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(("detail", kwargs))
        return _compression_detail(str(kwargs["candidate_id"]))

    def simulate(db_path: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(("simulate", kwargs))
        return _compression_simulation()

    monkeypatch.setattr(mcp_compression_router, "start_compression_analysis", start)
    monkeypatch.setattr(mcp_compression_router, "compression_profile", profile)
    monkeypatch.setattr(mcp_compression_router, "compression_candidates", candidates)
    monkeypatch.setattr(mcp_compression_router, "compression_candidate_detail", detail)
    monkeypatch.setattr(mcp_compression_router, "compression_simulate", simulate)

    payload = mcp_compression_router.build_compression_investigation_router(
        db_path=Path("usage.sqlite3"),
        goal="token_waste",
        since=None,
        until=None,
        thread=None,
        include_archived=False,
        evidence_limit=3,
        privacy_mode="strict",
    )

    assert payload["schema"] == "codex-usage-tracker-agentic-investigation-v1"
    assert payload["content_mode"] == "compression_lab_router"
    assert payload["privacy_mode"] == "strict"
    assert payload["compression_lab"]["run_id"] == "run-1"
    assert payload["compression_lab"]["profile"]["profile"]["candidate_count"] == 3
    assert [row["candidate_id"] for row in payload["compression_lab"]["selected_details"]] == [
        "cmp_001"
    ]
    assert payload["compression_lab"]["simulation"]["simulation"]["selected_candidate_count"] == 1
    assert payload["findings"][0]["evidence_summary"]["row_count"] == 3
    assert payload["findings"][0]["evidence"][0]["candidate_id"] == "cmp_001"
    assert [call[0] for call in calls] == [
        "start",
        "profile",
        "candidates",
        "detail",
        "simulate",
    ]


def test_usage_investigate_running_compression_run_returns_polling_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_usage_tracker.cli import mcp_compression_router

    calls: list[str] = []

    def start(db_path: Path, scope: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append("start")
        return _compression_status("running")

    monkeypatch.setattr(mcp_compression_router, "start_compression_analysis", start)
    monkeypatch.setattr(
        mcp_compression_router,
        "compression_profile",
        lambda *args, **kwargs: pytest.fail("running router must not read profile"),
    )

    payload = mcp_compression_router.build_compression_investigation_router(
        db_path=Path("usage.sqlite3"),
        goal="token_waste",
        since="2026-07-01",
        until=None,
        thread="thread:one",
        include_archived=True,
        evidence_limit=5,
        privacy_mode="normal",
    )

    assert calls == ["start"]
    assert payload["summary"]["confidence"] == "compression_analysis_running"
    assert payload["compression_lab"]["next"]["tool"] == "usage_compression_status"
    assert payload["compression_lab"]["next"]["arguments"] == {"run_id": "run-1"}
    assert payload["findings"][0]["verify_with"] == [
        "usage_compression_status",
        "usage_compression_profile",
    ]


def test_usage_action_brief_returns_compact_compression_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_usage_tracker.cli import mcp_compression_router

    monkeypatch.setattr(
        mcp_compression_router,
        "start_compression_analysis",
        lambda *args, **kwargs: _compression_status("completed"),
    )
    monkeypatch.setattr(
        mcp_compression_router,
        "compression_profile",
        lambda *args, **kwargs: _compression_profile(),
    )
    monkeypatch.setattr(
        mcp_compression_router,
        "compression_candidates",
        lambda *args, **kwargs: _compression_candidates(),
    )
    monkeypatch.setattr(
        mcp_compression_router,
        "compression_candidate_detail",
        lambda *args, **kwargs: _compression_detail(str(kwargs["candidate_id"])),
    )
    monkeypatch.setattr(
        mcp_compression_router,
        "compression_simulate",
        lambda *args, **kwargs: _compression_simulation(),
    )

    payload = mcp_compression_router.build_compression_action_router(
        db_path=Path("usage.sqlite3"),
        goal="token_waste",
        since=None,
        until=None,
        thread=None,
        include_archived=False,
        evidence_limit=2,
        privacy_mode="strict",
    )

    assert payload["schema"] == "codex-usage-tracker-action-brief-v1"
    assert payload["content_mode"] == "compression_lab_router"
    assert payload["summary"]["source_reports"] == ["codex-usage-tracker-compression-api-v1"]
    assert payload["actions"][0]["family"] == "stale_context"
    assert payload["actions"][0]["recommended_next_tools"] == [
        "usage_compression_candidate_detail",
        "usage_compression_simulate",
    ]
    assert payload["recommended_next_tools"] == [
        "usage_compression_candidates",
        "usage_compression_candidate_detail",
        "usage_compression_simulate",
    ]


def _compression_status(status: str) -> dict[str, Any]:
    return {
        "schema": "codex-usage-tracker-compression-api-v1",
        "kind": "status",
        "status": status,
        "run_id": "run-1",
        "scope": {"include_archived": False},
        "filters": {},
        "include_archived": False,
        "content_mode": "aggregate",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "progress": {"percent": 100 if status == "completed" else 40},
        "next": {
            "tool": "usage_compression_profile"
            if status == "completed"
            else "usage_compression_status",
            "arguments": {"run_id": "run-1"},
        },
        "warnings": [],
        "caveats": ["heuristic"],
    }


def _compression_profile() -> dict[str, Any]:
    payload = _compression_status("completed")
    payload.update(
        {
            "kind": "profile",
            "profile": {
                "run_id": "run-1",
                "candidate_count": 3,
                "coverage": {"call_count": 40},
                "summary": "Compression candidates found.",
                "cache": {"reused": True, "mode": "completed"},
            },
            "next": {
                "tool": "usage_compression_candidates",
                "arguments": {"run_id": "run-1"},
            },
        }
    )
    return payload


def _compression_candidates() -> dict[str, Any]:
    payload = _compression_status("completed")
    payload.update(
        {
            "kind": "candidate_page",
            "candidates": [
                _candidate("cmp_001", "stale_context", 9000),
                _candidate("cmp_002", "shell_churn", 4000),
                _candidate("cmp_003", "repeated_file_rediscovery", 2000),
            ],
            "pagination": {
                "total": 3,
                "offset": 0,
                "requested_limit": 3,
                "returned": 3,
                "truncated": False,
                "next_offset": None,
            },
            "next": {
                "tool": "usage_compression_candidate_detail",
                "arguments": {"candidate_id": "cmp_001"},
            },
        }
    )
    return payload


def _compression_detail(candidate_id: str) -> dict[str, Any]:
    payload = _compression_status("completed")
    payload.update(
        {
            "kind": "candidate_detail",
            "candidate": _candidate(candidate_id, "stale_context", 9000),
            "evidence_mode": "handles",
            "claims": [{"record_id": "record-1", "total_tokens": 1234}],
            "evidence": [{"trace_handle": "handle-1", "record_id": "record-1"}],
            "evidence_pagination": {"requested": 1, "returned": 1, "truncated": False},
        }
    )
    return payload


def _compression_simulation() -> dict[str, Any]:
    payload = _compression_status("completed")
    payload.update(
        {
            "kind": "simulation",
            "simulation": {
                "selected_candidate_count": 1,
                "total_adjusted_estimate": {"low": 3000, "likely": 9000, "high": 12000},
                "candidates": [{"candidate_id": "cmp_001", "adjusted_likely": 9000}],
            },
            "verification_plan": {"rows": []},
        }
    )
    return payload


def _candidate(candidate_id: str, family: str, likely: int) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "family": family,
        "pattern": family.replace("_", " "),
        "confidence": "high",
        "observed_exposure_tokens": likely * 2,
        "adjusted_estimate": {"low": likely // 2, "likely": likely, "high": likely * 2},
        "estimator": {"assumptions": ["heuristic local aggregate estimate"]},
    }
