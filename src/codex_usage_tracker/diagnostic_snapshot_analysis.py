"""Aggregate diagnostic snapshot analyzers."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_usage_tracker.diagnostic_snapshot_events import (
    READ_PRODUCTIVITY_NOTE,
    int_value,
    modified_path_refs,
    path_privacy_metadata,
    ratio,
    safe_label,
    simple_rows,
)
from codex_usage_tracker.diagnostic_snapshot_rows import (
    command_output_rows,
    command_rows,
    file_modification_path_rows,
    function_rows,
    git_interaction_rows,
    largest_file_modification_event_rows,
    largest_read_command_rows,
    read_path_rows,
    read_productivity_path_rows,
    read_productivity_reader_rows,
    read_reader_rows,
)
from codex_usage_tracker.diagnostic_snapshot_source_scan import (
    mark_later_modifications,
    record_file_modification_refs,
    record_function_call,
    record_function_output,
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
        "git_interaction_calls": Counter(),
        "git_interaction_with_count": Counter(),
        "git_interaction_missing_count": Counter(),
        "git_interaction_token_sum": Counter(),
        "git_interactions_by_category": Counter(),
        "git_interactions_by_mutability": Counter(),
        "git_interactions_by_root": Counter(),
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


@dataclass
class _SourceLogScanState:
    call_names: dict[str, str] = field(default_factory=dict)
    call_roots: dict[str, str] = field(default_factory=dict)
    call_git_interactions: dict[str, tuple[str, str, str, str]] = field(default_factory=dict)
    call_read_events: dict[str, list[int]] = field(default_factory=dict)
    source_read_events: list[int] = field(default_factory=list)
    modified_orders_by_path: defaultdict[str, list[int]] = field(
        default_factory=lambda: defaultdict(list)
    )


def _scan_source_log(source_log: Path, *, counters: dict[str, Any], meta: Counter[str]) -> None:
    state = _SourceLogScanState()
    try:
        lines = source_log.open(encoding="utf-8")
    except OSError:
        meta["read_errors"] += 1
        return

    with lines:
        for order, line in enumerate(lines):
            _scan_source_log_line(
                line,
                order=order,
                counters=counters,
                meta=meta,
                state=state,
            )

    mark_later_modifications(
        counters=counters,
        source_read_events=state.source_read_events,
        modified_orders_by_path=state.modified_orders_by_path,
    )


def _scan_source_log_line(
    line: str,
    *,
    order: int,
    counters: dict[str, Any],
    meta: Counter[str],
    state: _SourceLogScanState,
) -> None:
    if not _source_log_line_may_have_diagnostic_payload(line):
        return
    envelope = _json_envelope(line, meta=meta)
    if envelope is None:
        return
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return
    _scan_source_log_payload(
        envelope,
        payload,
        order=order,
        counters=counters,
        meta=meta,
        state=state,
    )


def _source_log_line_may_have_diagnostic_payload(line: str) -> bool:
    return '"response_item"' in line or '"patch_apply_end"' in line


def _scan_source_log_payload(
    envelope: dict[str, Any],
    payload: dict[str, Any],
    *,
    order: int,
    counters: dict[str, Any],
    meta: Counter[str],
    state: _SourceLogScanState,
) -> None:
    envelope_type = envelope.get("type")
    if envelope_type == "event_msg":
        _record_source_log_modification(
            payload,
            counters=counters,
            event_kind=safe_label(payload.get("type")) or "file_modification",
            order=order,
            state=state,
        )
        return
    if envelope_type != "response_item":
        return
    if _record_source_log_modification(
        payload,
        counters=counters,
        event_kind=safe_label(payload.get("name")) or "file_modification",
        order=order,
        state=state,
    ):
        return
    _record_source_log_response_item(
        payload,
        order=order,
        counters=counters,
        meta=meta,
        state=state,
    )


def _record_source_log_modification(
    payload: dict[str, Any],
    *,
    counters: dict[str, Any],
    event_kind: str,
    order: int,
    state: _SourceLogScanState,
) -> bool:
    path_refs = modified_path_refs(payload)
    if not path_refs:
        return False
    record_file_modification_refs(
        path_refs,
        counters=counters,
        event_kind=event_kind,
    )
    for path_ref in path_refs:
        state.modified_orders_by_path[path_ref["path_key"]].append(order)
    return True


def _record_source_log_response_item(
    payload: dict[str, Any],
    *,
    order: int,
    counters: dict[str, Any],
    meta: Counter[str],
    state: _SourceLogScanState,
) -> None:
    payload_type = payload.get("type")
    if payload_type == "function_call":
        record_function_call(
            payload,
            order=order,
            counters=counters,
            meta=meta,
            call_names=state.call_names,
            call_roots=state.call_roots,
            call_git_interactions=state.call_git_interactions,
            call_read_events=state.call_read_events,
            source_read_events=state.source_read_events,
        )
    elif payload_type == "function_call_output":
        record_function_output(
            payload,
            counters=counters,
            call_names=state.call_names,
            call_roots=state.call_roots,
            call_git_interactions=state.call_git_interactions,
            call_read_events=state.call_read_events,
        )


def _json_envelope(line: str, *, meta: Counter[str]) -> dict[str, Any] | None:
    try:
        envelope = json.loads(line)
    except json.JSONDecodeError:
        meta["invalid_json"] += 1
        return None
    return envelope if isinstance(envelope, dict) else None


def _analysis_payload(*, counters: dict[str, Any], meta: Counter[str]) -> dict[str, Any]:
    return {
        "meta": {key: int(value) for key, value in meta.items()},
        "tool_output": _tool_output_payload(counters),
        "commands": _commands_payload(counters, meta=meta),
        "git_interactions": _git_interactions_payload(counters),
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


def _git_interactions_payload(counters: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": {
            "git_shell_calls": int(sum(counters["git_interaction_calls"].values())),
            "git_command_calls": int(counters["git_interactions_by_root"]["git"]),
            "github_cli_calls": int(counters["git_interactions_by_root"]["gh"]),
            "unique_interactions": len(counters["git_interaction_calls"]),
            "interactions_with_original_token_count": int(
                sum(counters["git_interaction_with_count"].values())
            ),
            "interactions_missing_original_token_count": int(
                sum(counters["git_interaction_missing_count"].values())
            ),
            "original_token_sum": int(sum(counters["git_interaction_token_sum"].values())),
        },
        "interactions": git_interaction_rows(
            git_interaction_calls=counters["git_interaction_calls"],
            git_interaction_with_count=counters["git_interaction_with_count"],
            git_interaction_missing_count=counters["git_interaction_missing_count"],
            git_interaction_token_sum=counters["git_interaction_token_sum"],
        ),
        "categories": simple_rows(counters["git_interactions_by_category"], key_name="category"),
        "mutability": simple_rows(counters["git_interactions_by_mutability"], key_name="mutability"),
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
