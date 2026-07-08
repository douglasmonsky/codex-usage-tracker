from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from codex_usage_tracker.core.json_contracts import validate_json_payload_contract
from codex_usage_tracker.store.api import EVENT_COLUMNS

SESSION_ID = "019e374d-c19f-7da3-a44f-8de043a7a64e"


def test_setup_support_bundle_and_reset_db_cli(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    allowance_path = tmp_path / "allowance.json"
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    marketplace_path = tmp_path / "marketplace.json"
    support_path = tmp_path / "support.json"

    setup = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "--allowance",
        str(allowance_path),
        "setup",
        "--codex-home",
        str(codex_home),
        "--plugin-dir",
        str(plugin_dir),
        "--marketplace",
        str(marketplace_path),
        "--skip-pricing",
    )

    assert setup.returncode == 0
    assert "Codex Usage Tracker setup summary" in setup.stdout
    assert "Restart Codex" in setup.stdout
    assert plugin_dir.exists()
    assert db_path.exists()

    support = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "--allowance",
        str(allowance_path),
        "--privacy-mode",
        "strict",
        "support-bundle",
        "--codex-home",
        str(codex_home),
        "--output",
        str(support_path),
    )
    bundle = json.loads(support_path.read_text(encoding="utf-8"))

    assert support.returncode == 0
    assert "GitHub issue fields safe to paste after review" in support.stdout
    assert "doctor.environment" in support.stdout
    assert bundle["privacy"]["contains_raw_logs"] is False
    assert bundle["privacy"]["project_metadata"]["mode"] == "strict"
    assert bundle["privacy"]["project_metadata"]["relative_cwd_hidden"] is True
    assert bundle["issue_report"]["safe_to_paste_after_review"] is True
    assert bundle["refresh"]["parsed_events"] == "1"
    assert "low_cache_ratio" in bundle["thresholds"]["keys"]
    assert bundle["projects"]["alias_count"] == 0
    assert "SECRET RAW PROMPT" not in json.dumps(bundle)

    reset_without_confirm = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "reset-db",
    )
    reset = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "reset-db",
        "--yes",
    )
    raw_log_path = next((codex_home / "sessions").glob("**/*.jsonl"))

    assert reset_without_confirm.returncode == 1
    assert "Re-run with --yes" in reset_without_confirm.stderr
    assert reset.returncode == 0
    assert "Raw Codex logs were not touched" in reset.stdout
    assert "SECRET RAW PROMPT" in raw_log_path.read_text(encoding="utf-8")


