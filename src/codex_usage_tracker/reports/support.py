"""Privacy-preserving support bundle generation."""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from codex_usage_tracker import __version__
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_MARKETPLACE_PATH,
    DEFAULT_OTEL_COMPLETIONS_DIR,
    DEFAULT_PLUGIN_LINK,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.core.projects import (
    load_project_config,
    project_privacy_metadata,
    validate_privacy_mode,
)
from codex_usage_tracker.core.redaction import redact_secrets
from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.pricing.allowance import load_allowance_config
from codex_usage_tracker.pricing.api import load_pricing_config
from codex_usage_tracker.reports.recommendations import load_threshold_config
from codex_usage_tracker.store.api import refresh_metadata, schema_state

ISSUE_SAFE_SECTIONS = (
    "privacy",
    "package",
    "paths",
    "database",
    "refresh",
    "otel",
    "pricing",
    "allowance",
    "thresholds",
    "projects",
    "doctor",
)

ISSUE_SAFE_FIELDS = (
    "privacy",
    "package.name",
    "package.version",
    "package.python",
    "package.platform",
    "paths.codex_home_exists",
    "paths.sessions_dir_exists",
    "database",
    "refresh",
    "otel",
    "pricing.loaded",
    "pricing.error",
    "pricing.model_count",
    "pricing.source",
    "allowance.loaded",
    "allowance.error",
    "allowance.window_count",
    "allowance.credit_rate_count",
    "thresholds.loaded",
    "thresholds.error",
    "thresholds.keys",
    "projects.loaded",
    "projects.error",
    "projects.alias_count",
    "projects.ignored_path_count",
    "projects.tag_group_count",
    "doctor.status",
    "doctor.checks",
    "doctor.repair_suggestions",
    "doctor.environment",
)

ISSUE_CLI_HINT_FIELDS = (
    "privacy",
    "package",
    "database",
    "refresh",
    "doctor.status",
    "doctor.checks",
    "doctor.environment",
    "issue_report.safe_fields",
)

ISSUE_UNSAFE_ADDITIONS = (
    "raw Codex JSONL logs",
    "prompts or conversation text",
    "assistant messages",
    "tool output",
    "command text",
    "patch text",
    "full local paths",
    "secrets or credentials",
    "private config values",
)


