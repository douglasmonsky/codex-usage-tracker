"""Local pricing config loading and template writing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_PRICING_PATH

PRICING_SCHEMA = "codex-usage-tracker-pricing-v1"
PRICING_TEMPLATE = {
    "_comment": (
        "Fill in current prices in USD per 1 million tokens. The tracker does "
        "not fetch pricing during normal reports. Prefer update-pricing when "
        "you want to cache current OpenAI-published rates locally."
    ),
    "models": {
        "replace-with-model-name": {
            "input_per_million": 0.0,
            "cached_input_per_million": 0.0,
            "output_per_million": 0.0,
        }
    },
    "aliases": {
        "local-codex-model-label": "official-openai-model-id",
    },
}


@dataclass(frozen=True)
class PricingConfig:
    """Parsed local model pricing config."""

    path: Path
    models: dict[str, dict[str, float]]
    loaded: bool
    aliases: dict[str, str] | None = None
    estimated_models: set[str] | None = None
    source: dict[str, Any] | None = None
    error: str | None = None

    def rates_for(self, model: object) -> dict[str, float] | None:
        if not isinstance(model, str) or not model:
            return None
        direct = self.models.get(model)
        if direct is not None:
            return direct
        alias_target = (self.aliases or {}).get(model)
        if not alias_target:
            return None
        return self.models.get(alias_target)

    def priced_as(self, model: object) -> str | None:
        if not isinstance(model, str) or not model:
            return None
        if model in self.models:
            return model
        alias_target = (self.aliases or {}).get(model)
        if alias_target and alias_target in self.models:
            return alias_target
        return None

    def is_estimated_model(self, model: object) -> bool:
        priced_as = self.priced_as(model)
        return bool(priced_as and priced_as in (self.estimated_models or set()))


def load_pricing_config(path: Path = DEFAULT_PRICING_PATH) -> PricingConfig:
    """Load optional local pricing without contacting external services."""

    if not path.exists():
        return PricingConfig(path=path, models={}, loaded=False)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        models = parse_models(raw)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return PricingConfig(path=path, models={}, loaded=False, error=str(exc))
    source = raw.get("_source") if isinstance(raw, dict) else None
    aliases = parse_aliases(raw)
    return PricingConfig(
        path=path,
        models=models,
        loaded=True,
        aliases=aliases,
        estimated_models=parse_estimated_models(raw),
        source=source if isinstance(source, dict) else None,
    )


def write_pricing_template(path: Path = DEFAULT_PRICING_PATH, force: bool = False) -> Path:
    """Write a local pricing template for user-maintained cost estimates."""

    if path.exists() and not force:
        raise FileExistsError(f"Pricing config already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(PRICING_TEMPLATE, indent=2) + "\n", encoding="utf-8")
    return path


def pin_pricing_snapshot(
    *,
    source_path: Path = DEFAULT_PRICING_PATH,
    output_path: Path,
    force: bool = False,
) -> Path:
    """Copy the current local pricing config to a reproducible report snapshot."""

    config = load_pricing_config(source_path)
    if config.error:
        raise ValueError(f"pricing config is invalid: {config.error}")
    if not config.loaded:
        raise FileNotFoundError(f"pricing config does not exist: {source_path}")
    output_path = output_path.expanduser()
    if output_path.exists() and not force:
        raise FileExistsError(f"pricing snapshot already exists: {output_path}")
    raw = json.loads(source_path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("pricing config must be a JSON object")
    source_payload = raw.get("_source")
    source: dict[str, Any] = source_payload if isinstance(source_payload, dict) else {}
    raw["_source"] = {
        **source,
        "pinned": True,
        "pinned_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "pin_note": "Use this file with --pricing for reproducible historical reports.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def parse_models(raw: object) -> dict[str, dict[str, float]]:
    if not isinstance(raw, dict):
        raise ValueError("pricing config must be a JSON object")
    model_payload = raw.get("models", raw)
    if not isinstance(model_payload, dict):
        raise ValueError("pricing config 'models' must be an object")

    models: dict[str, dict[str, float]] = {}
    for model, rates in model_payload.items():
        if not isinstance(model, str) or model.startswith("_"):
            continue
        if not isinstance(rates, dict):
            continue
        input_rate = _required_rate(rates, "input_per_million", model)
        cached_rate = _optional_rate(rates, "cached_input_per_million")
        output_rate = _required_rate(rates, "output_per_million", model)
        models[model] = {
            "input_per_million": float(input_rate),
            "cached_input_per_million": float(
                cached_rate if cached_rate is not None else input_rate
            ),
            "output_per_million": float(output_rate),
        }
    return models


def parse_aliases(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    aliases = raw.get("aliases")
    if not isinstance(aliases, dict):
        return {}
    parsed: dict[str, str] = {}
    for source, target in aliases.items():
        if isinstance(source, str) and isinstance(target, str) and source and target:
            parsed[source] = target
    return parsed


def parse_estimated_models(raw: object) -> set[str]:
    if not isinstance(raw, dict):
        return set()
    model_payload = raw.get("models", raw)
    if not isinstance(model_payload, dict):
        return set()
    return {
        model
        for model, rates in model_payload.items()
        if isinstance(model, str) and isinstance(rates, dict) and rates.get("estimated") is True
    }


def load_existing_aliases(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return parse_aliases(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, TypeError, json.JSONDecodeError):
        return {}


def _required_rate(rates: dict[str, Any], key: str, model: str) -> float:
    value = _optional_rate(rates, key)
    if value is None:
        raise ValueError(f"missing {key} for model {model}")
    return value


def _optional_rate(rates: dict[str, Any], key: str) -> float | None:
    value = rates.get(key)
    if value is None:
        return None
    parsed = _number(value)
    if parsed < 0:
        raise ValueError(f"{key} cannot be negative")
    return parsed


def _number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return 0.0
