"""Codex credit rate-card loading and parsing helpers."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_RATE_CARD_PATH

RATE_CARD_SCHEMA = "codex-usage-tracker-codex-rate-card-v1"

CODEX_PRICING_URL = "https://developers.openai.com/codex/pricing"
CODEX_RATE_CARD_URL = CODEX_PRICING_URL

DEFAULT_SOURCE = {
    "name": "OpenAI Codex rate card",
    "url": CODEX_RATE_CARD_URL,
    "pricing_url": CODEX_PRICING_URL,
    "fetched_at": "2026-07-09",
    "basis": "credits per 1M input, cached input, and output tokens",
    "tier": "standard",
}


@dataclass(frozen=True)
class RateCardUpdateResult:
    """Result from writing a local Codex credit rate-card snapshot."""

    path: Path
    source_url: str | None
    fetched_at: str | None
    model_count: int
    alias_count: int
    backup_path: Path | None = None


def load_bundled_rate_card() -> dict[str, Any]:
    """Load the package-bundled Codex credit rate-card snapshot."""

    rate_card = (
        resources.files("codex_usage_tracker.plugin_data")
        .joinpath("rate_cards")
        .joinpath("codex-credit-rates.json")
    )
    with rate_card.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("bundled Codex rate card must be a JSON object")
    return raw


def update_rate_card(
    path: Path = DEFAULT_RATE_CARD_PATH,
    *,
    source_file: Path | None = None,
) -> RateCardUpdateResult:
    """Write a validated Codex credit rate-card snapshot to the local config directory."""

    raw = load_json_file(source_file) if source_file is not None else load_bundled_rate_card()
    schema = raw.get("schema") or raw.get("_schema")
    if schema and schema != RATE_CARD_SCHEMA:
        raise ValueError(f"unsupported Codex rate-card schema: {schema}")
    source = parse_rate_card_source(raw)
    credit_rates = parse_credit_rates(raw.get("credit_rates", {}))
    aliases = parse_aliases(raw.get("aliases", {}))
    if not credit_rates:
        raise ValueError("rate card must contain at least one credit rate")
    parse_credit_rate_metadata(raw.get("credit_rates", {}), source=source)
    parse_alias_metadata(raw.get("aliases", {}), source=source)

    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = _backup_existing_rate_card(path)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return RateCardUpdateResult(
        path=path,
        source_url=optional_str(source.get("url")),
        fetched_at=optional_str(source.get("fetched_at")),
        model_count=len(credit_rates),
        alias_count=len(aliases),
        backup_path=backup_path,
    )


def parse_credit_rates(raw: object) -> dict[str, dict[str, float]]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, dict[str, float]] = {}
    for model, rates in raw.items():
        normalized = normalize_model(model)
        if not normalized or not isinstance(rates, dict):
            continue
        parsed[normalized] = {
            "input_per_million": _required_rate(rates, "input_per_million", normalized),
            "cached_input_per_million": _required_rate(
                rates, "cached_input_per_million", normalized
            ),
            "output_per_million": _required_rate(rates, "output_per_million", normalized),
        }
    return parsed


def parse_aliases(raw: object) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, dict[str, str]] = {}
    for source, target in raw.items():
        source_model = normalize_model(source)
        if not source_model:
            continue
        alias = _parse_alias_entry(source_model, target)
        if alias is not None:
            parsed[source_model] = alias
    return parsed


def _parse_alias_entry(source_model: str, target: object) -> dict[str, str] | None:
    if isinstance(target, str):
        return {
            "model": normalize_model(target) or target,
            "confidence": "estimated",
            "note": f"Mapped from {source_model} by local allowance config.",
        }
    if not isinstance(target, dict):
        return None
    target_model = normalize_model(target.get("model"))
    if not target_model:
        return None
    return {
        "model": target_model,
        "confidence": optional_str(target.get("confidence")) or "estimated",
        "note": optional_str(target.get("note"))
        or f"Mapped from {source_model} by local allowance config.",
    }


def parse_rate_card_source(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return dict(DEFAULT_SOURCE)
    source = raw.get("source") or raw.get("_source")
    if not isinstance(source, dict):
        return dict(DEFAULT_SOURCE)
    return {**DEFAULT_SOURCE, **source}


def parse_credit_rate_metadata(
    raw: object,
    *,
    source: dict[str, Any],
    default_confidence: str = "exact",
) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, dict[str, Any]] = {}
    for model, rates in raw.items():
        entry = _credit_rate_metadata_entry(model, rates, source, default_confidence)
        if entry is not None:
            normalized, metadata = entry
            parsed[normalized] = metadata
    return parsed


def _credit_rate_metadata_entry(
    model: object,
    rates: object,
    source: dict[str, Any],
    default_confidence: str,
) -> tuple[str, dict[str, Any]] | None:
    normalized = normalize_model(model)
    if not normalized or not isinstance(rates, dict):
        return None
    return normalized, {
        "confidence": optional_str(rates.get("confidence")) or default_confidence,
        "source_name": optional_str(rates.get("source_name"))
        or optional_str(source.get("name"))
        or "Codex credit rates",
        "source_url": optional_str(rates.get("source_url")) or optional_str(source.get("url")),
        "fetched_at": optional_str(rates.get("fetched_at"))
        or optional_str(source.get("fetched_at")),
        "tier": optional_str(rates.get("tier")) or optional_str(source.get("tier")),
        "note": optional_str(rates.get("note")),
    }


def parse_alias_metadata(raw: object, *, source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, dict[str, Any]] = {}
    for alias, target in raw.items():
        entry = _alias_metadata_entry(alias, target, source)
        if entry is not None:
            normalized, metadata = entry
            parsed[normalized] = metadata
    return parsed


def _alias_metadata_entry(
    alias: object,
    target: object,
    source: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    normalized = normalize_model(alias)
    if not normalized:
        return None
    if isinstance(target, str):
        return normalized, _string_alias_metadata(target, source)
    if isinstance(target, dict):
        return normalized, _mapping_alias_metadata(target, source)
    return None


def _string_alias_metadata(target: str, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "confidence": "estimated",
        "source_name": optional_str(source.get("name")) or "Codex credit rates",
        "source_url": optional_str(source.get("url")),
        "fetched_at": optional_str(source.get("fetched_at")),
        "tier": optional_str(source.get("tier")),
        "note": f"Mapped to {normalize_model(target) or target} by local alias.",
        "alias_reason": None,
    }


def _mapping_alias_metadata(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    return {
        "confidence": optional_str(target.get("confidence")) or "estimated",
        "source_name": optional_str(target.get("source_name"))
        or optional_str(source.get("name"))
        or "Codex credit rates",
        "source_url": optional_str(target.get("source_url")) or optional_str(source.get("url")),
        "fetched_at": optional_str(target.get("fetched_at"))
        or optional_str(source.get("fetched_at")),
        "tier": optional_str(target.get("tier")) or optional_str(source.get("tier")),
        "note": optional_str(target.get("note")),
        "alias_reason": optional_str(target.get("alias_reason")),
    }


def load_json_file(path: Path) -> dict[str, Any]:
    raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"JSON config must be an object: {path}")
    return raw


def _backup_existing_rate_card(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.{stamp}.bak")
    shutil.copy2(path, backup_path)
    return backup_path


def normalize_model(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().lower().replace("_", "-")


def _required_rate(raw: dict[str, Any], key: str, model: str) -> float:
    parsed = optional_positive_number(raw.get(key))
    if parsed is None:
        raise ValueError(f"missing {key} for Codex credit model {model}")
    return parsed


def optional_positive_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    number = number_value(value)
    if number < 0:
        raise ValueError("allowance values cannot be negative")
    return number


def optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def number_value(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return 0.0