def build_support_bundle(
    *,
    output_path: Path,
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    privacy_mode: str = "normal",
) -> Path:
    """Write a local diagnostic bundle without raw logs or transcript content."""

    output_path = output_path.expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = support_bundle_payload(
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
        privacy_mode=privacy_mode,
    )
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def support_bundle_payload(
    *,
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return support diagnostics safe to attach to a GitHub issue."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    redact_paths = privacy_mode in {"redacted", "strict"}
    path_replacements = _support_path_replacements(
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
    )
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(allowance_path, rate_card_path=rate_card_path)
    thresholds = load_threshold_config(thresholds_path)
    projects = load_project_config(projects_path)
    refresh = refresh_metadata(db_path)
    payload = {
        "bundle_version": 1,
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "privacy": {
            "contains_raw_logs": False,
            "contains_prompts": False,
            "contains_assistant_messages": False,
            "contains_tool_output": False,
            "diagnostic_paths_redacted": redact_paths,
            "project_metadata": project_privacy_metadata(privacy_mode),
        },
        "package": {
            "name": "codex-usage-tracker",
            "version": __version__,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "paths": {
            "codex_home": _support_path_value("codex_home", codex_home, privacy_mode),
            "codex_home_exists": codex_home.expanduser().exists(),
            "sessions_dir_exists": (codex_home.expanduser() / "sessions").exists(),
            "db_path": _support_path_value("db_path", db_path, privacy_mode),
            "pricing_path": _support_path_value("pricing_path", pricing_path, privacy_mode),
            "allowance_path": _support_path_value("allowance_path", allowance_path, privacy_mode),
            "rate_card_path": _support_path_value("rate_card_path", rate_card_path, privacy_mode),
            "thresholds_path": _support_path_value(
                "thresholds_path", thresholds_path, privacy_mode
            ),
            "projects_path": _support_path_value("projects_path", projects_path, privacy_mode),
        },
        "issue_report": support_bundle_issue_guidance(privacy_mode),
        "database": schema_state(db_path),
        "refresh": refresh,
        "otel": {
            "completion_directory_exists": DEFAULT_OTEL_COMPLETIONS_DIR.is_dir(),
            "refresh_counts": {
                key: value for key, value in refresh.items() if key.startswith("otel_")
            },
        },
        "pricing": {
            "loaded": pricing.loaded,
            "error": pricing.error,
            "model_count": len(pricing.models),
            "source": pricing.source,
        },
        "allowance": {
            "loaded": allowance.loaded,
            "error": allowance.error,
            "window_count": len(allowance.windows),
            "source": allowance.source,
            "rate_card_loaded": allowance.rate_card_loaded,
            "rate_card_error": allowance.rate_card_error,
            "credit_rate_count": len(allowance.credit_rates),
            "alias_count": len(allowance.aliases),
        },
        "thresholds": {
            "loaded": thresholds.loaded,
            "error": thresholds.error,
            "keys": sorted(thresholds.thresholds),
        },
        "projects": {
            "loaded": projects.loaded,
            "error": projects.error,
            "alias_count": len(projects.aliases),
            "ignored_path_count": len(projects.ignored_paths),
            "tag_group_count": len(projects.tags),
        },
        "doctor": run_doctor(
            codex_home=codex_home,
            db_path=db_path,
            pricing_path=pricing_path,
            suggest_repair=True,
        ),
    }
    return _sanitize_support_payload(
        payload,
        redact_paths=redact_paths,
        path_replacements=path_replacements,
    )


def support_bundle_issue_guidance(privacy_mode: str) -> dict[str, Any]:
    """Return reviewer-facing guidance for pasting support data into issues."""
    privacy_mode = validate_privacy_mode(privacy_mode)
    return {
        "recommended_privacy_mode": "strict",
        "current_privacy_mode": privacy_mode,
        "safe_to_paste_after_review": privacy_mode == "strict",
        "safe_sections": list(ISSUE_SAFE_SECTIONS),
        "safe_fields": list(ISSUE_SAFE_FIELDS),
        "cli_hint_fields": list(ISSUE_CLI_HINT_FIELDS),
        "do_not_add": list(ISSUE_UNSAFE_ADDITIONS),
        "note": (
            "For public GitHub issues, prefer a reviewed strict support bundle. "
            "Normal mode may include local diagnostic paths."
        ),
    }


def _support_path_value(label: str, path: Path, privacy_mode: str) -> str:
    expanded = _safe_path(path.expanduser())
    if privacy_mode == "normal":
        return str(expanded)
    return _redacted_path_label(label, expanded)


def _support_path_replacements(
    *,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
    projects_path: Path,
) -> tuple[tuple[str, str], ...]:
    raw_paths: list[tuple[str, Path]] = [
        ("codex_sessions", codex_home.expanduser() / "sessions"),
        ("codex_home", codex_home),
        ("db_path", db_path),
        ("pricing_path", pricing_path),
        ("allowance_path", allowance_path),
        ("rate_card_path", rate_card_path),
        ("thresholds_path", thresholds_path),
        ("projects_path", projects_path),
        ("dashboard_path", DEFAULT_DASHBOARD_PATH),
        ("plugin_path", DEFAULT_PLUGIN_LINK),
        ("marketplace_path", DEFAULT_MARKETPLACE_PATH),
        ("python_executable", Path(sys.executable)),
        ("cwd", Path.cwd()),
        ("home", Path.home()),
    ]
    replacements: dict[str, str] = {}
    for label, path in raw_paths:
        expanded = path.expanduser()
        candidates = (expanded, _safe_path(expanded))
        for candidate in candidates:
            _add_path_replacement(replacements, label, candidate)
            if label not in {"home", "cwd"}:
                _add_path_replacement(replacements, f"{label}_dir", candidate.parent)
    return tuple(sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True))


def _add_path_replacement(replacements: dict[str, str], label: str, path: Path) -> None:
    value = str(path)
    if not value or value in {".", "/"} or value in replacements:
        return
    replacements[value] = _redacted_path_label(label, path)


def _redacted_path_label(label: str, path: Path) -> str:
    digest = sha256(str(path).encode("utf-8")).hexdigest()[:8]
    safe_label = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in label)
    return f"[redacted path:{safe_label}:{digest}]"


def _sanitize_support_payload(
    value: Any,
    *,
    redact_paths: bool,
    path_replacements: tuple[tuple[str, str], ...],
) -> Any:
    if isinstance(value, str):
        return _sanitize_support_text(
            value,
            redact_paths=redact_paths,
            path_replacements=path_replacements,
        )
    if isinstance(value, list):
        return [
            _sanitize_support_payload(
                item,
                redact_paths=redact_paths,
                path_replacements=path_replacements,
            )
            for item in value
        ]
    if isinstance(value, dict):
        return {
            _sanitize_support_payload(
                key,
                redact_paths=redact_paths,
                path_replacements=path_replacements,
            )
            if isinstance(key, str)
            else key: _sanitize_support_payload(
                item,
                redact_paths=redact_paths,
                path_replacements=path_replacements,
            )
            for key, item in value.items()
        }
    return value


def _sanitize_support_text(
    text: str,
    *,
    redact_paths: bool,
    path_replacements: tuple[tuple[str, str], ...],
) -> str:
    sanitized = redact_secrets(text)
    if not redact_paths:
        return sanitized
    for raw_path, replacement in path_replacements:
        sanitized = sanitized.replace(raw_path, replacement)
    return sanitized


def _safe_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()
