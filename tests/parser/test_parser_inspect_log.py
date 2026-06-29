from pathlib import Path

from codex_usage_tracker.parser.api import inspect_log
from tests.store_dashboard_helpers import _entry, _token_event, _write_jsonl

SESSION_ID = "019e374d-c19f-7da3-a44f-8de043a7a64e"


def test_inspect_log_reports_aggregate_event_rows(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _token_event(150, 50),
        ],
    )

    payload = inspect_log(log_path)
    event_row = payload["events"][0]

    assert payload["event_count"] == 1
    assert {
        key: event_row[key]
        for key in (
            "turn_id",
            "model",
            "total_tokens",
            "cumulative_total_tokens",
        )
    } == {
        "turn_id": "turn-a",
        "model": "gpt-5.5",
        "total_tokens": 50,
        "cumulative_total_tokens": 150,
    }
