"""Allowance config and usage-window parsing helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_ALLOWANCE_PATH, DEFAULT_RATE_CARD_PATH
from codex_usage_tracker.pricing.allowance_rate_card import (
    load_bundled_rate_card,
    load_json_file,
    optional_positive_number,
    optional_str,
    parse_alias_metadata,
    parse_aliases,
    parse_credit_rate_metadata,
    parse_credit_rates,
    parse_rate_card_source,
)
from codex_usage_tracker.pricing.allowance_text import allowance_line_matches

__all__ = (
    "ALLOWANCE_SCHEMA",
    "ALLOWANCE_TEMPLATE",
    "AllowanceWindow",
    "UsageAllowanceConfig",
    "load_allowance_config",
    "parse_allowance_text",
    "parse_windows",
    "write_allowance_from_text",
    "write_allowance_template",
)

ALLOWANCE_SCHEMA = "codex-usage-tracker-allowance-v1"

ALLOWANCE_TEMPLATE = {
    "schema": ALLOWANCE_SCHEMA,
    "_comment": (
        "Optional. Copy remaining usage values from Codex Settings > Usage or "
        "from /status. Percent values can be 0-100 or 0-1. Add total_credits "
        "only when your plan or workspace exposes an exact credit allowance. "
        "Use credit_rates and aliases only for local rate-card overrides; "
        "bundled/default rates live in the separate rate-card snapshot."
    ),
    "windows": [
        {
            "key": "five_hour",
            "label": "5h",
            "remaining_percent": None,
            "reset_at": None,
            "captured_at": None,
            "total_credits": None,
            "remaining_credits": None,
        },
        {
            "key": "weekly",
            "label": "Weekly",
            "remaining_percent": None,
            "reset_at": None,
            "captured_at": None,
            "total_credits": None,
            "remaining_credits": None,
        },
    ],
    "credit_rates": {},
    "aliases": {},
}

@dataclass(frozen=True)
class AllowanceWindow:
    """One configured usage-limit window from the user's local allowance file."""

    key: str
    label: str
    total_credits: float | None = None
    remaining_credits: float | None = None
    remaining_percent: float | None = None
    reset_at: str | None = None
    captured_at: str | None = None


@dataclass(frozen=True)
class UsageAllowanceConfig:
    """Local usage allowance config plus bundled Codex credit rates."""

    path: Path
    rate_card_path: Path
    credit_rates: dict[str, dict[str, float]]
    aliases: dict[str, dict[str, str]]
    rate_metadata: dict[str, dict[str, Any]]
    alias_metadata: dict[str, dict[str, Any]]
    windows: list[AllowanceWindow]
    loaded: bool
    rate_card_loaded: bool
    source: dict[str, Any]
    error: str | None = None
    rate_card_error: str | None = None

def load_allowance_config(
    path: Path = DEFAULT_ALLOWANCE_PATH,
    *,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
) -> UsageAllowanceConfig:
    """Load optional allowance settings while always keeping bundled rate-card data."""

    base_card = load_bundled_rate_card()
    rate_card_loaded = False
    rate_card_error = None
    if rate_card_path.expanduser().exists():
        try:
            base_card = load_json_file(rate_card_path)
            rate_card_loaded = True
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            rate_card_error = str(exc)

    source = parse_rate_card_source(base_card)
    credit_rates = parse_credit_rates(base_card.get("credit_rates", {}))
    aliases = parse_aliases(base_card.get("aliases", {}))
    rate_metadata = parse_credit_rate_metadata(
        base_card.get("credit_rates", {}), source=source, default_confidence="exact"
    )
    alias_metadata = parse_alias_metadata(base_card.get("aliases", {}), source=source)
    windows: list[AllowanceWindow] = []
    if not path.exists():
        return UsageAllowanceConfig(
            path=path,
            rate_card_path=rate_card_path,
            credit_rates=credit_rates,
            aliases=aliases,
            rate_metadata=rate_metadata,
            alias_metadata=alias_metadata,
            windows=windows,
            loaded=False,
            rate_card_loaded=rate_card_loaded,
            source=source,
            rate_card_error=rate_card_error,
        )

    try:
        raw = load_json_file(path)
        local_rates = parse_credit_rates(raw.get("credit_rates", {}))
        credit_rates.update(local_rates)
        rate_metadata.update(
            parse_credit_rate_metadata(
                raw.get("credit_rates", {}),
                source={
                    "name": "Local allowance override",
                    "url": str(path.expanduser()),
                    "fetched_at": None,
                },
                default_confidence="user_override",
            )
        )
        local_aliases = parse_aliases(raw.get("aliases", {}))
        aliases.update(local_aliases)
        alias_metadata.update(
            parse_alias_metadata(
                raw.get("aliases", {}),
                source={
                    "name": "Local allowance override",
                    "url": str(path.expanduser()),
                    "fetched_at": None,
                },
            )
        )
        windows = parse_windows(raw.get("windows", []))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return UsageAllowanceConfig(
            path=path,
            rate_card_path=rate_card_path,
            credit_rates=credit_rates,
            aliases=aliases,
            rate_metadata=rate_metadata,
            alias_metadata=alias_metadata,
            windows=[],
            loaded=False,
            rate_card_loaded=rate_card_loaded,
            source=source,
            error=str(exc),
            rate_card_error=rate_card_error,
        )

    return UsageAllowanceConfig(
        path=path,
        rate_card_path=rate_card_path,
        credit_rates=credit_rates,
        aliases=aliases,
        rate_metadata=rate_metadata,
        alias_metadata=alias_metadata,
        windows=windows,
        loaded=True,
        rate_card_loaded=rate_card_loaded,
        source=source,
        rate_card_error=rate_card_error,
    )


