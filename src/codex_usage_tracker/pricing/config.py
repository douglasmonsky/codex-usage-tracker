"""Local pricing config loading and template writing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeGuard

from codex_usage_tracker.core.paths import DEFAULT_PRICING_PATH

PRICING_SCHEMA = "codex-usage-tracker-pricing-v2"
BILLING_BASES = ("unknown", "chatgpt_credits", "api_tokens")
API_SERVICE_TIER_ALIASES = {
    "fast": "priority",
    "priority": "priority",
    "default": "standard",
    "standard": "standard",
    "batch": "batch",
    "flex": "flex",
}
PRICING_TEMPLATE = {
    "_comment": (
        "Fill in current prices in USD per 1 million tokens. The tracker does "
        "not fetch pricing during normal reports. Prefer update-pricing when "
        "you want to cache current OpenAI-published rates locally."
    ),
    "_schema": PRICING_SCHEMA,
    "billing_basis": "unknown",
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
    api_service_tiers: dict[str, dict[str, dict[str, float]]] | None = None
    billing_basis: str = "unknown"

    def rates_for(
        self, model: object, *, service_tier: object | None = None
    ) -> dict[str, float] | None:
        normalized_tier = normalize_api_service_tier(service_tier)
        tier_models = (self.api_service_tiers or {}).get(normalized_tier or "")
        if tier_models is not None:
            return _rates_for_models(tier_models, self.aliases, model)
        return _rates_for_models(self.models, self.aliases, model)

    def pricing_tier_for(self, service_tier: object | None) -> str | None:
        normalized = normalize_api_service_tier(service_tier)
        if normalized and normalized in (self.api_service_tiers or {}):
            return normalized
        source_tier = normalize_api_service_tier((self.source or {}).get("tier"))
        return source_tier if source_tier else None

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
        api_service_tiers = parse_api_service_tiers(raw)
        billing_basis = parse_billing_basis(raw)
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
        api_service_tiers=api_service_tiers,
        billing_basis=billing_basis,
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
    model_payload = _required_model_payload(raw)
    models: dict[str, dict[str, float]] = {}
    for model, rates in model_payload.items():
        if not _valid_model_name(model):
            continue
        parsed_rates = _parsed_model_rates(model, rates)
        if parsed_rates is not None:
            models[model] = parsed_rates
    return models


def parse_api_service_tiers(
    raw: object,
) -> dict[str, dict[str, dict[str, float]]]:
    if not isinstance(raw, dict):
        return {}
    tier_payload = raw.get("api_service_tiers")
    if tier_payload is None:
        return {}
    if not isinstance(tier_payload, dict):
        raise ValueError("pricing config 'api_service_tiers' must be an object")
    parsed: dict[str, dict[str, dict[str, float]]] = {}
    for raw_tier, models in tier_payload.items():
        tier = normalize_api_service_tier(raw_tier)
        if tier is None or not isinstance(models, dict):
            raise ValueError(f"invalid API service tier pricing entry: {raw_tier!r}")
        parsed[tier] = _parse_model_payload(models)
    return parsed


def parse_billing_basis(raw: object) -> str:
    if not isinstance(raw, dict):
        return "unknown"
    value = raw.get("billing_basis", "unknown")
    if not isinstance(value, str) or value not in BILLING_BASES:
        raise ValueError(
            f"unknown billing_basis {value!r}; expected one of {', '.join(BILLING_BASES)}"
        )
    return value


def normalize_api_service_tier(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return API_SERVICE_TIER_ALIASES.get(value.strip().lower())


def _rates_for_models(
    models: dict[str, dict[str, float]],
    aliases: dict[str, str] | None,
    model: object,
) -> dict[str, float] | None:
    if not isinstance(model, str) or not model:
        return None
    direct = models.get(model)
    if direct is not None:
        return direct
    alias_target = (aliases or {}).get(model)
    return models.get(alias_target) if alias_target else None


def _parse_model_payload(
    model_payload: dict[object, object],
) -> dict[str, dict[str, float]]:
    models: dict[str, dict[str, float]] = {}
    for model, rates in model_payload.items():
        if not _valid_model_name(model):
            continue
        parsed_rates = _parsed_model_rates(model, rates)
        if parsed_rates is not None:
            models[model] = parsed_rates
    return models


def _required_model_payload(raw: object) -> dict[object, object]:
    if not isinstance(raw, dict):
        raise ValueError("pricing config must be a JSON object")
    model_payload = raw.get("models", raw)
    if not isinstance(model_payload, dict):
        raise ValueError("pricing config 'models' must be an object")
    return model_payload


def _optional_model_payload(raw: object) -> dict[object, object]:
    if not isinstance(raw, dict):
        return {}
    model_payload = raw.get("models", raw)
    if not isinstance(model_payload, dict):
        return {}
    return model_payload


def _parsed_model_rates(model: str, rates: object) -> dict[str, float] | None:
    if not isinstance(rates, dict):
        return None
    input_rate = _required_rate(rates, "input_per_million", model)
    cached_rate = _optional_rate(rates, "cached_input_per_million")
    output_rate = _required_rate(rates, "output_per_million", model)
    parsed = {
        "input_per_million": float(input_rate),
        "cached_input_per_million": float(cached_rate if cached_rate is not None else input_rate),
        "output_per_million": float(output_rate),
    }
    for key in (
        "long_context_threshold_tokens",
        "long_context_input_multiplier",
        "long_context_output_multiplier",
    ):
        value = _optional_rate(rates, key)
        if value is not None:
            parsed[key] = float(value)
    return parsed


def _valid_model_name(model: object) -> TypeGuard[str]:
    return isinstance(model, str) and not model.startswith("_")


def parse_aliases(raw: object) -> dict[str, str]:
    aliases = _optional_named_mapping(raw, "aliases")
    parsed: dict[str, str] = {}
    for alias in aliases.items():
        if _valid_alias(alias):
            source, target = alias
            parsed[source] = target
    return parsed


def _optional_named_mapping(raw: object, field: str) -> dict[object, object]:
    if not isinstance(raw, dict):
        return {}
    value = raw.get(field)
    if not isinstance(value, dict):
        return {}
    return value


def _valid_alias(alias: tuple[object, object]) -> TypeGuard[tuple[str, str]]:
    source, target = alias
    return all(
        (
            isinstance(source, str),
            isinstance(target, str),
            bool(source),
            bool(target),
        )
    )


def parse_estimated_models(raw: object) -> set[str]:
    model_payload = _optional_model_payload(raw)
    return {model for model, rates in model_payload.items() if _estimated_model_entry(model, rates)}


def _estimated_model_entry(model: object, rates: object) -> TypeGuard[str]:
    return isinstance(model, str) and isinstance(rates, dict) and rates.get("estimated") is True


def load_existing_aliases(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return parse_aliases(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, TypeError, json.JSONDecodeError):
        return {}


def load_existing_billing_basis(path: Path) -> str:
    if not path.exists():
        return "unknown"
    try:
        return parse_billing_basis(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return "unknown"


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
