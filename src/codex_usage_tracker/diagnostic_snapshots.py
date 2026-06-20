"""On-demand aggregate diagnostic report snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store import (
    connect,
    query_diagnostic_snapshot,
    upsert_diagnostic_snapshot,
)
from codex_usage_tracker.store_schema import init_db

DIAGNOSTIC_OVERVIEW_SCHEMA = "codex-usage-tracker-diagnostic-overview-v1"
DIAGNOSTIC_TOOL_OUTPUT_SCHEMA = "codex-usage-tracker-diagnostic-tool-output-v1"
DIAGNOSTIC_COMMANDS_SCHEMA = "codex-usage-tracker-diagnostic-commands-v1"
DIAGNOSTIC_FILE_READS_SCHEMA = "codex-usage-tracker-diagnostic-file-reads-v1"
DIAGNOSTIC_READ_PRODUCTIVITY_SCHEMA = "codex-usage-tracker-diagnostic-read-productivity-v1"
DIAGNOSTIC_OVERVIEW_SECTION = "overview"
DIAGNOSTIC_TOOL_OUTPUT_SECTION = "tool-output"
DIAGNOSTIC_COMMANDS_SECTION = "commands"
DIAGNOSTIC_FILE_READS_SECTION = "file-reads"
DIAGNOSTIC_READ_PRODUCTIVITY_SECTION = "read-productivity"
DIAGNOSTIC_HISTORY_ACTIVE = "active"
DIAGNOSTIC_HISTORY_ALL = "all"
DIAGNOSTIC_SNAPSHOT_NOTES = [
    "Diagnostic snapshots are recomputed only by explicit diagnostic refresh.",
    "Snapshot totals are aggregate-only and do not include raw context.",
]
SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SAFE_PATH_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:@*+-]{1,80}$")
SENSITIVE_LABEL_PREFIXES = ("sk-", "sk_", "ghp_", "github_pat_", "xox")
SHELL_TOOL_NAMES = {
    "bash",
    "exec_command",
    "functions.exec_command",
    "run_command",
    "shell",
    "terminal",
    "write_stdin",
}
READ_COMMAND_ROOTS = {"cat", "find", "grep", "head", "nl", "rg", "sed", "strings", "tail", "wc"}
SEARCH_READ_ROOTS = {"find", "rg"}
READ_PRODUCTIVITY_NOTE = (
    "Read-to-modify counts are temporal correlations: a read is counted when the same "
    "privacy-preserving path key is modified later in the same source log."
)
ORIGINAL_OUTPUT_RE = re.compile(
    r"^Chunk ID: (?P<chunk>[^\n]+)\n"
    r"Wall time: (?P<wall>[^\n]+)\n"
    r"(?:(?P<status>Process exited with code -?\d+|Process running with session ID \d+)\n)?"
    r"Original token count: (?P<count>\d+)\n",
    re.S,
)


@dataclass(frozen=True)
class DiagnosticSnapshotReport:
    """Resolved diagnostic snapshot payload for CLI and API surfaces."""

    payload: dict[str, Any]

    def render(self) -> str:
        if self.payload.get("status") != "ready":
            section = str(self.payload.get("section") or "snapshot")
            return f"No diagnostic {section} snapshot. Run diagnostics {section} --refresh first."
        section = self.payload.get("section")
        if section == DIAGNOSTIC_TOOL_OUTPUT_SECTION:
            return self._render_tool_output()
        if section == DIAGNOSTIC_COMMANDS_SECTION:
            return self._render_commands()
        if section == DIAGNOSTIC_FILE_READS_SECTION:
            return self._render_file_reads()
        if section == DIAGNOSTIC_READ_PRODUCTIVITY_SECTION:
            return self._render_read_productivity()
        return self._render_overview()

    def _render_overview(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        overview = self.payload.get("overview") or {}
        return "\n".join(
            [
                "Diagnostic overview snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Usage rows: {_int_text(overview.get('usage_rows'))}",
                f"Total tokens: {_int_text(overview.get('total_tokens'))}",
                f"Cached input: {_int_text(overview.get('cached_input_tokens'))}",
                f"Uncached input: {_int_text(overview.get('uncached_input_tokens'))}",
                f"Cache ratio: {_pct_text(overview.get('cache_ratio'))}",
            ]
        )

    def _render_tool_output(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic tool-output snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Function calls: {_int_text(summary.get('function_calls'))}",
                f"Function outputs: {_int_text(summary.get('function_outputs'))}",
                f"Outputs with Original token count: {_int_text(summary.get('outputs_with_original_token_count'))}",
                f"Terminal output tokens: {_int_text(summary.get('original_token_sum'))}",
            ]
        )

    def _render_commands(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic commands snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Shell calls: {_int_text(summary.get('shell_function_calls'))}",
                f"Command roots: {_int_text(summary.get('command_root_count'))}",
                f"Missing command text: {_int_text(summary.get('missing_command'))}",
            ]
        )

    def _render_file_reads(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic file-reads snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Read commands: {_int_text(summary.get('read_commands'))}",
                f"Read events: {_int_text(summary.get('read_events'))}",
                f"Allocated output tokens: {_int_text(summary.get('allocated_output_token_sum'))}",
                f"Missing output counts: {_int_text(summary.get('read_events_missing_output_count'))}",
            ]
        )

    def _render_read_productivity(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic read-productivity snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Read events: {_int_text(summary.get('read_events'))}",
                f"Read events modified later: {_int_text(summary.get('read_events_modified_later'))}",
                f"Read-to-modify rate: {_pct_text(summary.get('read_events_modified_later_pct'))}",
                READ_PRODUCTIVITY_NOTE,
            ]
        )


def build_diagnostic_overview_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest overview snapshot, optionally recomputing it first."""

    if refresh:
        return DiagnosticSnapshotReport(
            refresh_diagnostic_overview_snapshot(
                db_path=db_path,
                include_archived=include_archived,
            )
        )
    return DiagnosticSnapshotReport(
        diagnostic_overview_payload(
            db_path=db_path,
            include_archived=include_archived,
        )
    )