def write_allowance_template(
    path: Path = DEFAULT_ALLOWANCE_PATH, force: bool = False
) -> Path:
    """Write a local template for optional allowance-window settings."""

    if path.exists() and not force:
        raise FileExistsError(f"Allowance config already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ALLOWANCE_TEMPLATE, indent=2) + "\n", encoding="utf-8")
    return path


def parse_allowance_text(
    text: str,
    *,
    captured_at: str | None = None,
) -> list[AllowanceWindow]:
    """Parse pasted Codex usage text into allowance windows."""

    captured = captured_at or _utc_now()
    windows: list[AllowanceWindow] = []
    for key, label, percent, reset_at in allowance_line_matches(text):
        windows.append(
            AllowanceWindow(
                key=key,
                label=label,
                remaining_percent=_optional_percent(percent),
                reset_at=reset_at,
                captured_at=captured,
            )
        )
    return windows


def write_allowance_from_text(
    text: str,
    *,
    path: Path = DEFAULT_ALLOWANCE_PATH,
    force: bool = False,
    captured_at: str | None = None,
) -> Path:
    """Update the local allowance-window file from pasted usage text."""

    windows = parse_allowance_text(text, captured_at=captured_at)
    if not windows:
        raise ValueError("could not find 5h or weekly allowance percentages in pasted text")

    path = path.expanduser()
    if path.exists():
        try:
            payload = load_json_file(path)
        except (OSError, TypeError, json.JSONDecodeError, ValueError):
            if not force:
                raise
            payload = json.loads(json.dumps(ALLOWANCE_TEMPLATE))
    else:
        payload = json.loads(json.dumps(ALLOWANCE_TEMPLATE))
    payload["schema"] = ALLOWANCE_SCHEMA
    payload["windows"] = [asdict(window) for window in windows]
    payload["_source"] = {
        "name": "Pasted Codex usage text",
        "captured_at": windows[0].captured_at,
        "exact_allowance_source": False,
        "note": "Remaining percentages are user-copied from Codex UI or /status text.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

def parse_windows(raw: object) -> list[AllowanceWindow]:
    windows: list[AllowanceWindow] = []
    for row in _allowance_window_rows(raw):
        window = _parse_allowance_window(row)
        if window is not None:
            windows.append(window)
    return windows


def _allowance_window_rows(raw: object) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        return [{**value, "key": key} for key, value in raw.items() if isinstance(value, dict)]
    if isinstance(raw, list):
        return [value for value in raw if isinstance(value, dict)]
    return []


def _parse_allowance_window(row: dict[str, Any]) -> AllowanceWindow | None:
    key = optional_str(row.get("key"))
    if not key:
        return None
    label = optional_str(row.get("label")) or key.replace("_", " ").title()
    return AllowanceWindow(
        key=key,
        label=label,
        total_credits=optional_positive_number(row.get("total_credits")),
        remaining_credits=optional_positive_number(row.get("remaining_credits")),
        remaining_percent=_optional_percent(row.get("remaining_percent")),
        reset_at=optional_str(row.get("reset_at")),
        captured_at=optional_str(row.get("captured_at")),
    )


def _optional_percent(value: object) -> float | None:
    parsed = optional_positive_number(value)
    if parsed is None:
        return None
    return parsed / 100 if parsed > 1 else parsed


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
