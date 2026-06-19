"""Aggregate-only diagnostic fact classification for Codex JSONL events."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import asdict, replace
from typing import Any

from codex_usage_tracker.models import DiagnosticFact

EVIDENCE_SCOPE_BETWEEN_TOKEN_COUNTS = "between_token_counts"
SAFE_STRUCTURED_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SKILL_EVENT_TYPES = frozenset({
    "skill_completed",
    "skill_invoked",
    "skill_selected",
    "skill_started",
    "skill_used",
})
SHELL_TOOL_NAMES = frozenset({
    "bash",
    "exec_command",
    "functions.exec_command",
    "run_command",
    "shell",
    "terminal",
})
SEARCH_READ_COMMANDS = frozenset({
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
})

CONFIDENCE_ORDER = {
    "unknown": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


def diagnostic_facts_from_envelope(
    envelope: object,
    *,
    line_number: int,
) -> tuple[DiagnosticFact, ...]:
    """Return safe diagnostic facts from one JSONL envelope."""

    if not isinstance(envelope, dict):
        return ()
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    entry_type = envelope.get("type")
    payload_type = _optional_str(payload.get("type"))
    timestamp = _optional_str(envelope.get("timestamp"))
    if payload_type is None:
        return ()

    facts: list[DiagnosticFact] = []
    if entry_type == "event_msg":
        mapping = {
            "context_compacted": ("compaction", "post_compaction", "context", "high"),
            "patch_apply_end": ("outcome", "patch_applied", "patch", "high"),
            "task_complete": ("outcome", "task_complete", "task", "high"),
            "thread_rolled_back": ("outcome", "thread_rolled_back", "failure", "high"),
            "turn_aborted": ("outcome", "turn_aborted", "turn", "high"),
            "mcp_tool_call_end": ("tool", "mcp_tool_call_end", "mcp", "medium"),
            "web_search_end": ("tool", "web_search_end", "search", "medium"),
            "image_generation_end": ("tool", "image_generation_end", "media", "medium"),
        }
        classification = mapping.get(payload_type)
        if classification is not None:
            fact_type, fact_name, category, confidence = classification
            facts.append(
                _fact(
                    fact_type=fact_type,
                    fact_name=fact_name,
                    category=category,
                    confidence=confidence,
                    timestamp=timestamp,
                    line_number=line_number,
                )
            )
        facts.extend(
            _structured_tool_and_skill_facts(
                entry_type=entry_type,
                payload=payload,
                payload_type=payload_type,
                timestamp=timestamp,
                line_number=line_number,
            )
        )
        return tuple(facts)

    if entry_type == "response_item":
        mapping = {
            "function_call": ("tool", "function_call", "function", "low"),
            "function_call_output": ("tool", "function_call_output", "function", "medium"),
            "tool_search_call": ("tool", "tool_search_call", "search", "low"),
            "tool_search_output": ("tool", "tool_search_output", "search", "medium"),
        }
        classification = mapping.get(payload_type)
        if classification is not None:
            fact_type, fact_name, category, confidence = classification
            facts.append(
                _fact(
                    fact_type=fact_type,
                    fact_name=fact_name,
                    category=category,
                    confidence=confidence,
                    timestamp=timestamp,
                    line_number=line_number,
                )
            )
        facts.extend(
            _structured_tool_and_skill_facts(
                entry_type=entry_type,
                payload=payload,
                payload_type=payload_type,
                timestamp=timestamp,
                line_number=line_number,
            )
        )
        return tuple(facts)

    return ()


def _structured_tool_and_skill_facts(
    *,
    entry_type: object,
    payload: dict[str, Any],
    payload_type: str,
    timestamp: str | None,
    line_number: int,
) -> tuple[DiagnosticFact, ...]:
    """Classify safe structured labels without persisting args or outputs."""

    facts: list[DiagnosticFact] = []
    tool_label: str | None = None
    if entry_type == "response_item" and payload_type in {
        "function_call",
        "function_call_output",
    }:
        tool_label = _safe_structured_label(payload.get("name"))
        if tool_label:
            facts.append(
                _fact(
                    fact_type="function",
                    fact_name=tool_label,
                    category="function",
                    confidence="medium" if payload_type == "function_call_output" else "low",
                    timestamp=timestamp,
                    line_number=line_number,
                )
            )
            if _looks_like_mcp_tool_label(tool_label):
                facts.append(
                    _fact(
                        fact_type="mcp_tool",
                        fact_name=tool_label,
                        category="mcp",
                        confidence="medium",
                        timestamp=timestamp,
                        line_number=line_number,
                    )
                )
    if entry_type == "event_msg" and payload_type in {
        "mcp_tool_call_begin",
        "mcp_tool_call_end",
    }:
        tool_label = _safe_structured_label(
            payload.get("tool_name") or payload.get("name") or payload.get("tool")
        )
        if tool_label:
            facts.append(
                _fact(
                    fact_type="mcp_tool",
                    fact_name=tool_label,
                    category="mcp",
                    confidence="high" if payload_type == "mcp_tool_call_end" else "medium",
                    timestamp=timestamp,
                    line_number=line_number,
                )
            )
        server_label = _safe_structured_label(
            payload.get("server_name") or payload.get("server") or payload.get("mcp_server")
        )
        if server_label:
            facts.append(
                _fact(
                    fact_type="mcp_server",
                    fact_name=server_label,
                    category="mcp",
                    confidence="high" if payload_type == "mcp_tool_call_end" else "medium",
                    timestamp=timestamp,
                    line_number=line_number,
                )
            )
    skill_label = _skill_label(payload)
    if skill_label and (payload_type in SKILL_EVENT_TYPES or "skill" in payload):
        facts.append(
            _fact(
                fact_type="skill",
                fact_name=skill_label,
                category="skill",
                confidence="high" if payload_type in SKILL_EVENT_TYPES else "medium",
                timestamp=timestamp,
                line_number=line_number,
            )
        )
    command = _shell_command_from_payload(payload, tool_label=tool_label)
    if command is not None:
        family = _command_family(command)
        facts.append(
            _fact(
                fact_type="command_family",
                fact_name=family,
                category="command",
                confidence="medium" if family != "unknown_command" else "low",
                timestamp=timestamp,
                line_number=line_number,
            )
        )
        if _is_search_read_command(command):
            facts.append(
                _fact(
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


def _with_derived_loop_facts(
    segment: tuple[DiagnosticFact, ...],
) -> tuple[DiagnosticFact, ...]:
    enriched = tuple(segment)
    search_read_facts = [
        fact
        for fact in segment
        if fact.fact_category in {"read", "search"}
        or (fact.fact_type == "activity" and fact.fact_name == "search_read_command")
    ]
    search_read_count = sum(fact.event_count for fact in search_read_facts)
    if search_read_count >= 3:
        enriched = add_diagnostic_fact(
            enriched,
            _derived_loop_fact(
                fact_name="search_read_loop",
                category="search",
                event_count=search_read_count,
                source_facts=search_read_facts,
            ),
        )
    retry_facts = [
        fact
        for fact in segment
        if fact.fact_category in {"failure", "retry"}
        or fact.fact_name in {"thread_rolled_back", "turn_aborted"}
    ]
    retry_count = sum(fact.event_count for fact in retry_facts)
    if retry_count >= 2:
        enriched = add_diagnostic_fact(
            enriched,
            _derived_loop_fact(
                fact_name="retry_or_abort_loop",
                category="failure",
                event_count=retry_count,
                source_facts=retry_facts,
            ),
        )
    return enriched


def _derived_loop_fact(
    *,
    fact_name: str,
    category: str,
    event_count: int,
    source_facts: list[DiagnosticFact],
) -> DiagnosticFact:
    first_source_line = _min_optional_int(
        *[fact.first_source_line for fact in source_facts]
    )
    last_source_line = _max_optional_int(*[fact.last_source_line for fact in source_facts])
    return DiagnosticFact(
        record_id=None,
        fact_type="loop",
        fact_name=fact_name,
        fact_category=category,
        event_count=event_count,
        confidence="medium",
        first_event_timestamp=_timestamp_for_source_line(
            source_facts,
            source_line=first_source_line,
            first=True,
        ),
        last_event_timestamp=_timestamp_for_source_line(
            source_facts,
            source_line=last_source_line,
            first=False,
        ),
        first_source_line=first_source_line,
        last_source_line=last_source_line,
        evidence_scope=EVIDENCE_SCOPE_BETWEEN_TOKEN_COUNTS,
        raw_content_included=0,
    )


def _timestamp_for_source_line(
    facts: list[DiagnosticFact],
    *,
    source_line: int | None,
    first: bool,
) -> str | None:
    for fact in sorted(
        facts,
        key=lambda item: _source_line_sort_key(
            item.first_source_line if first else item.last_source_line
        ),
    ):
        candidate_line = fact.first_source_line if first else fact.last_source_line
        if candidate_line == source_line:
            return fact.first_event_timestamp if first else fact.last_event_timestamp
    return None


def add_diagnostic_fact(
    segment: tuple[DiagnosticFact, ...],
    fact: DiagnosticFact,
) -> tuple[DiagnosticFact, ...]:
    """Merge one fact into the pending between-token-count segment."""

    by_key = {(item.fact_type, item.fact_name): item for item in segment}
    key = (fact.fact_type, fact.fact_name)
    existing = by_key.get(key)
    by_key[key] = fact if existing is None else merge_diagnostic_facts(existing, fact)
    return tuple(by_key.values())


def merge_diagnostic_facts(
    existing: DiagnosticFact,
    incoming: DiagnosticFact,
) -> DiagnosticFact:
    """Combine repeated facts without storing raw evidence."""

    return replace(
        existing,
        event_count=existing.event_count + incoming.event_count,
        confidence=strongest_confidence([existing.confidence, incoming.confidence]),
        first_event_timestamp=_earliest_event_timestamp(existing, incoming),
        last_event_timestamp=_latest_event_timestamp(existing, incoming),
        first_source_line=_min_optional_int(existing.first_source_line, incoming.first_source_line),
        last_source_line=_max_optional_int(existing.last_source_line, incoming.last_source_line),
        raw_content_included=max(existing.raw_content_included, incoming.raw_content_included),
    )


def assign_record_id_to_diagnostic_facts(
    segment: tuple[DiagnosticFact, ...],
    *,
    record_id: str,
) -> tuple[DiagnosticFact, ...]:
    """Attach pending segment facts to the token-count row they describe."""

    enriched_segment = _with_derived_loop_facts(segment)
    return tuple(
        replace(fact, record_id=record_id)
        for fact in sorted(enriched_segment, key=lambda item: (item.fact_type, item.fact_name))
    )


def diagnostic_fact_to_json(fact: DiagnosticFact) -> dict[str, Any]:
    """Encode a pending diagnostic fact for parser-state persistence."""

    payload = asdict(fact)
    payload.pop("record_id", None)
    return payload


def diagnostic_fact_from_json(value: object) -> DiagnosticFact | None:
    """Decode a pending diagnostic fact from aggregate-only parser state."""

    if not isinstance(value, dict):
        return None
    fact_type = _optional_str(value.get("fact_type"))
    fact_name = _optional_str(value.get("fact_name"))
    if not fact_type or not fact_name:
        return None
    event_count = _positive_int(value.get("event_count")) or 1
    return DiagnosticFact(
        record_id=None,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=_optional_str(value.get("fact_category")),
        event_count=event_count,
        confidence=_optional_str(value.get("confidence")) or "medium",
        first_event_timestamp=_optional_str(value.get("first_event_timestamp")),
        last_event_timestamp=_optional_str(value.get("last_event_timestamp")),
        first_source_line=_positive_int(value.get("first_source_line")),
        last_source_line=_positive_int(value.get("last_source_line")),
        evidence_scope=(
            _optional_str(value.get("evidence_scope")) or EVIDENCE_SCOPE_BETWEEN_TOKEN_COUNTS
        ),
        raw_content_included=1 if value.get("raw_content_included") == 1 else 0,
    )


def strongest_confidence(values: list[str]) -> str:
    """Return the strongest confidence label in a stable order."""

    if not values:
        return "unknown"
    return max(values, key=lambda value: CONFIDENCE_ORDER.get(value, 0))


def _fact(
    *,
    fact_type: str,
    fact_name: str,
    category: str,
    confidence: str,
    timestamp: str | None,
    line_number: int,
) -> DiagnosticFact:
    return DiagnosticFact(
        record_id=None,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=category,
        event_count=1,
        confidence=confidence,
        first_event_timestamp=timestamp,
        last_event_timestamp=timestamp,
        first_source_line=line_number,
        last_source_line=line_number,
        evidence_scope=EVIDENCE_SCOPE_BETWEEN_TOKEN_COUNTS,
        raw_content_included=0,
    )


def _earliest_event_timestamp(
    existing: DiagnosticFact,
    incoming: DiagnosticFact,
) -> str | None:
    if _source_line_sort_key(incoming.first_source_line) < _source_line_sort_key(
        existing.first_source_line
    ):
        return incoming.first_event_timestamp
    return existing.first_event_timestamp


def _latest_event_timestamp(
    existing: DiagnosticFact,
    incoming: DiagnosticFact,
) -> str | None:
    if _source_line_sort_key(incoming.last_source_line) >= _source_line_sort_key(
        existing.last_source_line
    ):
        return incoming.last_event_timestamp
    return existing.last_event_timestamp


def _source_line_sort_key(value: int | None) -> int:
    return value if value is not None else -1


def _min_optional_int(*items: int | None) -> int | None:
    values = [value for value in items if value is not None]
    return min(values) if values else None


def _max_optional_int(*items: int | None) -> int | None:
    values = [value for value in items if value is not None]
    return max(values) if values else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None
