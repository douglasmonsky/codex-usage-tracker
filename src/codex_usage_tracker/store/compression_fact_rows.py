"""Build detector-ready compression rows from one bounded parser batch."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.parser.state import PARSER_ADAPTER_VERSION
from codex_usage_tracker.store.compression_fact_contract import (
    COMPRESSION_FACTS_VERSION,
    MIN_TOOL_OUTPUT_BYTES,
    RELEVANT_COMMAND_ROOTS,
    ManifestAccumulator,
    call_revision_identity,
)
from codex_usage_tracker.store.compression_fact_manifest import (
    call_revision_row as _call_revision_row,
)
from codex_usage_tracker.store.compression_fact_manifest import (
    event_rows_by_record as _event_rows_by_record,
)
from codex_usage_tracker.store.compression_fact_manifest import (
    evidence_manifest as _evidence_manifest,
)
from codex_usage_tracker.store.compression_fact_manifest import (
    rows_by_record as _rows_by_record,
)
from codex_usage_tracker.store.compression_fact_manifest import (
    thread_key as _thread_key,
)
from codex_usage_tracker.store.content_index_models import _ExtractedContentRows

RECORD_FACT_COLUMNS = (
    "record_id",
    "source_file",
    "session_id",
    "thread_key",
    "event_timestamp",
    "model",
    "effort",
    "is_archived",
    "thread_call_index",
    "previous_record_id",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "estimated_cost_usd",
    "usage_credits",
    "cache_ratio",
    "context_window_percent",
    "turn_count",
    "indexed_call",
    "tool_call_count",
    "command_run_count",
    "file_event_count",
    "content_fragment_count",
    "compaction_count",
    "source_record_count",
    "parser_warning_record_count",
    "parser_adapter",
    "parser_version",
    "content_exposure_tokens",
    "tool_output_exposure_tokens",
    "manifest_count",
    "manifest_sum_hex",
    "manifest_xor_hex",
    "facts_version",
    "updated_at",
)
SEQUENCE_FACT_COLUMNS = (
    "fact_key",
    "record_id",
    "thread_key",
    "turn_key",
    "source_order",
    "fact_kind",
    "category",
    "status",
    "duration_ms",
    "output_size_bytes",
    "command_label",
    "exit_code",
    "retry_group",
    "path_identity",
    "exposure_tokens",
    "facts_version",
)


@dataclass(frozen=True)
class IngestionFactRows:
    """Fact rows and local source-order counters produced by one parser unit."""

    record_rows: list[list[object]]
    sequence_rows: list[list[object]]
    source_order_counts: dict[str, int]


def build_ingestion_fact_rows(
    *,
    events: Iterable[UsageEvent],
    content_rows: Iterable[_ExtractedContentRows],
) -> IngestionFactRows:
    """Build facts without touching SQLite so parser workers can share the work."""

    extracted_list = [rows for rows in content_rows if rows.has_usage_rows]
    turns = _rows_by_record(extracted_list, "turn_rows")
    fragments = _rows_by_record(extracted_list, "fragment_rows")
    tools = _event_rows_by_record(extracted_list, "tool_call_rows")
    commands = _event_rows_by_record(extracted_list, "command_run_rows")
    files = _event_rows_by_record(extracted_list, "file_event_rows")
    source_orders = {"tool": 0, "command": 0, "file": 0, "fragment": 0}
    record_rows: list[list[object]] = []
    sequence_rows: list[list[object]] = []
    for event in events:
        record_id = event.record_id
        record_turns = turns.get(record_id, [])
        record_fragments = fragments.get(record_id, [])
        record_tools = tools.get(record_id, [])
        record_commands = commands.get(record_id, [])
        record_files = files.get(record_id, [])
        manifest = _evidence_manifest(
            tool_rows=record_tools,
            command_rows=record_commands,
            file_rows=record_files,
            fragment_rows=record_fragments,
        )
        manifest.add("call", call_revision_identity(_call_revision_row(event)))
        record_rows.append(
            _record_fact_values(
                event,
                turn_rows=record_turns,
                fragment_rows=record_fragments,
                tool_rows=record_tools,
                command_rows=record_commands,
                file_rows=record_files,
                manifest=manifest,
            )
        )
        sequence_rows.extend(
            _sequence_fact_values(
                event,
                fragment_rows=record_fragments,
                tool_rows=record_tools,
                command_rows=record_commands,
                file_rows=record_files,
                source_orders=source_orders,
            )
        )
    return IngestionFactRows(
        record_rows=record_rows,
        sequence_rows=sequence_rows,
        source_order_counts=source_orders,
    )


def source_order_group(fact_kind: str) -> str:
    return {
        "tool_output": "tool",
        "command": "command",
        "file_read": "file",
        "content_turn": "fragment",
    }[fact_kind]


def _sequence_fact_values(
    event: UsageEvent,
    *,
    fragment_rows: list[dict[str, object]],
    tool_rows: list[dict[str, object]],
    command_rows: list[dict[str, object]],
    file_rows: list[dict[str, object]],
    source_orders: dict[str, int],
) -> list[list[object]]:
    thread_key = _thread_key(event)
    rows = _tool_sequence_values(event, thread_key, tool_rows, source_orders)
    rows.extend(_command_sequence_values(event, thread_key, command_rows, source_orders))
    rows.extend(_file_sequence_values(event, thread_key, file_rows, source_orders))
    rows.extend(_content_sequence_values(event, thread_key, fragment_rows, source_orders))
    return rows


def _tool_sequence_values(
    event: UsageEvent,
    thread_key: str,
    tool_rows: list[dict[str, object]],
    source_orders: dict[str, int],
) -> list[list[object]]:
    rows: list[list[object]] = []
    for row in tool_rows:
        source_orders["tool"] += 1
        output_size = _as_int(row.get("output_size_bytes"))
        if output_size < MIN_TOOL_OUTPUT_BYTES:
            continue
        rows.append(
            [
                f"tool:{row['tool_call_key']}",
                event.record_id,
                thread_key,
                row.get("turn_key"),
                source_orders["tool"],
                "tool_output",
                str(row.get("tool_name") or ""),
                row.get("status"),
                row.get("duration_ms"),
                output_size,
                None,
                None,
                None,
                None,
                _token_estimate(output_size),
                COMPRESSION_FACTS_VERSION,
            ]
        )
    return rows


def _command_sequence_values(
    event: UsageEvent,
    thread_key: str,
    command_rows: list[dict[str, object]],
    source_orders: dict[str, int],
) -> list[list[object]]:
    rows: list[list[object]] = []
    for row in command_rows:
        source_orders["command"] += 1
        command_root = str(row.get("command_root") or "")
        if command_root not in RELEVANT_COMMAND_ROOTS:
            continue
        output_size = _as_int(row.get("output_size_bytes"))
        rows.append(
            [
                f"command:{row['command_run_key']}",
                event.record_id,
                thread_key,
                row.get("turn_key"),
                source_orders["command"],
                "command",
                command_root,
                row.get("status"),
                None,
                output_size,
                command_root,
                row.get("exit_code"),
                row.get("retry_group"),
                None,
                _token_estimate(output_size),
                COMPRESSION_FACTS_VERSION,
            ]
        )
    return rows


def _file_sequence_values(
    event: UsageEvent,
    thread_key: str,
    file_rows: list[dict[str, object]],
    source_orders: dict[str, int],
) -> list[list[object]]:
    rows: list[list[object]] = []
    for row in file_rows:
        source_orders["file"] += 1
        path_hash = str(row.get("path_hash") or "")
        if row.get("operation") != "read" or not path_hash:
            continue
        rows.append(
            [
                f"file:{row['file_event_key']}",
                event.record_id,
                thread_key,
                row.get("turn_key"),
                source_orders["file"],
                "file_read",
                path_hash,
                None,
                None,
                0,
                None,
                None,
                None,
                path_hash,
                0,
                COMPRESSION_FACTS_VERSION,
            ]
        )
    return rows


def _content_sequence_values(
    event: UsageEvent,
    thread_key: str,
    fragment_rows: list[dict[str, object]],
    source_orders: dict[str, int],
) -> list[list[object]]:
    content_groups: dict[tuple[str, str], list[int]] = {}
    for row in fragment_rows:
        source_orders["fragment"] += 1
        turn_key = str(row.get("turn_key") or "")
        if not turn_key:
            continue
        size = _as_int(row.get("content_size_bytes"))
        group = content_groups.setdefault(
            (event.record_id, turn_key),
            [source_orders["fragment"], 0, 0],
        )
        group[1] += size
        group[2] += _token_estimate(size)
    rows: list[list[object]] = []
    for (record_id, turn_key), (source_order, output_size, exposure) in content_groups.items():
        rows.append(
            [
                f"content:{record_id}:{turn_key}",
                record_id,
                thread_key,
                turn_key,
                source_order,
                "content_turn",
                "",
                None,
                None,
                output_size,
                None,
                None,
                None,
                None,
                exposure,
                COMPRESSION_FACTS_VERSION,
            ]
        )
    return rows


def _record_fact_values(
    event: UsageEvent,
    *,
    turn_rows: list[dict[str, object]],
    fragment_rows: list[dict[str, object]],
    tool_rows: list[dict[str, object]],
    command_rows: list[dict[str, object]],
    file_rows: list[dict[str, object]],
    manifest: ManifestAccumulator,
) -> list[object]:
    content_tokens = _sum_estimated_tokens(fragment_rows, "content_size_bytes")
    tool_tokens = _sum_estimated_tokens(tool_rows, "output_size_bytes")
    command_tokens = _sum_estimated_tokens(command_rows, "output_size_bytes")
    indexed_call = max(
        (_as_int(row.get("indexed_content_included")) for row in turn_rows),
        default=0,
    )
    manifest_count, manifest_sum, manifest_xor = manifest.storage_values()
    return [
        event.record_id,
        event.source_file,
        event.session_id,
        _thread_key(event),
        event.event_timestamp,
        event.model,
        event.effort,
        event.is_archived,
        event.thread_call_index,
        event.previous_record_id,
        event.cached_input_tokens,
        event.uncached_input_tokens,
        event.output_tokens,
        event.reasoning_output_tokens,
        None,
        None,
        event.cache_ratio,
        event.context_window_percent,
        len(turn_rows),
        indexed_call,
        len(tool_rows),
        len(command_rows),
        len(file_rows),
        len(fragment_rows),
        sum(
            1
            for row in fragment_rows
            if str(row.get("fragment_kind") or "") in {"compaction", "compaction_history"}
        ),
        1,
        0,
        "codex-jsonl",
        PARSER_ADAPTER_VERSION,
        content_tokens,
        max(tool_tokens, command_tokens),
        manifest_count,
        manifest_sum,
        manifest_xor,
        COMPRESSION_FACTS_VERSION,
        event.event_timestamp,
    ]


def _token_estimate(size_bytes: int) -> int:
    return (size_bytes + 3) // 4


def _sum_estimated_tokens(rows: list[dict[str, object]], key: str) -> int:
    return sum(_token_estimate(_as_int(row.get(key))) for row in rows)


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (float, str, bytes, bytearray)):
        return int(value)
    return 0
