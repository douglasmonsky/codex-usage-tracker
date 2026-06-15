from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from codex_usage_tracker.json_contracts import validate_json_payload_contract
from codex_usage_tracker.models import UsageEvent
from codex_usage_tracker.pricing import PricingUpdateResult

SESSION_ID = "019e374d-c19f-7da3-a44f-8de043a7a64e"
SECOND_SESSION_ID = "019e37d4-c1f1-71aa-b154-2d5d837af92c"
AUTO_REVIEW_SESSION_ID = "019e37d5-01fd-71df-87f4-ae3e8d60df7a"
ARCHIVED_SESSION_ID = "019e37d5-bb36-76ba-aa33-ed0beaf4f9ce"


def _extract_js_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    brace = source.index("{", start)
    depth = 0
    for offset, char in enumerate(source[brace:], start=brace):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise AssertionError(f"could not extract function {name}")


def _make_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    log_dir = codex_home / "sessions" / "2026" / "05" / "17"
    log_path = log_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    second_log_path = log_dir / f"rollout-2026-05-17T16-24-11-{SECOND_SESSION_ID}.jsonl"
    auto_review_log_path = log_dir / f"rollout-2026-05-17T16-31-02-{AUTO_REVIEW_SESSION_ID}.jsonl"
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Add Codex token tracking",
                "updated_at": "2026-05-17T18:58:27Z",
            },
            {
                "id": SECOND_SESSION_ID,
                "updated_at": "2026-05-17T20:24:11Z",
            },
            {
                "id": AUTO_REVIEW_SESSION_ID,
                "updated_at": "2026-05-17T20:31:02Z",
            },
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
                    "content": [
                        {
                            "type": "input_text",
                            "text": "# AGENTS.md instructions for /tmp/codex-usage-tracker\n\n"
                            "<INSTRUCTIONS>\nKeep local logs private.\n</INSTRUCTIONS>",
                        }
                    ],
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
                            "text": "SECRET RAW PROMPT "
                            + "sk"
                            + "-proj-abcdefghijklmnopqrstuvwxyz123456 "
                            + "AKIAIOSFODNN7EXAMPLE "
                            + "Authorization: Bearer abc.def.ghi123456789 "
                            + "xoxb-123456789012-123456789012-abcdefghijklmnopqrstuvwx "
                            + "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                            + "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkNvZGV4In0."
                            + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c "
                            + "client_secret=super-secret-value "
                            + "-----BEGIN OPENSSH PRIVATE KEY-----abc123-----END OPENSSH PRIVATE KEY-----",
                        }
                    ],
                },
            ),
            _entry(
                "compacted",
                {
                    "message": "",
                    "replacement_history": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "COMPACTED REPLACEMENT SUMMARY "
                                    + "sk"
                                    + "-proj-compactedsecret1234567890",
                                }
                            ],
                        },
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Retained compacted work plan.",
                                }
                            ],
                        },
                    ],
                },
            ),
            _entry(
                "event_msg",
                {
                    "type": "context_compacted",
                    "message": "Context compacted by Codex.",
                    "goal": "LOCAL_GOAL_SENTINEL_DO_NOT_RETURN "
                    + "sk"
                    + "-proj-goalsecret1234567890",
                    "replacement_history": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "EVENT MSG COMPACTION SUMMARY",
                                }
                            ],
                        }
                    ],
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "Reasoning summary"}],
                    "encrypted_content": "ENCRYPTED_STATE_SENTINEL_DO_NOT_RETURN "
                    + "sk"
                    + "-proj-encryptedsecret1234567890",
                },
            ),
            _token_event(100, 100),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "AFTER SELECTED CALL"}],
                },
            ),
            _token_event(300, 200),
        ],
    )
    _write_jsonl(
        second_log_path,
        [
            _entry(
                "session_meta",
                {
                    "id": SECOND_SESSION_ID,
                    "thread_source": "subagent",
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "parent_thread_id": SESSION_ID,
                                "agent_nickname": "Verifier",
                                "agent_role": "test_runner",
                            }
                        }
                    },
                },
            ),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-c",
                    "model": "gpt-5.5",
                    "effort": "medium",
                    "cwd": "/tmp/codex-usage-tracker",
                },
            ),
            _token_event(50, 50),
        ],
    )
    _write_jsonl(
        auto_review_log_path,
        [
            _entry(
                "session_meta",
                {
                    "id": AUTO_REVIEW_SESSION_ID,
                    "thread_source": "subagent",
                    "source": {"subagent": {"other": "guardian"}},
                },
            ),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-d",
                    "model": "codex-auto-review",
                    "effort": "low",
                    "cwd": "/tmp/codex-usage-tracker",
                },
            ),
            _token_event(50, 50),
        ],
    )
    return codex_home


def _write_archived_log(codex_home: Path) -> Path:
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
            _token_event(900, 900),
        ],
    )
    return archived_log_path


def _usage_event(
    *,
    record_id: str,
    session_id: str,
    thread_key: str,
    event_timestamp: str,
    cumulative_total_tokens: int,
) -> UsageEvent:
    return UsageEvent(
        record_id=record_id,
        session_id=session_id,
        thread_name=thread_key.removeprefix("thread:"),
        session_updated_at="2026-05-17T18:58:27Z",
        event_timestamp=event_timestamp,
        source_file=f"/tmp/synthetic/{record_id}.jsonl",
        line_number=1,
        turn_id=f"turn-{record_id}",
        turn_timestamp=event_timestamp,
        cwd="/tmp/project",
        model="gpt-5.5",
        effort="high",
        current_date="2026-05-17",
        timezone="UTC",
        call_initiator="user",
        call_initiator_reason="user_message",
        call_initiator_confidence="high",
        is_archived=0,
        thread_key=thread_key,
        thread_call_index=None,
        previous_record_id=None,
        next_record_id=None,
        thread_source="user",
        subagent_type=None,
        agent_role=None,
        agent_nickname=None,
        parent_session_id=None,
        parent_thread_name=None,
        parent_session_updated_at=None,
        model_context_window=200000,
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=10,
        reasoning_output_tokens=5,
        total_tokens=110,
        cumulative_input_tokens=cumulative_total_tokens - 10,
        cumulative_cached_input_tokens=20,
        cumulative_output_tokens=10,
        cumulative_reasoning_output_tokens=5,
        cumulative_total_tokens=cumulative_total_tokens,
    )


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


def _assert_contract(payload: object) -> None:
    assert validate_json_payload_contract(payload) == []


def _read_json(url: str, headers: dict[str, str] | None = None) -> dict[str, object]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - local test server only
        return json.loads(response.read().decode("utf-8"))


def _http_error_json(url: str, headers: dict[str, str] | None = None) -> dict[str, object]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        urllib.request.urlopen(request, timeout=5)  # noqa: S310 - local test server only
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "payload": json.loads(exc.read().decode("utf-8")),
        }
    raise AssertionError("expected HTTPError")


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
            "rate_limits": {
                "plan_type": "pro",
                "limit_id": "codex",
                "primary": {
                    "used_percent": 2.0,
                    "window_minutes": 300,
                    "resets_at": 1781562696,
                },
                "secondary": {
                    "used_percent": 29.0,
                    "window_minutes": 10080,
                    "resets_at": 1781887793,
                },
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
