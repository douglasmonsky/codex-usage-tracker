"""Derived project and workflow attribution from aggregate cwd fields."""

from __future__ import annotations

import configparser
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_PROJECTS_PATH

PROJECT_CONFIG_TEMPLATE: dict[str, object] = {
    "aliases": {},
    "ignored_paths": [],
    "tags": {},
}

PRIVACY_MODE_CHOICES = ("normal", "redacted", "strict")


@dataclass(frozen=True)
class ProjectConfig:
    path: Path
    aliases: dict[str, str]
    ignored_paths: list[str]
    tags: dict[str, list[str]]
    loaded: bool = False
    error: str | None = None


def load_project_config(path: Path = DEFAULT_PROJECTS_PATH) -> ProjectConfig:
    """Load local project attribution aliases, ignored paths, and tags."""

    path = path.expanduser()
    if not path.exists():
        return _empty_project_config(path)
    payload, error = _read_project_config_payload(path)
    if error is not None:
        return _empty_project_config(path, error=error)
    if not isinstance(payload, dict):
        return _empty_project_config(path, error="Project config must be a JSON object.")
    return ProjectConfig(
        path=path,
        aliases=_project_aliases(payload),
        ignored_paths=_project_ignored_paths(payload),
        tags=_project_tags(payload),
        loaded=True,
    )


def _empty_project_config(path: Path, error: str | None = None) -> ProjectConfig:
    return ProjectConfig(path=path, aliases={}, ignored_paths=[], tags={}, error=error)


def _read_project_config_payload(path: Path) -> tuple[Any, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)


