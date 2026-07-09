"""SQLite schema metadata for aggregate usage events."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class UsageColumn:
    """One persisted usage_events column."""

    name: str
    declaration: str
    alter_type: str
    repairable: bool = False


USAGE_EVENT_COLUMNS = (
    UsageColumn("record_id", "TEXT PRIMARY KEY", "TEXT"),
    UsageColumn("session_id", "TEXT NOT NULL", "TEXT"),
    UsageColumn("thread_name", "TEXT", "TEXT", repairable=True),
    UsageColumn("session_updated_at", "TEXT", "TEXT", repairable=True),
    UsageColumn("event_timestamp", "TEXT NOT NULL", "TEXT"),
    UsageColumn("source_file", "TEXT NOT NULL", "TEXT"),
    UsageColumn("line_number", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("turn_id", "TEXT", "TEXT", repairable=True),
    UsageColumn("turn_timestamp", "TEXT", "TEXT", repairable=True),
    UsageColumn("cwd", "TEXT", "TEXT", repairable=True),
    UsageColumn("model", "TEXT", "TEXT", repairable=True),
    UsageColumn("effort", "TEXT", "TEXT", repairable=True),
    UsageColumn("current_date", "TEXT", "TEXT", repairable=True),
    UsageColumn("timezone", "TEXT", "TEXT", repairable=True),
    UsageColumn("call_initiator", "TEXT", "TEXT", repairable=True),
    UsageColumn("call_initiator_reason", "TEXT", "TEXT", repairable=True),
    UsageColumn("call_initiator_confidence", "TEXT", "TEXT", repairable=True),
    UsageColumn(
        "is_archived",
        "INTEGER NOT NULL DEFAULT 0",
        "INTEGER NOT NULL DEFAULT 0",
        repairable=True,
    ),
    UsageColumn("thread_key", "TEXT", "TEXT", repairable=True),
    UsageColumn("thread_call_index", "INTEGER", "INTEGER", repairable=True),
    UsageColumn("previous_record_id", "TEXT", "TEXT", repairable=True),
    UsageColumn("next_record_id", "TEXT", "TEXT", repairable=True),
    UsageColumn("thread_source", "TEXT", "TEXT", repairable=True),
    UsageColumn("subagent_type", "TEXT", "TEXT", repairable=True),
    UsageColumn("agent_role", "TEXT", "TEXT", repairable=True),
    UsageColumn("agent_nickname", "TEXT", "TEXT", repairable=True),
    UsageColumn("parent_session_id", "TEXT", "TEXT", repairable=True),
    UsageColumn("parent_thread_name", "TEXT", "TEXT", repairable=True),
    UsageColumn("parent_session_updated_at", "TEXT", "TEXT", repairable=True),
    UsageColumn("model_context_window", "INTEGER", "INTEGER", repairable=True),
    UsageColumn("input_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("cached_input_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("output_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("reasoning_output_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("total_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("cumulative_input_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("cumulative_cached_input_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("cumulative_output_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("cumulative_reasoning_output_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("cumulative_total_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("rate_limit_plan_type", "TEXT", "TEXT", repairable=True),
    UsageColumn("rate_limit_limit_id", "TEXT", "TEXT", repairable=True),
    UsageColumn("rate_limit_primary_used_percent", "REAL", "REAL", repairable=True),
    UsageColumn("rate_limit_primary_window_minutes", "INTEGER", "INTEGER", repairable=True),
    UsageColumn("rate_limit_primary_resets_at", "INTEGER", "INTEGER", repairable=True),
    UsageColumn("rate_limit_secondary_used_percent", "REAL", "REAL", repairable=True),
    UsageColumn("rate_limit_secondary_window_minutes", "INTEGER", "INTEGER", repairable=True),
    UsageColumn("rate_limit_secondary_resets_at", "INTEGER", "INTEGER", repairable=True),
    UsageColumn("uncached_input_tokens", "INTEGER NOT NULL", "INTEGER"),
    UsageColumn("cache_ratio", "REAL NOT NULL", "REAL"),
    UsageColumn("reasoning_output_ratio", "REAL NOT NULL", "REAL"),
    UsageColumn("context_window_percent", "REAL NOT NULL", "REAL"),
)

USAGE_EVENT_COLUMN_NAMES = tuple(column.name for column in USAGE_EVENT_COLUMNS)
USAGE_EVENT_CREATE_COLUMNS_SQL = ",\n            ".join(
    f"{column.name} {column.declaration}" for column in USAGE_EVENT_COLUMNS
)
USAGE_EVENT_SCHEMA_CHECKSUM = hashlib.sha256(
    "|".join(f"{column.name}:{column.declaration}" for column in USAGE_EVENT_COLUMNS).encode(
        "utf-8"
    )
).hexdigest()
USAGE_EVENT_REPAIR_COLUMNS = {
    column.name: column.alter_type for column in USAGE_EVENT_COLUMNS if column.repairable
}

DIAGNOSTIC_FACT_COLUMN_NAMES = (
    "record_id",
    "fact_type",
    "fact_name",
    "fact_category",
    "event_count",
    "confidence",
    "first_event_timestamp",
    "last_event_timestamp",
    "first_source_line",
    "last_source_line",
    "evidence_scope",
    "raw_content_included",
)
