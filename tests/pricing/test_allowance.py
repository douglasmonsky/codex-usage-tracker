from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_usage_tracker.pricing.allowance import (
    UsageAllowanceConfig,
    annotate_rows_with_allowance,
    load_allowance_config,
    parse_allowance_text,
    update_rate_card,
    write_allowance_from_text,
    write_allowance_template,
)


def _credit_row(
    *, model: str, fast: int | None, service_tier: str | None
) -> dict[str, object]:
    return {
        "model": model,
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "uncached_input_tokens": 80,
        "output_tokens": 10,
        "total_tokens": 110,
        "fast": fast,
        "service_tier": service_tier,
        "service_tier_source": "otel_response_completed" if fast is not None else None,
        "service_tier_confidence": "exact" if fast is not None else None,
    }


def _synthetic_allowance_config() -> UsageAllowanceConfig:
    rates = {
        "input_per_million": 10.0,
        "cached_input_per_million": 1.0,
        "output_per_million": 50.0,
    }
    models = (
        "gpt-5.6",
        "gpt-5.6-sol",
        "gpt-5.5",
        "gpt-5.4",
        "synthetic-unknown",
    )
    return UsageAllowanceConfig(
        path=Path("/synthetic/allowance.json"),
        rate_card_path=Path("/synthetic/rate-card.json"),
        credit_rates={model: dict(rates) for model in models},
        aliases={},
        rate_metadata={model: {} for model in models},
        alias_metadata={},
        windows=[],
        loaded=True,
        rate_card_loaded=True,
        source={"name": "Synthetic credit rates"},
    )


@pytest.mark.parametrize(
    ("model", "multiplier"),
    [
        ("gpt-5.6", 2.5),
        ("gpt-5.6-sol", 2.5),
        ("gpt-5.5", 2.5),
        ("gpt-5.4", 2.0),
    ],
)
def test_confirmed_fast_multiplies_standard_credit_estimate(
    model: str, multiplier: float
) -> None:
    row = _credit_row(model=model, fast=1, service_tier="fast")

    annotated = annotate_rows_with_allowance(
        [row], _synthetic_allowance_config()
    )[0]

    assert annotated["usage_credits"] == pytest.approx(
        annotated["standard_usage_credits"] * multiplier
    )
    assert annotated["usage_credit_multiplier"] == multiplier
    assert annotated["usage_credit_multiplier_source"] == "otel_response_completed"


@pytest.mark.parametrize("fast", [0, None])
def test_standard_and_unknown_rows_keep_multiplier_one(fast: int | None) -> None:
    row = _credit_row(
        model="gpt-5.6",
        fast=fast,
        service_tier="standard" if fast == 0 else None,
    )

    annotated = annotate_rows_with_allowance(
        [row], _synthetic_allowance_config()
    )[0]

    assert annotated["usage_credits"] == annotated["standard_usage_credits"]
    assert annotated["usage_credit_multiplier"] == 1.0


def test_confirmed_fast_unknown_model_does_not_invent_multiplier() -> None:
    row = _credit_row(model="synthetic-unknown", fast=1, service_tier="fast")

    annotated = annotate_rows_with_allowance(
        [row], _synthetic_allowance_config()
    )[0]

    assert annotated["usage_credit_multiplier"] == 1.0
    assert (
        annotated["usage_credit_multiplier_source"]
        == "no_documented_fast_multiplier"
    )


def test_unpriced_rows_include_bounded_multiplier_annotations() -> None:
    row = _credit_row(model="not-in-rate-card", fast=1, service_tier="fast")

    annotated = annotate_rows_with_allowance(
        [row], _synthetic_allowance_config()
    )[0]

    assert annotated["usage_credits"] is None
    assert annotated["standard_usage_credits"] is None
    assert annotated["usage_credit_multiplier"] == 1.0
    assert (
        annotated["usage_credit_multiplier_source"]
        == "no_documented_fast_multiplier"
    )


def test_allowance_estimates_exact_codex_credit_usage() -> None:
    rows = annotate_rows_with_allowance(
        [
            {
                "model": "gpt-5.5",
                "input_tokens": 1000,
                "cached_input_tokens": 200,
                "uncached_input_tokens": 800,
                "output_tokens": 100,
                "total_tokens": 1100,
            }
        ]
    )

    assert rows[0]["usage_credit_model"] == "gpt-5.5"
    assert rows[0]["usage_credit_confidence"] == "exact"
    assert rows[0]["usage_credit_source_url"] == "https://developers.openai.com/codex/pricing"
    assert rows[0]["usage_credit_fetched_at"] == "2026-07-09"
    assert rows[0]["usage_credit_tier"] == "standard"
    assert rows[0]["usage_credits"] == 0.1775


def test_allowance_estimates_gpt_5_6_direct_and_alias_credit_usage() -> None:
    rows = annotate_rows_with_allowance(
        [
            {
                "model": model,
                "input_tokens": 1000,
                "cached_input_tokens": 200,
                "uncached_input_tokens": 800,
                "output_tokens": 100,
                "total_tokens": 1100,
            }
            for model in ("gpt-5.6-sol", "gpt-5.6")
        ]
    )

    assert [row["usage_credit_model"] for row in rows] == [
        "gpt-5.6-sol",
        "gpt-5.6-sol",
    ]
    assert [row["usage_credit_confidence"] for row in rows] == ["exact", "exact"]
    assert [row["usage_credits"] for row in rows] == [0.355, 0.355]