def test_rate_card_allowance_and_pricing_snapshot_cli(tmp_path: Path) -> None:
    rate_card_path = tmp_path / "rate-card.json"
    allowance_path = tmp_path / "allowance.json"
    pricing_path = tmp_path / "pricing.json"
    pinned_pricing_path = tmp_path / "pricing-pinned.json"
    pricing_path.write_text(
        json.dumps(
            {
                "_source": {"name": "Synthetic pricing", "fetched_at": "2026-06-05T12:00:00Z"},
                "models": {
                    "gpt-5.5": {
                        "input_per_million": 1,
                        "cached_input_per_million": 0.1,
                        "output_per_million": 2,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    update_rate_card = _run_cli(
        tmp_path,
        "--rate-card",
        str(rate_card_path),
        "update-rate-card",
    )
    parse_allowance = _run_cli(
        tmp_path,
        "--allowance",
        str(allowance_path),
        "parse-allowance",
        "5h",
        "79%",
        "6:50 PM",
        "Weekly",
        "33%",
        "Jun 7",
    )
    pin_pricing = _run_cli(
        tmp_path,
        "--pricing",
        str(pricing_path),
        "pin-pricing",
        "--output",
        str(pinned_pricing_path),
    )

    assert update_rate_card.returncode == 0
    assert "Codex credit rates" in update_rate_card.stdout
    assert json.loads(rate_card_path.read_text(encoding="utf-8"))["schema"] == (
        "codex-usage-tracker-codex-rate-card-v1"
    )
    assert parse_allowance.returncode == 0
    allowance = json.loads(allowance_path.read_text(encoding="utf-8"))
    assert allowance["windows"][0]["remaining_percent"] == 0.79
    assert allowance["windows"][1]["remaining_percent"] == 0.33
    assert pin_pricing.returncode == 0
    pinned = json.loads(pinned_pricing_path.read_text(encoding="utf-8"))
    assert pinned["_source"]["pinned"] is True
    assert pinned["_source"]["pin_note"].startswith("Use this file")


def test_lifecycle_commands_return_actionable_errors_without_real_logs(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    unrelated_plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    unrelated_plugin_dir.mkdir(parents=True)
    (unrelated_plugin_dir / "README.md").write_text("not generated by tracker\n", encoding="utf-8")

    reset_without_confirm = _run_cli(tmp_path, "--db", str(db_path), "reset-db")
    inspect_missing_log = _run_cli(tmp_path, "inspect-log", str(tmp_path / "missing.jsonl"))
    install_unrelated_plugin = _run_cli(
        tmp_path,
        "install-plugin",
        "--plugin-dir",
        str(unrelated_plugin_dir),
        "--marketplace",
        str(tmp_path / "marketplace.json"),
    )

    for result in (reset_without_confirm, inspect_missing_log, install_unrelated_plugin):
        assert result.returncode == 1
        assert result.stdout == ""
        assert "Traceback" not in result.stderr
        assert result.stderr.startswith("Error: [")

    assert "[invalid_value]" in reset_without_confirm.stderr
    assert "Re-run with --yes" in reset_without_confirm.stderr
    assert "[file_not_found]" in inspect_missing_log.stderr
    assert "missing.jsonl" in inspect_missing_log.stderr
    assert "[file_exists]" in install_unrelated_plugin.stderr
    assert "does not look like a Codex Usage Tracker plugin" in install_unrelated_plugin.stderr


def test_report_json_and_query_cli(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    allowance_path = tmp_path / "allowance.json"
    pricing_path.write_text(
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

    refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "refresh",
        "--codex-home",
        str(codex_home),
        "--json",
    )
    summary = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "summary",
        "--group-by",
        "model",
        "--json",
    )
    query = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "--allowance",
        str(allowance_path),
        "--privacy-mode",
        "strict",
        "query",
        "--model",
        "gpt-5.5",
        "--min-tokens",
        "50",
    )
    recommendations = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(tmp_path / "missing-pricing.json"),
        "--allowance",
        str(allowance_path),
        "recommendations",
        "--limit",
        "1",
        "--json",
    )
    action_brief = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "--allowance",
        str(allowance_path),
        "--privacy-mode",
        "strict",
        "action-brief",
        "--evidence-limit",
        "2",
        "--json",
    )
    session = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "session",
        SESSION_ID,
        "--json",
    )
    expensive = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "expensive",
        "--limit",
        "1",
        "--json",
    )
    csv_path = tmp_path / "redacted.csv"
    export = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--privacy-mode",
        "redacted",
        "export",
        "--output",
        str(csv_path),
        "--json",
    )

    assert refresh.returncode == 0
    refresh_payload = json.loads(refresh.stdout)
    summary_payload = json.loads(summary.stdout)
    query_payload = json.loads(query.stdout)
    recommendations_payload = json.loads(recommendations.stdout)
    action_brief_payload = json.loads(action_brief.stdout)
    session_payload = json.loads(session.stdout)
    expensive_payload = json.loads(expensive.stdout)
    _assert_contract(refresh_payload)
    _assert_contract(summary_payload)
    _assert_contract(query_payload)
    _assert_contract(recommendations_payload)
    _assert_contract(action_brief_payload)
    _assert_contract(session_payload)
    _assert_contract(expensive_payload)
    assert refresh_payload["schema"] == "codex-usage-tracker-refresh-v1"
    assert summary_payload["schema"] == "codex-usage-tracker-summary-v1"
    assert summary_payload["rows"][0]["group_key"] == "gpt-5.5"
    assert query_payload["schema"] == "codex-usage-tracker-query-v1"
    assert query_payload["filters"]["model"] == "gpt-5.5"
    assert query_payload["filters"]["privacy_mode"] == "strict"
    assert query_payload["row_count"] == 1
    assert query_payload["rows"][0]["model"] == "gpt-5.5"
    assert query_payload["rows"][0]["pricing_model"] == "gpt-5.5"
    assert query_payload["rows"][0]["cwd"].startswith("[redacted cwd:")
    assert query_payload["rows"][0]["project_relative_cwd"] is None
    assert "/tmp/codex-usage-tracker" not in query.stdout
    assert "SECRET RAW PROMPT" not in query.stdout
    assert action_brief_payload["schema"] == "codex-usage-tracker-action-brief-v1"
    assert action_brief_payload["content_mode"] == "aggregate_action_brief"
    assert action_brief_payload["includes_raw_fragments"] is False
    assert recommendations_payload["schema"] == "codex-usage-tracker-recommendations-v1"
    assert recommendations_payload["row_count"] == 1
    assert recommendations_payload["rows"][0]["primary_signal"] == "pricing-gap"
    assert recommendations_payload["rows"][0]["recommendation_score"] > 0
    assert recommendations_payload["threads"][0]["primary_recommendation"]["key"] == "pricing-gap"
    assert session_payload["schema"] == "codex-usage-tracker-session-v1"
    assert session_payload["resolved_session_id"] == SESSION_ID
    assert expensive_payload["schema"] == "codex-usage-tracker-summary-v1"
    assert expensive_payload["is_expensive"] is True
    export_payload = json.loads(export.stdout)
    _assert_contract(export_payload)
    assert export.returncode == 0
    assert export_payload["privacy_mode"] == "redacted"
    csv_text = csv_path.read_text(encoding="utf-8")
    csv_rows = list(csv.DictReader(csv_text.splitlines()))
    assert csv_rows
    assert list(csv_rows[0]) == EVENT_COLUMNS
    assert "[redacted cwd:" in csv_text


