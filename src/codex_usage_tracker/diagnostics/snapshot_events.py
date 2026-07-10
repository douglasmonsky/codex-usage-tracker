"""Safe event parsing helpers for diagnostic snapshot reports."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.command_parsing import (
    GIT_COMMAND_ROOTS,
    SENSITIVE_LABEL_PREFIXES,
    command_tokens,
    git_operation,
    looks_like_assignment,
    strip_command_wrappers,
)

SAFE_PATH_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:@*+-]{1,80}$")
SHELL_TOOL_NAMES = {
    "bash",
    "exec_command",
    "functions.exec_command",
    "run_command",
    "shell",
    "terminal",
    "write_stdin",
}
READ_COMMAND_ROOTS = {"cat", "find", "grep", "head", "nl", "rg", "sed", "strings", "tail", "wc"}
SEARCH_READ_ROOTS = {"find", "rg"}
GIT_OPERATION_CATEGORIES = {
    "add": ("local_mutation", "local_mutation"),
    "branch": ("read_only", "read_only"),
    "checkout": ("local_mutation", "local_mutation"),
    "cherry-pick": ("local_mutation", "local_mutation"),
    "clean": ("local_mutation", "local_mutation"),
    "clone": ("remote_ref", "remote_ref"),
    "commit": ("local_mutation", "local_mutation"),
    "describe": ("read_only", "read_only"),
    "diff": ("read_only", "read_only"),
    "fetch": ("remote_ref", "remote_ref"),
    "log": ("read_only", "read_only"),
    "merge": ("local_mutation", "local_mutation"),
    "mv": ("local_mutation", "local_mutation"),
    "pull": ("remote_ref", "remote_ref"),
    "push": ("remote_ref", "remote_ref"),
    "rebase": ("local_mutation", "local_mutation"),
    "remote": ("read_only", "read_only"),
    "reset": ("local_mutation", "local_mutation"),
    "restore": ("local_mutation", "local_mutation"),
    "rev-parse": ("read_only", "read_only"),
    "rm": ("local_mutation", "local_mutation"),
    "show": ("read_only", "read_only"),
    "stash": ("local_mutation", "local_mutation"),
    "status": ("read_only", "read_only"),
    "submodule": ("remote_ref", "remote_ref"),
    "switch": ("local_mutation", "local_mutation"),
    "tag": ("local_mutation", "local_mutation"),
}
GH_OPERATION_CATEGORIES = {
    "api": ("api", "github_remote"),
    "auth": ("auth_config", "github_remote"),
    "config": ("auth_config", "github_remote"),
    "issue": ("issue", "github_remote"),
    "pr": ("pull_request", "github_remote"),
    "release": ("release", "github_remote"),
    "repo": ("repository", "github_remote"),
    "run": ("workflow", "github_remote"),
    "workflow": ("workflow", "github_remote"),
}
READ_PRODUCTIVITY_NOTE = (
    "Read-to-modify counts are temporal correlations: a read is counted when the same "
    "privacy-preserving path key is modified later in the same source log."
)
ORIGINAL_OUTPUT_RE = re.compile(
    r"^Chunk ID: (?P<chunk>[^\n]+)\n"
    r"Wall time: (?P<wall>[^\n]+)\n"
    r"(?:(?P<status>Process exited with code -?\d+|Process running with session ID \d+)\n)?"
    r"Original token count: (?P<count>\d+)\n",
    re.S,
)


def shell_command_from_payload(payload: dict[str, Any], *, function_name: str) -> str | None:
    if not is_shell_tool(function_name):
        return None
    return _shell_command_from_arguments(payload.get("arguments")) or _command_from_mapping(payload)


def _shell_command_from_arguments(arguments: object) -> str | None:
    if isinstance(arguments, str):
        return _shell_command_from_json_arguments(arguments)
    if isinstance(arguments, dict):
        return _command_from_mapping(arguments)
    return None


def _shell_command_from_json_arguments(arguments: str) -> str | None:
    try:
        loaded = json.loads(arguments)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict):
        return _command_from_mapping(loaded)
    return None


def _command_from_mapping(mapping: dict[str, Any]) -> str | None:
    command = mapping.get("cmd") or mapping.get("command")
    return command if isinstance(command, str) else None


def is_shell_tool(function_name: str) -> bool:
    lowered = function_name.lower()
    suffix = lowered.rsplit(".", 1)[-1].rsplit("__", 1)[-1]
    return lowered in SHELL_TOOL_NAMES or suffix in SHELL_TOOL_NAMES


def read_path_refs_from_command(command: str, *, root: str) -> list[dict[str, str]]:
    if root not in READ_COMMAND_ROOTS:
        return []
    tokens = strip_command_wrappers(command_tokens(command))
    if not tokens:
        return []
    path_tokens = _read_path_tokens(root=root, tokens=tokens)
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for token in path_tokens:
        path_ref = _path_ref_from_token(token)
        if path_ref is None or path_ref["path_key"] in seen:
            continue
        seen.add(path_ref["path_key"])
        refs.append(path_ref)
    return refs


def git_interaction_from_command(command: str, *, root: str) -> dict[str, str] | None:
    if root not in GIT_COMMAND_ROOTS:
        return None
    tokens = strip_command_wrappers(command_tokens(command))
    if not tokens:
        return None
    operation = git_operation(tokens, root=root)
    if operation is None:
        return None
    if root == "git":
        category, mutability = GIT_OPERATION_CATEGORIES.get(operation, ("other", "unknown"))
    else:
        category, mutability = GH_OPERATION_CATEGORIES.get(operation, ("other", "github_remote"))
    return {
        "root": root,
        "operation": operation,
        "category": category,
        "mutability": mutability,
    }


def read_reader(root: str) -> str:
    if root in SEARCH_READ_ROOTS:
        return f"search_path_scan:{root}"
    return f"direct_file_read:{root}"


def modified_path_refs(payload: dict[str, Any]) -> list[dict[str, str]]:
    paths: list[str] = []
    if payload.get("type") == "patch_apply_end":
        for key in ("changed_paths", "paths", "files", "modified_paths"):
            paths.extend(_path_values(payload.get(key)))
        paths.extend(_path_values(payload.get("changes")))
    if _is_apply_patch_tool_payload(payload):
        paths.extend(_patch_header_paths(payload.get("input")))
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in paths:
        path_ref = _path_ref_from_token(path)
        if path_ref is None or path_ref["path_key"] in seen:
            continue
        seen.add(path_ref["path_key"])
        refs.append(path_ref)
    return refs


def _is_apply_patch_tool_payload(payload: dict[str, Any]) -> bool:
    name = payload.get("name")
    return isinstance(name, str) and name.rsplit(".", 1)[-1] == "apply_patch"


def _patch_header_paths(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    paths: list[str] = []
    for line in value.splitlines():
        if line.startswith("*** Add File: "):
            paths.append(line.removeprefix("*** Add File: ").strip())
        elif line.startswith("*** Update File: "):
            paths.append(line.removeprefix("*** Update File: ").strip())
        elif line.startswith("*** Delete File: "):
            paths.append(line.removeprefix("*** Delete File: ").strip())
        elif line.startswith("*** Move to: "):
            paths.append(line.removeprefix("*** Move to: ").strip())
    return paths


def path_privacy_metadata() -> dict[str, str]:
    return {
        "label_policy": "basename_only",
        "hash_policy": "sha256_12",
        "normal": "basename_only_with_hash",
        "redacted": "basename_only_with_hash",
        "strict": "hash_available_for_hiding_labels",
    }


def original_output_count(output: object) -> int | None:
    if not isinstance(output, str):
        return None
    match = ORIGINAL_OUTPUT_RE.match(output)
    if not match:
        return None
    return int(match.group("count"))


def optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def simple_rows(
    counter: Counter[str],
    *,
    key_name: str = "name",
) -> list[dict[str, Any]]:
    return [
        {key_name: name, "count": int(count)}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def unique_path_rows(paths: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in paths:
        path_hash = path["path_hash"]
        if path_hash in seen:
            continue
        seen.add(path_hash)
        rows.append({"path_label": path["path_label"], "path_hash": path_hash})
    return rows[:25]


def allocate_token_count(count: int, bucket_count: int) -> list[int]:
    if bucket_count <= 0:
        return []
    base = count // bucket_count
    remainder = count % bucket_count
    return [base + (1 if index < remainder else 0) for index in range(bucket_count)]


def int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value:
        return int(value)
    return 0


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _read_path_tokens(*, root: str, tokens: list[str]) -> list[str]:
    args = tokens[1:]
    if root == "find":
        return _find_path_tokens(args)
    if root == "rg":
        return _ripgrep_path_tokens(args)
    if root == "grep":
        operands = _non_option_operands(args, root=root)
        return operands[1:] if len(operands) > 1 else []
    if root == "sed":
        operands = _non_option_operands(args, root=root)
        return operands[1:] if len(operands) > 1 else []
    return _non_option_operands(args, root=root)


def _find_path_tokens(args: list[str]) -> list[str]:
    paths: list[str] = []
    for token in args:
        if _is_shell_separator(token):
            break
        if token == "--":
            continue
        if token.startswith("-") or token in {"!", "(", ")"}:
            break
        paths.append(token)
    return paths or ["."]


def _ripgrep_path_tokens(args: list[str]) -> list[str]:
    operands = _non_option_operands(args, root="rg")
    if any(token == "--files" or token.startswith("--files=") for token in args):
        return operands or ["."]
    return operands[1:] if len(operands) > 1 else []


def _non_option_operands(args: list[str], *, root: str) -> list[str]:
    option_args = _option_args_for_root(root)
    operands: list[str] = []
    skip_next = False
    passthrough = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if _is_shell_separator(token):
            break
        if token in {">", ">>", "<", "2>", "2>>"}:
            break
        if passthrough:
            operands.append(token)
            continue
        if token == "--":
            passthrough = True
            continue
        if token.startswith("-"):
            option_name = token.split("=", 1)[0]
            if option_name in option_args and "=" not in token:
                skip_next = True
            continue
        operands.append(token)
    return operands


def _option_args_for_root(root: str) -> set[str]:
    return {
        "grep": {
            "-A",
            "-B",
            "-C",
            "-e",
            "-f",
            "-m",
            "--after-context",
            "--before-context",
            "--context",
            "--file",
            "--max-count",
            "--regexp",
        },
        "head": {"-c", "-n", "--bytes", "--lines"},
        "rg": {
            "-A",
            "-B",
            "-C",
            "-e",
            "-f",
            "-g",
            "-m",
            "-t",
            "-T",
            "--after-context",
            "--before-context",
            "--context",
            "--file",
            "--glob",
            "--max-count",
            "--max-depth",
            "--type",
            "--type-not",
        },
        "sed": {"-e", "-f", "--expression", "--file"},
        "tail": {"-c", "-n", "--bytes", "--lines"},
    }.get(root, set())


def _path_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple):
        paths: list[str] = []
        for item in value:
            paths.extend(_path_values(item))
        return paths
    if isinstance(value, dict):
        paths = []
        for key in ("path", "file", "filename", "new_path", "old_path"):
            paths.extend(_path_values(value.get(key)))
        return paths
    return []


def _path_ref_from_token(token: str) -> dict[str, str] | None:
    raw = token.strip()
    if not raw or raw == "-" or _is_shell_separator(raw) or looks_like_assignment(raw):
        return None
    if raw.startswith(("$", "`")) or "://" in raw:
        return None
    label = _safe_path_label(raw)
    if label is None:
        return None
    path_hash = _stable_hash(raw)
    return {"path_key": path_hash, "path_label": label, "path_hash": path_hash}


def _safe_path_label(token: str) -> str | None:
    normalized = token.rstrip("/")
    label = normalized if normalized in {".", ".."} else Path(normalized).name
    if not label:
        return None
    lowered = label.lower()
    if lowered.startswith(SENSITIVE_LABEL_PREFIXES):
        return "path"
    return label if SAFE_PATH_LABEL_RE.fullmatch(label) else "path"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _is_shell_separator(token: str) -> bool:
    return token in {"&&", "||", ";", "|"}
