from __future__ import annotations

import json
import sys
import time
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
    ARCHIVED_SESSION_ID,
    SESSION_ID,
    _assert_contract,
    _entry,
    _fake_pricing_update,
    _make_codex_home,
    _token_event,
    _write_jsonl,
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
    repetition_scan_json = mcp_server.usage_repetition_scan(min_occurrences=1, limit=2)
    command_scan_json = mcp_server.usage_command_loop_scan(min_occurrences=1, limit=2)
    file_scan_json = mcp_server.usage_file_churn_scan(min_occurrences=1, limit=2)
    context_scan_json = mcp_server.usage_context_bloat_scan(min_occurrences=1, limit=2)
    suggestions_json = mcp_server.usage_suggest_investigations(goal="token_waste", limit=2)
    agentic_investigation_json = mcp_server.usage_investigate(
        goal="token_waste",
        evidence_limit=2,
    )
    hypothesis_test_json = mcp_server.usage_test_hypotheses(
        question="Look for actionable token waste",
        hypotheses=[
            "Token waste is concentrated in large low-output calls.",
            "Repeated shell probing is creating workflow churn.",
        ],
        evidence_limit=2,
    )
    default_hypothesis_json = mcp_server.usage_test_hypotheses(
        question="What usage hypotheses should I test?",
        evidence_limit=1,
    )
    investigation_walk_json = mcp_server.usage_investigation_walk(
        question="Look for local token waste patterns",
        min_occurrences=1,
        evidence_limit=2,
    )
    local_evidence_export_json = mcp_server.usage_local_evidence_export(
        question="Share local token waste evidence",
        min_occurrences=1,
        evidence_limit=2,
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
        repetition_scan_json,
        command_scan_json,
        file_scan_json,
        context_scan_json,
        suggestions_json,
        agentic_investigation_json,
        hypothesis_test_json,
        default_hypothesis_json,
        investigation_walk_json,
        local_evidence_export_json,
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
    for payload in (
        repetition_scan_json,
        command_scan_json,
        file_scan_json,
        context_scan_json,
    ):
        assert payload["schema"] == "codex-usage-tracker-pattern-scan-v1"
        assert payload["content_mode"] == "local_content_index"
        assert payload["includes_indexed_content"] is True
        assert payload["includes_raw_fragments"] is False
    assert investigation_walk_json["schema"] == "codex-usage-tracker-investigation-walk-v1"
    assert investigation_walk_json["content_mode"] == "local_content_index"
    assert investigation_walk_json["includes_indexed_content"] is True
    assert investigation_walk_json["includes_raw_fragments"] is False
    assert investigation_walk_json["branches"]
    assert suggestions_json["schema"] == "codex-usage-tracker-investigation-suggestions-v1"
    assert suggestions_json["content_mode"] == "aggregate_guidance"
    assert suggestions_json["includes_raw_fragments"] is False
    assert suggestions_json["suggestions"]
    suggestion_goals = [row["goal"] for row in suggestions_json["suggestions"]]
    assert suggestion_goals == ["token_waste", "cache_failure"]
    overview_suggestions = mcp_server.usage_suggest_investigations(goal="overview", limit=5)
    assert [row["goal"] for row in overview_suggestions["suggestions"]] == [
        "overview",
        "token_waste",
        "cache_failure",
        "workflow_churn",
        "allowance_change",
    ]
    assert agentic_investigation_json["schema"] == "codex-usage-tracker-agentic-investigation-v1"
    assert agentic_investigation_json["content_mode"] == "aggregate_investigation"
    assert agentic_investigation_json["includes_indexed_content"] is False
    assert agentic_investigation_json["includes_raw_fragments"] is False
    assert agentic_investigation_json["filters"]["detail_mode"] == "compact"
    assert agentic_investigation_json["findings"]
    first_finding = agentic_investigation_json["findings"][0]
    assert first_finding["evidence_summary"]["row_count"] == first_finding["evidence_count"]
    assert first_finding["missing_access"]
    if first_finding["evidence"]:
        assert "source_file" not in first_finding["evidence"][0]
    full_investigation_json = mcp_server.usage_investigate(
        goal="token_waste",
        evidence_limit=1,
        detail_mode="full",
    )
    assert full_investigation_json["filters"]["detail_mode"] == "full"
    assert full_investigation_json["findings"][0]["evidence_summary"]["row_count"] == 1
    assert hypothesis_test_json["schema"] == "codex-usage-tracker-hypothesis-test-v1"
    assert hypothesis_test_json["content_mode"] == "aggregate_with_local_index_signals"
    assert hypothesis_test_json["includes_raw_fragments"] is False
    assert hypothesis_test_json["question"] == "Look for actionable token waste"
    assert hypothesis_test_json["summary"]["hypothesis_count"] == 2
    assert hypothesis_test_json["hypotheses"]
    first_hypothesis = hypothesis_test_json["hypotheses"][0]
    assert first_hypothesis["family"] == "token_waste"
    assert hypothesis_test_json["hypotheses"][1]["family"] == "shell_churn"
    assert first_hypothesis["status"] in {
        "true",
        "false",
        "partially_true",
        "insufficient_evidence",
    }
    assert first_hypothesis["i_would_like_to_be_able_to"]
    assert first_hypothesis["i_will_accomplish_this_using"]
    assert first_hypothesis["i_am_missing_access_to"]
    assert first_hypothesis["evidence_summary"]
    assert first_hypothesis["next_action"]
    assert hypothesis_test_json["recommended_next_tools"]
    assert default_hypothesis_json["summary"]["hypothesis_count"] == 6
    assert {row["family"] for row in default_hypothesis_json["hypotheses"]} == {
        "token_waste",
        "cache_failure",
        "repeated_file_rediscovery",
        "shell_churn",
        "effort_model_choice",
        "allowance_change",
    }
    assert local_evidence_export_json["schema"] == "codex-usage-tracker-local-evidence-export-v1"
    assert local_evidence_export_json["content_mode"] == "shareable_local_evidence"
    assert local_evidence_export_json["includes_indexed_content"] is False
    assert local_evidence_export_json["includes_raw_fragments"] is False
    supported_export_branches = [
        branch for branch in local_evidence_export_json["branches"] if not branch["pruned"]
    ]
    assert supported_export_branches
    for branch in supported_export_branches:
        aggregate = branch["aggregate_evidence"]
        assert aggregate["evidence_row_count"] == branch["evidence_count"]
        assert aggregate["occurrences"] >= branch["evidence_count"]
        assert aggregate["call_count"] >= branch["evidence_count"]
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


def test_agentic_mcp_reports_default_active_scope_excludes_archived(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from codex_usage_tracker.cli import mcp_server

    codex_home = _make_codex_home(tmp_path)
    archived_log_path = (
        codex_home
        / "archived_sessions"
        / f"rollout-2026-05-17T17-00-00-{ARCHIVED_SESSION_ID}.jsonl"
    )
    _write_jsonl(
        archived_log_path,
        [
            _entry("session_meta", {"id": ARCHIVED_SESSION_ID}),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-archived",
                    "model": "gpt-5.5",
                    "effort": "low",
                    "cwd": "/tmp/codex-usage-tracker",
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "call_id": "archived-sed-1",
                    "name": "functions.exec_command",
                    "arguments": json.dumps({"cmd": "sed -n '1,80p' src/archived-only.py"}),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "call_id": "archived-sed-2",
                    "name": "functions.exec_command",
                    "arguments": json.dumps({"cmd": "sed -n '80,160p' src/archived-only.py"}),
                },
            ),
            _token_event(60_000, 60_000),
        ],
    )

    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    allowance_path = tmp_path / "allowance.json"
    projects_path = tmp_path / "projects.json"
    monkeypatch.setattr(mcp_server, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_PRICING_PATH", pricing_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_ALLOWANCE_PATH", allowance_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_PROJECTS_PATH", projects_path)

    refresh_usage_index(codex_home=codex_home, db_path=db_path, include_archived=True)

    active_large = mcp_server.usage_large_low_output_calls(
        min_total_tokens=0,
        max_output_tokens=1000,
        limit=100,
    )
    all_large = mcp_server.usage_large_low_output_calls(
        include_archived=True,
        min_total_tokens=0,
        max_output_tokens=1000,
        limit=100,
    )
    active_shell = mcp_server.usage_shell_churn(min_occurrences=1, limit=100)
    all_shell = mcp_server.usage_shell_churn(
        include_archived=True,
        min_occurrences=1,
        limit=100,
    )
    active_files = mcp_server.usage_repeated_file_rediscovery(min_occurrences=1, limit=100)
    all_files = mcp_server.usage_repeated_file_rediscovery(
        include_archived=True,
        min_occurrences=1,
        limit=100,
    )
    active_agentic = mcp_server.usage_investigate(goal="token_waste", evidence_limit=10)
    active_export = mcp_server.usage_local_evidence_export(
        question="token waste",
        min_occurrences=1,
        evidence_limit=10,
    )
    active_hypotheses = mcp_server.usage_test_hypotheses(
        question="Look for token waste",
        hypotheses=["Token waste is concentrated in large low-output calls."],
        evidence_limit=10,
    )

    assert ARCHIVED_SESSION_ID in json.dumps(all_large)
    assert ARCHIVED_SESSION_ID in json.dumps(all_shell)
    assert "archived-only.py" in json.dumps(all_files)
    for payload in (
        active_large,
        active_shell,
        active_files,
        active_agentic,
        active_export,
        active_hypotheses,
    ):
        encoded = json.dumps(payload)
        assert ARCHIVED_SESSION_ID not in encoded
        assert "archived-only.py" not in encoded
        assert payload["filters"]["include_archived"] is False


def test_mcp_dogfood_async_job_reports_progress(tmp_path: Path, monkeypatch) -> None:
    from codex_usage_tracker.cli import mcp_server

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    allowance_path = tmp_path / "allowance.json"
    projects_path = tmp_path / "projects.json"
    rate_card_path = tmp_path / "rate-card.json"
    output_dir = tmp_path / "dogfood-jobs"

    monkeypatch.setattr(mcp_server, "DEFAULT_CODEX_HOME", codex_home)
    monkeypatch.setattr(mcp_server, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_PRICING_PATH", pricing_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_ALLOWANCE_PATH", allowance_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_PROJECTS_PATH", projects_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_RATE_CARD_PATH", rate_card_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_AGENTIC_DOGFOOD_DIR", output_dir)
    with mcp_server._DOGFOOD_JOB_LOCK:
        mcp_server._DOGFOOD_JOBS.clear()
        mcp_server._DOGFOOD_RESULT_CACHE.clear()

    started = mcp_server.usage_dogfood_start(
        evidence_limit=1,
        privacy_mode="strict",
        refresh=True,
        write_markdown=False,
    )
    assert started["schema"] == "codex-usage-tracker-async-job-status-v1"
    assert started["status"] in {"queued", "running", "completed"}
    job_id = started["job_id"]

    status = started
    for _ in range(100):
        status = mcp_server.usage_dogfood_status(job_id)
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert status["status"] == "completed", status.get("error")
    assert status["percent_complete"] == 100
    assert status["result_available"] is True
    assert status["cache"]["cache_keys"]
    assert status["stages"][-1]["stage"] == "write_artifacts"
    assert Path(status["artifacts"]["summary_json_path"]).exists()

    result = mcp_server.usage_dogfood_result(job_id)
    assert result["schema"] == "codex-usage-tracker-agentic-dogfood-v1"
    assert result["progress"]["percent_complete"] == 100
    assert result["cache"]["scope"] == "single_run_shared_reports"

    cached = mcp_server.usage_dogfood_start(
        evidence_limit=1,
        privacy_mode="strict",
        refresh=False,
        write_markdown=False,
    )
    assert cached["status"] == "completed"
    assert cached["percent_complete"] == 100
    assert cached["current_stage"] == "result_cache"
    assert cached["result_cache"]["hit"] is True
    assert cached["result_cache"]["source"] in {"memory", "disk"}
    assert cached["stages"][-1]["stage"] == "result_cache"
    cached_result = mcp_server.usage_dogfood_result(cached["job_id"])
    assert cached_result["schema"] == "codex-usage-tracker-agentic-dogfood-v1"

    with mcp_server._DOGFOOD_JOB_LOCK:
        mcp_server._DOGFOOD_RESULT_CACHE.clear()
    disk_cached = mcp_server.usage_dogfood_start(
        evidence_limit=1,
        privacy_mode="strict",
        refresh=False,
        write_markdown=False,
    )
    assert disk_cached["status"] == "completed"
    assert disk_cached["result_cache"]["hit"] is True
    assert disk_cached["result_cache"]["source"] == "disk"


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