def test_diagnostics_cli_returns_aggregate_json(tmp_path: Path) -> None:
    codex_home = _make_diagnostics_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "refresh",
        "--codex-home",
        str(codex_home),
        "--json",
    )
    summary = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "summary",
        "--json",
    )
    facts = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "facts",
        "--limit",
        "0",
        "--json",
    )
    compactions = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "compactions",
        "--json",
    )
    tools = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "tools",
        "--json",
    )
    overview_missing = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "overview",
        "--json",
    )
    overview_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "overview",
        "--refresh",
        "--json",
    )
    tool_output_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "tool-output",
        "--refresh",
        "--json",
    )
    commands_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "commands",
        "--refresh",
        "--json",
    )
    git_interactions_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "git-interactions",
        "--refresh",
        "--json",
    )
    file_reads_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "file-reads",
        "--refresh",
        "--json",
    )
    file_modifications_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "file-modifications",
        "--refresh",
        "--json",
    )
    read_productivity_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "read-productivity",
        "--refresh",
        "--json",
    )
    concentration_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "concentration",
        "--refresh",
        "--json",
    )
    guided_summary_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "guided-summary",
        "--refresh",
        "--json",
    )
    usage_drain_refresh = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diagnostics",
        "usage-drain",
        "--refresh",
        "--json",
    )
    fact_calls = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--privacy-mode",
        "strict",
        "diagnostics",
        "fact-calls",
        "--fact-type",
        "compaction",
        "--fact-name",
        "post_compaction",
        "--json",
    )

    assert refresh.returncode == 0
    summary_payload = json.loads(summary.stdout)
    facts_payload = json.loads(facts.stdout)
    compactions_payload = json.loads(compactions.stdout)
    tools_payload = json.loads(tools.stdout)
    overview_missing_payload = json.loads(overview_missing.stdout)
    overview_refresh_payload = json.loads(overview_refresh.stdout)
    tool_output_refresh_payload = json.loads(tool_output_refresh.stdout)
    commands_refresh_payload = json.loads(commands_refresh.stdout)
    git_interactions_refresh_payload = json.loads(git_interactions_refresh.stdout)
    file_reads_refresh_payload = json.loads(file_reads_refresh.stdout)
    file_modifications_refresh_payload = json.loads(file_modifications_refresh.stdout)
    read_productivity_refresh_payload = json.loads(read_productivity_refresh.stdout)
    concentration_refresh_payload = json.loads(concentration_refresh.stdout)
    guided_summary_refresh_payload = json.loads(guided_summary_refresh.stdout)
    usage_drain_refresh_payload = json.loads(usage_drain_refresh.stdout)
    fact_calls_payload = json.loads(fact_calls.stdout)
    for payload in (
        summary_payload,
        facts_payload,
        compactions_payload,
        tools_payload,
        overview_missing_payload,
        overview_refresh_payload,
        tool_output_refresh_payload,
        commands_refresh_payload,
        git_interactions_refresh_payload,
        file_reads_refresh_payload,
        file_modifications_refresh_payload,
        read_productivity_refresh_payload,
        concentration_refresh_payload,
        usage_drain_refresh_payload,
        fact_calls_payload,
    ):
        _assert_contract(payload)
        assert payload["raw_context_included"] is False
    for payload in (
        summary_payload,
        facts_payload,
        compactions_payload,
        tools_payload,
        fact_calls_payload,
    ):
        assert payload["schema"] == "codex-usage-tracker-diagnostics-v1"
        assert "Associated token totals are not additive" in payload["notes"][0]

    fact_names = {row["fact_name"] for row in facts_payload["rows"]}
    assert {"function_call_output", "patch_applied", "post_compaction"} <= fact_names
    assert summary_payload["view"] == "summary"
    assert {row["fact_type"] for row in summary_payload["rows"]} >= {
        "compaction",
        "outcome",
        "tool",
    }
    assert compactions_payload["filters"]["fact_type"] == "compaction"
    assert {row["fact_type"] for row in compactions_payload["rows"]} == {"compaction"}
    assert tools_payload["filters"]["fact_type"] is None
    assert tools_payload["filters"]["fact_group"] == "tools"
    assert "tool" in {row["fact_type"] for row in tools_payload["rows"]}
    assert overview_missing_payload["schema"] == "codex-usage-tracker-diagnostic-overview-v1"
    assert overview_missing_payload["status"] == "missing"
    assert overview_refresh_payload["schema"] == "codex-usage-tracker-diagnostic-overview-v1"
    assert overview_refresh_payload["status"] == "ready"
    assert overview_refresh_payload["overview"]["usage_rows"] == 2
    assert overview_refresh_payload["refreshed"] is True
    assert (
        tool_output_refresh_payload["schema"]
        == "codex-usage-tracker-diagnostic-tool-output-v1"
    )
    assert tool_output_refresh_payload["summary"]["original_token_sum"] == 9
    assert (
        commands_refresh_payload["schema"]
        == "codex-usage-tracker-diagnostic-commands-v1"
    )
    assert commands_refresh_payload["commands"][0]["root"] == "git"
    assert commands_refresh_payload["commands"][0]["children"][0] == {
        "child": "status",
        "count": 1,
    }
    assert (
        git_interactions_refresh_payload["schema"]
        == "codex-usage-tracker-diagnostic-git-interactions-v1"
    )
    assert git_interactions_refresh_payload["summary"]["git_shell_calls"] == 1
    assert git_interactions_refresh_payload["interactions"][0]["operation"] == "status"
    assert (
        file_reads_refresh_payload["schema"]
        == "codex-usage-tracker-diagnostic-file-reads-v1"
    )
    assert file_reads_refresh_payload["summary"]["read_events"] == 0
    assert (
        file_modifications_refresh_payload["schema"]
        == "codex-usage-tracker-diagnostic-file-modifications-v1"
    )
    assert file_modifications_refresh_payload["summary"]["modification_events"] == 1
    assert (
        read_productivity_refresh_payload["schema"]
        == "codex-usage-tracker-diagnostic-read-productivity-v1"
    )
    assert read_productivity_refresh_payload["summary"]["read_events_modified_later"] == 0
    assert (
        concentration_refresh_payload["schema"]
        == "codex-usage-tracker-diagnostic-concentration-v1"
    )
    assert concentration_refresh_payload["summary"]["usage_rows"] == 2
    assert concentration_refresh_payload["metrics"]
    assert (
        guided_summary_refresh_payload["schema"]
        == "codex-usage-tracker-diagnostic-guided-summary-v1"
    )
    assert guided_summary_refresh_payload["summary"]["usage_rows"] == 2
    assert guided_summary_refresh_payload["drivers"]
    assert (
        usage_drain_refresh_payload["schema"]
        == "codex-usage-tracker-diagnostic-usage-drain-v1"
    )
    assert usage_drain_refresh_payload["summary"]["usage_rows"] == 2
    assert "thread_cost_curves" in usage_drain_refresh_payload
    usage_drain_thread = usage_drain_refresh_payload["thread_cost_curves"]["threads"][0]
    assert usage_drain_thread["largest_record_id"]
    assert (
        usage_drain_thread["representative_record_id"]
        == usage_drain_thread["largest_record_id"]
    )
    assert fact_calls_payload["view"] == "fact-calls"
    assert fact_calls_payload["filters"]["privacy_mode"] == "strict"
    assert fact_calls_payload["rows"][0]["cwd"].startswith("[redacted cwd:")
    combined = json.dumps(
        [
            summary_payload,
            facts_payload,
            compactions_payload,
            tools_payload,
            usage_drain_refresh_payload,
            fact_calls_payload,
        ]
    )
    assert "SECRET" not in combined
    assert "/tmp/private-diagnostics" not in json.dumps(fact_calls_payload)


