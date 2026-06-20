"""On-demand aggregate diagnostic report snapshots."""

from __future__ import annotations

import json
import re
import shlex
from collections import Counter
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
DIAGNOSTIC_OVERVIEW_SECTION = "overview"
DIAGNOSTIC_TOOL_OUTPUT_SECTION = "tool-output"
DIAGNOSTIC_COMMANDS_SECTION = "commands"
DIAGNOSTIC_HISTORY_ACTIVE = "active"
DIAGNOSTIC_HISTORY_ALL = "all"
DIAGNOSTIC_SNAPSHOT_NOTES = [
    "Diagnostic snapshots are recomputed only by explicit diagnostic refresh.",
    "Snapshot totals are aggregate-only and do not include raw context.",
]
SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
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
    missing_reasons: Counter[str] = Counter()
    meta: Counter[str] = Counter()
    meta["source_logs_scanned"] = len(source_logs)
    meta["usage_rows_scanned"] = usage_rows_scanned

    for source_log in source_logs:
        call_names: dict[str, str] = {}
        call_roots: dict[str, str] = {}
        try:
            lines = source_log.read_text(encoding="utf-8").splitlines()
        except OSError:
            meta["read_errors"] += 1
            continue
        for line in lines:
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                meta["invalid_json"] += 1
                continue
            if not isinstance(envelope, dict) or envelope.get("type") != "response_item":
                continue
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
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
            elif payload_type == "function_call_output":
                call_id = _optional_str(payload.get("call_id"))
                function_name = call_names.get(call_id or "", "unknown_function")
                function_outputs[function_name] += 1
                output = payload.get("output")
                count = _original_output_count(output)
                if count is None:
                    output_missing_count[function_name] += 1
                    missing_reasons["string_no_header" if isinstance(output, str) else "non_string_output"] += 1
                    root = call_roots.get(call_id or "")
                    if root:
                        command_missing_count[root] += 1
                    continue
                output_with_count[function_name] += 1
                output_token_sum[function_name] += count
                root = call_roots.get(call_id or "")
                if root:
                    command_with_count[root] += 1
                    command_token_sum[root] += count

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


def _simple_rows(
    counter: Counter[str],
    *,
    key_name: str = "name",
) -> list[dict[str, Any]]:
    return [
        {key_name: name, "count": int(count)}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


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


def _int_text(value: object) -> str:
    return f"{_int_value(value):,}"


def _pct_text(value: object) -> str:
    try:
        ratio = float(value) if isinstance(value, int | float | str) and value != "" else 0.0
    except (TypeError, ValueError):
        ratio = 0.0
    return f"{ratio:.1%}"
