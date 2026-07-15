from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.cli.parser import build_parser
from codex_usage_tracker.store.api import upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def test_allowance_intelligence_cli_commands_parse() -> None:
    parser = build_parser()

    diagnostics = parser.parse_args(
        ["allowance-diagnostics", "--window-kind", "weekly", "--limit", "0", "--json"]
    )
    export = parser.parse_args(["allowance-export", "--output", "/tmp/allowance-evidence.json"])

    assert diagnostics.command == "allowance-diagnostics"
    assert diagnostics.window_kind == "weekly"
    assert diagnostics.limit == 0
    assert diagnostics.as_json is True
    assert export.command == "allowance-export"
    assert export.output == Path("/tmp/allowance-evidence.json")


def test_usage_allowance_mcp_tools_return_contracts(tmp_path: Path, monkeypatch) -> None:
    from codex_usage_tracker.cli import mcp_allowance, mcp_server

    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id="rec-1",
                session_id="session-1",
                thread_key="thread:allowance",
                event_timestamp="2026-06-01T00:00:00Z",
                cumulative_total_tokens=100,
                rate_limit_plan_type="pro",
                rate_limit_limit_id="codex",
                rate_limit_primary_used_percent=10.0,
                rate_limit_primary_window_minutes=10080,
                rate_limit_primary_resets_at=1000,
            ),
            _usage_event(
                record_id="rec-2",
                session_id="session-1",
                thread_key="thread:allowance",
                event_timestamp="2026-06-01T00:01:00Z",
                cumulative_total_tokens=200,
                rate_limit_plan_type="pro",
                rate_limit_limit_id="codex",
                rate_limit_primary_used_percent=11.0,
                rate_limit_primary_window_minutes=10080,
                rate_limit_primary_resets_at=1000,
            ),
        ],
        db_path=db_path,
    )
    monkeypatch.setattr(mcp_allowance, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_allowance, "DEFAULT_ALLOWANCE_PATH", tmp_path / "allowance.json")
    monkeypatch.setattr(mcp_allowance, "DEFAULT_RATE_CARD_PATH", tmp_path / "rate-card.json")

    history = mcp_server.usage_allowance_history(window_kind="weekly")
    diagnostics = mcp_server.usage_allowance_diagnostics(window_kind="weekly")
    export = mcp_server.usage_allowance_export(window_kind="weekly")

    assert history["schema"] == "codex-usage-tracker-allowance-history-v1"
    assert diagnostics["schema"] == "codex-usage-tracker-allowance-diagnostics-v1"
    assert export["schema"] == "codex-usage-tracker-allowance-evidence-export-v1"
    assert export["privacy_mode"] == "strict"


