"""Classify structured diagnostic facts from safe aggregate labels."""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Callable
from typing import Any

from codex_usage_tracker.core.models import DiagnosticFact

FactFactory = Callable[..., DiagnosticFact]

SAFE_STRUCTURED_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")

SKILL_EVENT_TYPES = frozenset(
    {
        "skill_completed",
        "skill_invoked",
        "skill_selected",
        "skill_started",
        "skill_used",
    }
)

SHELL_TOOL_NAMES = frozenset(
    {
        "bash",
        "exec_command",
        "functions.exec_command",
        "run_command",
        "shell",
        "terminal",
    }
)

SEARCH_READ_COMMANDS = frozenset(
    {
        "cat",
        "fd",
        "find",
        "grep",
        "head",
        "ls",
        "nl",
        "rg",
        "sed",
        "tail",
        "wc",
    }
)

def structured_tool_and_skill_facts(
    *,
    entry_type: object,
    payload: dict[str, Any],
    payload_type: str,
    timestamp: str | None,
    line_number: int,
    fact_factory: FactFactory,
) -> tuple[DiagnosticFact, ...]:
    """Classify safe structured labels without persisting args outputs."""
    tool_label, response_facts = _response_item_tool_facts(
        entry_type=entry_type,
        payload=payload,
        payload_type=payload_type,
        timestamp=timestamp,
        line_number=line_number,
        fact_factory=fact_factory,
    )
    mcp_tool_label, mcp_facts = _mcp_event_facts(
        entry_type=entry_type,
        payload=payload,
        payload_type=payload_type,
        timestamp=timestamp,
        line_number=line_number,
        fact_factory=fact_factory,
    )
    if mcp_tool_label is not None:
        tool_label = mcp_tool_label
    return (
        *response_facts,
        *mcp_facts,
        *_skill_event_facts(
            payload=payload,
            payload_type=payload_type,
            timestamp=timestamp,
            line_number=line_number,
            fact_factory=fact_factory,
        ),
        *_command_activity_facts(
            payload=payload,
            tool_label=tool_label,
            timestamp=timestamp,
            line_number=line_number,
            fact_factory=fact_factory,
        ),
    )


def _response_item_tool_facts(
    *,
    entry_type: object,
    payload: dict[str, Any],
    payload_type: str,
    timestamp: str | None,
    line_number: int,
    fact_factory: FactFactory,
) -> tuple[str | None, tuple[DiagnosticFact, ...]]:
    if entry_type != "response_item" or payload_type not in {
        "function_call",
        "function_call_output",
    }:
        return None, ()
    tool_label = _safe_structured_label(payload.get("name"))
    if not tool_label:
        return None, ()
    facts = [
        fact_factory(
            fact_type="function",
            fact_name=tool_label,
            category="function",
            confidence="medium" if payload_type == "function_call_output" else "low",
            timestamp=timestamp,
            line_number=line_number,
        )
    ]
    if _looks_like_mcp_tool_label(tool_label):
        facts.append(
            fact_factory(
                fact_type="mcp_tool",
                fact_name=tool_label,
                category="mcp",
                confidence="medium",
                timestamp=timestamp,
                line_number=line_number,
            )
        )
    return tool_label, tuple(facts)


def _mcp_event_facts(
    *,
    entry_type: object,
    payload: dict[str, Any],
    payload_type: str,
    timestamp: str | None,
    line_number: int,
    fact_factory: FactFactory,
) -> tuple[str | None, tuple[DiagnosticFact, ...]]:
    if entry_type != "event_msg" or payload_type not in {
        "mcp_tool_call_begin",
        "mcp_tool_call_end",
    }:
        return None, ()
    confidence = "high" if payload_type == "mcp_tool_call_end" else "medium"
    facts: list[DiagnosticFact] = []
    tool_label = _safe_structured_label(
        payload.get("tool_name") or payload.get("name") or payload.get("tool")
    )
    if tool_label:
        facts.append(
            fact_factory(
                fact_type="mcp_tool",
                fact_name=tool_label,
                category="mcp",
                confidence=confidence,
                timestamp=timestamp,
                line_number=line_number,
            )
        )
    server_label = _safe_structured_label(
        payload.get("server_name") or payload.get("server") or payload.get("mcp_server")
    )
    if server_label:
        facts.append(
            fact_factory(
                fact_type="mcp_server",
                fact_name=server_label,
                category="mcp",
                confidence=confidence,
                timestamp=timestamp,
                line_number=line_number,
            )
        )
    return tool_label, tuple(facts)