def build_diagnostic_tool_output_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest tool-output snapshot, optionally recomputing it first."""

    return _build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_TOOL_OUTPUT_SECTION,
        schema=DIAGNOSTIC_TOOL_OUTPUT_SCHEMA,
    )


def build_diagnostic_commands_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest commands snapshot, optionally recomputing it first."""

    return _build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_COMMANDS_SECTION,
        schema=DIAGNOSTIC_COMMANDS_SCHEMA,
    )


def build_diagnostic_file_reads_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest file-read snapshot, optionally recomputing it first."""

    return _build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_FILE_READS_SECTION,
        schema=DIAGNOSTIC_FILE_READS_SCHEMA,
    )


def build_diagnostic_read_productivity_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest read-productivity snapshot, optionally recomputing it first."""

    return _build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_READ_PRODUCTIVITY_SECTION,
        schema=DIAGNOSTIC_READ_PRODUCTIVITY_SCHEMA,
    )


def refresh_diagnostic_overview_snapshot(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Recompute and persist the aggregate overview diagnostic snapshot."""

    history_scope = _history_scope(include_archived)
    computed_at = _utc_now()
    overview, source_logs_scanned = _compute_overview(
        db_path=db_path,
        include_archived=include_archived,
    )
    snapshot = _snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=source_logs_scanned,
        usage_rows_scanned=int(overview["usage_rows"]),
    )
    payload = _ready_payload(
        schema=DIAGNOSTIC_OVERVIEW_SCHEMA,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        snapshot=snapshot,
        refreshed=True,
        overview=overview,
    )
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope=history_scope,
        payload=payload,
        computed_at=computed_at,
        source_logs_scanned=source_logs_scanned,
        usage_rows_scanned=int(overview["usage_rows"]),
        raw_content_included=False,
    )
    return payload


def _build_source_log_snapshot_report(
    *,
    db_path: Path,
    include_archived: bool,
    refresh: bool,
    section: str,
    schema: str,
) -> DiagnosticSnapshotReport:
    if refresh:
        return DiagnosticSnapshotReport(
            _refresh_source_log_snapshot(
                db_path=db_path,
                include_archived=include_archived,
                section=section,
                schema=schema,
            )
        )
    return DiagnosticSnapshotReport(
        _source_log_snapshot_payload(
            db_path=db_path,
            include_archived=include_archived,
            section=section,
            schema=schema,
        )
    )


def _refresh_source_log_snapshot(
    *,
    db_path: Path,
    include_archived: bool,
    section: str,
    schema: str,
) -> dict[str, Any]:
    history_scope = _history_scope(include_archived)
    computed_at = _utc_now()
    analysis = _analyze_indexed_source_logs(db_path=db_path, include_archived=include_archived)
    snapshot = _snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=analysis["meta"]["source_logs_scanned"],
        usage_rows_scanned=analysis["meta"]["usage_rows_scanned"],
    )
    if section == DIAGNOSTIC_TOOL_OUTPUT_SECTION:
        payload = _ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["tool_output"]["summary"],
            functions=analysis["tool_output"]["functions"],
            command_roots=analysis["tool_output"]["command_roots"],
            missing_reasons=analysis["tool_output"]["missing_reasons"],
        )
    elif section == DIAGNOSTIC_COMMANDS_SECTION:
        payload = _ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["commands"]["summary"],
            commands=analysis["commands"]["commands"],
        )
    elif section == DIAGNOSTIC_FILE_READS_SECTION:
        payload = _ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["file_reads"]["summary"],
            by_reader=analysis["file_reads"]["by_reader"],
            top_paths=analysis["file_reads"]["top_paths"],
            largest_read_commands=analysis["file_reads"]["largest_read_commands"],
            path_privacy=analysis["file_reads"]["path_privacy"],
        )
    elif section == DIAGNOSTIC_READ_PRODUCTIVITY_SECTION:
        payload = _ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["read_productivity"]["summary"],
            by_reader=analysis["read_productivity"]["by_reader"],
            top_modified_paths=analysis["read_productivity"]["top_modified_paths"],
            path_privacy=analysis["read_productivity"]["path_privacy"],
        )
    else:
        raise ValueError(f"unknown diagnostic snapshot section: {section}")
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=section,
        history_scope=history_scope,
        payload=payload,
        computed_at=computed_at,
        source_logs_scanned=analysis["meta"]["source_logs_scanned"],
        usage_rows_scanned=analysis["meta"]["usage_rows_scanned"],
        raw_content_included=False,
    )
    return payload


def diagnostic_overview_payload(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return the latest persisted overview snapshot without recomputing it."""

    history_scope = _history_scope(include_archived)
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope=history_scope,
    )
    if stored is None:
        return _missing_payload(history_scope=history_scope)
    payload = dict(stored["payload"])
    payload["status"] = "ready"
    payload["refreshed"] = False
    payload["snapshot"] = _snapshot_metadata(
        computed_at=str(stored["computed_at"]),
        history_scope=str(stored["history_scope"]),
        source_logs_scanned=int(stored["source_logs_scanned"]),
        usage_rows_scanned=int(stored["usage_rows_scanned"]),
    )
    payload["raw_context_included"] = bool(stored["raw_content_included"])
    return payload