def test_usage_allowance_v2_tools_default_to_canonical_bounded_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_usage_tracker.cli import mcp_allowance, mcp_server
    from codex_usage_tracker.server.analysis_jobs import AnalysisJobRegistry
    from codex_usage_tracker.store.connection import connect

    db_path = tmp_path / "usage.sqlite3"
    first = _usage_event(
        record_id="rec-v2-1",
        session_id="session-v2",
        thread_key="thread:allowance-v2",
        event_timestamp="2026-07-14T00:00:00Z",
        cumulative_total_tokens=100,
        rate_limit_plan_type="pro",
        rate_limit_limit_id="codex",
        rate_limit_primary_used_percent=10.0,
        rate_limit_primary_window_minutes=10080,
        rate_limit_primary_resets_at=1_769_000_000,
    )
    second = _usage_event(
        record_id="rec-v2-2",
        session_id="session-v2",
        thread_key="thread:allowance-v2",
        event_timestamp="2026-07-14T01:00:00Z",
        cumulative_total_tokens=200,
        rate_limit_plan_type="pro",
        rate_limit_limit_id="codex",
        rate_limit_primary_used_percent=11.0,
        rate_limit_primary_window_minutes=10080,
        rate_limit_primary_resets_at=1_769_000_000,
    )
    copied = replace(
        second,
        record_id="rec-v2-copy",
        session_id="session-v2-clone",
        source_file="/tmp/synthetic/rec-v2-copy.jsonl",
        canonical_record_id=second.record_id,
        is_duplicate=1,
        duplicate_reason="copied_clone_history",
    )
    upsert_usage_events([first, second, copied], db_path=db_path)
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO allowance_source_state VALUES "
            "(1, 1, 'r-mcp', 3, ?, 'reset-aware-v2', ?)",
            (second.event_timestamp, second.event_timestamp),
        )
        connection.execute(
            """INSERT INTO allowance_cycles
            (cycle_id,window_kind,window_key,cohort_key,is_archived,reset_at,
             first_observed_at,last_observed_at,latest_used_percent,
             observation_count,canonical_observation_count,canonical_tokens,
             price_coverage,quality_grade,status,cycle_state,source_revision,model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "mcp-week",
                "weekly",
                "primary",
                "codex",
                0,
                1_785_000_000,
                first.event_timestamp,
                second.event_timestamp,
                11.0,
                3,
                2,
                200,
                1.0,
                "high",
                "open",
                "open",
                "r-mcp",
                "reset-aware-v2",
            ),
        )
        connection.execute(
            """INSERT INTO allowance_intervals
            (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,
             start_record_id,end_record_id,end_observed_at,end_used_percent,
             point_kind,source_revision,model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "mcp-evidence",
                "mcp-week",
                "weekly",
                "primary",
                "codex",
                0,
                first.record_id,
                second.record_id,
                second.event_timestamp,
                11.0,
                "positive",
                "r-mcp",
                "reset-aware-v2",
            ),
        )
    monkeypatch.setattr(mcp_allowance, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_allowance, "_ALLOWANCE_ANALYSIS_JOBS", AnalysisJobRegistry())

    status = mcp_server.usage_allowance_status()
    series = mcp_server.usage_allowance_series(range_preset="7d")
    evidence = mcp_server.usage_allowance_evidence(limit=50, privacy_mode="local")

    assert status["schema"] == "codex-usage-tracker-allowance-status-v2"
    assert status["quality"]["canonical"] is True
    assert status["quality"]["copied_rows_excluded"] == 1
    assert status["next"]["action"] == "usage_refresh_start"
    assert series["schema"] == "codex-usage-tracker-allowance-series-v2"
    assert series["quality"]["canonical"] is True
    assert series["quality"]["copied_rows_excluded"] == 1
    assert evidence["schema"] == "codex-usage-tracker-allowance-evidence-v2"
    assert evidence["copied_rows_excluded"] == 1
    assert evidence["provenance"] == "local"
    assert evidence["rows"]
    assert "start_record_id" in evidence["rows"][0]
    assert "end_record_id" in evidence["rows"][0]

    with pytest.raises(ValueError, match="limit must be between 1 and 500"):
        mcp_server.usage_allowance_evidence(limit=0)
    with pytest.raises(ValueError, match="range_preset must be"):
        mcp_server.usage_allowance_series(range_preset="all")

    started = mcp_server.usage_allowance_analysis()
    assert started["schema"] == "codex-usage-tracker-analysis-job-v1"
    assert started["job_kind"] == "allowance-analysis"
    job_id = str(started["job_id"])
    terminal = _wait_for_analysis(mcp_server, job_id)
    assert terminal["status"] == "completed"
    assert terminal["next"] == {
        "action": "reload_persisted_results",
        "endpoint": "/api/allowance/analysis",
    }

    persisted = mcp_server.usage_allowance_analysis()
    assert persisted["schema"] == "codex-usage-tracker-allowance-analysis-v2"
    assert persisted["status"] in {
        "insufficient_evidence",
        "no_supported_change",
        "supported_change",
    }
    assert persisted["quality"]["canonical"] is True
    assert persisted["quality"]["copied_rows_excluded"] == 1


def test_bundled_skills_default_allowance_questions_to_v2_tools() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    pairs = [
        (
            repo_root / "skills" / "codex-usage-tracker" / "SKILL.md",
            repo_root
            / "src"
            / "codex_usage_tracker"
            / "plugin_data"
            / "skills"
            / "codex-usage-tracker"
            / "SKILL.md",
        ),
        (
            repo_root / "skills" / "codex-usage-api" / "SKILL.md",
            repo_root
            / "src"
            / "codex_usage_tracker"
            / "plugin_data"
            / "skills"
            / "codex-usage-api"
            / "SKILL.md",
        ),
    ]

    for source, bundled in pairs:
        text = source.read_text(encoding="utf-8")
        assert text == bundled.read_text(encoding="utf-8")
        assert "usage_allowance_status" in text
        assert "usage_allowance_series" in text
        assert "usage_allowance_evidence" in text
        assert "usage_allowance_analysis" in text
        assert "canonical" in text
        assert "bounded" in text


def _wait_for_analysis(mcp_server, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while True:
        payload = mcp_server.usage_allowance_analysis_status(job_id)
        if payload["status"] not in {"pending", "running"}:
            return payload
        assert payload["next"]["poll_after_ms"] == 500
        assert time.monotonic() < deadline
        time.sleep(0.01)
