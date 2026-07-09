"""Action hints for aggregate diagnostic facts."""

from __future__ import annotations

_DEFAULT_ACTION_HINT = "Open associated high-cost calls when the pattern needs more context."
_COMMAND_FAMILY_HINT = (
    "Review repeated validation or command loops when associated uncached input is high."
)
_UNKNOWN_COMMAND_HINT = (
    "Open associated calls when shell activity is high; command text is intentionally not stored."
)
_COMPACTION_HINT = "Review associated calls to see whether compaction reduced context or a fresh handoff would be cleaner."
_FACT_TYPE_ACTION_HINTS = {
    "mcp_server": (
        "Inspect repeated MCP activity and narrow tool result scope when associated costs are high."
    ),
    "mcp_tool": (
        "Inspect repeated MCP activity and narrow tool result scope when associated costs are high."
    ),
    "skill": (
        "Skill use is detected only from structured events; inspect associated calls for repeated workflow cost."
    ),
    "function": (
        "Check whether repeated function calls are carrying more context forward than needed."
    ),
    "tool": ("Check whether repeated tool activity is carrying forward more context than needed."),
}
_FACT_NAME_ACTION_HINTS = {
    "search_read_command": (
        "Inspect repeated search/read loops or narrow the task before loading more source context."
    ),
    "search_read_loop": (
        "Inspect repeated search/read loops or narrow the task before loading more source context."
    ),
    "retry_or_abort_loop": (
        "Inspect associated calls for interrupted work, rollback, or retry loops."
    ),
    "function_call_output": (
        "Inspect repeated large tool results when associated uncached input is high."
    ),
    "patch_applied": ("Likely productive work; verify tests or commit state captured the change."),
    "task_complete": ("Consider archiving or writing a handoff before reviving the thread later."),
    "turn_aborted": ("Inspect associated calls for interrupted work or retry loops."),
}


def action_hint(*, fact_type: str, fact_name: str) -> str:
    """Return a reader-facing action hint for an aggregate diagnostic fact."""

    if _is_compaction_fact(fact_type=fact_type, fact_name=fact_name):
        return _COMPACTION_HINT
    if fact_type == "command_family":
        return _command_family_action_hint(fact_name)
    return (
        _FACT_TYPE_ACTION_HINTS.get(fact_type)
        or _FACT_NAME_ACTION_HINTS.get(fact_name)
        or _DEFAULT_ACTION_HINT
    )


def _is_compaction_fact(*, fact_type: str, fact_name: str) -> bool:
    return fact_type == "compaction" or fact_name == "post_compaction"


def _command_family_action_hint(fact_name: str) -> str:
    if fact_name == "unknown_command":
        return _UNKNOWN_COMMAND_HINT
    return _COMMAND_FAMILY_HINT
