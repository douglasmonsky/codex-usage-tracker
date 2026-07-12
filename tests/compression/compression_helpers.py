from __future__ import annotations

from codex_usage_tracker.compression.evidence import (
    CallEvidence,
    CommandRunEvidence,
    CompressionEvidenceSnapshot,
    ContentFragmentEvidence,
    EvidenceCoverage,
    FileEventEvidence,
    ToolCallEvidence,
)
from codex_usage_tracker.compression.models import ComponentExposure


def snapshot(
    *,
    calls: tuple[CallEvidence, ...] = (),
    commands: tuple[CommandRunEvidence, ...] = (),
    files: tuple[FileEventEvidence, ...] = (),
    tools: tuple[ToolCallEvidence, ...] = (),
    fragments: tuple[ContentFragmentEvidence, ...] = (),
) -> CompressionEvidenceSnapshot:
    return CompressionEvidenceSnapshot(
        calls=calls,
        turns=(),
        tool_calls=tools,
        command_runs=commands,
        file_events=files,
        content_fragments=fragments,
        compactions=tuple(
            row for row in fragments if row.fragment_kind in {"compaction", "compaction_history"}
        ),
        coverage=EvidenceCoverage(
            call_count=len(calls),
            tool_call_count=len(tools),
            command_run_count=len(commands),
            file_event_count=len(files),
            content_fragment_count=len(fragments),
        ),
        source_revision="revision-1",
    )


def call(
    record_id: str,
    *,
    thread: str = "thread:one",
    uncached: int = 1_000,
    cached: int = 1_000,
    output: int = 100,
    reasoning: int = 20,
    cache_ratio: float = 0.5,
    context_percent: float = 0.5,
    previous: str | None = None,
    index: int = 1,
) -> CallEvidence:
    return CallEvidence(
        record_id=record_id,
        session_id=f"session-{record_id}",
        thread_key=thread,
        event_timestamp=f"2026-07-10T10:{index:02d}:00+00:00",
        model="gpt-5.5",
        effort="high",
        is_archived=False,
        thread_call_index=index,
        previous_record_id=previous,
        exposure=ComponentExposure(
            cached_input=cached,
            uncached_input=uncached,
            output=output,
            reasoning_output=reasoning,
        ),
        cache_ratio=cache_ratio,
        context_window_percent=context_percent,
    )


def command(
    key: str,
    record_id: str,
    root: str,
    *,
    retry_group: str | None = None,
    output_bytes: int = 400,
    exit_code: int = 0,
) -> CommandRunEvidence:
    return CommandRunEvidence(
        command_run_key=key,
        record_id=record_id,
        turn_key=f"turn-{record_id}",
        command_root=root,
        command_label=f"{root} synthetic",
        exit_code=exit_code,
        status="completed" if exit_code == 0 else "failed",
        output_size_bytes=output_bytes,
        retry_group=retry_group,
    )


def file_event(key: str, record_id: str, *, path_hash: str = "hash-a") -> FileEventEvidence:
    return FileEventEvidence(
        file_event_key=key,
        record_id=record_id,
        turn_key=f"turn-{record_id}",
        operation="read",
        path_hash=path_hash,
        path_identity=f"path:{path_hash}",
    )


def fragment(
    key: str,
    record_id: str,
    *,
    size_bytes: int = 400,
    kind: str = "message",
) -> ContentFragmentEvidence:
    return ContentFragmentEvidence(
        fragment_id=key,
        record_id=record_id,
        turn_key=f"turn-{record_id}",
        fragment_kind=kind,
        role="tool" if kind == "tool_output" else "user",
        safe_label=kind,
        content_hash=f"content-{key}",
        content_size_bytes=size_bytes,
        includes_raw_fragment=False,
    )


def tool(
    key: str,
    record_id: str,
    *,
    output_bytes: int,
    name: str = "exec_command",
) -> ToolCallEvidence:
    return ToolCallEvidence(
        tool_call_key=key,
        record_id=record_id,
        turn_key=f"turn-{record_id}",
        tool_name=name,
        status="completed",
        duration_ms=100,
        output_size_bytes=output_bytes,
    )
