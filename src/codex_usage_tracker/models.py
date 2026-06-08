"""Typed records for aggregate Codex usage data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class SessionInfo:
    """Metadata from Codex's session index."""

    session_id: str
    thread_name: str | None
    updated_at: str | None


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
    source_provider: str
    source_app: str
    source_format: str
    provider_request_id: str | None
    turn_id: str | None
    turn_timestamp: str | None
    cwd: str | None
    model: str | None
    effort: str | None
    current_date: str | None
    timezone: str | None
    thread_source: str | None
    subagent_type: str | None
    agent_role: str | None
    agent_nickname: str | None
    parent_session_id: str | None
    parent_thread_name: str | None
    parent_session_updated_at: str | None
    model_context_window: int | None
    cache_creation_input_tokens: int
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
        return row


@dataclass(frozen=True)
class RefreshResult:
    scanned_files: int
    parsed_events: int
    inserted_or_updated_events: int
    db_path: str
    skipped_events: int = 0
    parser_diagnostics: dict[str, int] = field(default_factory=dict)
