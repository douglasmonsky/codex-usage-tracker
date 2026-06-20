"""Shared constants for diagnostic snapshot reports."""

DIAGNOSTIC_OVERVIEW_SCHEMA = "codex-usage-tracker-diagnostic-overview-v1"
DIAGNOSTIC_TOOL_OUTPUT_SCHEMA = "codex-usage-tracker-diagnostic-tool-output-v1"
DIAGNOSTIC_COMMANDS_SCHEMA = "codex-usage-tracker-diagnostic-commands-v1"
DIAGNOSTIC_FILE_READS_SCHEMA = "codex-usage-tracker-diagnostic-file-reads-v1"
DIAGNOSTIC_READ_PRODUCTIVITY_SCHEMA = "codex-usage-tracker-diagnostic-read-productivity-v1"
DIAGNOSTIC_CONCENTRATION_SCHEMA = "codex-usage-tracker-diagnostic-concentration-v1"
DIAGNOSTIC_BATCH_REFRESH_SCHEMA = "codex-usage-tracker-diagnostic-snapshot-refresh-v1"
DIAGNOSTIC_OVERVIEW_SECTION = "overview"
DIAGNOSTIC_TOOL_OUTPUT_SECTION = "tool-output"
DIAGNOSTIC_COMMANDS_SECTION = "commands"
DIAGNOSTIC_FILE_READS_SECTION = "file-reads"
DIAGNOSTIC_READ_PRODUCTIVITY_SECTION = "read-productivity"
DIAGNOSTIC_CONCENTRATION_SECTION = "concentration"
DIAGNOSTIC_HISTORY_ACTIVE = "active"
DIAGNOSTIC_HISTORY_ALL = "all"
DIAGNOSTIC_SNAPSHOT_NOTES = [
    "Diagnostic snapshots are recomputed only by explicit diagnostic refresh.",
    "Snapshot totals are aggregate-only and do not include raw context.",
]
