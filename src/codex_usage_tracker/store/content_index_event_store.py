"""Persist normalized local event rows for the content index."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from codex_usage_tracker.parser.state import PARSER_ADAPTER_VERSION
from codex_usage_tracker.store.content_index_events import (
    PendingCommandRun,
    PendingFileEvent,
    PendingToolCall,
)

PARSER_ADAPTER_NAME = "codex-jsonl"

UsageRow = sqlite3.Row | Mapping[str, object]


@dataclass(frozen=True)
class PendingEventRows:
    tool_call_rows: list[dict[str, object]]
    command_run_rows: list[dict[str, object]]
    file_event_rows: list[dict[str, object]]


def flush_pending_event_rows(
    conn: sqlite3.Connection,
    *,
    tool_calls: list[PendingToolCall],
    command_runs: list[PendingCommandRun],
    file_events: list[PendingFileEvent],
    usage_row: sqlite3.Row,
) -> None:
    """Persist normalized local events for one usage row."""

    upsert_pending_event_rows(
        conn,
        pending_event_rows(
            tool_calls=tool_calls,
            command_runs=command_runs,
            file_events=file_events,
            usage_row=usage_row,
        ),
    )


def pending_event_rows(
    *,
    tool_calls: list[PendingToolCall],
    command_runs: list[PendingCommandRun],
    file_events: list[PendingFileEvent],
    usage_row: UsageRow,
) -> PendingEventRows:
    return PendingEventRows(
        tool_call_rows=_tool_call_rows(tool_calls=tool_calls, usage_row=usage_row),
        command_run_rows=_command_run_rows(command_runs=command_runs, usage_row=usage_row),
        file_event_rows=_file_event_rows(file_events=file_events, usage_row=usage_row),
    )


def upsert_pending_event_rows(
    conn: sqlite3.Connection,
    rows: PendingEventRows,
) -> None:
    if rows.tool_call_rows:
        _upsert_tool_call_rows(conn, rows.tool_call_rows)
    if rows.command_run_rows:
        _upsert_command_run_rows(conn, rows.command_run_rows)
    if rows.file_event_rows:
        _upsert_file_event_rows(conn, rows.file_event_rows)


def _tool_call_rows(
    *,
    tool_calls: list[PendingToolCall],
    usage_row: UsageRow,
) -> list[dict[str, object]]:
    rows_by_key: dict[str, dict[str, object]] = {}
    for index, tool_call in enumerate(tool_calls):
        identity = tool_call.call_id or f"{tool_call.tool_name}:{tool_call.line_start}:{index}"
        tool_call_key = _stable_hash(f"tool:{usage_row['record_id']}:{identity}")
        row = _tool_call_row(
            tool_call_key=tool_call_key,
            tool_call=tool_call,
            usage_row=usage_row,
        )
        existing = rows_by_key.get(tool_call_key)
        if existing is None:
            rows_by_key[tool_call_key] = row
            continue
        _merge_tool_call_row(existing, row)
    return list(rows_by_key.values())


def _tool_call_row(
    *,
    tool_call_key: str,
    tool_call: PendingToolCall,
    usage_row: UsageRow,
) -> dict[str, object]:
    return {
        "tool_call_key": tool_call_key,
        "record_id": str(usage_row["record_id"]),
        "turn_key": None,
        "tool_name": tool_call.tool_name,
        "call_id": tool_call.call_id,
        "status": tool_call.status,
        "started_at": tool_call.started_at,
        "ended_at": tool_call.ended_at,
        "duration_ms": None,
        "argument_shape": tool_call.argument_shape,
        "output_size_bytes": tool_call.output_size_bytes,
        "source_file_id": usage_row["source_file_id"],
        "line_start": tool_call.line_start,
        "line_end": tool_call.line_end,
        "parser_adapter": usage_row["parser_adapter"] or PARSER_ADAPTER_NAME,
        "parser_version": usage_row["parser_version"] or PARSER_ADAPTER_VERSION,
        "parse_warnings_json": "[]",
    }


def _merge_tool_call_row(existing: dict[str, object], row: dict[str, object]) -> None:
    if row["tool_name"] != "function_call_output":
        existing["tool_name"] = row["tool_name"]
    existing["status"] = _merged_status(existing.get("status"), row.get("status"))
    existing["started_at"] = existing.get("started_at") or row.get("started_at")
    existing["ended_at"] = row.get("ended_at") or existing.get("ended_at")
    existing["argument_shape"] = existing.get("argument_shape") or row.get("argument_shape")
    existing["output_size_bytes"] = max(
        _int_value(existing.get("output_size_bytes")),
        _int_value(row.get("output_size_bytes")),
    )
    existing["line_start"] = min(_int_value(existing["line_start"]), _int_value(row["line_start"]))
    existing["line_end"] = max(_int_value(existing["line_end"]), _int_value(row["line_end"]))


def _command_run_rows(
    *,
    command_runs: list[PendingCommandRun],
    usage_row: UsageRow,
) -> list[dict[str, object]]:
    rows_by_key: dict[str, dict[str, object]] = {}
    for index, command_run in enumerate(command_runs):
        identity = (
            command_run.call_id
            or f"{command_run.command_root}:{command_run.command_label}:{command_run.line_start}:{index}"
        )
        command_run_key = _stable_hash(f"command:{usage_row['record_id']}:{identity}")
        row = _command_run_row(
            command_run_key=command_run_key,
            command_run=command_run,
            usage_row=usage_row,
        )
        existing = rows_by_key.get(command_run_key)
        if existing is None:
            rows_by_key[command_run_key] = row
            continue
        _merge_command_run_row(existing, row)
    return list(rows_by_key.values())


def _command_run_row(
    *,
    command_run_key: str,
    command_run: PendingCommandRun,
    usage_row: UsageRow,
) -> dict[str, object]:
    return {
        "command_run_key": command_run_key,
        "record_id": str(usage_row["record_id"]),
        "turn_key": None,
        "command_root": command_run.command_root,
        "command_label": command_run.command_label,
        "exit_code": command_run.exit_code,
        "status": command_run.status,
        "duration_ms": None,
        "output_size_bytes": command_run.output_size_bytes,
        "failure_category": command_run.failure_category,
        "retry_group": command_run.retry_group,
        "source_file_id": usage_row["source_file_id"],
        "line_start": command_run.line_start,
        "line_end": command_run.line_end,
        "parser_adapter": usage_row["parser_adapter"] or PARSER_ADAPTER_NAME,
        "parser_version": usage_row["parser_version"] or PARSER_ADAPTER_VERSION,
        "parse_warnings_json": "[]",
    }


def _merge_command_run_row(existing: dict[str, object], row: dict[str, object]) -> None:
    if row["command_root"] != "unknown_command":
        existing["command_root"] = row["command_root"]
        existing["command_label"] = row["command_label"]
    existing["status"] = _merged_status(existing.get("status"), row.get("status"))
    existing["exit_code"] = row.get("exit_code") if row.get("exit_code") is not None else existing.get("exit_code")
    existing["output_size_bytes"] = max(
        _int_value(existing.get("output_size_bytes")),
        _int_value(row.get("output_size_bytes")),
    )
    existing["line_start"] = min(_int_value(existing["line_start"]), _int_value(row["line_start"]))
    existing["line_end"] = max(_int_value(existing["line_end"]), _int_value(row["line_end"]))


def _file_event_rows(
    *,
    file_events: list[PendingFileEvent],
    usage_row: UsageRow,
) -> list[dict[str, object]]:
    rows_by_key: dict[str, dict[str, object]] = {}
    for index, file_event in enumerate(file_events):
        file_event_key = _stable_hash(
            f"file:{usage_row['record_id']}:{file_event.operation}:{file_event.path_hash}:{index}"
        )
        rows_by_key[file_event_key] = {
            "file_event_key": file_event_key,
            "record_id": str(usage_row["record_id"]),
            "turn_key": None,
            "operation": file_event.operation,
            "path_hash": file_event.path_hash,
            "path_basename": file_event.path_basename,
            "path_extension": file_event.path_extension,
            "path_identity": file_event.path_identity,
            "source_file_id": usage_row["source_file_id"],
            "line_start": file_event.line_start,
            "line_end": file_event.line_end,
            "parser_adapter": usage_row["parser_adapter"] or PARSER_ADAPTER_NAME,
            "parser_version": usage_row["parser_version"] or PARSER_ADAPTER_VERSION,
            "parse_warnings_json": "[]",
        }
    return list(rows_by_key.values())


def _upsert_tool_call_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    columns = (
        "tool_call_key",
        "record_id",
        "turn_key",
        "tool_name",
        "call_id",
        "status",
        "started_at",
        "ended_at",
        "duration_ms",
        "argument_shape",
        "output_size_bytes",
        "source_file_id",
        "line_start",
        "line_end",
        "parser_adapter",
        "parser_version",
        "parse_warnings_json",
    )
    conn.executemany(
        _upsert_sql("tool_calls", columns, "tool_call_key"),
        ([row[column] for column in columns] for row in rows),
    )


def _upsert_command_run_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    columns = (
        "command_run_key",
        "record_id",
        "turn_key",
        "command_root",
        "command_label",
        "exit_code",
        "status",
        "duration_ms",
        "output_size_bytes",
        "failure_category",
        "retry_group",
        "source_file_id",
        "line_start",
        "line_end",
        "parser_adapter",
        "parser_version",
        "parse_warnings_json",
    )
    conn.executemany(
        _upsert_sql("command_runs", columns, "command_run_key"),
        ([row[column] for column in columns] for row in rows),
    )


def _upsert_file_event_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    columns = (
        "file_event_key",
        "record_id",
        "turn_key",
        "operation",
        "path_hash",
        "path_basename",
        "path_extension",
        "path_identity",
        "source_file_id",
        "line_start",
        "line_end",
        "parser_adapter",
        "parser_version",
        "parse_warnings_json",
    )
    conn.executemany(
        _upsert_sql("file_events", columns, "file_event_key"),
        ([row[column] for column in columns] for row in rows),
    )


def _upsert_sql(table_name: str, columns: tuple[str, ...], primary_key: str) -> str:
    placeholders = ", ".join("?" for _column in columns)
    update_clause = ", ".join(f"{column}=excluded.{column}" for column in columns if column != primary_key)
    return (
        f"INSERT INTO {table_name} ({', '.join(columns)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT({primary_key}) DO UPDATE SET {update_clause}"
    )


def _merged_status(existing: object, incoming: object) -> object:
    if incoming == "completed" or existing == "completed":
        return "completed"
    return incoming or existing


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default
