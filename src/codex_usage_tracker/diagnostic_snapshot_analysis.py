"""Aggregate diagnostic snapshot analyzers."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from codex_usage_tracker.diagnostic_snapshot_events import (
    READ_PRODUCTIVITY_NOTE,
    allocate_token_count,
    command_root_and_child,
    int_value,
    is_shell_tool,
    modified_path_refs,
    optional_str,
    original_output_count,
    path_privacy_metadata,
    ratio,
    read_path_refs_from_command,
    read_reader,
    safe_label,
    shell_command_from_payload,
    simple_rows,
    unique_path_rows,
)
from codex_usage_tracker.diagnostic_snapshot_rows import (
    command_output_rows,
    command_rows,
    file_modification_path_rows,
    function_rows,
    largest_file_modification_event_rows,
    largest_read_command_rows,
    read_path_rows,
    read_productivity_path_rows,
    read_productivity_reader_rows,
    read_reader_rows,
)
from codex_usage_tracker.store import connect
from codex_usage_tracker.store_schema import init_db


def analyze_indexed_source_logs(
    *,
    db_path: Path,
    include_archived: bool,
) -> dict[str, Any]:
    source_logs, usage_rows_scanned = _indexed_source_logs(
        db_path=db_path,
        include_archived=include_archived,
    )
    counters = _empty_counters()
    meta: Counter[str] = Counter()
    meta["source_logs_scanned"] = len(source_logs)
    meta["usage_rows_scanned"] = usage_rows_scanned

    for source_log in source_logs:
        _scan_source_log(source_log, counters=counters, meta=meta)

    return _analysis_payload(counters=counters, meta=meta)


def _indexed_source_logs(
    *,
    db_path: Path,
    include_archived: bool,
) -> tuple[list[Path], int]:
    where = "" if include_archived else "WHERE is_archived = 0"
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"SELECT source_file FROM source_files {where} ORDER BY source_file"
        ).fetchall()
        usage_row = conn.execute(
            f"SELECT COUNT(*) AS usage_rows FROM usage_events {where}"
        ).fetchone()
    return [Path(str(row["source_file"])) for row in rows], int_value(usage_row["usage_rows"])


def _empty_counters() -> dict[str, Any]:
    return {
        "function_calls": Counter(),
        "function_outputs": Counter(),
        "output_with_count": Counter(),
        "output_missing_count": Counter(),
        "output_token_sum": Counter(),
        "command_calls": Counter(),
        "command_children": {},
        "command_with_count": Counter(),
        "command_missing_count": Counter(),
        "command_token_sum": Counter(),
        "read_events": [],
        "read_command_count": 0,
        "read_events_by_reader": Counter(),
        "read_events_by_path": Counter(),
        "read_events_with_count_by_reader": Counter(),
        "read_events_missing_count_by_reader": Counter(),
        "read_tokens_by_reader": Counter(),
        "read_tokens_by_path": Counter(),
        "read_modified_by_reader": Counter(),
        "read_modified_by_path": Counter(),
        "read_path_refs": {},
        "largest_read_commands": [],
        "file_modification_events": 0,
        "file_modification_path_events": Counter(),
        "file_modification_path_refs": {},
        "file_modification_extensions": Counter(),
        "largest_file_modification_events": [],
        "missing_reasons": Counter(),
    }


def _scan_source_log(source_log: Path, *, counters: dict[str, Any], meta: Counter[str]) -> None:
    call_names: dict[str, str] = {}
    call_roots: dict[str, str] = {}
    call_read_events: dict[str, list[int]] = {}
    source_read_events: list[int] = []
    modified_orders_by_path: dict[str, list[int]] = defaultdict(list)
    try:
        lines = source_log.open(encoding="utf-8")
    except OSError:
        meta["read_errors"] += 1
        return

    with lines:
        for order, line in enumerate(lines):
            if '"response_item"' not in line and '"patch_apply_end"' not in line:
                continue
            envelope = _json_envelope(line, meta=meta)
            if envelope is None:
                continue
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                continue
            if envelope.get("type") == "event_msg":
                path_refs = modified_path_refs(payload)
                if path_refs:
                    _record_file_modification_refs(path_refs, counters=counters)
                for path_ref in path_refs:
                    modified_orders_by_path[path_ref["path_key"]].append(order)
                continue
            if envelope.get("type") != "response_item":
                continue
            if payload.get("type") == "function_call":
                _record_function_call(
                    payload,
                    order=order,
                    counters=counters,
                    meta=meta,
                    call_names=call_names,
                    call_roots=call_roots,
                    call_read_events=call_read_events,
                    source_read_events=source_read_events,
                )
            elif payload.get("type") == "function_call_output":
                _record_function_output(
                    payload,
                    counters=counters,
                    call_names=call_names,
                    call_roots=call_roots,
                    call_read_events=call_read_events,
                )

    _mark_later_modifications(
        counters=counters,
        source_read_events=source_read_events,
        modified_orders_by_path=modified_orders_by_path,
    )


def _json_envelope(line: str, *, meta: Counter[str]) -> dict[str, Any] | None:
    try:
        envelope = json.loads(line)
    except json.JSONDecodeError:
        meta["invalid_json"] += 1
        return None
    return envelope if isinstance(envelope, dict) else None


def _record_function_call(
    payload: dict[str, Any],
    *,
    order: int,
    counters: dict[str, Any],
    meta: Counter[str],
    call_names: dict[str, str],
    call_roots: dict[str, str],
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
    read_refs = read_path_refs_from_command(command, root=root)
    if read_refs:
        counters["read_command_count"] += 1
        read_event_indexes = _record_read_refs(
            read_refs,
            root=root,
            order=order,
            counters=counters,
            source_read_events=source_read_events,
        )
        if call_id:
            call_read_events[call_id] = read_event_indexes


def _record_read_refs(
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


def _record_file_modification_refs(
    path_refs: list[dict[str, str]],
    *,
    counters: dict[str, Any],
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
            "event_kind": "patch_apply_end",
            "modified_path_count": len(path_refs),
            "paths": unique_path_rows(event_paths),
        }
    )


def _record_function_output(
    payload: dict[str, Any],
    *,
    counters: dict[str, Any],
    call_names: dict[str, str],
    call_roots: dict[str, str],
    call_read_events: dict[str, list[int]],
) -> None:
    call_id = optional_str(payload.get("call_id"))
    function_name = call_names.get(call_id or "", "unknown_function")
    counters["function_outputs"][function_name] += 1
    output = payload.get("output")
    count = original_output_count(output)
    read_indexes = call_read_events.get(call_id or "", [])
    if count is None:
        _record_missing_output_count(
            output,
            counters=counters,
            function_name=function_name,
            root=call_roots.get(call_id or ""),
            read_indexes=read_indexes,
        )
        return
    _record_output_count(
        int(count),
        counters=counters,
        function_name=function_name,
        root=call_roots.get(call_id or ""),
        read_indexes=read_indexes,
    )


def _record_missing_output_count(
    output: object,
    *,
    counters: dict[str, Any],
    function_name: str,
    root: str | None,
    read_indexes: list[int],
) -> None:
    counters["output_missing_count"][function_name] += 1
    counters["missing_reasons"]["string_no_header" if isinstance(output, str) else "non_string_output"] += 1
    if root:
        counters["command_missing_count"][root] += 1
    for event_index in read_indexes:
        reader = str(counters["read_events"][event_index]["reader"])
        counters["read_events_missing_count_by_reader"][reader] += 1


def _record_output_count(
    count: int,
    *,
    counters: dict[str, Any],
    function_name: str,
    root: str | None,
    read_indexes: list[int],
) -> None:
    counters["output_with_count"][function_name] += 1
    counters["output_token_sum"][function_name] += count
    if root:
        counters["command_with_count"][root] += 1
        counters["command_token_sum"][root] += count
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


def _mark_later_modifications(
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


def _analysis_payload(*, counters: dict[str, Any], meta: Counter[str]) -> dict[str, Any]:
    return {
        "meta": {key: int(value) for key, value in meta.items()},
        "tool_output": _tool_output_payload(counters),
        "commands": _commands_payload(counters, meta=meta),
        "file_reads": _file_reads_payload(counters),
        "file_modifications": _file_modifications_payload(counters),
        "read_productivity": _read_productivity_payload(counters),
    }


def _tool_output_payload(counters: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": {
            "function_calls": int(sum(counters["function_calls"].values())),
            "function_outputs": int(sum(counters["function_outputs"].values())),
            "outputs_with_original_token_count": int(sum(counters["output_with_count"].values())),
            "outputs_missing_original_token_count": int(sum(counters["output_missing_count"].values())),
            "original_token_sum": int(sum(counters["output_token_sum"].values())),
        },
        "functions": function_rows(
            function_calls=counters["function_calls"],
            function_outputs=counters["function_outputs"],
            output_with_count=counters["output_with_count"],
            output_missing_count=counters["output_missing_count"],
            output_token_sum=counters["output_token_sum"],
        ),
        "command_roots": command_output_rows(
            command_calls=counters["command_calls"],
            command_with_count=counters["command_with_count"],
            command_missing_count=counters["command_missing_count"],
            command_token_sum=counters["command_token_sum"],
        ),
        "missing_reasons": simple_rows(counters["missing_reasons"]),
    }


def _commands_payload(counters: dict[str, Any], *, meta: Counter[str]) -> dict[str, Any]:
    return {
        "summary": {
            "shell_function_calls": int(sum(counters["command_calls"].values())),
            "command_root_count": len(counters["command_calls"]),
            "missing_command": int(meta["missing_command"]),
        },
        "commands": command_rows(
            command_calls=counters["command_calls"],
            command_children=counters["command_children"],
        ),
    }


def _file_reads_payload(counters: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": {
            "read_commands": counters["read_command_count"],
            "read_events": len(counters["read_events"]),
            "unique_paths_read": len(counters["read_path_refs"]),
            "read_events_with_output_count": int(sum(counters["read_events_with_count_by_reader"].values())),
            "read_events_missing_output_count": int(sum(counters["read_events_missing_count_by_reader"].values())),
            "allocated_output_token_sum": int(sum(counters["read_tokens_by_reader"].values())),
        },
        "by_reader": read_reader_rows(
            read_events_by_reader=counters["read_events_by_reader"],
            read_events_with_count_by_reader=counters["read_events_with_count_by_reader"],
            read_events_missing_count_by_reader=counters["read_events_missing_count_by_reader"],
            read_tokens_by_reader=counters["read_tokens_by_reader"],
        ),
        "top_paths": read_path_rows(
            read_path_refs=counters["read_path_refs"],
            read_events_by_path=counters["read_events_by_path"],
            read_tokens_by_path=counters["read_tokens_by_path"],
        ),
        "largest_read_commands": largest_read_command_rows(counters["largest_read_commands"]),
        "path_privacy": path_privacy_metadata(),
    }


def _file_modifications_payload(counters: dict[str, Any]) -> dict[str, Any]:
    modified_path_events = int(sum(counters["file_modification_path_events"].values()))
    largest_event_path_count = max(
        (int(row["modified_path_count"]) for row in counters["largest_file_modification_events"]),
        default=0,
    )
    return {
        "summary": {
            "modification_events": int(counters["file_modification_events"]),
            "modified_path_events": modified_path_events,
            "unique_paths_modified": len(counters["file_modification_path_refs"]),
            "largest_event_path_count": largest_event_path_count,
        },
        "top_paths": file_modification_path_rows(
            modification_path_refs=counters["file_modification_path_refs"],
            modifications_by_path=counters["file_modification_path_events"],
        ),
        "by_extension": simple_rows(counters["file_modification_extensions"], key_name="extension"),
        "largest_events": largest_file_modification_event_rows(
            counters["largest_file_modification_events"]
        ),
        "path_privacy": path_privacy_metadata(),
    }


def _read_productivity_payload(counters: dict[str, Any]) -> dict[str, Any]:
    read_modified_count = int(sum(counters["read_modified_by_reader"].values()))
    return {
        "summary": {
            "read_events": len(counters["read_events"]),
            "read_events_modified_later": read_modified_count,
            "read_events_modified_later_pct": ratio(read_modified_count, len(counters["read_events"])),
            "unique_paths_read": len(counters["read_path_refs"]),
            "unique_paths_modified_later": len(counters["read_modified_by_path"]),
            "unique_path_modified_later_pct": ratio(
                len(counters["read_modified_by_path"]),
                len(counters["read_path_refs"]),
            ),
            "correlation_note": READ_PRODUCTIVITY_NOTE,
        },
        "by_reader": read_productivity_reader_rows(
            read_events_by_reader=counters["read_events_by_reader"],
            read_modified_by_reader=counters["read_modified_by_reader"],
        ),
        "top_modified_paths": read_productivity_path_rows(
            read_path_refs=counters["read_path_refs"],
            read_events_by_path=counters["read_events_by_path"],
            read_modified_by_path=counters["read_modified_by_path"],
        ),
        "path_privacy": path_privacy_metadata(),
    }


def _extension_label(path_label: str) -> str:
    suffix = Path(path_label).suffix.lower()
    return suffix if suffix else "<none>"
