from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

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
