from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from codex_usage_tracker.kernel.discovery import observe_source, plan_source
from codex_usage_tracker.kernel.parser import parse_jsonl


def test_parser_emits_only_structural_facts_and_never_raw_content(
    tmp_path: Path,
) -> None:
    sentinel = "PRIVATE_SYNTHETIC_SENTINEL"
    source = tmp_path / "sessions" / "rollout-synthetic.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:01Z","type":"response_item",'
        '"payload":{"type":"function_call","name":"functions.exec_command",'
        '"arguments":"'
        + sentinel
        + '"}}\n'
        '{"timestamp":"2026-01-01T00:00:02Z","type":"synthetic_unknown",'
        '"payload":{"private":"'
        + sentinel
        + '"}}\n',
        encoding="utf-8",
    )
    plan = plan_source(observe_source(source), None)
    assert plan is not None

    parsed = parse_jsonl(plan)

    assert parsed.unsupported_shape_count == 1
    assert sentinel not in repr(asdict(parsed))
    assert str(source) not in repr(asdict(parsed))
