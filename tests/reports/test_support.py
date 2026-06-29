from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.reports.support import build_support_bundle, support_bundle_payload
from codex_usage_tracker.store.api import refresh_usage_index

SESSION_ID = "019e3915-5120-7f93-a30f-4bb23669b2a8"
PROMPT_SENTINEL = "SUPPORT_RAW_PROMPT_SENTINEL"
ASSISTANT_SENTINEL = "SUPPORT_RAW_ASSISTANT_SENTINEL"
TOOL_OUTPUT_SENTINEL = "SUPPORT_RAW_TOOL_OUTPUT_SENTINEL"
OPENAI_SECRET = "sk" + "-proj-supportbundleabcdefghijklmnopqrstuvwxyz"
AWS_SECRET = "AKIA" + "IOSFODNN7EXAMPLE"
BEARER_SECRET = "Authorization: " + "Bearer support.bundle.token123456"
RAW_SENTINELS = (
    PROMPT_SENTINEL,
    ASSISTANT_SENTINEL,
    TOOL_OUTPUT_SENTINEL,
    OPENAI_SECRET,
    AWS_SECRET,
    BEARER_SECRET,
)


def test_support_bundle_default_mode_contract_and_secret_safety(tmp_path: Path) -> None:
    fixture = _make_support_fixture(tmp_path)
    output_path = tmp_path / "support.json"

    refresh_usage_index(codex_home=fixture["codex_home"], db_path=fixture["db_path"])
    build_support_bundle(
        output_path=output_path,
        codex_home=fixture["codex_home"],
        db_path=fixture["db_path"],
        pricing_path=fixture["pricing_path"],
        allowance_path=fixture["allowance_path"],
        rate_card_path=fixture["rate_card_path"],
        thresholds_path=fixture["thresholds_path"],
        projects_path=fixture["projects_path"],
    )

    bundle = json.loads(output_path.read_text(encoding="utf-8"))
    bundle_text = json.dumps(bundle)

    assert bundle["bundle_version"] == 1
    assert bundle["privacy"]["contains_raw_logs"] is False
    assert bundle["privacy"]["contains_prompts"] is False
    assert bundle["privacy"]["contains_assistant_messages"] is False
    assert bundle["privacy"]["contains_tool_output"] is False
    assert bundle["privacy"]["project_metadata"]["mode"] == "normal"
    assert bundle["privacy"]["diagnostic_paths_redacted"] is False
    assert bundle["package"]["version"]
    assert bundle["package"]["python"]
    assert bundle["package"]["platform"]
    assert bundle["paths"]["db_path"] == str(fixture["db_path"])
    assert bundle["database"]["exists"] is True
    assert bundle["refresh"]["parsed_events"] == "1"
    assert bundle["pricing"]["loaded"] is True
    assert bundle["allowance"]["window_count"] == 0
    assert "low_cache_ratio" in bundle["thresholds"]["keys"]
    assert bundle["projects"]["tag_group_count"] == 1
    assert bundle["doctor"]["schema"] == "codex-usage-tracker-doctor-v1"
    assert any(check["name"] == "Parser diagnostics" for check in bundle["doctor"]["checks"])

    for sentinel in RAW_SENTINELS:
        assert sentinel not in bundle_text
    assert "[REDACTED_OPENAI_KEY]" in bundle_text
    assert "[REDACTED_AWS_ACCESS_KEY]" in bundle_text
    assert "Authorization: Bearer [REDACTED_BEARER_TOKEN]" in bundle_text


