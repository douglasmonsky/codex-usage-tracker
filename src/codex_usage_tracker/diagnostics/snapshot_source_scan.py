"""Low-level diagnostic source-log scan recorders."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from codex_usage_tracker.diagnostics.snapshot_events import (
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
    call_record_ids: dict[str, str],
    source_read_events: list[int],
    representative_record_id: str | None,
) -> None:
    call_id, function_name = _record_function_identity(
        payload,
        counters=counters,
        call_names=call_names,
    )
    command = shell_command_from_payload(payload, function_name=function_name)
    if command is None:
        _record_missing_shell_command(function_name, meta=meta)
        return

    root = _record_shell_command(command, counters=counters)
    if call_id:
        call_roots[call_id] = root
        if representative_record_id:
            call_record_ids[call_id] = representative_record_id
    _set_representative_record_id(counters["function_record_ids"], function_name, representative_record_id)
    _set_representative_record_id(counters["command_record_ids"], root, representative_record_id)
    _record_git_command_interaction(
        command,
        root=root,
        call_id=call_id,
        counters=counters,
        call_git_interactions=call_git_interactions,
        representative_record_id=representative_record_id,
    )
    _record_read_command(
        command,
        root=root,
        order=order,
        counters=counters,
        call_id=call_id,
        call_read_events=call_read_events,
        source_read_events=source_read_events,
        representative_record_id=representative_record_id,
    )


def _record_function_identity(
    payload: dict[str, Any],
    *,
    counters: dict[str, Any],
    call_names: dict[str, str],
) -> tuple[str | None, str]:
    call_id = optional_str(payload.get("call_id") or payload.get("id"))
    function_name = safe_label(payload.get("name")) or "unknown_function"
    counters["function_calls"][function_name] += 1
    if call_id:
        call_names[call_id] = function_name
    return call_id, function_name


def _record_missing_shell_command(
    function_name: str,
    *,
    meta: Counter[str],
) -> None:
    if is_shell_tool(function_name):
        meta["missing_command"] += 1


def _set_representative_record_id(mapping: dict[object, str], key: object, record_id: str | None) -> None:
    if record_id and key not in mapping:
        mapping[key] = record_id


def _record_shell_command(command: str, *, counters: dict[str, Any]) -> str:
    root, child = command_root_and_child(command)
    counters["command_calls"][root] += 1
    counters["command_children"].setdefault(root, Counter())[child] += 1
    return root


def _record_git_command_interaction(
    command: str,
    *,
    root: str,
    call_id: str | None,
    counters: dict[str, Any],
    call_git_interactions: dict[str, tuple[str, str, str, str]],
    representative_record_id: str | None,
) -> None:
    interaction = git_interaction_from_command(command, root=root)
    if interaction is None:
        return

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
    _set_representative_record_id(counters["git_interaction_record_ids"], interaction_key, representative_record_id)


def _record_read_command(
    command: str,
    *,
    root: str,
    order: int,
    counters: dict[str, Any],
    call_id: str | None,
    call_read_events: dict[str, list[int]],
    source_read_events: list[int],
    representative_record_id: str | None,
) -> None:
    read_refs = read_path_refs_from_command(command, root=root)
    if not read_refs:
        return

    counters["read_command_count"] += 1
    read_event_indexes = record_read_refs(
        read_refs,
        root=root,
        order=order,
        counters=counters,
        source_read_events=source_read_events,
        representative_record_id=representative_record_id,
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
    representative_record_id: str | None,
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
                "record_id": representative_record_id or "",
            }
        )
        source_read_events.append(event_index)
        indexes.append(event_index)
        counters["read_events_by_reader"][reader] += 1
        counters["read_events_by_path"][path_key] += 1
        _set_representative_record_id(counters["read_reader_record_ids"], reader, representative_record_id)
        _set_representative_record_id(counters["read_path_record_ids"], path_key, representative_record_id)
    return indexes


def record_file_modification_refs(
    path_refs: list[dict[str, str]],
    *,
    counters: dict[str, Any],
    event_kind: str,
    representative_record_id: str | None,
) -> None:
    counters["file_modification_events"] += 1
    event_paths: list[dict[str, str]] = []
    for path_ref in path_refs:
        path_key = path_ref["path_key"]
        path_label = path_ref["path_label"]
        counters["file_modification_path_refs"][path_key] = path_ref
        counters["file_modification_path_events"][path_key] += 1
        _set_representative_record_id(
            counters["file_modification_path_record_ids"],
            path_key,
            representative_record_id,
        )
        counters["file_modification_extensions"][_extension_label(path_label)] += 1
        event_paths.append({"path_label": path_label, "path_hash": path_ref["path_hash"]})
    counters["largest_file_modification_events"].append(
        {
            "event_kind": event_kind,
            "modified_path_count": len(path_refs),
            "representative_record_id": representative_record_id or "",
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
    call_record_ids: dict[str, str],
    representative_record_id: str | None,
) -> None:
    call_id = optional_str(payload.get("call_id"))
    function_name = call_names.get(call_id or "", "unknown_function")
    output_record_id = call_record_ids.get(call_id or "") or representative_record_id
    counters["function_outputs"][function_name] += 1
    _set_representative_record_id(counters["function_record_ids"], function_name, output_record_id)
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
            representative_record_id=output_record_id,
        )
        return
    record_output_count(
        int(count),
        counters=counters,
        function_name=function_name,
        root=call_roots.get(call_id or ""),
        git_interaction=git_interaction,
        read_indexes=read_indexes,
        representative_record_id=output_record_id,
    )


def record_missing_output_count(
    output: object,
    *,
    counters: dict[str, Any],
    function_name: str,
    root: str | None,
    git_interaction: tuple[str, str, str, str] | None,
    read_indexes: list[int],
    representative_record_id: str | None,
) -> None:
    counters["output_missing_count"][function_name] += 1
    missing_reason = "string_no_header" if isinstance(output, str) else "non_string_output"
    counters["missing_reasons"][missing_reason] += 1
    if root:
        counters["command_missing_count"][root] += 1
        _set_representative_record_id(counters["command_record_ids"], root, representative_record_id)
    if git_interaction:
        counters["git_interaction_missing_count"][git_interaction] += 1
        _set_representative_record_id(
            counters["git_interaction_record_ids"],
            git_interaction,
            representative_record_id,
        )
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
    representative_record_id: str | None,
) -> None:
    counters["output_with_count"][function_name] += 1
    counters["output_token_sum"][function_name] += count
    if root:
        counters["command_with_count"][root] += 1
        counters["command_token_sum"][root] += count
        _set_representative_record_id(counters["command_record_ids"], root, representative_record_id)
    if git_interaction:
        counters["git_interaction_with_count"][git_interaction] += 1
        counters["git_interaction_token_sum"][git_interaction] += count
        _set_representative_record_id(
            counters["git_interaction_record_ids"],
            git_interaction,
            representative_record_id,
        )
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
            "representative_record_id": representative_record_id or "",
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