def _source_log_snapshot_payload(
    *,
    db_path: Path,
    include_archived: bool,
    section: str,
    schema: str,
) -> dict[str, Any]:
    history_scope = _history_scope(include_archived)
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=section,
        history_scope=history_scope,
    )
    if stored is None:
        return _missing_payload(schema=schema, section=section, history_scope=history_scope)
    payload = dict(stored["payload"])
    payload["status"] = "ready"
    payload["refreshed"] = False
    payload["snapshot"] = _snapshot_metadata(
        computed_at=str(stored["computed_at"]),
        history_scope=str(stored["history_scope"]),
        source_logs_scanned=int(stored["source_logs_scanned"]),
        usage_rows_scanned=int(stored["usage_rows_scanned"]),
    )
    payload["raw_context_included"] = bool(stored["raw_content_included"])
    return payload


def _compute_overview(
    *,
    db_path: Path,
    include_archived: bool,
) -> tuple[dict[str, Any], int]:
    usage_where = "" if include_archived else "WHERE is_archived = 0"
    source_where = "" if include_archived else "WHERE is_archived = 0"
    with connect(db_path) as conn:
        init_db(conn)
        usage_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS usage_rows,
                COUNT(DISTINCT session_id) AS session_count,
                COUNT(DISTINCT thread_key) AS thread_count,
                COUNT(DISTINCT model) AS model_count,
                MIN(event_timestamp) AS first_event_timestamp,
                MAX(event_timestamp) AS latest_event_timestamp,
                coalesce(SUM(input_tokens), 0) AS input_tokens,
                coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
                coalesce(SUM(output_tokens), 0) AS output_tokens,
                coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                coalesce(SUM(total_tokens), 0) AS total_tokens,
                AVG(cache_ratio) AS avg_cache_ratio
            FROM usage_events
            {usage_where}
            """
        ).fetchone()
        facts_row = conn.execute(
            f"""
            SELECT COUNT(*) AS diagnostic_fact_rows
            FROM call_diagnostic_facts AS facts
            JOIN usage_events ON usage_events.record_id = facts.record_id
            {usage_where}
            """
        ).fetchone()
        source_row = conn.execute(
            f"SELECT COUNT(*) AS source_logs_scanned FROM source_files {source_where}"
        ).fetchone()
    input_tokens = _int_value(usage_row["input_tokens"])
    cached_input_tokens = _int_value(usage_row["cached_input_tokens"])
    overview = {
        "usage_rows": _int_value(usage_row["usage_rows"]),
        "session_count": _int_value(usage_row["session_count"]),
        "thread_count": _int_value(usage_row["thread_count"]),
        "model_count": _int_value(usage_row["model_count"]),
        "first_event_timestamp": usage_row["first_event_timestamp"],
        "latest_event_timestamp": usage_row["latest_event_timestamp"],
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": _int_value(usage_row["uncached_input_tokens"]),
        "output_tokens": _int_value(usage_row["output_tokens"]),
        "reasoning_output_tokens": _int_value(usage_row["reasoning_output_tokens"]),
        "total_tokens": _int_value(usage_row["total_tokens"]),
        "cache_ratio": cached_input_tokens / input_tokens if input_tokens else 0.0,
        "avg_call_cache_ratio": float(usage_row["avg_cache_ratio"] or 0),
        "diagnostic_fact_rows": _int_value(facts_row["diagnostic_fact_rows"]),
    }
    return overview, _int_value(source_row["source_logs_scanned"])


def _ready_payload(
    *,
    schema: str,
    section: str,
    snapshot: dict[str, Any],
    refreshed: bool,
    **sections: object,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": schema,
        "section": section,
        "status": "ready",
        "refreshed": refreshed,
        "raw_context_included": False,
        "snapshot": snapshot,
        "notes": list(DIAGNOSTIC_SNAPSHOT_NOTES),
    }
    payload.update(sections)
    return payload


def _missing_payload(
    *,
    history_scope: str,
    schema: str = DIAGNOSTIC_OVERVIEW_SCHEMA,
    section: str = DIAGNOSTIC_OVERVIEW_SECTION,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": schema,
        "section": section,
        "status": "missing",
        "refreshed": False,
        "raw_context_included": False,
        "snapshot": None,
        "history_scope": history_scope,
        "notes": list(DIAGNOSTIC_SNAPSHOT_NOTES),
    }
    if section == DIAGNOSTIC_OVERVIEW_SECTION:
        payload["overview"] = None
    elif section == DIAGNOSTIC_TOOL_OUTPUT_SECTION:
        payload["summary"] = None
        payload["functions"] = []
        payload["command_roots"] = []
        payload["missing_reasons"] = []
    elif section == DIAGNOSTIC_COMMANDS_SECTION:
        payload["summary"] = None
        payload["commands"] = []
    elif section == DIAGNOSTIC_FILE_READS_SECTION:
        payload["summary"] = None
        payload["by_reader"] = []
        payload["top_paths"] = []
        payload["largest_read_commands"] = []
        payload["path_privacy"] = _path_privacy_metadata()
    elif section == DIAGNOSTIC_READ_PRODUCTIVITY_SECTION:
        payload["summary"] = None
        payload["by_reader"] = []
        payload["top_modified_paths"] = []
        payload["path_privacy"] = _path_privacy_metadata()
    return payload


def _analyze_indexed_source_logs(
    *,
    db_path: Path,
    include_archived: bool,
) -> dict[str, Any]:
    source_logs, usage_rows_scanned = _indexed_source_logs(
        db_path=db_path,
        include_archived=include_archived,
    )
    function_calls: Counter[str] = Counter()
    function_outputs: Counter[str] = Counter()
    output_with_count: Counter[str] = Counter()
    output_missing_count: Counter[str] = Counter()
    output_token_sum: Counter[str] = Counter()
    command_calls: Counter[str] = Counter()
    command_children: dict[str, Counter[str]] = {}
    command_with_count: Counter[str] = Counter()
    command_missing_count: Counter[str] = Counter()
    command_token_sum: Counter[str] = Counter()
    read_events: list[dict[str, Any]] = []
    read_command_count = 0
    read_events_by_reader: Counter[str] = Counter()
    read_events_by_path: Counter[str] = Counter()
    read_events_with_count_by_reader: Counter[str] = Counter()
    read_events_missing_count_by_reader: Counter[str] = Counter()
    read_tokens_by_reader: Counter[str] = Counter()
    read_tokens_by_path: Counter[str] = Counter()
    read_modified_by_reader: Counter[str] = Counter()
    read_modified_by_path: Counter[str] = Counter()
    read_path_refs: dict[str, dict[str, str]] = {}
    largest_read_commands: list[dict[str, Any]] = []
    missing_reasons: Counter[str] = Counter()
    meta: Counter[str] = Counter()
    meta["source_logs_scanned"] = len(source_logs)
    meta["usage_rows_scanned"] = usage_rows_scanned

    for source_log in source_logs:
        call_names: dict[str, str] = {}
        call_roots: dict[str, str] = {}
        call_read_events: dict[str, list[int]] = {}
        source_read_events: list[int] = []
        modified_orders_by_path: dict[str, list[int]] = defaultdict(list)
        try:
            lines = source_log.read_text(encoding="utf-8").splitlines()
        except OSError:
            meta["read_errors"] += 1
            continue
        for order, line in enumerate(lines):
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                meta["invalid_json"] += 1
                continue
            if not isinstance(envelope, dict):
                continue
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                continue
            if envelope.get("type") == "event_msg":
                for path_ref in _modified_path_refs(payload):
                    modified_orders_by_path[path_ref["path_key"]].append(order)
                continue
            if envelope.get("type") != "response_item":
                continue
            payload_type = payload.get("type")
            if payload_type == "function_call":
                call_id = _optional_str(payload.get("call_id") or payload.get("id"))
                function_name = _safe_label(payload.get("name")) or "unknown_function"
                function_calls[function_name] += 1
                if call_id:
                    call_names[call_id] = function_name
                command = _shell_command_from_payload(payload, function_name=function_name)
                if command is None:
                    if _is_shell_tool(function_name):
                        meta["missing_command"] += 1
                    continue
                root, child = _command_root_and_child(command)
                command_calls[root] += 1
                command_children.setdefault(root, Counter())[child] += 1
                if call_id:
                    call_roots[call_id] = root
                read_refs = _read_path_refs_from_command(command, root=root)
                if read_refs:
                    read_command_count += 1
                    indexes: list[int] = []
                    reader = _read_reader(root)
                    for path_ref in read_refs:
                        path_key = path_ref["path_key"]
                        read_path_refs[path_key] = path_ref
                        event_index = len(read_events)
                        read_events.append(
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
                        read_events_by_reader[reader] += 1
                        read_events_by_path[path_key] += 1
                    if call_id:
                        call_read_events[call_id] = indexes
            elif payload_type == "function_call_output":
                call_id = _optional_str(payload.get("call_id"))
                function_name = call_names.get(call_id or "", "unknown_function")
                function_outputs[function_name] += 1
                output = payload.get("output")
                count = _original_output_count(output)
                read_indexes = call_read_events.get(call_id or "", [])
                if count is None:
                    output_missing_count[function_name] += 1
                    missing_reasons["string_no_header" if isinstance(output, str) else "non_string_output"] += 1
                    root = call_roots.get(call_id or "")
                    if root:
                        command_missing_count[root] += 1
                    for event_index in read_indexes:
                        reader = str(read_events[event_index]["reader"])
                        read_events_missing_count_by_reader[reader] += 1
                    continue
                output_with_count[function_name] += 1
                output_token_sum[function_name] += count
                root = call_roots.get(call_id or "")
                if root:
                    command_with_count[root] += 1
                    command_token_sum[root] += count
                if read_indexes:
                    allocations = _allocate_token_count(count, len(read_indexes))
                    paths: list[dict[str, str]] = []
                    readers: Counter[str] = Counter()
                    for event_index, allocated in zip(read_indexes, allocations, strict=True):
                        event = read_events[event_index]
                        reader = str(event["reader"])
                        path_key = str(event["path_key"])
                        read_events_with_count_by_reader[reader] += 1
                        read_tokens_by_reader[reader] += allocated
                        read_tokens_by_path[path_key] += allocated
                        readers[reader] += 1
                        paths.append(
                            {
                                "path_label": str(event["path_label"]),
                                "path_hash": str(event["path_hash"]),
                            }
                        )
                    largest_read_commands.append(
                        {
                            "root": root or "unknown_command",
                            "read_event_count": len(read_indexes),
                            "original_token_count": int(count),
                            "readers": _simple_rows(readers, key_name="reader"),
                            "paths": _unique_path_rows(paths),
                        }
                    )
        for event_index in source_read_events:
            event = read_events[event_index]
            path_key = str(event["path_key"])
            if any(order > int(event["order"]) for order in modified_orders_by_path.get(path_key, [])):
                event["modified_later"] = True
                read_modified_by_reader[str(event["reader"])] += 1
                read_modified_by_path[path_key] += 1

    function_rows = _function_rows(
        function_calls=function_calls,
        function_outputs=function_outputs,
        output_with_count=output_with_count,
        output_missing_count=output_missing_count,
        output_token_sum=output_token_sum,
    )
    command_output_rows = _command_output_rows(
        command_calls=command_calls,
        command_with_count=command_with_count,
        command_missing_count=command_missing_count,
        command_token_sum=command_token_sum,
    )
    command_rows = _command_rows(command_calls=command_calls, command_children=command_children)
    return {
        "meta": {key: int(value) for key, value in meta.items()},
        "tool_output": {
            "summary": {
                "function_calls": int(sum(function_calls.values())),
                "function_outputs": int(sum(function_outputs.values())),
                "outputs_with_original_token_count": int(sum(output_with_count.values())),
                "outputs_missing_original_token_count": int(sum(output_missing_count.values())),
                "original_token_sum": int(sum(output_token_sum.values())),
            },
            "functions": function_rows,
            "command_roots": command_output_rows,
            "missing_reasons": _simple_rows(missing_reasons),
        },
        "commands": {
            "summary": {
                "shell_function_calls": int(sum(command_calls.values())),
                "command_root_count": len(command_calls),
                "missing_command": int(meta["missing_command"]),
            },
            "commands": command_rows,
        },
        "file_reads": {
            "summary": {
                "read_commands": read_command_count,
                "read_events": len(read_events),
                "unique_paths_read": len(read_path_refs),
                "read_events_with_output_count": int(sum(read_events_with_count_by_reader.values())),
                "read_events_missing_output_count": int(sum(read_events_missing_count_by_reader.values())),
                "allocated_output_token_sum": int(sum(read_tokens_by_reader.values())),
            },
            "by_reader": _read_reader_rows(
                read_events_by_reader=read_events_by_reader,
                read_events_with_count_by_reader=read_events_with_count_by_reader,
                read_events_missing_count_by_reader=read_events_missing_count_by_reader,
                read_tokens_by_reader=read_tokens_by_reader,
            ),
            "top_paths": _read_path_rows(
                read_path_refs=read_path_refs,
                read_events_by_path=read_events_by_path,
                read_tokens_by_path=read_tokens_by_path,
            ),
            "largest_read_commands": _largest_read_command_rows(largest_read_commands),
            "path_privacy": _path_privacy_metadata(),
        },
        "read_productivity": {
            "summary": {
                "read_events": len(read_events),
                "read_events_modified_later": int(sum(read_modified_by_reader.values())),
                "read_events_modified_later_pct": _ratio(
                    int(sum(read_modified_by_reader.values())),
                    len(read_events),
                ),
                "unique_paths_read": len(read_path_refs),
                "unique_paths_modified_later": len(read_modified_by_path),
                "unique_path_modified_later_pct": _ratio(len(read_modified_by_path), len(read_path_refs)),
                "correlation_note": READ_PRODUCTIVITY_NOTE,
            },
            "by_reader": _read_productivity_reader_rows(
                read_events_by_reader=read_events_by_reader,
                read_modified_by_reader=read_modified_by_reader,
            ),
            "top_modified_paths": _read_productivity_path_rows(
                read_path_refs=read_path_refs,
                read_events_by_path=read_events_by_path,
                read_modified_by_path=read_modified_by_path,
            ),
            "path_privacy": _path_privacy_metadata(),
        },
    }


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
    return [Path(str(row["source_file"])) for row in rows], _int_value(usage_row["usage_rows"])


def _function_rows(
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


def _command_output_rows(
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


def _command_rows(
    *,
    command_calls: Counter[str],
    command_children: dict[str, Counter[str]],
) -> list[dict[str, Any]]:
    rows = []
    for root, total in command_calls.items():
        children = _simple_rows(command_children.get(root, Counter()), key_name="child")
        rows.append({"root": root, "total": int(total), "children": children[:25]})
    return sorted(rows, key=lambda row: (-int(row["total"]), row["root"]))


def _read_reader_rows(
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


def _read_path_rows(
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


def _largest_read_command_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -int(row["original_token_count"]),
            -int(row["read_event_count"]),
            row["root"],
        ),
    )[:25]


def _read_productivity_reader_rows(
    *,
    read_events_by_reader: Counter[str],
    read_modified_by_reader: Counter[str],
) -> list[dict[str, Any]]:
    rows = [
        {
            "reader": reader,
            "read_events": int(read_events_by_reader[reader]),
            "read_events_modified_later": int(read_modified_by_reader[reader]),
            "read_events_modified_later_pct": _ratio(
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


def _read_productivity_path_rows(
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
            "read_events_modified_later_pct": _ratio(
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


def _simple_rows(
    counter: Counter[str],
    *,
    key_name: str = "name",
) -> list[dict[str, Any]]:
    return [
        {key_name: name, "count": int(count)}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _unique_path_rows(paths: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in paths:
        path_hash = path["path_hash"]
        if path_hash in seen:
            continue
        seen.add(path_hash)
        rows.append({"path_label": path["path_label"], "path_hash": path_hash})
    return rows[:25]


def _allocate_token_count(count: int, bucket_count: int) -> list[int]:
    if bucket_count <= 0:
        return []
    base = count // bucket_count
    remainder = count % bucket_count
    return [base + (1 if index < remainder else 0) for index in range(bucket_count)]


def _read_path_refs_from_command(command: str, *, root: str) -> list[dict[str, str]]:
    if root not in READ_COMMAND_ROOTS:
        return []
    tokens = _strip_command_wrappers(_command_tokens(command))
    if not tokens:
        return []
    path_tokens = _read_path_tokens(root=root, tokens=tokens)
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for token in path_tokens:
        path_ref = _path_ref_from_token(token)
        if path_ref is None or path_ref["path_key"] in seen:
            continue
        seen.add(path_ref["path_key"])
        refs.append(path_ref)
    return refs


def _read_path_tokens(*, root: str, tokens: list[str]) -> list[str]:
    args = tokens[1:]
    if root == "find":
        return _find_path_tokens(args)
    if root == "rg":
        return _ripgrep_path_tokens(args)
    if root == "grep":
        operands = _non_option_operands(args, root=root)
        return operands[1:] if len(operands) > 1 else []
    if root == "sed":
        operands = _non_option_operands(args, root=root)
        return operands[1:] if len(operands) > 1 else []
    return _non_option_operands(args, root=root)


def _find_path_tokens(args: list[str]) -> list[str]:
    paths: list[str] = []
    for token in args:
        if _is_shell_separator(token):
            break
        if token == "--":
            continue
        if token.startswith("-") or token in {"!", "(", ")"}:
            break
        paths.append(token)
    return paths or ["."]


def _ripgrep_path_tokens(args: list[str]) -> list[str]:
    operands = _non_option_operands(args, root="rg")
    if any(token == "--files" or token.startswith("--files=") for token in args):
        return operands or ["."]
    return operands[1:] if len(operands) > 1 else []


def _non_option_operands(args: list[str], *, root: str) -> list[str]:
    option_args = _option_args_for_root(root)
    operands: list[str] = []
    skip_next = False
    passthrough = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if _is_shell_separator(token):
            break
        if token in {">", ">>", "<", "2>", "2>>"}:
            break
        if passthrough:
            operands.append(token)
            continue
        if token == "--":
            passthrough = True
            continue
        if token.startswith("-"):
            option_name = token.split("=", 1)[0]
            if option_name in option_args and "=" not in token:
                skip_next = True
            continue
        operands.append(token)
    return operands


def _option_args_for_root(root: str) -> set[str]:
    return {
        "grep": {
            "-A",
            "-B",
            "-C",
            "-e",
            "-f",
            "-m",
            "--after-context",
            "--before-context",
            "--context",
            "--file",
            "--max-count",
            "--regexp",
        },
        "head": {"-c", "-n", "--bytes", "--lines"},
        "rg": {
            "-A",
            "-B",
            "-C",
            "-e",
            "-f",
            "-g",
            "-m",
            "-t",
            "-T",
            "--after-context",
            "--before-context",
            "--context",
            "--file",
            "--glob",
            "--max-count",
            "--max-depth",
            "--type",
            "--type-not",
        },
        "sed": {"-e", "-f", "--expression", "--file"},
        "tail": {"-c", "-n", "--bytes", "--lines"},
    }.get(root, set())


def _read_reader(root: str) -> str:
    if root in SEARCH_READ_ROOTS:
        return f"search_path_scan:{root}"
    return f"direct_file_read:{root}"


def _modified_path_refs(payload: dict[str, Any]) -> list[dict[str, str]]:
    if payload.get("type") != "patch_apply_end":
        return []
    paths: list[str] = []
    for key in ("changed_paths", "paths", "files", "modified_paths"):
        paths.extend(_path_values(payload.get(key)))
    paths.extend(_path_values(payload.get("changes")))
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in paths:
        path_ref = _path_ref_from_token(path)
        if path_ref is None or path_ref["path_key"] in seen:
            continue
        seen.add(path_ref["path_key"])
        refs.append(path_ref)
    return refs


def _path_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple):
        paths: list[str] = []
        for item in value:
            paths.extend(_path_values(item))
        return paths
    if isinstance(value, dict):
        paths = []
        for key in ("path", "file", "filename", "new_path", "old_path"):
            paths.extend(_path_values(value.get(key)))
        return paths
    return []


def _path_ref_from_token(token: str) -> dict[str, str] | None:
    raw = token.strip()
    if not raw or raw == "-" or _is_shell_separator(raw) or _looks_like_assignment(raw):
        return None
    if raw.startswith(("$", "`")) or "://" in raw:
        return None
    label = _safe_path_label(raw)
    if label is None:
        return None
    path_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return {"path_key": path_hash, "path_label": label, "path_hash": path_hash}


def _safe_path_label(token: str) -> str | None:
    normalized = token.rstrip("/")
    label = normalized if normalized in {".", ".."} else Path(normalized).name
    if not label:
        return None
    lowered = label.lower()
    if lowered.startswith(SENSITIVE_LABEL_PREFIXES):
        return "path"
    return label if SAFE_PATH_LABEL_RE.fullmatch(label) else "path"


def _is_shell_separator(token: str) -> bool:
    return token in {"&&", "||", ";", "|"}


def _path_privacy_metadata() -> dict[str, str]:
    return {
        "label_policy": "basename_only",
        "hash_policy": "sha256_12",
        "normal": "basename_only_with_hash",
        "redacted": "basename_only_with_hash",
        "strict": "hash_available_for_hiding_labels",
    }


def _shell_command_from_payload(payload: dict[str, Any], *, function_name: str) -> str | None:
    if not _is_shell_tool(function_name):
        return None
    arguments = payload.get("arguments")
    if isinstance(arguments, str):
        try:
            loaded = json.loads(arguments)
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            command = loaded.get("cmd") or loaded.get("command")
            if isinstance(command, str):
                return command
    if isinstance(arguments, dict):
        command = arguments.get("cmd") or arguments.get("command")
        if isinstance(command, str):
            return command
    command = payload.get("cmd") or payload.get("command")
    return command if isinstance(command, str) else None


def _is_shell_tool(function_name: str) -> bool:
    lowered = function_name.lower()
    suffix = lowered.rsplit(".", 1)[-1].rsplit("__", 1)[-1]
    return lowered in SHELL_TOOL_NAMES or suffix in SHELL_TOOL_NAMES


def _command_root_and_child(command: str) -> tuple[str, str]:
    tokens = _strip_command_wrappers(_command_tokens(command))
    if not tokens:
        return "unknown_command", "unknown"
    root = _command_root(tokens)
    return root, _command_child(root, tokens)


def _command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def _strip_command_wrappers(tokens: list[str]) -> list[str]:
    remaining = list(tokens)
    while remaining:
        while remaining and _looks_like_assignment(remaining[0]):
            remaining.pop(0)
        if not remaining:
            break
        base = _basename(remaining[0])
        if base in {"command", "env", "sudo"}:
            remaining.pop(0)
            continue
        break
    return remaining


def _command_root(tokens: list[str]) -> str:
    base = _basename(tokens[0])
    if base in {"py.test", "pytest"}:
        return "pytest"
    if base == "py" or base == "python" or base.startswith("python"):
        return "python"
    return _safe_label(base) or "unknown_command"


def _command_child(root: str, tokens: list[str]) -> str:
    if root == "python":
        for index, token in enumerate(tokens[:-1]):
            if token == "-m":
                module = _safe_label(_basename(tokens[index + 1]).split(".", 1)[0])
                return f"-m:{module}" if module else "-m:unknown"
        return tokens[1] if len(tokens) > 1 and tokens[1].startswith("-") else "<script>"
    if len(tokens) <= 1:
        return "<none>"
    child = _safe_label(_basename(tokens[1]))
    return child or "<arg>"


def _original_output_count(output: object) -> int | None:
    if not isinstance(output, str):
        return None
    match = ORIGINAL_OUTPUT_RE.match(output)
    if not match:
        return None
    return int(match.group("count"))


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered.startswith(SENSITIVE_LABEL_PREFIXES):
        return None
    if "/" in stripped or "\\" in stripped:
        return None
    return lowered if SAFE_LABEL_RE.fullmatch(stripped) else None


def _looks_like_assignment(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token))


def _basename(token: str) -> str:
    return re.split(r"[\\/]", token)[-1].lower()


def _snapshot_metadata(
    *,
    computed_at: str,
    history_scope: str,
    source_logs_scanned: int,
    usage_rows_scanned: int,
) -> dict[str, Any]:
    return {
        "computed_at": computed_at,
        "history_scope": history_scope,
        "source_logs_scanned": int(source_logs_scanned),
        "usage_rows_scanned": int(usage_rows_scanned),
        "raw_content_included": False,
    }


def _history_scope(include_archived: bool) -> str:
    return DIAGNOSTIC_HISTORY_ALL if include_archived else DIAGNOSTIC_HISTORY_ACTIVE


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value:
        return int(value)
    return 0


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _int_text(value: object) -> str:
    return f"{_int_value(value):,}"


def _pct_text(value: object) -> str:
    try:
        ratio = float(value) if isinstance(value, int | float | str) and value != "" else 0.0
    except (TypeError, ValueError):
        ratio = 0.0
    return f"{ratio:.1%}"
