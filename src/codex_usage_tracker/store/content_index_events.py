"""Extract normalized local event rows from Codex JSONL payloads."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.command_parsing import command_root_and_child

_SHELL_TOOL_NAMES = {
    "bash",
    "exec_command",
    "functions.exec_command",
    "run_command",
    "shell",
    "terminal",
    "write_stdin",
}
_READ_COMMAND_ROOTS = {"cat", "find", "grep", "head", "nl", "rg", "sed", "strings", "tail", "wc"}
_PATH_PAYLOAD_KEYS = ("changed_paths", "paths", "files", "modified_paths")
_PATH_VALUE_KEYS = ("path", "file", "filename", "new_path", "old_path")
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_SENSITIVE_PREFIXES = ("sk-", "sk_", "ghp_", "github_pat_", "xox")


@dataclass(frozen=True)
class PendingToolCall:
    """Tool-call evidence waiting for a linked usage row."""

    tool_name: str
    call_id: str | None
    status: str | None
    started_at: str | None
    ended_at: str | None
    argument_shape: str
    output_size_bytes: int
    line_start: int
    line_end: int


@dataclass(frozen=True)
class PendingCommandRun:
    """Command-run evidence waiting for a linked usage row."""

    call_id: str | None
    command_root: str
    command_label: str
    status: str | None
    exit_code: int | None
    output_size_bytes: int
    failure_category: str | None
    retry_group: str | None
    line_start: int
    line_end: int


@dataclass(frozen=True)
class PendingFileEvent:
    """File/path evidence waiting for a linked usage row."""

    operation: str
    path_hash: str
    path_basename: str
    path_extension: str
    path_identity: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class PendingLocalEvents:
    """Normalized event rows extracted from one source-log envelope."""

    tool_calls: list[PendingToolCall]
    command_runs: list[PendingCommandRun]
    file_events: list[PendingFileEvent]


def extract_pending_local_events(
    *,
    envelope: dict[str, Any],
    payload: dict[str, Any],
    line_number: int,
    timestamp: str | None,
) -> PendingLocalEvents:
    """Return normalized tool, command, and file events for one JSONL entry."""

    entry_type = envelope.get("type")
    payload_type = _optional_str(payload.get("type")) or ""
    if entry_type == "response_item":
        return _response_item_events(
            payload=payload,
            payload_type=payload_type,
            line_number=line_number,
            timestamp=timestamp,
        )
    if entry_type == "event_msg":
        return _event_msg_events(
            payload=payload,
            payload_type=payload_type,
            line_number=line_number,
            timestamp=timestamp,
        )
    return PendingLocalEvents(tool_calls=[], command_runs=[], file_events=[])


def _response_item_events(
    *,
    payload: dict[str, Any],
    payload_type: str,
    line_number: int,
    timestamp: str | None,
) -> PendingLocalEvents:
    if payload_type == "function_call":
        return _function_call_events(payload=payload, line_number=line_number, timestamp=timestamp)
    if payload_type == "function_call_output":
        return _function_output_events(
            payload=payload, line_number=line_number, timestamp=timestamp
        )
    return PendingLocalEvents(tool_calls=[], command_runs=[], file_events=[])


def _event_msg_events(
    *,
    payload: dict[str, Any],
    payload_type: str,
    line_number: int,
    timestamp: str | None,
) -> PendingLocalEvents:
    if payload_type in {"mcp_tool_call_begin", "mcp_tool_call_end"}:
        return _mcp_tool_events(
            payload=payload,
            payload_type=payload_type,
            line_number=line_number,
            timestamp=timestamp,
        )
    if payload_type == "patch_apply_end":
        return PendingLocalEvents(
            tool_calls=[],
            command_runs=[],
            file_events=_file_events_from_payload(
                payload=payload,
                operation="modify",
                line_number=line_number,
            ),
        )
    return PendingLocalEvents(tool_calls=[], command_runs=[], file_events=[])


def _function_call_events(
    *,
    payload: dict[str, Any],
    line_number: int,
    timestamp: str | None,
) -> PendingLocalEvents:
    tool_name = _optional_str(payload.get("name")) or "function_call"
    call_id = _optional_str(payload.get("call_id"))
    tool_call = PendingToolCall(
        tool_name=_safe_label(tool_name) or "function_call",
        call_id=call_id,
        status="started",
        started_at=timestamp,
        ended_at=None,
        argument_shape=_argument_shape(payload.get("arguments")),
        output_size_bytes=0,
        line_start=line_number,
        line_end=line_number,
    )
    command = _shell_command_from_payload(payload=payload, tool_name=tool_name)
    command_runs: list[PendingCommandRun] = []
    file_events: list[PendingFileEvent] = []
    if command:
        command_root, command_label = _command_root_and_label(command)
        command_runs.append(
            PendingCommandRun(
                call_id=call_id,
                command_root=command_root,
                command_label=command_label,
                status="started",
                exit_code=None,
                output_size_bytes=0,
                failure_category=None,
                retry_group=None,
                line_start=line_number,
                line_end=line_number,
            )
        )
        file_events.extend(
            _file_events_from_command(command, root=command_root, line_number=line_number)
        )
    file_events.extend(
        _file_events_from_payload(payload=payload, operation="modify", line_number=line_number)
    )
    return PendingLocalEvents(
        tool_calls=[tool_call], command_runs=command_runs, file_events=file_events
    )


def _function_output_events(
    *,
    payload: dict[str, Any],
    line_number: int,
    timestamp: str | None,
) -> PendingLocalEvents:
    output = payload.get("output")
    return PendingLocalEvents(
        tool_calls=[
            PendingToolCall(
                tool_name="function_call_output",
                call_id=_optional_str(payload.get("call_id")),
                status="completed",
                started_at=None,
                ended_at=timestamp,
                argument_shape="",
                output_size_bytes=_output_size_bytes(output),
                line_start=line_number,
                line_end=line_number,
            )
        ],
        command_runs=[
            PendingCommandRun(
                call_id=_optional_str(payload.get("call_id")),
                command_root="unknown_command",
                command_label="unknown_command",
                status="completed",
                exit_code=_exit_code(output),
                output_size_bytes=_output_size_bytes(output),
                failure_category=None,
                retry_group=None,
                line_start=line_number,
                line_end=line_number,
            )
        ],
        file_events=[],
    )


def _mcp_tool_events(
    *,
    payload: dict[str, Any],
    payload_type: str,
    line_number: int,
    timestamp: str | None,
) -> PendingLocalEvents:
    tool_name = (
        _optional_str(payload.get("tool_name"))
        or _optional_str(payload.get("name"))
        or _optional_str(payload.get("server_name"))
        or payload_type
    )
    is_end = payload_type == "mcp_tool_call_end"
    return PendingLocalEvents(
        tool_calls=[
            PendingToolCall(
                tool_name=_safe_label(tool_name) or payload_type,
                call_id=_optional_str(payload.get("call_id")) or _optional_str(payload.get("id")),
                status="completed" if is_end else "started",
                started_at=None if is_end else timestamp,
                ended_at=timestamp if is_end else None,
                argument_shape=_argument_shape(payload.get("arguments")),
                output_size_bytes=_output_size_bytes(payload.get("output")),
                line_start=line_number,
                line_end=line_number,
            )
        ],
        command_runs=[],
        file_events=[],
    )


def _shell_command_from_payload(*, payload: dict[str, Any], tool_name: str) -> str | None:
    if not _is_shell_tool(tool_name):
        return None
    return _command_from_arguments(payload.get("arguments")) or _command_from_mapping(payload)


def _is_shell_tool(tool_name: str) -> bool:
    lowered = tool_name.lower()
    suffix = lowered.rsplit(".", 1)[-1].rsplit("__", 1)[-1]
    return lowered in _SHELL_TOOL_NAMES or suffix in _SHELL_TOOL_NAMES


def _command_from_arguments(arguments: object) -> str | None:
    if isinstance(arguments, dict):
        return _command_from_mapping(arguments)
    if not isinstance(arguments, str):
        return None
    try:
        loaded = json.loads(arguments)
    except json.JSONDecodeError:
        return None
    return _command_from_mapping(loaded) if isinstance(loaded, dict) else None


def _command_from_mapping(mapping: dict[str, Any]) -> str | None:
    command = mapping.get("cmd") or mapping.get("command")
    return command if isinstance(command, str) and command.strip() else None


def _command_root_and_label(command: str) -> tuple[str, str]:
    root, child = command_root_and_child(command)
    safe_root = _safe_command_label(root)
    if safe_root == "unknown_command":
        return "unknown_command", "unknown_command"
    safe_child = _safe_command_child(safe_root, child)
    if safe_child is None:
        return safe_root, safe_root
    return safe_root, f"{safe_root} {safe_child}"


def _safe_command_child(root: str, child: str) -> str | None:
    if root in _READ_COMMAND_ROOTS:
        return None
    if child in {"<none>", "<arg>", "<target>", "unknown"} or child.startswith("-"):
        return None
    safe_child = _safe_command_label(child)
    return None if safe_child == "unknown_command" else safe_child


def _command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _file_events_from_command(
    command: str,
    *,
    root: str,
    line_number: int,
) -> list[PendingFileEvent]:
    if root not in _READ_COMMAND_ROOTS:
        return []
    events: list[PendingFileEvent] = []
    for path in _read_path_tokens(command, root=root):
        event = _file_event(path=path, operation="read", line_number=line_number)
        if event is not None:
            events.append(event)
    return events


def _read_path_tokens(command: str, *, root: str) -> list[str]:
    tokens = _command_tokens(command)
    if not tokens:
        return []
    args = tokens[1:]
    if root in {"cat", "head", "tail", "nl", "wc", "strings"}:
        return [token for token in args if _looks_like_path_argument(token)]
    if root in {"rg", "grep", "find"}:
        return [token for token in args if _looks_like_path_argument(token)]
    if root == "sed":
        return [token for token in args if _looks_like_path_argument(token)]
    return []


def _looks_like_path_argument(token: str) -> bool:
    if not token or token == "-" or token.startswith("-"):
        return False
    if "=" in token and not token.startswith(("./", "../", "/")):
        return False
    if token.startswith(("$", "`")) or "://" in token:
        return False
    return "/" in token or "." in Path(token).name or token in {".", ".."}


def _file_events_from_payload(
    *,
    payload: dict[str, Any],
    operation: str,
    line_number: int,
) -> list[PendingFileEvent]:
    paths: list[str] = []
    for key in _PATH_PAYLOAD_KEYS:
        paths.extend(_path_values(payload.get(key)))
    paths.extend(_path_values(payload.get("changes")))
    paths.extend(_patch_header_paths(payload))

    events: list[PendingFileEvent] = []
    seen: set[str] = set()
    for path in paths:
        event = _file_event(path=path, operation=operation, line_number=line_number)
        if event is None or event.path_hash in seen:
            continue
        seen.add(event.path_hash)
        events.append(event)
    return events


def _path_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple):
        paths: list[str] = []
        for item in value:
            paths.extend(_path_values(item))
        return paths
    if isinstance(value, dict):
        dict_paths: list[str] = []
        for key in _PATH_VALUE_KEYS:
            dict_paths.extend(_path_values(value.get(key)))
        return dict_paths
    return []


def _patch_header_paths(payload: dict[str, Any]) -> list[str]:
    values = [payload.get("input"), payload.get("arguments")]
    paths: list[str] = []
    for value in values:
        text = _patch_text(value)
        if not text:
            continue
        for line in text.splitlines():
            paths.extend(_patch_path_from_line(line))
    return paths


def _patch_text(value: object) -> str | None:
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return value
        return _patch_text(loaded)
    if isinstance(value, dict):
        for key in ("patch", "input", "text"):
            nested = _patch_text(value.get(key))
            if nested:
                return nested
    return None


def _patch_path_from_line(line: str) -> list[str]:
    prefixes = {
        "*** Add File: ": "add",
        "*** Update File: ": "modify",
        "*** Delete File: ": "delete",
        "*** Move to: ": "move",
    }
    for prefix in prefixes:
        if line.startswith(prefix):
            return [line.removeprefix(prefix).strip()]
    return []


def _file_event(
    *,
    path: str,
    operation: str,
    line_number: int,
) -> PendingFileEvent | None:
    normalized = path.strip().rstrip("/")
    if not normalized or normalized in {"-", ">", ">>", "|"}:
        return None
    if normalized.startswith(("$", "`")) or "://" in normalized:
        return None
    basename = Path(normalized).name if normalized not in {".", ".."} else normalized
    if not basename:
        return None
    path_hash = _stable_hash(normalized)[:12]
    extension = Path(basename).suffix.lower()
    return PendingFileEvent(
        operation=operation,
        path_hash=path_hash,
        path_basename=basename[:120],
        path_extension=extension[:40],
        path_identity=path_hash,
        line_start=line_number,
        line_end=line_number,
    )


def _argument_shape(value: object) -> str:
    if value in (None, ""):
        return ""
    shaped_value = _shape_value(value)
    return json.dumps(shaped_value, sort_keys=True, separators=(",", ":"))[:1000]


def _shape_value(value: object) -> object:
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return "str"
        return _shape_value(loaded)
    if isinstance(value, dict):
        shaped: dict[str, object] = {}
        for key, nested in sorted(value.items(), key=lambda item: str(item[0])):
            safe_key = _safe_label(str(key)) or "field"
            shaped[safe_key] = _type_name(nested)
        return shaped
    if isinstance(value, list | tuple):
        return [_type_name(item) for item in value[:10]]
    return _type_name(value)


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list | tuple):
        return "array"
    return type(value).__name__


def _safe_label(value: str) -> str | None:
    stripped = value.strip()
    lowered = stripped.lower()
    if not stripped or lowered.startswith(_SENSITIVE_PREFIXES):
        return None
    if "/" in stripped or "\\" in stripped:
        return None
    return lowered if _SAFE_LABEL_RE.fullmatch(stripped) else None


def _safe_command_label(value: str) -> str:
    return _safe_label(Path(value).name) or "unknown_command"


def _output_size_bytes(value: object) -> int:
    if not isinstance(value, str):
        return 0
    return len(value.encode("utf-8"))


def _exit_code(output: object) -> int | None:
    if not isinstance(output, str):
        return None
    match = re.search(r"Process exited with code (?P<code>-?\d+)", output)
    if not match:
        return None
    return int(match.group("code"))


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
