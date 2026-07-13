"""Manifest and row-group helpers for ingestion-built compression facts."""

from __future__ import annotations

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.store.compression_fact_contract import (
    ManifestAccumulator,
    command_revision_identity,
    file_revision_identity,
    fragment_revision_identity,
    tool_revision_identity,
)
from codex_usage_tracker.store.content_index_models import _ExtractedContentRows


def evidence_manifest(
    *,
    tool_rows: list[dict[str, object]],
    command_rows: list[dict[str, object]],
    file_rows: list[dict[str, object]],
    fragment_rows: list[dict[str, object]],
) -> ManifestAccumulator:
    manifest = ManifestAccumulator()
    _add_tool_revisions(manifest, tool_rows)
    _add_command_revisions(manifest, command_rows)
    _add_file_revisions(manifest, file_rows)
    _add_fragment_revisions(manifest, fragment_rows)
    return manifest


def rows_by_record(
    extracted_rows: list[_ExtractedContentRows],
    attribute: str,
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for extracted in extracted_rows:
        for row in getattr(extracted, attribute):
            grouped.setdefault(str(row["record_id"]), []).append(row)
    return grouped


def event_rows_by_record(
    extracted_rows: list[_ExtractedContentRows],
    attribute: str,
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for extracted in extracted_rows:
        for row in getattr(extracted.event_rows, attribute):
            grouped.setdefault(str(row["record_id"]), []).append(row)
    return grouped


def thread_key(event: UsageEvent) -> str:
    return event.thread_key or event.thread_name or event.session_id


def call_revision_row(event: UsageEvent) -> tuple[object, ...]:
    return (
        event.record_id,
        event.session_id,
        thread_key(event),
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
        event.cache_ratio,
        event.context_window_percent,
    )


def _add_tool_revisions(
    manifest: ManifestAccumulator,
    rows: list[dict[str, object]],
) -> None:
    for row in rows:
        manifest.add(
            "tool",
            tool_revision_identity(
                (
                    row["tool_call_key"],
                    row["record_id"],
                    row.get("turn_key"),
                    row["tool_name"],
                    row.get("status"),
                    row.get("duration_ms"),
                    row.get("output_size_bytes"),
                )
            ),
        )


def _add_command_revisions(
    manifest: ManifestAccumulator,
    rows: list[dict[str, object]],
) -> None:
    for row in rows:
        root = row["command_root"]
        manifest.add(
            "command",
            command_revision_identity(
                (
                    row["command_run_key"],
                    row["record_id"],
                    row.get("turn_key"),
                    root,
                    root,
                    row.get("exit_code"),
                    row.get("status"),
                    row.get("output_size_bytes"),
                    row.get("retry_group"),
                )
            ),
        )


def _add_file_revisions(
    manifest: ManifestAccumulator,
    rows: list[dict[str, object]],
) -> None:
    for row in rows:
        path_hash = row["path_hash"]
        manifest.add(
            "file",
            file_revision_identity(
                (
                    row["file_event_key"],
                    row["record_id"],
                    row.get("turn_key"),
                    row["operation"],
                    path_hash,
                    path_hash,
                )
            ),
        )


def _add_fragment_revisions(
    manifest: ManifestAccumulator,
    rows: list[dict[str, object]],
) -> None:
    for row in rows:
        kind = row["fragment_kind"]
        manifest.add(
            "fragment",
            fragment_revision_identity(
                (
                    row["fragment_id"],
                    row["record_id"],
                    row.get("turn_key"),
                    kind,
                    row.get("role"),
                    kind,
                    row["content_hash"],
                    row.get("content_size_bytes"),
                    row.get("includes_raw_fragment"),
                )
            ),
        )
