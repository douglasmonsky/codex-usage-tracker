"""Row shaping helpers for diagnostic snapshot reports."""

from __future__ import annotations

from collections import Counter
from typing import Any

from codex_usage_tracker.diagnostic_snapshot_events import ratio, simple_rows


def function_rows(
    *,
    function_calls: Counter[str],
    function_outputs: Counter[str],
    output_with_count: Counter[str],
    output_missing_count: Counter[str],
    output_token_sum: Counter[str],
) -> list[dict[str, Any]]:
    names = set(function_calls) | set(function_outputs) | set(output_with_count) | set(output_token_sum)
    rows = [
        {
            "function": name,
            "calls": int(function_calls[name]),
            "outputs": int(function_outputs[name]),
            "with_original_token_count": int(output_with_count[name]),
            "missing_original_token_count": int(output_missing_count[name]),
            "original_token_sum": int(output_token_sum[name]),
        }
        for name in names
    ]
    return sorted(rows, key=lambda row: (-int(row["original_token_sum"]), -int(row["calls"]), row["function"]))


def command_output_rows(
    *,
    command_calls: Counter[str],
    command_with_count: Counter[str],
    command_missing_count: Counter[str],
    command_token_sum: Counter[str],
) -> list[dict[str, Any]]:
    rows = [
        {
            "root": root,
            "calls": int(command_calls[root]),
            "with_original_token_count": int(command_with_count[root]),
            "missing_original_token_count": int(command_missing_count[root]),
            "original_token_sum": int(command_token_sum[root]),
        }
        for root in set(command_calls) | set(command_token_sum)
    ]
    return sorted(rows, key=lambda row: (-int(row["original_token_sum"]), -int(row["calls"]), row["root"]))


def command_rows(
    *,
    command_calls: Counter[str],
    command_children: dict[str, Counter[str]],
) -> list[dict[str, Any]]:
    rows = []
    for root, total in command_calls.items():
        children = simple_rows(command_children.get(root, Counter()), key_name="child")
        rows.append({"root": root, "total": int(total), "children": children[:25]})
    return sorted(rows, key=lambda row: (-int(row["total"]), row["root"]))


def read_reader_rows(
    *,
    read_events_by_reader: Counter[str],
    read_events_with_count_by_reader: Counter[str],
    read_events_missing_count_by_reader: Counter[str],
    read_tokens_by_reader: Counter[str],
) -> list[dict[str, Any]]:
    rows = [
        {
            "reader": reader,
            "read_events": int(read_events_by_reader[reader]),
            "events_with_output_count": int(read_events_with_count_by_reader[reader]),
            "events_missing_output_count": int(read_events_missing_count_by_reader[reader]),
            "allocated_output_token_sum": int(read_tokens_by_reader[reader]),
        }
        for reader in set(read_events_by_reader) | set(read_tokens_by_reader)
    ]
    return sorted(
        rows,
        key=lambda row: (-int(row["allocated_output_token_sum"]), -int(row["read_events"]), row["reader"]),
    )


def read_path_rows(
    *,
    read_path_refs: dict[str, dict[str, str]],
    read_events_by_path: Counter[str],
    read_tokens_by_path: Counter[str],
) -> list[dict[str, Any]]:
    rows = [
        {
            "path_label": read_path_refs[path_key]["path_label"],
            "path_hash": read_path_refs[path_key]["path_hash"],
            "read_events": int(read_events_by_path[path_key]),
            "allocated_output_token_sum": int(read_tokens_by_path[path_key]),
        }
        for path_key in set(read_events_by_path) | set(read_tokens_by_path)
        if path_key in read_path_refs
    ]
    return sorted(
        rows,
        key=lambda row: (
            -int(row["allocated_output_token_sum"]),
            -int(row["read_events"]),
            row["path_label"],
            row["path_hash"],
        ),
    )[:50]


def largest_read_command_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -int(row["original_token_count"]),
            -int(row["read_event_count"]),
            row["root"],
        ),
    )[:25]


def read_productivity_reader_rows(
    *,
    read_events_by_reader: Counter[str],
    read_modified_by_reader: Counter[str],
) -> list[dict[str, Any]]:
    rows = [
        {
            "reader": reader,
            "read_events": int(read_events_by_reader[reader]),
            "read_events_modified_later": int(read_modified_by_reader[reader]),
            "read_events_modified_later_pct": ratio(
                int(read_modified_by_reader[reader]),
                int(read_events_by_reader[reader]),
            ),
        }
        for reader in read_events_by_reader
    ]
    return sorted(
        rows,
        key=lambda row: (
            -int(row["read_events_modified_later"]),
            -int(row["read_events"]),
            row["reader"],
        ),
    )


def read_productivity_path_rows(
    *,
    read_path_refs: dict[str, dict[str, str]],
    read_events_by_path: Counter[str],
    read_modified_by_path: Counter[str],
) -> list[dict[str, Any]]:
    rows = [
        {
            "path_label": read_path_refs[path_key]["path_label"],
            "path_hash": read_path_refs[path_key]["path_hash"],
            "read_events": int(read_events_by_path[path_key]),
            "read_events_modified_later": int(read_modified_by_path[path_key]),
            "read_events_modified_later_pct": ratio(
                int(read_modified_by_path[path_key]),
                int(read_events_by_path[path_key]),
            ),
        }
        for path_key in read_modified_by_path
        if path_key in read_path_refs
    ]
    return sorted(
        rows,
        key=lambda row: (
            -int(row["read_events_modified_later"]),
            -int(row["read_events"]),
            row["path_label"],
            row["path_hash"],
        ),
    )[:50]
