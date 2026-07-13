from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.parser.api import parse_usage_events_from_file_with_state

SESSION_ID = "019e374d-c19f-7da3-a44f-8de043a7a64e"


def test_parser_observer_receives_decoded_entries_and_emitted_usage_events(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    entries = [
        _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
        _entry(
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "observer sentinel"}],
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
                    "model_context_window": 258400,
                },
            },
        ),
    ]
    log_path.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )
    observations: list[tuple[object, int, str | None]] = []

    parse_usage_events_from_file_with_state(
        log_path,
        entry_observer=lambda envelope, _payload, line_number, event: observations.append(
            (envelope.get("type"), line_number, event.record_id if event else None)
        ),
    )

    assert [observation[:2] for observation in observations] == [
        ("turn_context", 1),
        ("response_item", 2),
        ("event_msg", 3),
    ]
    assert observations[-1][2] is not None


def _entry(entry_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": "2026-05-17T18:58:27Z",
        "type": entry_type,
        "payload": payload,
    }