def _skill_event_facts(
    *,
    payload: dict[str, Any],
    payload_type: str,
    timestamp: str | None,
    line_number: int,
    fact_factory: FactFactory,
) -> tuple[DiagnosticFact, ...]:
    skill_label = _skill_label(payload)
    if not skill_label or (payload_type not in SKILL_EVENT_TYPES and "skill" not in payload):
        return ()
    return (
        fact_factory(
            fact_type="skill",
            fact_name=skill_label,
            category="skill",
            confidence="high" if payload_type in SKILL_EVENT_TYPES else "medium",
            timestamp=timestamp,
            line_number=line_number,
        ),
    )


def _command_activity_facts(
    *,
    payload: dict[str, Any],
    tool_label: str | None,
    timestamp: str | None,
    line_number: int,
    fact_factory: FactFactory,
) -> tuple[DiagnosticFact, ...]:
    command = _shell_command_from_payload(payload, tool_label=tool_label)
    if command is None:
        return ()
    family = _command_family(command)
    facts = [
        fact_factory(
            fact_type="command_family",
            fact_name=family,
            category="command",
            confidence="medium" if family != "unknown_command" else "low",
            timestamp=timestamp,
            line_number=line_number,
        )
    ]
    if _is_search_read_command(command):
        facts.append(
            fact_factory(
                fact_type="activity",
                fact_name="search_read_command",
                category="read",
                confidence="medium",
                timestamp=timestamp,
                line_number=line_number,
            )
        )
    return tuple(facts)




def _skill_label(payload: dict[str, Any]) -> str | None:
    label = _safe_structured_label(
        payload.get("skill_name") or payload.get("skill_id") or payload.get("skill")
    )
    if label:
        return label
    skill = payload.get("skill")
    if isinstance(skill, dict):
        return _safe_structured_label(skill.get("name") or skill.get("id"))
    return None


def _shell_command_from_payload(
    payload: dict[str, Any],
    *,
    tool_label: str | None,
) -> str | None:
    if not tool_label or not _is_shell_tool_label(tool_label):
        return None
    for key in ("cmd", "command"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    arguments = _arguments_dict(payload.get("arguments"))
    for key in ("cmd", "command"):
        value = arguments.get(key)
        if isinstance(value, str):
            return value
    return None


def _arguments_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(loaded, dict):
            return loaded
    return {}


def _command_family(command: str) -> str:
    tokens = _command_tokens(command)
    tokens = _strip_command_wrappers(tokens)
    if not tokens:
        return "unknown_command"
    base = _command_basename(tokens[0])
    if base in {"py.test", "pytest"}:
        return "pytest"
    if _is_python_command(base):
        module_family = _python_module_family(tokens)
        return module_family or "python"
    normalized = {
        "git": "git",
        "mypy": "mypy",
        "node": "node",
        "npm": "npm",
        "pnpm": "pnpm",
        "ruff": "ruff",
    }.get(base)
    return normalized or "unknown_command"


def _command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def _strip_command_wrappers(tokens: list[str]) -> list[str]:
    remaining = list(tokens)
    while remaining:
        while remaining and _looks_like_assignment(remaining[0]):
            remaining.pop(0)
        if not remaining:
            break
        base = _command_basename(remaining[0])
        if base in {"command", "env", "sudo"}:
            remaining.pop(0)
            continue
        break
    return remaining


def _looks_like_assignment(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token))


def _python_module_family(tokens: list[str]) -> str | None:
    for index, token in enumerate(tokens[:-1]):
        if token != "-m":
            continue
        module = _command_basename(tokens[index + 1]).split(".", 1)[0]
        if module in {"mypy", "pytest", "ruff"}:
            return module
        return None
    return None


def _is_search_read_command(command: str) -> bool:
    tokens = _strip_command_wrappers(_command_tokens(command))
    return bool(tokens and _command_basename(tokens[0]) in SEARCH_READ_COMMANDS)


def _is_python_command(base: str) -> bool:
    return base == "py" or base == "python" or base.startswith("python")


def _command_basename(token: str) -> str:
    return re.split(r"[\\/]", token)[-1].lower()


def _is_shell_tool_label(label: str) -> bool:
    lowered = label.lower()
    suffix = lowered.rsplit(".", 1)[-1].rsplit("__", 1)[-1]
    return lowered in SHELL_TOOL_NAMES or suffix in SHELL_TOOL_NAMES


def _looks_like_mcp_tool_label(label: str) -> bool:
    return label.startswith("mcp__")


def _safe_structured_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not SAFE_STRUCTURED_LABEL_RE.fullmatch(stripped):
        return None
    return stripped.lower()
