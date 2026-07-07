from __future__ import annotations

import json
import sys
from pathlib import Path

from codex_usage_tracker.dashboard.api import generate_dashboard
from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.pricing.api import (
    annotate_rows_with_efficiency,
    load_pricing_config,
)
from codex_usage_tracker.store.api import (
    query_most_expensive_calls,
    query_session_usage,
    refresh_usage_index,
)
from tests.store_dashboard_helpers import (
    SESSION_ID,
    _assert_contract,
    _fake_pricing_update,
    _make_codex_home,
    _write_pricing,
)


def test_mcp_wrappers_smoke(tmp_path: Path, monkeypatch) -> None:
    from codex_usage_tracker import mcp_server

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    dashboard_path = tmp_path / "dashboard.html"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    allowance_path = tmp_path / "allowance.json"
    projects_path = tmp_path / "projects.json"
    rate_card_path = tmp_path / "rate-card.json"
    thresholds_path = tmp_path / "thresholds.json"
    monkeypatch.setattr(mcp_server, "DEFAULT_CODEX_HOME", codex_home)
    monkeypatch.setattr(mcp_server, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_DASHBOARD_PATH", dashboard_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_PRICING_PATH", pricing_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_ALLOWANCE_PATH", allowance_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_PROJECTS_PATH", projects_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_RATE_CARD_PATH", rate_card_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_THRESHOLDS_PATH", thresholds_path)
    monkeypatch.setattr(mcp_server, "update_pricing_from_openai_docs", _fake_pricing_update)

    refresh = mcp_server.refresh_usage_index()
    summary = mcp_server.usage_summary(group_by="thread")
    summary_json = mcp_server.usage_summary(group_by="model", response_format="json")
    project_summary = mcp_server.usage_summary(group_by="project")
    model_summary = mcp_server.usage_summary(preset="by-model")
    expensive = mcp_server.most_expensive_usage_calls(limit=1)
    expensive_json = mcp_server.most_expensive_usage_calls(limit=1, response_format="json")
    query_json = mcp_server.usage_query(
        model="gpt-5.5",
        min_tokens=50,
        limit=2,
        privacy_mode="strict",
    )
    recommendations_json = mcp_server.usage_recommendations(
        limit=2,
        response_format="json",
        privacy_mode="strict",
    )
    pricing_coverage = mcp_server.usage_pricing_coverage()
    pricing_coverage_json = mcp_server.usage_pricing_coverage(response_format="json")
    source_coverage = mcp_server.usage_source_coverage()
    source_coverage_json = mcp_server.usage_source_coverage(response_format="json")
    content_search_json = mcp_server.usage_content_search(
        query="SECRET RAW PROMPT",
        limit=1,
        max_snippet_chars=48,
    )
    thread_trace_json = mcp_server.usage_thread_trace(
        thread="Add Codex token tracking",
        limit=5,
        max_snippet_chars=48,
    )
    session = mcp_server.session_usage(session_id=SESSION_ID)
    session_json = mcp_server.session_usage(session_id=SESSION_ID, response_format="json")
    record_id = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]["record_id"]
    status_json = mcp_server.usage_status()
    calls_json = mcp_server.usage_calls(
        model="gpt-5.5",
        limit=1,
        privacy_mode="strict",
    )
    call_detail_json = mcp_server.usage_call_detail(
        record_id=record_id,
        privacy_mode="strict",
    )
    threads_json = mcp_server.usage_threads(limit=2)
    dashboard_recommendations_json = mcp_server.usage_dashboard_recommendations(
        limit=2,
        privacy_mode="strict",
    )
    report_pack_json = mcp_server.usage_report_pack(
        limit=2,
        evidence_limit=1,
        privacy_mode="strict",
    )
    context_disabled = mcp_server.usage_call_context(record_id=record_id)
    context_disabled_json = json.loads(context_disabled)
    monkeypatch.setenv("CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT", "1")
    context = mcp_server.usage_call_context(record_id=record_id)
    context_json = json.loads(context)
    dashboard = mcp_server.generate_usage_dashboard()
    csv_export = mcp_server.export_usage_csv(str(tmp_path / "usage.csv"), privacy_mode="redacted")
    pricing_init = mcp_server.init_usage_pricing_config(force=True)
    pricing_update = mcp_server.update_usage_pricing_config()
    allowance = mcp_server.init_usage_allowance_config()
    doctor = mcp_server.usage_doctor()
    doctor_json = mcp_server.usage_doctor(response_format="json")

    for payload in (
        refresh,
        summary_json,
        expensive_json,
        query_json,
        recommendations_json,
        pricing_coverage_json,
        content_search_json,
        thread_trace_json,
        session_json,
        status_json,
        calls_json,
        call_detail_json,
        threads_json,
        dashboard_recommendations_json,
        report_pack_json,
        context_disabled_json,
        context_json,
        dashboard,
        csv_export,
        pricing_init,
        pricing_update,
        allowance,
        doctor_json,
    ):
        _assert_contract(payload)

    assert refresh["parsed_events"] == 4
    assert refresh["skipped_events"] == 0
    assert "Add Codex token tracking" in summary
    assert summary_json["schema"] == "codex-usage-tracker-summary-v1"
    assert summary_json["rows"][0]["group_key"] == "gpt-5.5"
    assert "codex-usage-tracker" in project_summary
    assert "estimated cost" in model_summary
    assert "Most expensive Codex calls" in expensive
    assert expensive_json["is_expensive"] is True
    assert query_json["schema"] == "codex-usage-tracker-query-v1"
    assert query_json["filters"]["model"] == "gpt-5.5"
    assert query_json["row_count"] == 2
    assert query_json["rows"][0]["pricing_model"] == "gpt-5.5"
    assert query_json["rows"][0]["cwd"].startswith("[redacted cwd:")
    assert query_json["rows"][0]["project_relative_cwd"] is None
    assert recommendations_json["schema"] == "codex-usage-tracker-recommendations-v1"
    assert recommendations_json["row_count"] >= 1
    assert recommendations_json["rows"][0]["recommendation_score"] > 0
    assert recommendations_json["threads"]
    assert "Codex pricing coverage" in pricing_coverage
    assert pricing_coverage_json["schema"] == "codex-usage-tracker-pricing-coverage-v1"
    assert "Codex source coverage" in source_coverage
    assert source_coverage_json["schema"] == "codex-usage-tracker-source-coverage-v1"
    assert source_coverage_json["content_mode"] == "aggregate_only"
    assert source_coverage_json["includes_indexed_content"] is False
    assert source_coverage_json["includes_raw_fragments"] is False
    assert content_search_json["schema"] == "codex-usage-tracker-content-search-v1"
    assert content_search_json["content_mode"] == "local_content_index"
    assert content_search_json["includes_indexed_content"] is True
    assert content_search_json["row_count"] == 1
    assert "SECRET" in content_search_json["rows"][0]["snippet"]
    assert thread_trace_json["schema"] == "codex-usage-tracker-thread-trace-v1"
    assert thread_trace_json["content_mode"] == "local_content_index"
    assert thread_trace_json["includes_indexed_content"] is True
    assert thread_trace_json["call_count"] >= 1
    assert any(call["fragment_count"] > 0 for call in thread_trace_json["calls"])
    assert SESSION_ID in session
    assert session_json["resolved_session_id"] == SESSION_ID
    assert session_json["row_count"] == 2
    assert status_json["schema"] == "codex-usage-tracker-status-v1"
    assert status_json["row_counts"]["active_rows"] >= 2
    assert calls_json["schema"] == "codex-usage-tracker-calls-v1"
    assert calls_json["row_count"] == 1
    assert calls_json["total_matched_rows"] > calls_json["row_count"]
    assert calls_json["rows"][0]["cwd"].startswith("[redacted cwd:")
    assert calls_json["raw_context_included"] is False
    assert call_detail_json["schema"] == "codex-usage-tracker-call-v1"
    assert call_detail_json["record"]["record_id"] == record_id
    assert call_detail_json["raw_context_included"] is False
    assert "SECRET RAW PROMPT" not in json.dumps(call_detail_json)
    assert threads_json["schema"] == "codex-usage-tracker-threads-v1"
    assert threads_json["row_count"] >= 1
    assert dashboard_recommendations_json["schema"] == "codex-usage-tracker-recommendations-v1"
    assert dashboard_recommendations_json["row_count"] >= 1
    assert report_pack_json["schema"] == "codex-usage-tracker-reports-pack-v1"
    assert report_pack_json["evidence"]["cost-curves"]["raw_context_included"] is False
    assert "Raw context loading through MCP is disabled" in context_disabled
    assert context_disabled_json["schema"] == "codex-usage-tracker-context-disabled-v1"
    assert "SECRET RAW PROMPT" not in context_disabled
    assert "SECRET RAW PROMPT" in context
    assert context_json["schema"] == "codex-usage-tracker-context-v1"
    assert "sk" + "-proj-" not in context
    assert "[REDACTED_OPENAI_KEY]" in context
    assert dashboard["dashboard_path"] == str(dashboard_path)
    assert csv_export["privacy_mode"] == "redacted"
    assert pricing_init["pricing_path"] == str(pricing_path)
    assert pricing_update["model_count"] == 1
    assert pricing_update["source_url"] == "https://example.test/pricing.md"
    assert allowance["allowance_path"] == str(allowance_path)
    assert allowance_path.exists()
    assert "Codex Usage Tracker doctor" in doctor
    assert doctor_json["schema"] == "codex-usage-tracker-doctor-v1"


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
                        "command": sys.executable,
                        "args": ["-m", "codex_usage_tracker.mcp_server"],
                        "env": {
                            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")
                        },
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
