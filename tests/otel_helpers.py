from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


def completion_attributes(
    *,
    conversation_id: str = "synthetic-conversation",
    tokens: tuple[int, int, int, int] = (120, 40, 30, 10),
    model: str = "gpt-5.6-sol",
    effort: str = "high",
    service_tier: str | None = "priority",
    app_version: str = "0.143.0",
) -> dict[str, object]:
    input_tokens, cached_tokens, output_tokens, reasoning_tokens = tokens
    values: dict[str, object] = {
        "event.name": "codex.sse_event",
        "event.kind": "response.completed",
        "conversation.id": conversation_id,
        "input_token_count": input_tokens,
        "cached_token_count": cached_tokens,
        "output_token_count": output_tokens,
        "reasoning_token_count": reasoning_tokens,
        "model": model,
        "model_reasoning_effort": effort,
        "app.version": app_version,
    }
    if service_tier is not None:
        values["service_tier"] = service_tier
    return values


def _otlp_scalar(value: object) -> dict[str, object]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def synthetic_otlp_line(*, attributes: dict[str, object], body: str = "synthetic body") -> str:
    encoded = [
        {"key": key, "value": _otlp_scalar(value)} for key, value in attributes.items()
    ]
    return json.dumps(
        {
            "resourceLogs": [
                {
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {
                                    "timeUnixNano": "1784160000000000000",
                                    "body": {"stringValue": body},
                                    "attributes": encoded,
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    )


def synthetic_fast_completion(conversation_id: str, input_tokens: int) -> str:
    return synthetic_otlp_line(
        attributes=completion_attributes(
            conversation_id=conversation_id,
            tokens=(input_tokens, 0, 20, 5),
            service_tier="priority",
        )
    )


def synthetic_standard_completion(conversation_id: str, input_tokens: int) -> str:
    return synthetic_otlp_line(
        attributes=completion_attributes(
            conversation_id=conversation_id,
            tokens=(input_tokens, 0, 20, 5),
            service_tier=None,
        )
    )


def synthetic_usage_event(
    record_id: str,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
    *,
    canonical: str = "canonical-a",
    model: str = "gpt-5.6-sol",
    effort: str = "high",
    service_tier: str | None = None,
    fast: int | None = None,
    duplicate: int = 0,
) -> UsageEvent:
    input_tokens, cached_tokens, output_tokens, reasoning_tokens = tokens
    total_tokens = input_tokens + output_tokens
    return UsageEvent(
        record_id=record_id,
        session_id=conversation_id,
        thread_name="Synthetic thread",
        session_updated_at="2026-07-16T00:00:00Z",
        event_timestamp="2026-07-16T00:00:00Z",
        source_file="/synthetic/session.jsonl",
        line_number=1,
        turn_id="synthetic-turn",
        turn_timestamp="2026-07-16T00:00:00Z",
        cwd="/synthetic/project",
        model=model,
        effort=effort,
        current_date="2026-07-16",
        timezone="UTC",
        call_initiator="user",
        call_initiator_reason="user_message",
        call_initiator_confidence="high",
        is_archived=0,
        thread_key="thread:Synthetic",
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
        model_context_window=258_400,
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        cumulative_input_tokens=input_tokens,
        cumulative_cached_input_tokens=cached_tokens,
        cumulative_output_tokens=output_tokens,
        cumulative_reasoning_output_tokens=reasoning_tokens,
        cumulative_total_tokens=total_tokens,
        usage_fingerprint=f"synthetic-fingerprint-{canonical}",
        canonical_record_id=canonical,
        is_duplicate=duplicate,
        duplicate_reason="copied_usage_fingerprint" if duplicate else None,
        service_tier=service_tier
        or ("fast" if fast == 1 else "standard" if fast == 0 else None),
        fast=fast,
        service_tier_source="otel_response_completed" if fast is not None else None,
        service_tier_confidence="exact" if fast is not None else None,
    )


def write_usage_session(
    tmp_path: Path,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
) -> Path:
    input_tokens, cached_tokens, output_tokens, reasoning_tokens = tokens
    total_tokens = input_tokens + output_tokens
    codex_home = tmp_path / "codex"
    log_path = codex_home / "sessions" / "2026" / "07" / "16" / "synthetic.jsonl"
    rows = [
        {
            "timestamp": "2026-07-16T00:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": conversation_id},
        },
        {
            "timestamp": "2026-07-16T00:00:01.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": input_tokens,
                        "cached_input_tokens": cached_tokens,
                        "output_tokens": output_tokens,
                        "reasoning_output_tokens": reasoning_tokens,
                        "total_tokens": total_tokens,
                    },
                    "last_token_usage": {
                        "input_tokens": input_tokens,
                        "cached_input_tokens": cached_tokens,
                        "output_tokens": output_tokens,
                        "reasoning_output_tokens": reasoning_tokens,
                        "total_tokens": total_tokens,
                    },
                    "model_context_window": 258_400,
                },
            },
        },
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return codex_home


def write_otel_directory(
    tmp_path: Path,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
) -> Path:
    directory = tmp_path / "otel"
    write_lines(
        directory / "codex-completions.jsonl",
        [
            synthetic_otlp_line(
                attributes=completion_attributes(
                    conversation_id=conversation_id,
                    tokens=tokens,
                    service_tier="priority",
                )
            )
        ],
    )
    return directory


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def append_text(path: Path, value: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(value)


@contextmanager
def initialized_connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "usage.sqlite3") as conn:
        init_db(conn)
        yield conn
