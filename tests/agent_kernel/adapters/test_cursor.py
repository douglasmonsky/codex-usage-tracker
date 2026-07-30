from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.cursor import (
    build_cursor,
    classify_cursor,
    iter_complete_records,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.discovery import (
    discover_inventory,
    select_sources,
)
from codex_usage_tracker.agent_kernel.adapters.contracts import CursorOutcome


def _selected_source(root: Path):
    plans = select_sources(discover_inventory(root), max_bytes=1 << 20)
    return next(plan for plan in plans if plan.inventory.selected)


def test_partial_final_line_never_advances_complete_record_cursor(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    source.write_bytes(b'{"complete":true}\n{"partial":')
    plan = _selected_source(tmp_path)
    records = list(iter_complete_records(source))
    assert len(records) == 1
    cursor = build_cursor(
        source,
        inventory=plan.inventory,
        byte_offset=records[0].byte_end,
        record_ordinal=1,
        latest_source_order=0,
        parser_version="parser.v1",
        adapter_version="adapter.v1",
    )
    source.write_bytes(source.read_bytes() + b"false}\n")
    current = _selected_source(tmp_path)
    classification = classify_cursor(
        source,
        inventory=current.inventory,
        cursor=cursor,
        parser_version="parser.v1",
        adapter_version="adapter.v1",
    )
    assert classification.outcome is CursorOutcome.APPEND_SAFE
    assert list(iter_complete_records(source, start_offset=cursor.byte_offset, start_ordinal=1))


def test_cursor_rejects_truncation_and_prefix_replacement(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    source.write_bytes(b"one\ntwo\n")
    plan = _selected_source(tmp_path)
    cursor = build_cursor(
        source,
        inventory=plan.inventory,
        byte_offset=4,
        record_ordinal=1,
        latest_source_order=1,
        parser_version="parser.v1",
        adapter_version="adapter.v1",
    )
    source.write_bytes(b"one")
    truncated = classify_cursor(
        source,
        inventory=_selected_source(tmp_path).inventory,
        cursor=cursor,
        parser_version="parser.v1",
        adapter_version="adapter.v1",
    )
    assert truncated.outcome is CursorOutcome.TRUNCATED
    source.write_bytes(b"eno\ntwo\n")
    replaced = classify_cursor(
        source,
        inventory=_selected_source(tmp_path).inventory,
        cursor=cursor,
        parser_version="parser.v1",
        adapter_version="adapter.v1",
    )
    assert replaced.outcome is CursorOutcome.REPLACED


def test_manifestation_keys_remain_stable_when_a_path_is_inserted(tmp_path: Path) -> None:
    first = tmp_path / "source.jsonl"
    first.write_bytes(b'{"type":"session_start","payload":{"session_id":"s"}}\n')
    before = discover_inventory(tmp_path)
    before_key = before[0].inventory.manifestation_key
    (tmp_path / "aaa.jsonl").write_bytes(first.read_bytes())
    after = discover_inventory(tmp_path)
    by_path = {plan.inventory.technical_path_key: plan.inventory for plan in after}
    assert by_path["source.jsonl"].manifestation_key == before_key


def test_file_budget_is_explicitly_deferred(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"source-{index}.jsonl").write_bytes(b"{}\n")
    plans = discover_inventory(tmp_path, max_files=2)
    assert len(plans) == 3
    assert plans[-1].inventory.state.value == "deferred"
    assert plans[-1].inventory.deferred_reason == "file_budget"
