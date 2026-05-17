from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.dashboard import generate_dashboard
from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.pricing import (
    PricingUpdateResult,
    annotate_rows_with_efficiency,
    load_pricing_config,
)
from codex_usage_tracker.store import (
    export_usage_csv,
    query_most_expensive_calls,
    query_session_usage,
    query_summary,
    refresh_usage_index,
)

SESSION_ID = "019e374d-c19f-7da3-a44f-8de043a7a64e"


def test_refresh_is_idempotent_and_summary_works(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    first = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    session_rows = query_session_usage(db_path=db_path, session_id=SESSION_ID)
    summary = query_summary(db_path=db_path, group_by="model")
    recent_summary = query_summary(db_path=db_path, group_by="model", since="2026-05-17")
    future_summary = query_summary(db_path=db_path, group_by="model", since="2099-01-01")
    expensive = query_most_expensive_calls(db_path=db_path, limit=1)

    assert first.parsed_events == 2
    assert second.parsed_events == 2
    assert len(session_rows) == 2
    assert summary[0]["group_key"] == "gpt-5.5"
    assert summary[0]["total_tokens"] == 300
    assert recent_summary[0]["total_tokens"] == 300
    assert future_summary == []
    assert expensive[0]["total_tokens"] == 200


def test_dashboard_and_csv_are_aggregate_only(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    dashboard_path = tmp_path / "dashboard.html"
    csv_path = tmp_path / "usage.csv"

    generate_dashboard(db_path=db_path, output_path=dashboard_path, pricing_path=pricing_path)
    exported = export_usage_csv(output_path=csv_path, db_path=db_path)

    dashboard = dashboard_path.read_text(encoding="utf-8")
    csv_text = csv_path.read_text(encoding="utf-8")
    assert exported == 2
    assert "SECRET RAW PROMPT" not in dashboard
    assert "SECRET RAW PROMPT" not in csv_text
    assert "last call" in dashboard.lower()
    assert "session cumulative" in dashboard.lower()
    assert "Estimated Cost" in dashboard
    assert "estimated_cost_usd" in dashboard


def test_mcp_wrappers_smoke(tmp_path: Path, monkeypatch) -> None:
    from codex_usage_tracker import mcp_server

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    dashboard_path = tmp_path / "dashboard.html"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    monkeypatch.setattr(mcp_server, "DEFAULT_CODEX_HOME", codex_home)
    monkeypatch.setattr(mcp_server, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_DASHBOARD_PATH", dashboard_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_PRICING_PATH", pricing_path)
    monkeypatch.setattr(mcp_server, "update_pricing_from_openai_docs", _fake_pricing_update)

    refresh = mcp_server.refresh_usage_index()
    summary = mcp_server.usage_summary(group_by="thread")
    model_summary = mcp_server.usage_summary(preset="by-model")
    expensive = mcp_server.most_expensive_usage_calls(limit=1)
    pricing_coverage = mcp_server.usage_pricing_coverage()
    session = mcp_server.session_usage(session_id=SESSION_ID)
    dashboard = mcp_server.generate_usage_dashboard()
    pricing_update = mcp_server.update_usage_pricing_config()
    doctor = mcp_server.usage_doctor()

    assert refresh["parsed_events"] == 2
    assert "Add Codex token tracking" in summary
    assert "estimated cost" in model_summary
    assert "Most expensive Codex calls" in expensive
    assert "Codex pricing coverage" in pricing_coverage
    assert SESSION_ID in session
    assert dashboard["dashboard_path"] == str(dashboard_path)
    assert pricing_update["model_count"] == 1
    assert pricing_update["source_url"] == "https://example.test/pricing.md"
    assert "Codex Usage Tracker doctor" in doctor


def test_pricing_annotation_and_doctor_pass(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    dashboard_path = tmp_path / "dashboard.html"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    generate_dashboard(db_path=db_path, output_path=dashboard_path, pricing_path=pricing_path)

    rows = query_most_expensive_calls(db_path=db_path, limit=1)
    annotated = annotate_rows_with_efficiency(
        rows, pricing=load_pricing_config(tmp_path / "missing-pricing.json")
    )
    assert annotated[0]["estimated_cost_usd"] is None
    annotated = annotate_rows_with_efficiency(rows, pricing=load_pricing_config(pricing_path))
    assert annotated[0]["estimated_cost_usd"] > 0

    repo_root = tmp_path / "repo"
    (repo_root / ".codex-plugin").mkdir(parents=True)
    (repo_root / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (repo_root / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "codex-usage-tracker": {
                        "command": "/usr/bin/python3",
                        "args": ["-m", "codex_usage_tracker.mcp_server"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    plugin_link = tmp_path / "plugins" / "codex-usage-tracker"
    plugin_link.parent.mkdir()
    plugin_link.symlink_to(repo_root, target_is_directory=True)
    marketplace_path = tmp_path / "marketplace.json"
    marketplace_path.write_text(
        json.dumps({"plugins": [{"name": "codex-usage-tracker"}]}),
        encoding="utf-8",
    )

    report = run_doctor(
        codex_home=codex_home,
        db_path=db_path,
        dashboard_path=dashboard_path,
        pricing_path=pricing_path,
        plugin_link=plugin_link,
        marketplace_path=marketplace_path,
        repo_root=repo_root,
    )

    assert report["status"] == "pass"


def _make_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    log_dir = codex_home / "sessions" / "2026" / "05" / "17"
    log_path = log_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Add Codex token tracking",
                "updated_at": "2026-05-17T18:58:27Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-a",
                    "model": "gpt-5.5",
                    "effort": "xhigh",
                    "cwd": "/tmp/codex-usage-tracker",
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "SECRET RAW PROMPT"}],
                },
            ),
            _token_event(100, 100),
            _token_event(300, 200),
        ],
    )
    return codex_home


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


def _fake_pricing_update(
    path: Path,
    tier: str = "standard",
    include_estimates: bool = True,
) -> PricingUpdateResult:
    return PricingUpdateResult(
        path=path,
        source_url="https://example.test/pricing.md",
        tier=tier,
        fetched_at="2026-05-17T00:00:00+00:00",
        model_count=1,
        estimated_model_count=1 if include_estimates else 0,
        backup_path=None,
    )


def _token_event(cumulative_total: int, last_total: int) -> dict[str, object]:
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": cumulative_total - 25,
                    "cached_input_tokens": 25,
                    "output_tokens": 25,
                    "reasoning_output_tokens": 5,
                    "total_tokens": cumulative_total,
                },
                "last_token_usage": {
                    "input_tokens": last_total - 25,
                    "cached_input_tokens": 10,
                    "output_tokens": 25,
                    "reasoning_output_tokens": 5,
                    "total_tokens": last_total,
                },
                "model_context_window": 258400,
            },
        },
    )


def _entry(entry_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": "2026-05-17T18:58:27.000Z",
        "type": entry_type,
        "payload": payload,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