def _project_aliases(payload: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in _dict_section(payload, "aliases").items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _project_ignored_paths(payload: dict[str, Any]) -> list[str]:
    return [
        str(value)
        for value in _list_section(payload, "ignored_paths")
        if isinstance(value, str)
    ]


def _project_tags(payload: dict[str, Any]) -> dict[str, list[str]]:
    return {
        str(key): [str(tag) for tag in value if isinstance(tag, str)]
        for key, value in _dict_section(payload, "tags").items()
        if isinstance(key, str) and isinstance(value, list)
    }


def _dict_section(payload: dict[str, Any], key: str) -> dict[Any, Any]:
    value = payload.get(key) or {}
    return value if isinstance(value, dict) else {}


def _list_section(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key) or []
    return value if isinstance(value, list) else []


def write_project_template(path: Path = DEFAULT_PROJECTS_PATH, force: bool = False) -> Path:
    """Write a local project attribution template."""

    path = path.expanduser()
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists. Use --force to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(PROJECT_CONFIG_TEMPLATE, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def annotate_rows_with_project_identity(
    rows: list[dict[str, Any]],
    config: ProjectConfig | None = None,
) -> list[dict[str, Any]]:
    """Attach derived project identity fields to copied aggregate rows."""

    project_config = config or load_project_config()
    cache: dict[str, dict[str, Any]] = {}
    annotated: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        cwd = str(copy.get("cwd") or "")
        if cwd not in cache:
            cache[cwd] = project_identity_for_cwd(cwd, project_config)
        copy.update(cache[cwd])
        annotated.append(copy)
    return annotated


def apply_project_privacy_to_rows(
    rows: list[dict[str, Any]],
    privacy_mode: str = "normal",
) -> list[dict[str, Any]]:
    """Return copied rows with sensitive project metadata redacted when requested."""

    mode = validate_privacy_mode(privacy_mode)
    if mode == "normal":
        return [dict(row) for row in rows]
    return [_apply_project_privacy_to_row(dict(row), mode) for row in rows]


def apply_project_privacy_to_summary_rows(
    rows: list[dict[str, Any]],
    *,
    group_by: str,
    privacy_mode: str = "normal",
) -> list[dict[str, Any]]:
    """Redact summary group labels that are derived from local paths."""

    mode = validate_privacy_mode(privacy_mode)
    if mode == "normal" or group_by != "cwd":
        return [dict(row) for row in rows]
    redacted: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        copy["group_key"] = _redacted_cwd_label(copy.get("group_key"))
        copy["privacy_mode"] = mode
        redacted.append(copy)
    return redacted


def project_privacy_metadata(privacy_mode: str = "normal") -> dict[str, Any]:
    """Return dashboard/report metadata for the active project privacy mode."""

    mode = validate_privacy_mode(privacy_mode)
    return {
        "mode": mode,
        "project_names_redacted": mode in {"redacted", "strict"},
        "cwd_redacted": mode in {"redacted", "strict"},
        "source_paths_redacted": mode in {"redacted", "strict"},
        "relative_cwd_hidden": mode == "strict",
        "git_branch_hidden": mode == "strict",
        "git_remote_label_hidden": mode in {"redacted", "strict"},
        "tags_hidden": mode == "strict",
        "aliases_preserved": mode in {"redacted", "strict"},
    }


def validate_privacy_mode(privacy_mode: str = "normal") -> str:
    """Normalize and validate a project metadata privacy mode."""

    mode = str(privacy_mode or "normal")
    if mode not in PRIVACY_MODE_CHOICES:
        allowed = ", ".join(PRIVACY_MODE_CHOICES)
        raise ValueError(f"privacy_mode must be one of: {allowed}")
    return mode


def project_identity_for_cwd(cwd: str, config: ProjectConfig | None = None) -> dict[str, Any]:
    """Derive project identity from one cwd string."""

    project_config = config or load_project_config()
    path = Path(cwd).expanduser() if cwd else None
    ignored = _is_ignored(path, project_config.ignored_paths)
    git_root = _find_git_root(path) if path and not ignored else None
    project_root = git_root or path
    project_key = _project_key(project_root)
    default_name = project_root.name if project_root else "Unknown project"
    project_name, alias_configured = _alias_for(
        project_root, project_key, default_name, project_config.aliases
    )
    tags = _tags_for(project_root, project_key, project_name, project_config.tags)
    git = _git_metadata(git_root) if git_root else {}
    return {
        "project_name": project_name,
        "project_key": project_key,
        "project_root_hash": project_key,
        "project_alias_configured": alias_configured,
        "project_relative_cwd": _relative_cwd(path, project_root),
        "project_ignored": ignored,
        "project_tags": tags,
        "git_branch": git.get("branch"),
        "git_remote_hash": git.get("remote_hash"),
        "git_remote_label": git.get("remote_label"),
    }


def _find_git_root(path: Path | None) -> Path | None:
    if path is None:
        return None
    current = path if path.is_dir() else path.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _git_metadata(root: Path) -> dict[str, str | None]:
    git_dir = root / ".git"
    if git_dir.is_file():
        return {}
    branch = _git_branch(git_dir)
    remote = _git_remote_origin(git_dir)
    return {
        "branch": branch,
        "remote_hash": _stable_hash(remote) if remote else None,
        "remote_label": _remote_label(remote) if remote else None,
    }


def _git_branch(git_dir: Path) -> str | None:
    head = git_dir / "HEAD"
    try:
        text = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if text.startswith("ref: refs/heads/"):
        return text.removeprefix("ref: refs/heads/")
    if text:
        return "detached"
    return None


def _git_remote_origin(git_dir: Path) -> str | None:
    config_path = git_dir / "config"
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path)
    except configparser.Error:
        return None
    section = 'remote "origin"'
    if not parser.has_section(section):
        return None
    url = parser.get(section, "url", fallback=None)
    return url.strip() if isinstance(url, str) and url.strip() else None


def _remote_label(remote: str) -> str:
    cleaned = remote.rstrip("/").removesuffix(".git")
    name = cleaned.rsplit("/", 1)[-1]
    return name or "origin"


def _is_ignored(path: Path | None, ignored_paths: list[str]) -> bool:
    if path is None:
        return False
    resolved = _safe_resolve(path)
    for ignored in ignored_paths:
        ignored_path = _safe_resolve(Path(ignored).expanduser())
        if resolved == ignored_path or ignored_path in resolved.parents:
            return True
    return False


def _alias_for(
    root: Path | None,
    key: str,
    default: str,
    aliases: dict[str, str],
) -> tuple[str, bool]:
    candidates = [key, default]
    if root:
        resolved = str(_safe_resolve(root))
        candidates.extend([resolved, str(root)])
    for candidate in candidates:
        if candidate in aliases:
            return aliases[candidate], True
    return default, False


def _tags_for(
    root: Path | None,
    key: str,
    name: str,
    tags: dict[str, list[str]],
) -> list[str]:
    values: list[str] = []
    candidates = [key, name]
    if root:
        resolved = str(_safe_resolve(root))
        candidates.extend([resolved, str(root)])
    for candidate in candidates:
        values.extend(tags.get(candidate, []))
    return sorted(set(values))


def _relative_cwd(path: Path | None, root: Path | None) -> str | None:
    if path is None or root is None:
        return None
    try:
        relative = _safe_resolve(path).relative_to(_safe_resolve(root))
    except ValueError:
        return None
    return "." if not relative.parts else relative.as_posix()


def _project_key(path: Path | None) -> str:
    return _stable_hash(str(_safe_resolve(path))) if path else "unknown"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _apply_project_privacy_to_row(row: dict[str, Any], mode: str) -> dict[str, Any]:
    project_key = str(row.get("project_key") or _stable_hash(str(row.get("cwd") or "unknown")))
    short_key = project_key[:8] if project_key and project_key != "unknown" else "unknown"
    alias_configured = bool(row.get("project_alias_configured"))
    if not alias_configured:
        row["project_name"] = f"Project {short_key}"
    row["cwd"] = _redacted_cwd_label(project_key)
    row["source_file"] = _redacted_source_label(row.get("source_file"))
    row["git_remote_label"] = None
    row["project_metadata_redacted"] = True
    row["privacy_mode"] = mode
    if mode == "strict":
        row["project_relative_cwd"] = None
        row["git_branch"] = None
        row["project_tags"] = []
    return row


def _redacted_cwd_label(value: object) -> str:
    key = str(value or "unknown")
    digest = key[:8] if len(key) >= 8 and all(ch in "0123456789abcdef" for ch in key[:8].lower()) else _stable_hash(key)[:8]
    return f"[redacted cwd:{digest}]"


def _redacted_source_label(value: object) -> str | None:
    if not value:
        return None
    return f"[redacted source:{_stable_hash(str(value))[:8]}]"


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()
