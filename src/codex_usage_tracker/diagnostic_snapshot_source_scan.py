"""Low-level diagnostic source-log scan recorders."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from codex_usage_tracker.diagnostic_snapshot_events import (
    allocate_token_count,
    command_root_and_child,
    git_interaction_from_command,
    is_shell_tool,
    optional_str,
    original_output_count,
    read_path_refs_from_command,
    read_reader,
    safe_label,
    shell_command_from_payload,
    simple_rows,
    unique_path_rows,
)


def record_function_call(
    payload: dict[str, Any],
    *,
    order: int,
    counters: dict[str, Any],
    meta: Counter[str],
    call_names: dict[str, str],
    call_roots: dict[str, str],
    call_git_interactions: dict[str, tuple[str, str, str, str]],
    call_read_events: dict[str, list[int]],
    source_read_events: list[int],
) -> None:
    call_id = optional_str(payload.get("call_id") or payload.get("id"))
    function_name = safe_label(payload.get("name")) or "unknown_function"
    counters["function_calls"][function_name] += 1
    if call_id:
        call_names[call_id] = function_name
    command = shell_command_from_payload(payload, function_name=function_name)
    if command is None:
        if is_shell_tool(function_name):
            meta["missing_command"] += 1
        return
    root, child = command_root_and_child(command)
    counters["command_calls"][root] += 1
    counters["command_children"].setdefault(root, Counter())[child] += 1
    if call_id:
        call_roots[call_id] = root
    interaction = git_interaction_from_command(command, root=root)
    if interaction is not None:
        interaction_key = (
            interaction["root"],
            interaction["operation"],
            interaction["category"],
            interaction["mutability"],
        )
        counters["git_interaction_calls"][interaction_key] += 1
        counters["git_interactions_by_category"][interaction["category"]] += 1
        counters["git_interactions_by_mutability"][interaction["mutability"]] += 1
        counters["git_interactions_by_root"][interaction["root"]] += 1
        if call_id:
            call_git_interactions[call_id] = interaction_key
    read_refs = read_path_refs_from_command(command, root=root)
    if read_refs:
        counters["read_command_count"] += 1
        read_event_indexes = record_read_refs(
            read_refs,
            root=root,
            order=order,
            counters=counters,
            source_read_events=source_read_events,
        )
        if call_id:
            call_read_events[call_id] = read_event_indexes


def record_read_refs(
    read_refs: list[dict[str, str]],
    *,
    root: str,
    order: int,
    counters: dict[str, Any],
    source_read_events: list[int],
) -> list[int]:
    indexes: list[int] = []
    reader = read_reader(root)
    for path_ref in read_refs:
        path_key = path_ref["path_key"]
        counters["read_path_refs"][path_key] = path_ref
        event_index = len(counters["read_events"])
        counters["read_events"].append(
            {
                "reader": reader,
                "root": root,
                "path_key": path_key,
                "path_label": path_ref["path_label"],
                "path_hash": path_ref["path_hash"],
                "order": order,
                "modified_later": False,
            }
        )
        source_read_events.append(event_index)
        indexes.append(event_index)
        counters["read_events_by_reader"][reader] += 1
        counters["read_events_by_path"][path_key] += 1
    return indexes


def record_file_modification_refs(
    path_refs: list[dict[str, str]],
    *,
    counters: dict[str, Any],
    event_kind: str,
) -> None:
    counters["file_modification_events"] += 1
    event_paths: list[dict[str, str]] = []
    for path_ref in path_refs:
        path_key = path_ref["path_key"]
        path_label = path_ref["path_label"]
        counters["file_modification_path_refs"][path_key] = path_ref
        counters["file_modification_path_events"][path_key] += 1
        counters["file_modification_extensions"][_extension_label(path_label)] += 1
        event_paths.append({"path_label": path_label, "path_hash": path_ref["path_hash"]})
    counters["largest_file_modification_events"].append(
        {
            "event_kind": event_kind,
            "modified_path_count": len(path_refs),
            "paths": unique_path_rows(event_paths),
        }
    )


def record_function_output(
    payload: dict[str, Any],
    *,
    counters: dict[str, Any],
    call_names: dict[str, str],
    call_roots: dict[str, str],
    call_git_interactions: dict[str, tuple[str, str, str, str]],
    call_read_events: dict[str, list[int]],
) -> None:
    call_id = optional_str(payload.get("call_id"))
    function_name = call_names.get(call_id or "", "unknown_function")
    counters["function_outputs"][function_name] += 1
    output = payload.get("output")
    count = original_output_count(output)
    read_indexes = call_read_events.get(call_id or "", [])
    git_interaction = call_git_interactions.get(call_id or "")
    if count is None:
        record_missing_output_count(
            output,
            counters=counters,
            function_name=function_name,
            root=call_roots.get(call_id or ""),
            git_interaction=git_interaction,
            read_indexes=read_indexes,
        )
        return
    record_output_count(
        int(count),
        counters=counters,
        function_name=function_name,
        root=call_roots.get(call_id or ""),
        git_interaction=git_interaction,
        read_indexes=read_indexes,
    )


def record_missing_output_count(
    output: object,
    *,
    counters: dict[str, Any],
    function_name: str,
    root: str | None,
    git_interaction: tuple[str, str, str, str] | None,
    read_indexes: list[int],
) -> None:
    counters["output_missing_count"][function_name] += 1
    missing_reason = "string_no_header" if isinstance(output, str) else "non_string_output"
    counters["missing_reasons"][missing_reason] += 1
    if root:
        counters["command_missing_count"][root] += 1
    if git_interaction:
        counters["git_interaction_missing_count"][git_interaction] += 1
    for event_index in read_indexes:
        reader = str(counters["read_events"][event_index]["reader"])
        counters["read_events_missing_count_by_reader"][reader] += 1


def record_output_count(
    count: int,
    *,
    counters: dict[str, Any],
    function_name: str,
    root: str | None,
    git_interaction: tuple[str, str, str, str] | None,
    read_indexes: list[int],
) -> None:
    counters["output_with_count"][function_name] += 1
    counters["output_token_sum"][function_name] += count
    if root:
        counters["command_with_count"][root] += 1
        counters["command_token_sum"][root] += count
    if git_interaction:
        counters["git_interaction_with_count"][git_interaction] += 1
        counters["git_interaction_token_sum"][git_interaction] += count
    if not read_indexes:
        return
    paths: list[dict[str, str]] = []
    readers: Counter[str] = Counter()
    allocations = allocate_token_count(count, len(read_indexes))
    for event_index, allocated in zip(read_indexes, allocations, strict=True):
        event = counters["read_events"][event_index]
        reader = str(event["reader"])
        path_key = str(event["path_key"])
        counters["read_events_with_count_by_reader"][reader] += 1
        counters["read_tokens_by_reader"][reader] += allocated
        counters["read_tokens_by_path"][path_key] += allocated
        readers[reader] += 1
        paths.append({"path_label": str(event["path_label"]), "path_hash": str(event["path_hash"])})
    counters["largest_read_commands"].append(
        {
            "root": root or "unknown_command",
            "read_event_count": len(read_indexes),
            "original_token_count": int(count),
            "readers": simple_rows(readers, key_name="reader"),
            "paths": unique_path_rows(paths),
        }
    )


def mark_later_modifications(
    *,
    counters: dict[str, Any],
    source_read_events: list[int],
    modified_orders_by_path: dict[str, list[int]],
) -> None:
    for event_index in source_read_events:
        event = counters["read_events"][event_index]
        path_key = str(event["path_key"])
        if any(order > int(event["order"]) for order in modified_orders_by_path.get(path_key, [])):
            event["modified_later"] = True
            counters["read_modified_by_reader"][str(event["reader"])] += 1
            counters["read_modified_by_path"][path_key] += 1


def _extension_label(path_label: str) -> str:
    suffix = Path(path_label).suffix.lower()
    return suffix if suffix else "<none>"
