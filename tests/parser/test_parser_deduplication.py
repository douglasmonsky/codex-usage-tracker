from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.parser.api import parse_usage_events_from_file
from tests.parser.test_parser import _entry, _token_event, _write_jsonl


def test_parser_assigns_canonical_identity_to_copied_usage(tmp_path: Path) -> None:
    original_id = "019e374d-c19f-7da3-a44f-8de043a7a64e"
    clone_id = "019e374d-c19f-7da3-a44f-8de043a7a64f"
    original_path = tmp_path / f"rollout-2026-05-17T14-58-23-{original_id}.jsonl"
    clone_path = tmp_path / f"rollout-2026-05-17T14-58-23-{clone_id}.jsonl"
    copied = _token_event(100, 100)
    copied["event_id"] = "evt-123"
    new_event = _token_event(150, 50)
    new_event["timestamp"] = "2026-05-17T18:59:27.000Z"
    _write_jsonl(original_path, [_entry("session_meta", {"id": original_id}), copied])
    _write_jsonl(clone_path, [_entry("session_meta", {"id": clone_id}), copied, new_event])

    [original] = parse_usage_events_from_file(original_path)
    copied_clone, new_clone = parse_usage_events_from_file(clone_path)

    assert original.record_id != copied_clone.record_id
    assert original.usage_fingerprint == copied_clone.usage_fingerprint
    assert original.canonical_record_id == copied_clone.canonical_record_id
    assert original.usage_fingerprint != new_clone.usage_fingerprint
    assert original.upstream_usage_id == "envelope.event_id:evt-123"


def test_parser_matches_clone_copy_with_rewritten_timestamps(tmp_path: Path) -> None:
    original_id = "019e374d-c19f-7da3-a44f-8de043a7a64e"
    clone_id = "019e374d-c19f-7da3-a44f-8de043a7a64f"
    original_path = tmp_path / f"rollout-original-{original_id}.jsonl"
    clone_path = tmp_path / f"rollout-clone-{clone_id}.jsonl"
    original_turn = _entry(
        "turn_context", {"turn_id": "turn-stable", "model": "gpt-5.5", "effort": "high"}
    )
    clone_turn = {**original_turn, "timestamp": "2026-05-18T18:58:27.000Z"}
    original_usage = _token_event(100, 100)
    clone_usage = {**original_usage, "timestamp": "2026-05-18T18:58:28.000Z"}
    _write_jsonl(
        original_path,
        [_entry("session_meta", {"id": original_id}), original_turn, original_usage],
    )
    _write_jsonl(
        clone_path,
        [_entry("session_meta", {"id": clone_id}), clone_turn, clone_usage],
    )

    [original] = parse_usage_events_from_file(original_path)
    [copied] = parse_usage_events_from_file(clone_path)

    assert original.event_timestamp != copied.event_timestamp
    assert original.turn_timestamp != copied.turn_timestamp
    assert original.turn_id == copied.turn_id == "turn-stable"
    assert original.usage_fingerprint == copied.usage_fingerprint