def test_support_bundle_strict_mode_redacts_local_paths_and_doctor_text(
    tmp_path: Path,
) -> None:
    fixture = _make_support_fixture(tmp_path)

    refresh_usage_index(codex_home=fixture["codex_home"], db_path=fixture["db_path"])
    bundle = support_bundle_payload(
        codex_home=fixture["codex_home"],
        db_path=fixture["db_path"],
        pricing_path=fixture["pricing_path"],
        allowance_path=fixture["allowance_path"],
        rate_card_path=fixture["rate_card_path"],
        thresholds_path=fixture["thresholds_path"],
        projects_path=fixture["projects_path"],
        privacy_mode="strict",
    )
    bundle_text = json.dumps(bundle)

    assert bundle["privacy"]["project_metadata"]["mode"] == "strict"
    assert bundle["privacy"]["project_metadata"]["relative_cwd_hidden"] is True
    assert bundle["privacy"]["diagnostic_paths_redacted"] is True
    assert bundle["paths"]["db_path"].startswith("[redacted path:db_path:")
    assert bundle["paths"]["codex_home"].startswith("[redacted path:codex_home:")
    assert "[redacted path:" in bundle_text

    for sentinel in RAW_SENTINELS:
        assert sentinel not in bundle_text
    for raw_path in (
        str(tmp_path),
        str(Path.cwd()),
        str(fixture["codex_home"]),
        str(fixture["cwd"]),
        str(fixture["db_path"]),
        str(fixture["pricing_path"]),
        str(fixture["projects_path"]),
    ):
        assert raw_path not in bundle_text


def _make_support_fixture(tmp_path: Path) -> dict[str, Path]:
    codex_home = tmp_path / ".codex"
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    allowance_path = tmp_path / "allowance.json"
    rate_card_path = tmp_path / "rate-card.json"
    thresholds_path = tmp_path / "thresholds.json"
    projects_path = tmp_path / "projects.json"
    cwd = tmp_path / "support-client-project" / "private" / "workflow"
    cwd.mkdir(parents=True)

    pricing_path.write_text(
        json.dumps(
            {
                "_source": {
                    "name": f"Synthetic {OPENAI_SECRET}",
                    "url": f"https://example.test/{AWS_SECRET}",
                    "fetched_at": BEARER_SECRET,
                },
                "models": {
                    "gpt-5.5": {
                        "input_per_million": 2.0,
                        "cached_input_per_million": 0.5,
                        "output_per_million": 10.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    thresholds_path.write_text(json.dumps({"low_cache_ratio": 0.25}), encoding="utf-8")
    projects_path.write_text(
        json.dumps({"tags": {"support-project": ["private-tag"]}}),
        encoding="utf-8",
    )

    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Synthetic support thread",
                "updated_at": "2026-05-17T19:00:00Z",
            }
        ],
    )
    _write_jsonl(
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "17"
        / f"rollout-2026-05-17T19-00-00-{SESSION_ID}.jsonl",
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry(
                "turn_context",
                {
                    "turn_id": "support-turn",
                    "model": "gpt-5.5",
                    "cwd": str(cwd),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"{PROMPT_SENTINEL} {OPENAI_SECRET}",
                        }
                    ],
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": ASSISTANT_SENTINEL}],
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call_output",
                    "name": "shell",
                    "output": f"{TOOL_OUTPUT_SENTINEL} {AWS_SECRET}",
                },
            ),
            _entry(
                "event_msg",
                {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 90,
                            "cached_input_tokens": 20,
                            "output_tokens": 10,
                            "reasoning_output_tokens": 5,
                            "total_tokens": 100,
                        },
                        "last_token_usage": {
                            "input_tokens": 90,
                            "cached_input_tokens": 20,
                            "output_tokens": 10,
                            "reasoning_output_tokens": 5,
                            "total_tokens": 100,
                        },
                    },
                },
            ),
        ],
    )
    return {
        "codex_home": codex_home,
        "db_path": db_path,
        "pricing_path": pricing_path,
        "allowance_path": allowance_path,
        "rate_card_path": rate_card_path,
        "thresholds_path": thresholds_path,
        "projects_path": projects_path,
        "cwd": cwd,
    }


def _entry(entry_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": "2026-05-17T19:00:00.000Z",
        "type": entry_type,
        "payload": payload,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