def test_allowance_marks_inferred_auto_review_mapping() -> None:
    rows = annotate_rows_with_allowance(
        [
            {
                "model": "codex-auto-review",
                "input_tokens": 1000,
                "cached_input_tokens": 500,
                "uncached_input_tokens": 500,
                "output_tokens": 100,
                "total_tokens": 1100,
            }
        ]
    )

    assert rows[0]["usage_credit_model"] == "gpt-5.3-codex"
    assert rows[0]["usage_credit_confidence"] == "estimated"
    assert (
        rows[0]["usage_credit_source_url"]
        == "https://help.openai.com/en/articles/20001106-codex-rate-card"
    )
    assert rows[0]["usage_credits"] == 0.0590625


def test_allowance_config_loads_windows_and_local_aliases(tmp_path: Path) -> None:
    path = tmp_path / "allowance.json"
    path.write_text(
        json.dumps(
            {
                "windows": {
                    "five_hour": {
                        "label": "5h",
                        "remaining_percent": 79,
                        "reset_at": "2026-06-03T18:50:00-04:00",
                    }
                },
                "aliases": {
                    "local-codex": {
                        "model": "gpt-5.4-mini",
                        "confidence": "estimated",
                        "note": "Local test alias.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_allowance_config(path)
    rows = annotate_rows_with_allowance(
        [
            {
                "model": "local-codex",
                "input_tokens": 1000,
                "cached_input_tokens": 0,
                "uncached_input_tokens": 1000,
                "output_tokens": 100,
                "total_tokens": 1100,
            }
        ],
        config,
    )

    assert config.loaded is True
    assert config.windows[0].remaining_percent == 0.79
    assert config.windows[0].reset_at == "2026-06-03T18:50:00-04:00"
    assert rows[0]["usage_credit_model"] == "gpt-5.4-mini"
    assert rows[0]["usage_credit_note"] == "Local test alias."


def test_allowance_marks_local_credit_rate_override(tmp_path: Path) -> None:
    path = tmp_path / "allowance.json"
    path.write_text(
        json.dumps(
            {
                "credit_rates": {
                    "local-codex": {
                        "input_per_million": 10,
                        "cached_input_per_million": 1,
                        "output_per_million": 20,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rows = annotate_rows_with_allowance(
        [
            {
                "model": "local-codex",
                "input_tokens": 1000,
                "cached_input_tokens": 0,
                "uncached_input_tokens": 1000,
                "output_tokens": 100,
                "total_tokens": 1100,
            }
        ],
        load_allowance_config(path),
    )

    assert rows[0]["usage_credit_confidence"] == "user_override"
    assert rows[0]["usage_credit_source"] == "Local allowance override"


def test_parse_allowance_text_reads_status_percentages() -> None:
    windows = parse_allowance_text(
        """
        Usage remaining
        5h 79% 6:50 PM
        Weekly 33% Jun 7
        Upgrade for more usage
        """,
        captured_at="2026-06-05T12:00:00Z",
    )

    assert [(window.key, window.remaining_percent, window.reset_at) for window in windows] == [
        ("five_hour", 0.79, "6:50 PM"),
        ("weekly", 0.33, "Jun 7"),
    ]
    assert windows[0].captured_at == "2026-06-05T12:00:00Z"


def test_write_allowance_from_text_preserves_local_overrides(tmp_path: Path) -> None:
    path = tmp_path / "allowance.json"
    path.write_text(
        json.dumps(
            {
                "credit_rates": {
                    "local-codex": {
                        "input_per_million": 1,
                        "cached_input_per_million": 1,
                        "output_per_million": 1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    write_allowance_from_text(
        "5h 79% 6:50 PM\nWeekly 33% Jun 7",
        path=path,
        captured_at="2026-06-05T12:00:00Z",
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["credit_rates"]["local-codex"]["input_per_million"] == 1
    assert raw["windows"][0]["remaining_percent"] == 0.79
    assert raw["_source"]["exact_allowance_source"] is False


def test_update_rate_card_writes_bundled_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "rate-card.json"

    result = update_rate_card(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    config = load_allowance_config(tmp_path / "missing-allowance.json", rate_card_path=path)

    assert result.model_count == 8
    assert result.alias_count == 2
    assert raw["schema"] == "codex-usage-tracker-codex-rate-card-v1"
    assert config.rate_card_loaded is True
    assert config.source["fetched_at"] == "2026-07-09"
    assert config.credit_rates["gpt-5.6-sol"]["output_per_million"] == 1500.0
    assert config.credit_rates["gpt-5.6-terra"]["output_per_million"] == 125.0
    assert config.credit_rates["gpt-5.6-luna"]["output_per_million"] == 300.0


def test_write_allowance_template_refuses_to_overwrite(tmp_path: Path) -> None:
    path = write_allowance_template(tmp_path / "allowance.json")

    try:
        write_allowance_template(path)
    except FileExistsError as exc:
        assert "Allowance config already exists" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")
