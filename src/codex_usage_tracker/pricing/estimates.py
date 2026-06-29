"""Explicitly marked internal Codex model pricing estimates."""

from __future__ import annotations

OPENAI_CODEX_LAUNCH_URL = "https://openai.com/index/introducing-codex/"
OPENAI_GPT_53_CODEX_MODEL_URL = "https://developers.openai.com/api/docs/models/gpt-5.3-codex"
OPENAI_CODEX_RATE_CARD_URL = "https://help.openai.com/en/articles/20001106-codex-rate-card"

PricingEstimateValue = float | bool | str

ESTIMATED_MODEL_PRICES: dict[str, dict[str, PricingEstimateValue]] = {
    "codex-auto-review": {
        "input_per_million": 1.5,
        "cached_input_per_million": 0.375,
        "output_per_million": 6.0,
        "estimated": True,
        "estimate_basis_model": "codex-mini-latest",
        "estimate_source_url": OPENAI_CODEX_LAUNCH_URL,
        "estimate_reason": (
            "codex-auto-review is an internal Codex model label without a public "
            "pricing row; estimate uses OpenAI-published codex-mini-latest rates."
        ),
    },
    "gpt-5.3-codex-spark": {
        "input_per_million": 1.75,
        "cached_input_per_million": 0.175,
        "output_per_million": 14.0,
        "estimated": True,
        "estimate_basis_model": "gpt-5.3-codex",
        "estimate_source_url": OPENAI_GPT_53_CODEX_MODEL_URL,
        "estimate_reference_url": OPENAI_CODEX_RATE_CARD_URL,
        "estimate_reason": (
            "GPT-5.3-Codex-Spark is listed by OpenAI as a research preview "
            "without final Codex credit rates; estimate uses the published "
            "GPT-5.3-Codex text-token rates until Spark rates are finalized."
        ),
    },
}


def estimated_model_prices() -> dict[str, dict[str, PricingEstimateValue]]:
    """Return a copy of configured internal model estimates."""

    return {model: dict(rates) for model, rates in ESTIMATED_MODEL_PRICES.items()}