def test_dogfood_agentic_cli_writes_compact_artifacts(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    allowance_path = tmp_path / "allowance.json"
    output_dir = tmp_path / "dogfood"
    pricing_path.write_text(
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

    result = _run_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "--allowance",
        str(allowance_path),
        "--privacy-mode",
        "strict",
        "dogfood-agentic",
        "--codex-home",
        str(codex_home),
        "--output-dir",
        str(output_dir),
        "--evidence-limit",
        "2",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema"] == "codex-usage-tracker-agentic-dogfood-v1"
    assert payload["family_checks"]["old_passed"] is True
    assert payload["family_checks"]["new_passed"] is True
    assert payload["privacy_checks"]["passed"] is True
    assert payload["progress"]["percent_complete"] == 100
    assert payload["cache"]["hypotheses"] is False
    assert payload["cache"]["deep_investigations"] is False
    assert Path(payload["artifacts"]["summary_json_path"]).exists()
    assert Path(payload["artifacts"]["summary_markdown_path"]).exists()
    assert "SECRET" not in result.stdout


def _assert_contract(payload: object) -> None:
    assert validate_json_payload_contract(payload) == []


def _run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codex_usage_tracker", *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )


def _make_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    log_dir = codex_home / "sessions" / "2026" / "05" / "17"
    log_path = log_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Synthetic setup test",
                "updated_at": "2026-05-17T18:58:27Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "SECRET RAW PROMPT"}],
                },
            ),
            _token_event(100, 100),
        ],
    )
    return codex_home


