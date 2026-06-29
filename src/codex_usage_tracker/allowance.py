"""Codex usage allowance and credit estimation helpers."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance_rate_card import (
    CODEX_PRICING_URL,
    CODEX_RATE_CARD_URL,
    DEFAULT_SOURCE,
    RATE_CARD_SCHEMA,
    RateCardUpdateResult,
    load_bundled_rate_card,
    load_json_file,
    normalize_model,
    number_value,
    optional_positive_number,
    optional_str,
    parse_alias_metadata,
    parse_aliases,
    parse_credit_rate_metadata,
    parse_credit_rates,
    parse_rate_card_source,
    update_rate_card,
)
from codex_usage_tracker.paths import DEFAULT_ALLOWANCE_PATH, DEFAULT_RATE_CARD_PATH

__all__ = (
    "ALLOWANCE_SCHEMA",
    "CODEX_PRICING_URL",
    "CODEX_RATE_CARD_URL",
    "DEFAULT_SOURCE",
    "RATE_CARD_SCHEMA",
    "ALLOWANCE_TEMPLATE",
    "AllowanceWindow",
    "UsageAllowanceConfig",
    "RateCardUpdateResult",
    "annotate_rows_with_allowance",
    "estimate_usage_credits",
    "load_allowance_config",
    "load_bundled_rate_card",
    "parse_alias_metadata",
    "parse_aliases",
    "parse_allowance_text",
    "parse_credit_rate_metadata",
    "parse_credit_rates",
    "parse_rate_card_source",
    "parse_windows",
    "resolve_credit_rate",
    "summarize_allowance_usage",
    "update_rate_card",
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
    for key, label, percent, reset_at in _allowance_line_matches(text):
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


def annotate_rows_with_allowance(
    rows: list[dict[str, Any]],
    config: UsageAllowanceConfig | None = None,
    *,
    model_field: str = "model",
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
) -> list[dict[str, Any]]:
    """Return copied rows with Codex credit usage annotations."""

    resolved = config or load_allowance_config(allowance_path)
    annotated: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        model = copy.get(model_field)
        match = resolve_credit_rate(model, resolved)
        if match is None:
            copy.update(
                {
                    "usage_credits": None,
                    "usage_credit_model": None,
                    "usage_credit_confidence": "unpriced",
                    "usage_credit_source": "No Codex credit rate",
                    "usage_credit_source_url": None,
                    "usage_credit_fetched_at": None,
                    "usage_credit_tier": None,
                    "usage_credit_note": "No bundled or configured credit rate matched this model.",
                }
            )
        else:
            rated_model, rates, confidence, note, metadata = match
            copy.update(
                {
                    "usage_credits": estimate_usage_credits(copy, rates),
                    "usage_credit_model": rated_model,
                    "usage_credit_confidence": confidence,
                    "usage_credit_source": metadata.get("source_name")
                    or resolved.source.get("name", "Codex credit rates"),
                    "usage_credit_source_url": metadata.get("source_url"),
                    "usage_credit_fetched_at": metadata.get("fetched_at"),
                    "usage_credit_tier": metadata.get("tier"),
                    "usage_credit_note": note,
                }
            )
        annotated.append(copy)
    return annotated


def summarize_allowance_usage(
    rows: list[dict[str, Any]], config: UsageAllowanceConfig | None = None
) -> dict[str, Any]:
    """Summarize Codex credit usage and configured allowance windows."""

    resolved = config or load_allowance_config()
    total_tokens = sum(number_value(row.get("total_tokens")) for row in rows)
    rated_tokens = sum(
        number_value(row.get("total_tokens"))
        for row in rows
        if row.get("usage_credits") is not None
    )
    usage_credits = sum(
        number_value(row.get("usage_credits"))
        for row in rows
        if row.get("usage_credits") is not None
    )
    estimated_credits = sum(
        number_value(row.get("usage_credits"))
        for row in rows
        if row.get("usage_credit_confidence") == "estimated"
    )
    override_credits = sum(
        number_value(row.get("usage_credits"))
        for row in rows
        if row.get("usage_credit_confidence") == "user_override"
    )
    exact_credits = sum(
        number_value(row.get("usage_credits"))
        for row in rows
        if row.get("usage_credit_confidence") == "exact"
    )
    return {
        "usage_credits": usage_credits,
        "exact_usage_credits": exact_credits,
        "estimated_usage_credits": estimated_credits,
        "user_override_usage_credits": override_credits,
        "rated_tokens": rated_tokens,
        "unrated_tokens": max(total_tokens - rated_tokens, 0.0),
        "credit_token_ratio": rated_tokens / total_tokens if total_tokens else 0.0,
        "windows": [asdict(window) for window in resolved.windows],
        "source": resolved.source,
        "configured": resolved.loaded,
        "error": resolved.error,
        "rate_card_loaded": resolved.rate_card_loaded,
        "rate_card_error": resolved.rate_card_error,
    }


def resolve_credit_rate(
    model: object, config: UsageAllowanceConfig
) -> tuple[str, dict[str, float], str, str, dict[str, Any]] | None:
    """Resolve a model label into a credit rate, confidence, and note."""

    normalized = normalize_model(model)
    if not normalized:
        return None
    direct = config.credit_rates.get(normalized)
    if direct is not None:
        metadata = config.rate_metadata.get(normalized, {})
        confidence = optional_str(metadata.get("confidence")) or "exact"
        note = optional_str(metadata.get("note")) or (
            "Direct match to Codex credit rates."
            if confidence != "user_override"
            else "Direct match to local user-provided Codex credit rate."
        )
        return normalized, direct, confidence, note, metadata

    alias = config.aliases.get(normalized)
    if not alias:
        return None
    target = normalize_model(alias.get("model"))
    if not target:
        return None
    rates = config.credit_rates.get(target)
    if rates is None:
        return None
    metadata = {**config.rate_metadata.get(target, {}), **config.alias_metadata.get(normalized, {})}
    confidence = alias.get("confidence") or optional_str(metadata.get("confidence")) or "estimated"
    note = alias.get("note") or optional_str(metadata.get("note")) or (
        f"Mapped from {normalized} to {target} by local alias."
    )
    return target, rates, confidence, note, metadata


def estimate_usage_credits(row: dict[str, Any], rates: dict[str, float]) -> float:
    """Estimate Codex credits from aggregate token counters."""

    input_rate = rates["input_per_million"]
    cached_rate = rates["cached_input_per_million"]
    output_rate = rates["output_per_million"]
    cached_input = number_value(row.get("cached_input_tokens"))
    uncached_input = number_value(row.get("uncached_input_tokens"))
    if uncached_input <= 0:
        uncached_input = max(number_value(row.get("input_tokens")) - cached_input, 0.0)
    output_tokens = number_value(row.get("output_tokens"))
    return (
        (uncached_input * input_rate)
        + (cached_input * cached_rate)
        + (output_tokens * output_rate)
    ) / 1_000_000












def parse_windows(raw: object) -> list[AllowanceWindow]:
    if isinstance(raw, dict):
        rows = [{**value, "key": key} for key, value in raw.items() if isinstance(value, dict)]
    elif isinstance(raw, list):
        rows = [value for value in raw if isinstance(value, dict)]
    else:
        rows = []

    windows: list[AllowanceWindow] = []
    for row in rows:
        key = optional_str(row.get("key"))
        if not key:
            continue
        label = optional_str(row.get("label")) or key.replace("_", " ").title()
        windows.append(
            AllowanceWindow(
                key=key,
                label=label,
            total_credits=optional_positive_number(row.get("total_credits")),
            remaining_credits=optional_positive_number(row.get("remaining_credits")),
                remaining_percent=_optional_percent(row.get("remaining_percent")),
                reset_at=optional_str(row.get("reset_at")),
                captured_at=optional_str(row.get("captured_at")),
            )
        )
    return windows






def _allowance_line_matches(text: str) -> list[tuple[str, str, str, str | None]]:
    lines = [line.strip() for line in text.replace("\u00a0", " ").splitlines() if line.strip()]
    matches: list[tuple[str, str, str, str | None]] = []
    for line in lines:
        match = _ALLOWANCE_LINE_RE.match(line)
        if not match:
            continue
        key = _allowance_window_key(match.group("label"))
        if key is None:
            continue
        reset_at = match.group("reset")
        if reset_at and _ALLOWANCE_LABEL_RE.search(reset_at):
            continue
        matches.append(
            (
                key,
                "5h" if key == "five_hour" else "Weekly",
                match.group("percent"),
                reset_at.strip() if reset_at and reset_at.strip() else None,
            )
        )
    if matches:
        return _dedupe_allowance_matches(matches)

    flat = " ".join(text.replace("\u00a0", " ").split())
    label_matches = list(_ALLOWANCE_LABEL_RE.finditer(flat))
    for index, match in enumerate(label_matches):
        key = _allowance_window_key(match.group(0))
        if key is None:
            continue
        next_start = label_matches[index + 1].start() if index + 1 < len(label_matches) else len(flat)
        segment = flat[match.end() : next_start].strip()
        percent_match = _ALLOWANCE_PERCENT_RE.search(segment)
        if percent_match is None:
            continue
        reset_at = segment[percent_match.end() :].strip()
        matches.append(
            (
                key,
                "5h" if key == "five_hour" else "Weekly",
                percent_match.group("percent"),
                reset_at or None,
            )
        )
    return _dedupe_allowance_matches(matches)


def _dedupe_allowance_matches(
    matches: list[tuple[str, str, str, str | None]],
) -> list[tuple[str, str, str, str | None]]:
    seen: set[str] = set()
    deduped: list[tuple[str, str, str, str | None]] = []
    for match in matches:
        key = match[0]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)
    return deduped


def _allowance_window_key(label: str) -> str | None:
    normalized = label.lower().replace("-", "_").replace(" ", "_")
    if normalized in {"5h", "5_hour", "five_hour"}:
        return "five_hour"
    if normalized in {"weekly", "week"}:
        return "weekly"
    return None








def _optional_percent(value: object) -> float | None:
    parsed = optional_positive_number(value)
    if parsed is None:
        return None
    return parsed / 100 if parsed > 1 else parsed






def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_ALLOWANCE_LINE_RE = re.compile(
    r"^(?P<label>5h|5-hour|five-hour|weekly|week)\s+"
    r"(?P<percent>\d+(?:\.\d+)?)\s*%"
    r"(?:\s+(?P<reset>.+?))?\s*$",
    re.IGNORECASE,
)
_ALLOWANCE_LABEL_RE = re.compile(r"\b(?:5h|5-hour|five-hour|weekly|week)\b", re.IGNORECASE)
_ALLOWANCE_PERCENT_RE = re.compile(r"(?P<percent>\d+(?:\.\d+)?)\s*%")
