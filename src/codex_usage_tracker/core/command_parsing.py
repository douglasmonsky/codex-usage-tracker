"""Privacy-safe normalization for shell command labels."""

from __future__ import annotations

import re
import shlex

SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SENSITIVE_LABEL_PREFIXES = ("sk-", "sk_", "ghp_", "github_pat_", "xox")
GIT_COMMAND_ROOTS = {"git", "gh"}

_SHELL_EXEC_WRAPPERS = {"bash", "fish", "sh", "zsh"}
_SHELL_EXEC_COMMAND_OPTIONS = {"-c", "-lc", "-cl"}
_RUN_WRAPPERS = {"npx", "pipenv", "poetry", "uv"}
_GIT_GLOBAL_OPTIONS_WITH_VALUES = {
    "-C",
    "-c",
    "--config-env",
    "--git-dir",
    "--namespace",
    "--super-prefix",
    "--work-tree",
}
_GH_GLOBAL_OPTIONS_WITH_VALUES = {
    "-H",
    "-R",
    "--hostname",
    "--repo",
}


def safe_label(value: object) -> str | None:
    """Return a bounded lowercase label without path or secret-like content."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered.startswith(SENSITIVE_LABEL_PREFIXES):
        return None
    if "/" in stripped or "\\" in stripped:
        return None
    return lowered if SAFE_LABEL_RE.fullmatch(stripped) else None


def command_root_and_child(command: str) -> tuple[str, str]:
    """Return normalized command and subcommand labels."""
    tokens = strip_command_wrappers(command_tokens(command))
    if not tokens:
        return "unknown_command", "unknown"
    root = _command_root(tokens)
    return root, _command_child(root, tokens)


def command_tokens(command: str) -> list[str]:
    """Tokenize a shell command, returning no tokens for malformed quoting."""
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def strip_command_wrappers(tokens: list[str]) -> list[str]:
    """Remove common environment, shell, and package-runner wrappers."""
    remaining = list(tokens)
    while remaining:
        remaining = _without_assignments(remaining)
        if not remaining:
            break
        unwrapped = _unwrap_once(remaining)
        if unwrapped is None:
            break
        remaining = unwrapped
    return remaining


def git_operation(tokens: list[str], *, root: str) -> str | None:
    """Return the first Git or GitHub CLI operation after global options."""
    option_args = (
        _GIT_GLOBAL_OPTIONS_WITH_VALUES if root == "git" else _GH_GLOBAL_OPTIONS_WITH_VALUES
    )
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if _is_shell_separator(token):
            break
        if token == "--":
            continue
        if token.startswith("-"):
            option_name = token.split("=", 1)[0]
            if option_name in option_args and "=" not in token:
                skip_next = True
            continue
        return safe_label(_basename(token))
    return "<none>"


def looks_like_assignment(token: str) -> bool:
    """Return whether a shell token is an environment assignment."""
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token))


def _command_root(tokens: list[str]) -> str:
    base = _basename(tokens[0])
    if base in {"py.test", "pytest"}:
        return "pytest"
    module_root = _python_module_root(tokens)
    if module_root:
        return module_root
    if base == "py" or base == "python" or base.startswith("python"):
        return "python"
    return safe_label(base) or "unknown_command"


def _command_child(root: str, tokens: list[str]) -> str:
    module_child = _python_module_child(root, tokens)
    if module_child is not None:
        return module_child
    if root == "python":
        return _python_command_child(tokens)
    if root in GIT_COMMAND_ROOTS:
        return git_operation(tokens, root=root) or "<none>"
    return _positional_child(tokens)


def _positional_child(tokens: list[str]) -> str:
    if len(tokens) <= 1:
        return "<none>"
    child = safe_label(_basename(tokens[1]))
    return child or "<arg>"


def _python_command_child(tokens: list[str]) -> str:
    for index, token in enumerate(tokens[:-1]):
        if token == "-m":
            module = safe_label(_basename(tokens[index + 1]).split(".", 1)[0])
            return f"-m:{module}" if module else "-m:unknown"
    return tokens[1] if len(tokens) > 1 and tokens[1].startswith("-") else "<script>"


def _python_module_child(root: str, tokens: list[str]) -> str | None:
    if root not in {"mypy", "pytest", "ruff"}:
        return None
    for index, token in enumerate(tokens[:-1]):
        if token != "-m":
            continue
        if index + 2 < len(tokens):
            child = tokens[index + 2]
            return child if child.startswith("-") else "<target>"
        return "<none>"
    return None


def _is_shell_separator(token: str) -> bool:
    return token in {"&&", "||", ";", "|"}


def _shell_exec_nested_tokens(tokens: list[str]) -> list[str] | None:
    for index, token in enumerate(tokens[1:], start=1):
        if token not in _SHELL_EXEC_COMMAND_OPTIONS:
            continue
        if index + 1 >= len(tokens):
            return None
        nested = command_tokens(tokens[index + 1])
        return nested or [tokens[index + 1]]
    return None


def _unwrap_once(tokens: list[str]) -> list[str] | None:
    base = _basename(tokens[0])
    if base in {"command", "env", "sudo"}:
        return tokens[1:]
    if base in _SHELL_EXEC_WRAPPERS:
        return _shell_exec_nested_tokens(tokens)
    if base in _RUN_WRAPPERS and len(tokens) > 2 and tokens[1] == "run":
        return tokens[2:]
    if base == "npx" and len(tokens) > 1:
        return tokens[1:]
    return None


def _without_assignments(tokens: list[str]) -> list[str]:
    first_command = next(
        (index for index, token in enumerate(tokens) if not looks_like_assignment(token)),
        len(tokens),
    )
    return tokens[first_command:]


def _python_module_root(tokens: list[str]) -> str | None:
    base = _basename(tokens[0]) if tokens else ""
    if not (base == "py" or base == "python" or base.startswith("python")):
        return None
    for index, token in enumerate(tokens[:-1]):
        if token != "-m":
            continue
        module = safe_label(_basename(tokens[index + 1]).split(".", 1)[0])
        return module if module in {"mypy", "pytest", "ruff"} else None
    return None


def _basename(token: str) -> str:
    return re.split(r"[\\/]", token)[-1].lower().lstrip("$")
