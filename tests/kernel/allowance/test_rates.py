from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.allowance import LocalUsage
from codex_usage_tracker.kernel.allowance.rates import (
    estimate_local_usage,
    load_rate_card,
    rate_card_status,
)


def test_source_stamped_rate_card_estimates_cost_credits_and_coverage(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rate-card.json"
    path.write_text(
        json.dumps(
            {
                "schema": "codex-usage-tracker.kernel-rate-card.v1",
                "source": {
                    "name": "Synthetic rate card",
                    "url": "https://example.invalid/rates",
                    "effective_at": "2026-01-01",
                    "fetched_at": "2026-01-02",
                },
                "models": {
                    "gpt-synthetic": {
                        "input_per_million": 10,
                        "cached_input_per_million": 1,
                        "output_per_million": 20,
                        "credits_input_per_million": 5,
                        "credits_cached_input_per_million": 0.5,
                        "credits_output_per_million": 10,
                        "confidence": "exact",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    card = load_rate_card(path)

    estimate = estimate_local_usage(
        {
            "gpt-synthetic": LocalUsage(
                uncached_input_tokens=100,
                cached_input_tokens=50,
                reasoning_tokens=20,
                output_tokens=30,
                calls=1,
                turns=1,
            ),
            "unrated-model": LocalUsage(
                uncached_input_tokens=20,
                output_tokens=10,
                calls=1,
                turns=1,
            ),
        },
        card,
    )

    assert estimate.estimated_cost_usd == pytest.approx(0.00165)
    assert estimate.estimated_credits == pytest.approx(0.000825)
    assert estimate.rated_tokens == 180
    assert estimate.total_tokens == 210
    assert estimate.coverage_percent == pytest.approx(100 * 180 / 210)
    assert estimate.unrated_models == ("unrated-model",)
    assert estimate.provenance["name"] == "Synthetic rate card"
    assert estimate.provenance["effective_at"] == "2026-01-01"
    assert rate_card_status(path) == {
        "configured": True,
        "status": "ready",
        "source": {
            "name": "Synthetic rate card",
            "url": "https://example.invalid/rates",
            "effective_at": "2026-01-01",
            "fetched_at": "2026-01-02",
        },
        "model_count": 1,
        "revision": card.digest,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema": "wrong", "source": {}, "models": {}},
        {
            "schema": "codex-usage-tracker.kernel-rate-card.v1",
            "source": {"name": "missing provenance"},
            "models": {},
        },
        {
            "schema": "codex-usage-tracker.kernel-rate-card.v1",
            "source": {
                "name": "Synthetic",
                "url": "https://user:secret@example.invalid/rates",
                "effective_at": "2026-01-01",
                "fetched_at": "2026-01-02",
            },
            "models": {"": {}},
        },
        {
            "schema": "codex-usage-tracker.kernel-rate-card.v1",
            "source": {
                "name": "Synthetic",
                "url": "https://example.invalid/rates",
                "effective_at": "2026-01-01",
                "fetched_at": "2026-01-02",
            },
            "models": {
                "gpt-synthetic": {
                    "input_per_million": math.nan,
                    "cached_input_per_million": 1,
                    "output_per_million": 1,
                    "credits_input_per_million": 1,
                    "credits_cached_input_per_million": 1,
                    "credits_output_per_million": 1,
                    "confidence": "exact",
                }
            },
        },
    ],
)
def test_invalid_rate_card_fails_closed(tmp_path: Path, payload: object) -> None:
    path = tmp_path / "rate-card.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="rate card"):
        load_rate_card(path)
