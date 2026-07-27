"""Strict local rate-card loading and aggregate estimate calculations."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .efficiency import LocalUsage

RATE_CARD_SCHEMA = "codex-usage-tracker.kernel-rate-card.v1"
MAX_RATE_CARD_BYTES = 256 * 1024
MAX_RATE_CARD_MODELS = 256
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_RATE_FIELDS = (
    "input_per_million",
    "cached_input_per_million",
    "output_per_million",
    "credits_input_per_million",
    "credits_cached_input_per_million",
    "credits_output_per_million",
)


@dataclass(frozen=True)
class ModelRates:
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float
    credits_input_per_million: float
    credits_cached_input_per_million: float
    credits_output_per_million: float
    confidence: str


@dataclass(frozen=True)
class RateCard:
    source: dict[str, str]
    models: dict[str, ModelRates]


@dataclass(frozen=True)
class UsageEstimate:
    estimated_cost_usd: float | None
    estimated_credits: float | None
    rated_tokens: int
    total_tokens: int
    coverage_percent: float
    unrated_models: tuple[str, ...]
    provenance: dict[str, str] | None


def load_rate_card(path: Path) -> RateCard | None:
    """Load one source-stamped local card; absence means unconfigured."""

    if not path.is_file():
        return None
    try:
        if path.stat().st_size > MAX_RATE_CARD_BYTES:
            raise ValueError("rate card exceeds the size limit")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("rate card is unreadable") from exc
    if not isinstance(payload, dict) or payload.get("schema") != RATE_CARD_SCHEMA:
        raise ValueError("rate card schema is invalid")
    source = _source(payload.get("source"))
    raw_models = payload.get("models")
    if (
        not isinstance(raw_models, dict)
        or not 1 <= len(raw_models) <= MAX_RATE_CARD_MODELS
    ):
        raise ValueError("rate card models are invalid")
    if any(
        not isinstance(model, str) or _MODEL_NAME.fullmatch(model) is None
        for model in raw_models
    ):
        raise ValueError("rate card model name is invalid")
    return RateCard(
        source=source,
        models={
            model: _model_rates(model, raw)
            for model, raw in raw_models.items()
        },
    )


def rate_card_status(path: Path) -> dict[str, Any]:
    """Return bounded provenance for Settings and status responses."""

    try:
        card = load_rate_card(path)
    except ValueError:
        return {"configured": False, "status": "invalid", "source": None}
    if card is None:
        return {"configured": False, "status": "absent", "source": None}
    return {
        "configured": True,
        "status": "ready",
        "source": card.source,
        "model_count": len(card.models),
    }


def estimate_local_usage(
    usage_by_model: dict[str, LocalUsage],
    card: RateCard | None,
) -> UsageEstimate:
    """Estimate only rated local facts and expose exact token coverage."""

    total_tokens = sum(usage.total_tokens for usage in usage_by_model.values())
    if card is None:
        return UsageEstimate(
            estimated_cost_usd=None,
            estimated_credits=None,
            rated_tokens=0,
            total_tokens=total_tokens,
            coverage_percent=100.0 if total_tokens == 0 else 0.0,
            unrated_models=tuple(sorted(usage_by_model)),
            provenance=None,
        )
    cost = 0.0
    credits = 0.0
    rated_tokens = 0
    unrated: list[str] = []
    for model, usage in usage_by_model.items():
        rates = card.models.get(model)
        if rates is None:
            unrated.append(model)
            continue
        rated_tokens += usage.total_tokens
        cost += _estimate(
            usage,
            rates.input_per_million,
            rates.cached_input_per_million,
            rates.output_per_million,
        )
        credits += _estimate(
            usage,
            rates.credits_input_per_million,
            rates.credits_cached_input_per_million,
            rates.credits_output_per_million,
        )
    coverage = 100.0 if total_tokens == 0 else 100.0 * rated_tokens / total_tokens
    return UsageEstimate(
        estimated_cost_usd=cost if rated_tokens else None,
        estimated_credits=credits if rated_tokens else None,
        rated_tokens=rated_tokens,
        total_tokens=total_tokens,
        coverage_percent=coverage,
        unrated_models=tuple(sorted(unrated)),
        provenance=card.source,
    )


def _estimate(
    usage: LocalUsage,
    input_rate: float,
    cached_rate: float,
    output_rate: float,
) -> float:
    return (
        usage.uncached_input_tokens * input_rate
        + usage.cached_input_tokens * cached_rate
        + usage.output_tokens * output_rate
    ) / 1_000_000


def _source(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError("rate card source is invalid")
    required = ("name", "url", "effective_at", "fetched_at")
    if any(
        not isinstance(raw.get(name), str)
        or not raw[name]
        or len(raw[name]) > (2048 if name == "url" else 256)
        or any(ord(character) < 32 for character in raw[name])
        for name in required
    ):
        raise ValueError("rate card source provenance is incomplete")
    parsed = urlsplit(raw["url"])
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("rate card source URL is invalid")
    return {name: raw[name] for name in required}


def _model_rates(model: str, raw: Any) -> ModelRates:
    if not isinstance(raw, dict):
        raise ValueError(f"rate card model {model} is invalid")
    values = {name: _rate(raw.get(name), model) for name in _RATE_FIELDS}
    confidence = raw.get("confidence")
    if confidence not in {"exact", "estimated", "user_override"}:
        raise ValueError(f"rate card model {model} confidence is invalid")
    return ModelRates(**values, confidence=confidence)


def _rate(value: Any, model: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"rate card model {model} rate is invalid")
    return float(value)
