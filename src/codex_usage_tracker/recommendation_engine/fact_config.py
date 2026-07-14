"""Configuration identity for persisted recommendation facts."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.pricing.allowance_config import (
    UsageAllowanceConfig,
    load_allowance_config,
)
from codex_usage_tracker.pricing.allowance_usage import annotate_rows_with_allowance
from codex_usage_tracker.pricing.config import PricingConfig, load_pricing_config
from codex_usage_tracker.pricing.costing import annotate_rows_with_efficiency
from codex_usage_tracker.reports.recommendations import (
    ThresholdConfig,
    annotate_rows_with_recommendations,
    load_threshold_config,
)

RECOMMENDATION_FACTS_VERSION = 1
RECOMMENDATION_ALGORITHM_VERSION = 1
_IGNORED_CONFIG_FIELDS = frozenset({"error", "path", "rate_card_error", "rate_card_path"})


@dataclass(frozen=True)
class RecommendationFactConfig:
    pricing: PricingConfig
    allowance: UsageAllowanceConfig
    thresholds: ThresholdConfig
    fingerprint: str


def annotate_rows_for_recommendation_facts(
    rows: list[dict[str, Any]],
    config: RecommendationFactConfig,
) -> list[dict[str, Any]]:
    values = annotate_rows_with_efficiency(rows, config.pricing)
    values = annotate_rows_with_allowance(values, config.allowance)
    return annotate_rows_with_recommendations(values, config.thresholds)


def load_recommendation_fact_config(
    *,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
) -> RecommendationFactConfig:
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(allowance_path, rate_card_path=rate_card_path)
    thresholds = load_threshold_config(thresholds_path)
    payload = {
        "algorithm_version": RECOMMENDATION_ALGORITHM_VERSION,
        "allowance": _canonical_config(allowance),
        "facts_version": RECOMMENDATION_FACTS_VERSION,
        "pricing": _canonical_config(pricing),
        "thresholds": _canonical_config(thresholds),
    }
    fingerprint = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return RecommendationFactConfig(pricing, allowance, thresholds, fingerprint)


def recommendation_generation_fingerprint(
    *,
    source_generation: int,
    config_fingerprint: str,
) -> str:
    payload = {
        "algorithm_version": RECOMMENDATION_ALGORITHM_VERSION,
        "config_fingerprint": config_fingerprint,
        "facts_version": RECOMMENDATION_FACTS_VERSION,
        "source_generation": source_generation,
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_config(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_config(getattr(value, item.name))
            for item in fields(value)
            if item.name not in _IGNORED_CONFIG_FIELDS
        }
    if isinstance(value, dict):
        return {str(key): _canonical_config(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical_config(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical_config(item) for item in value)
    if isinstance(value, Path):
        return value.name
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
