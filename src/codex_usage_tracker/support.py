"""Privacy-preserving support bundle generation."""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker import __version__
from codex_usage_tracker.allowance import load_allowance_config
from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.pricing import load_pricing_config
from codex_usage_tracker.projects import (
    load_project_config,
    project_privacy_metadata,
    validate_privacy_mode,
)
from codex_usage_tracker.recommendations import load_threshold_config
from codex_usage_tracker.store import refresh_metadata, schema_state


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
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(allowance_path, rate_card_path=rate_card_path)
    thresholds = load_threshold_config(thresholds_path)
    projects = load_project_config(projects_path)
    return {
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
            "project_metadata": project_privacy_metadata(privacy_mode),
        },
        "package": {
            "name": "codex-usage-tracker",
            "version": __version__,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "paths": {
            "codex_home_exists": codex_home.expanduser().exists(),
            "sessions_dir_exists": (codex_home.expanduser() / "sessions").exists(),
            "db_path": str(db_path.expanduser()),
            "pricing_path": str(pricing_path.expanduser()),
            "allowance_path": str(allowance_path.expanduser()),
            "rate_card_path": str(rate_card_path.expanduser()),
            "thresholds_path": str(thresholds_path.expanduser()),
            "projects_path": str(projects_path.expanduser()),
        },
        "database": schema_state(db_path),
        "refresh": refresh_metadata(db_path),
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
