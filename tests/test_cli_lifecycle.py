from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from codex_usage_tracker.json_contracts import validate_json_payload_contract
from codex_usage_tracker.store import EVENT_COLUMNS

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
    assert bundle["privacy"]["contains_raw_logs"] is False
    assert bundle["privacy"]["project_metadata"]["mode"] == "strict"
    assert bundle["privacy"]["project_metadata"]["relative_cwd_hidden"] is True
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
    session_payload = json.loads(session.stdout)
    expensive_payload = json.loads(expensive.stdout)
    _assert_contract(refresh_payload)
    _assert_contract(summary_payload)
    _assert_contract(query_payload)
    _assert_contract(recommendations_payload)
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
    repo_root = Path(__file__).resolve().parents[1]
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else src_path
    )
    return env