def _make_diagnostics_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    log_dir = codex_home / "sessions" / "2026" / "05" / "17"
    log_path = log_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Synthetic diagnostics test",
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
                    "cwd": "/tmp/private-diagnostics",
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "call_id": "call-git",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "git status SECRET_ARG"}),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "call-git",
                    "output": (
                        "Chunk ID: abc123\n"
                        "Wall time: 0.0000 seconds\n"
                        "Process exited with code 0\n"
                        "Original token count: 9\n"
                        "Output:\n"
                        "SECRET TOOL OUTPUT"
                    ),
                },
            ),
            _entry(
                "event_msg",
                {
                    "type": "patch_apply_end",
                    "changed_paths": ["src/app.py"],
                    "patch": "SECRET PATCH TEXT",
                },
            ),
            _token_event(120, 120),
            _entry(
                "event_msg",
                {
                    "type": "context_compacted",
                    "replacement_history": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {"type": "output_text", "text": "SECRET COMPACTION TEXT"}
                            ],
                        }
                    ],
                },
            ),
            _token_event(220, 100),
        ],
    )
    return codex_home


def _token_event(cumulative_total: int, last_total: int) -> dict[str, object]:
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": cumulative_total - 10,
                    "cached_input_tokens": 20,
                    "output_tokens": 10,
                    "reasoning_output_tokens": 5,
                    "total_tokens": cumulative_total,
                },
                "last_token_usage": {
                    "input_tokens": last_total - 10,
                    "cached_input_tokens": 5,
                    "output_tokens": 10,
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


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[2]
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else src_path
    )
    return env
