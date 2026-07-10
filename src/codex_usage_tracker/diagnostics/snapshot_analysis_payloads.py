"""Payload assembly for aggregate source-log diagnostics."""

from __future__ import annotations

from collections import Counter
from typing import Any

from codex_usage_tracker.diagnostics.snapshot_events import (
    READ_PRODUCTIVITY_NOTE,
    path_privacy_metadata,
    ratio,
    simple_rows,
)
from codex_usage_tracker.diagnostics.snapshot_rows import (
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
            "outputs_missing_original_token_count": int(
                sum(counters["output_missing_count"].values())
            ),
            "original_token_sum": int(sum(counters["output_token_sum"].values())),
        },
        "functions": function_rows(
            function_calls=counters["function_calls"],
            function_outputs=counters["function_outputs"],
            function_record_ids=counters["function_record_ids"],
            output_with_count=counters["output_with_count"],
            output_missing_count=counters["output_missing_count"],
            output_token_sum=counters["output_token_sum"],
        ),
        "command_roots": command_output_rows(
            command_calls=counters["command_calls"],
            command_record_ids=counters["command_record_ids"],
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
            command_record_ids=counters["command_record_ids"],
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
            git_interaction_record_ids=counters["git_interaction_record_ids"],
            git_interaction_with_count=counters["git_interaction_with_count"],
            git_interaction_missing_count=counters["git_interaction_missing_count"],
            git_interaction_token_sum=counters["git_interaction_token_sum"],
        ),
        "categories": simple_rows(counters["git_interactions_by_category"], key_name="category"),
        "mutability": simple_rows(
            counters["git_interactions_by_mutability"], key_name="mutability"
        ),
    }


def _file_reads_payload(counters: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": {
            "read_commands": counters["read_command_count"],
            "read_events": len(counters["read_events"]),
            "unique_paths_read": len(counters["read_path_refs"]),
            "read_events_with_output_count": int(
                sum(counters["read_events_with_count_by_reader"].values())
            ),
            "read_events_missing_output_count": int(
                sum(counters["read_events_missing_count_by_reader"].values())
            ),
            "allocated_output_token_sum": int(sum(counters["read_tokens_by_reader"].values())),
        },
        "by_reader": read_reader_rows(
            read_events_by_reader=counters["read_events_by_reader"],
            read_reader_record_ids=counters["read_reader_record_ids"],
            read_events_with_count_by_reader=counters["read_events_with_count_by_reader"],
            read_events_missing_count_by_reader=counters["read_events_missing_count_by_reader"],
            read_tokens_by_reader=counters["read_tokens_by_reader"],
        ),
        "top_paths": read_path_rows(
            read_path_refs=counters["read_path_refs"],
            read_events_by_path=counters["read_events_by_path"],
            read_path_record_ids=counters["read_path_record_ids"],
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
            modification_path_record_ids=counters["file_modification_path_record_ids"],
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
            "read_events_modified_later_pct": ratio(
                read_modified_count, len(counters["read_events"])
            ),
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
            read_reader_record_ids=counters["read_reader_record_ids"],
        ),
        "top_modified_paths": read_productivity_path_rows(
            read_path_refs=counters["read_path_refs"],
            read_events_by_path=counters["read_events_by_path"],
            read_modified_by_path=counters["read_modified_by_path"],
            read_path_record_ids=counters["read_path_record_ids"],
        ),
        "path_privacy": path_privacy_metadata(),
    }
