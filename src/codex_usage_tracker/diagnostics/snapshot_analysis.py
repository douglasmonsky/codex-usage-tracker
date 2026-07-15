"""Aggregate diagnostic snapshot analyzers."""

from __future__ import annotations

import bisect
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.command_parsing import safe_label
from codex_usage_tracker.diagnostics.snapshot_analysis_payloads import _analysis_payload
from codex_usage_tracker.diagnostics.snapshot_events import (
    int_value,
    modified_path_refs,
)
from codex_usage_tracker.diagnostics.snapshot_source_scan import (
    mark_later_modifications,
    record_file_modification_refs,
    record_function_call,
    record_function_output,
)
from codex_usage_tracker.store.api import connect
from codex_usage_tracker.store.schema import init_db

SourceRecordIndex = dict[str, list[tuple[int, str]]]


def analyze_indexed_source_logs(
    *,
    db_path: Path,
    include_archived: bool,
) -> dict[str, Any]:
    source_logs, usage_rows_scanned = _indexed_source_logs(
        db_path=db_path,
        include_archived=include_archived,
    )
    source_record_index = _source_record_index(
        db_path=db_path,
        include_archived=include_archived,
    )
    counters = _empty_counters()
    meta: Counter[str] = Counter()
    meta["source_logs_scanned"] = len(source_logs)
    meta["usage_rows_scanned"] = usage_rows_scanned

    for source_log in source_logs:
        _scan_source_log(
            source_log, counters=counters, meta=meta, source_record_index=source_record_index
        )

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
            f"SELECT COUNT(*) AS usage_rows FROM canonical_usage_events {where}"
        ).fetchone()
    return [Path(str(row["source_file"])) for row in rows], int_value(usage_row["usage_rows"])


def _source_record_index(*, db_path: Path, include_archived: bool) -> SourceRecordIndex:
    where = "" if include_archived else "WHERE is_archived = 0"
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT source_file, line_number, record_id
            FROM canonical_usage_events
            {where}
            ORDER BY source_file, line_number
            """
        ).fetchall()
    index: SourceRecordIndex = {}
    for row in rows:
        source_file = str(row["source_file"] or "")
        record_id = str(row["record_id"] or "")
        line_number = int_value(row["line_number"])
        if source_file and record_id and line_number > 0:
            index.setdefault(source_file, []).append((line_number, record_id))
    return index


def _empty_counters() -> dict[str, Any]:
    return {
        "function_calls": Counter(),
        "function_outputs": Counter(),
        "function_record_ids": {},
        "output_with_count": Counter(),
        "output_missing_count": Counter(),
        "output_token_sum": Counter(),
        "command_calls": Counter(),
        "command_children": {},
        "command_record_ids": {},
        "command_with_count": Counter(),
        "command_missing_count": Counter(),
        "command_token_sum": Counter(),
        "git_interaction_calls": Counter(),
        "git_interaction_record_ids": {},
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
        "read_reader_record_ids": {},
        "read_path_record_ids": {},
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
        "file_modification_path_record_ids": {},
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
    call_record_ids: dict[str, str] = field(default_factory=dict)
    source_read_events: list[int] = field(default_factory=list)
    modified_orders_by_path: defaultdict[str, list[int]] = field(
        default_factory=lambda: defaultdict(list)
    )


def _scan_source_log(
    source_log: Path,
    *,
    counters: dict[str, Any],
    meta: Counter[str],
    source_record_index: SourceRecordIndex,
) -> None:
    state = _SourceLogScanState()
    try:
        lines = source_log.open(encoding="utf-8")
    except OSError:
        meta["read_errors"] += 1
        return

    with lines:
        for order, line in enumerate(lines):
            _scan_source_log_line(
                source_log,
                line,
                order=order,
                counters=counters,
                meta=meta,
                state=state,
                source_record_index=source_record_index,
            )

    mark_later_modifications(
        counters=counters,
        source_read_events=state.source_read_events,
        modified_orders_by_path=state.modified_orders_by_path,
    )


def _scan_source_log_line(
    source_log: Path,
    line: str,
    *,
    order: int,
    counters: dict[str, Any],
    meta: Counter[str],
    state: _SourceLogScanState,
    source_record_index: SourceRecordIndex,
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
        representative_record_id=_record_id_for_order(source_log, order, source_record_index),
    )


def _source_log_line_may_have_diagnostic_payload(line: str) -> bool:
    return '"response_item"' in line or '"patch_apply_end"' in line


def _record_id_for_order(
    source_log: Path, order: int, source_record_index: SourceRecordIndex
) -> str | None:
    rows = source_record_index.get(str(source_log))
    if not rows:
        return None
    line_number = order + 1
    index = bisect.bisect_left(rows, (line_number, ""))
    if index < len(rows):
        return rows[index][1]
    return rows[-1][1]


def _scan_source_log_payload(
    envelope: dict[str, Any],
    payload: dict[str, Any],
    *,
    order: int,
    counters: dict[str, Any],
    meta: Counter[str],
    state: _SourceLogScanState,
    representative_record_id: str | None,
) -> None:
    envelope_type = envelope.get("type")
    if envelope_type == "event_msg":
        _record_source_log_modification(
            payload,
            counters=counters,
            event_kind=safe_label(payload.get("type")) or "file_modification",
            order=order,
            state=state,
            representative_record_id=representative_record_id,
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
        representative_record_id=representative_record_id,
    ):
        return
    _record_source_log_response_item(
        payload,
        order=order,
        counters=counters,
        meta=meta,
        state=state,
        representative_record_id=representative_record_id,
    )


def _record_source_log_modification(
    payload: dict[str, Any],
    *,
    counters: dict[str, Any],
    event_kind: str,
    order: int,
    state: _SourceLogScanState,
    representative_record_id: str | None,
) -> bool:
    path_refs = modified_path_refs(payload)
    if not path_refs:
        return False
    record_file_modification_refs(
        path_refs,
        counters=counters,
        event_kind=event_kind,
        representative_record_id=representative_record_id,
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
    representative_record_id: str | None,
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
            call_record_ids=state.call_record_ids,
            source_read_events=state.source_read_events,
            representative_record_id=representative_record_id,
        )
    elif payload_type == "function_call_output":
        record_function_output(
            payload,
            counters=counters,
            call_names=state.call_names,
            call_roots=state.call_roots,
            call_git_interactions=state.call_git_interactions,
            call_read_events=state.call_read_events,
            call_record_ids=state.call_record_ids,
            representative_record_id=representative_record_id,
        )


def _json_envelope(line: str, *, meta: Counter[str]) -> dict[str, Any] | None:
    try:
        envelope = json.loads(line)
    except json.JSONDecodeError:
        meta["invalid_json"] += 1
        return None
    return envelope if isinstance(envelope, dict) else None
