"""Typed records for aggregate Codex usage data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from codex_usage_tracker.schema import USAGE_EVENT_COLUMN_NAMES


@dataclass(frozen=True)
class SessionInfo:
    """Metadata from Codex's session index."""

    session_id: str
    thread_name: str | None
    updated_at: str | None


@dataclass(frozen=True)
class TaskReceiptSignal:
    """Aggregate-only signal that a call is near durable task activity."""

    category: str
    confidence: str
    event_count: int
    first_event_timestamp: str | None
    last_event_timestamp: str | None
    first_source_line: int | None
    last_source_line: int | None
    evidence_scope: str
    reason: str | None


@dataclass(frozen=True)
class UsageEvent:
    """One aggregate token-count event from a Codex session log."""

    record_id: str
    session_id: str
    thread_name: str | None
    session_updated_at: str | None
    event_timestamp: str
    source_file: str
    line_number: int
    turn_id: str | None
    turn_timestamp: str | None
    cwd: str | None
    model: str | None
    effort: str | None
    current_date: str | None
    timezone: str | None
    call_initiator: str | None
    call_initiator_reason: str | None
    call_initiator_confidence: str | None
    is_archived: int
    thread_key: str | None
    thread_call_index: int | None
    previous_record_id: str | None
    next_record_id: str | None
    thread_source: str | None
    subagent_type: str | None
    agent_role: str | None
    agent_nickname: str | None
    parent_session_id: str | None
    parent_thread_name: str | None
    parent_session_updated_at: str | None
    model_context_window: int | None
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
    cumulative_input_tokens: int
    cumulative_cached_input_tokens: int
    cumulative_output_tokens: int
    cumulative_reasoning_output_tokens: int
    cumulative_total_tokens: int
    rate_limit_plan_type: str | None = None
    rate_limit_limit_id: str | None = None
    rate_limit_primary_used_percent: float | None = None
    rate_limit_primary_window_minutes: int | None = None
    rate_limit_primary_resets_at: int | None = None
    rate_limit_secondary_used_percent: float | None = None
    rate_limit_secondary_window_minutes: int | None = None
    rate_limit_secondary_resets_at: int | None = None
    source_byte_start: int | None = None
    source_byte_end: int | None = None
    turn_start_line: int | None = None
    turn_start_byte: int | None = None
    task_receipt_signals: tuple[TaskReceiptSignal, ...] = ()

    @property
    def uncached_input_tokens(self) -> int:
        return max(self.input_tokens - self.cached_input_tokens, 0)

    @property
    def cache_ratio(self) -> float:
        if self.input_tokens <= 0:
            return 0.0
        return self.cached_input_tokens / self.input_tokens

    @property
    def reasoning_output_ratio(self) -> float:
        if self.output_tokens <= 0:
            return 0.0
        return self.reasoning_output_tokens / self.output_tokens

    @property
    def context_window_percent(self) -> float:
        if not self.model_context_window:
            return 0.0
        return self.input_tokens / self.model_context_window

    def to_row(self) -> dict[str, object]:
        row = asdict(self)
        row["uncached_input_tokens"] = self.uncached_input_tokens
        row["cache_ratio"] = self.cache_ratio
        row["reasoning_output_ratio"] = self.reasoning_output_ratio
        row["context_window_percent"] = self.context_window_percent
        return {column: row[column] for column in USAGE_EVENT_COLUMN_NAMES}


@dataclass(frozen=True)
class RefreshResult:
    scanned_files: int
    parsed_events: int
    inserted_or_updated_events: int
    db_path: str
    skipped_events: int = 0
    parser_diagnostics: dict[str, int] = field(default_factory=dict)
    changed_source_files: int = 0
    append_source_files: int = 0
    full_reparse_source_files: int = 0
    inserted_records: int = 0
    deleted_records: int = 0
    affected_threads: int = 0
    skipped_downstream_work: bool = False
