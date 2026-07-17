from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.pricing.allowance import load_allowance_config


def test_local_fast_multiplier_override_is_source_stamped(tmp_path: Path) -> None:
    path = tmp_path / "allowance.json"
    path.write_text(
        json.dumps(
            {
                "fast_multipliers": {
                    "gpt-5.6": {
                        "multiplier": 3.0,
                        "source_name": "Synthetic override",
                        "source_url": "https://example.invalid/synthetic-fast-rate",
                        "fetched_at": "2026-07-16",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_allowance_config(
        path, rate_card_path=tmp_path / "missing-rate-card.json"
    )
    rate = config.fast_multipliers["gpt-5.6"]

    assert rate.multiplier == 3.0
    assert rate.source_name == "Synthetic override"
    assert rate.source_url == "https://example.invalid/synthetic-fast-rate"
    assert rate.fetched_at == "2026-07-16"
    assert rate.confidence == "user_override"


def test_malformed_local_multiplier_retains_valid_bundled_rate(tmp_path: Path) -> None:
    path = tmp_path / "allowance.json"
    path.write_text(
        json.dumps(
            {"fast_multipliers": {"gpt-5.6": {"multiplier": 0.5}}}
        ),
        encoding="utf-8",
    )

    config = load_allowance_config(
        path, rate_card_path=tmp_path / "missing-rate-card.json"
    )

    assert config.loaded is True
    assert config.fast_multipliers["gpt-5.6"].multiplier == 2.5
    assert config.fast_multipliers["gpt-5.6"].confidence == "exact"


def test_boolean_local_multiplier_retains_valid_bundled_rate(tmp_path: Path) -> None:
    path = tmp_path / "allowance.json"
    path.write_text(
        json.dumps(
            {"fast_multipliers": {"gpt-5.6": {"multiplier": True}}}
        ),
        encoding="utf-8",
    )

    config = load_allowance_config(
        path, rate_card_path=tmp_path / "missing-rate-card.json"
    )

    assert config.loaded is True
    assert config.fast_multipliers["gpt-5.6"].multiplier == 2.5
    assert config.fast_multipliers["gpt-5.6"].confidence == "exact"


def test_legacy_local_rate_card_inherits_bundled_fast_multipliers(
    tmp_path: Path,
) -> None:
    rate_card_path = tmp_path / "legacy-rate-card.json"
    rate_card_path.write_text(
        json.dumps(
            {
                "schema": "codex-usage-tracker-codex-rate-card-v1",
                "credit_rates": {
                    "gpt-5.6": {
                        "input_per_million": 1,
                        "cached_input_per_million": 1,
                        "output_per_million": 1,
                    }
                },
                "aliases": {},
            }
        ),
        encoding="utf-8",
    )

    config = load_allowance_config(
        tmp_path / "missing-allowance.json", rate_card_path=rate_card_path
    )

    assert config.rate_card_loaded is True
    assert config.fast_multipliers["gpt-5.6"].multiplier == 2.5
