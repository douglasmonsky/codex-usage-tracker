from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_usage_tracker.pricing import openai as pricing_openai
from codex_usage_tracker.pricing.api import (
    ESTIMATED_MODEL_PRICES,
    OPENAI_LATEST_MODEL_MD_URL,
    OPENAI_PRICING_MD_URL,
    PRICING_SCHEMA,
    PricingParseError,
    annotate_rows_with_efficiency,
    efficiency_flags,
    estimate_cost_usd,
    load_pricing_config,
    parse_openai_latest_model_id,
    parse_openai_pricing_markdown,
    summarize_pricing_coverage,
    update_pricing_from_openai_docs,
)

OPENAI_PRICING_FIXTURE = """
<TextTokenPricingTables
  client:load
  tier="standard"
  rows={[
    ["gpt-5.6-sol", 5, 0.5, 6.25, 30],
    ["gpt-5.6-terra", 2.5, 0.25, 3.125, 15],
    ["gpt-5.6-luna", 1, 0.1, 1.25, 6],
    ["gpt-5.5 (<272K context length)", 5, 0.5, 30],
    ["gpt-5.4-mini", 0.75, 0.075, 4.5],
    ["gpt-5-pro", 15, null, 120],
  ]}
/>
<TextTokenPricingTables
  client:load
  tier="batch"
  rows={[
    ["gpt-5.5 (<272K context length)", 2.5, 0.25, 15],
  ]}
/>
"""


def test_pricing_fetch_rejects_non_https_sources() -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        pricing_openai._fetch_text("file:///tmp/pricing.md")


OPENAI_LATEST_MODEL_FIXTURE = """---
latestModelInfo:
  model: gpt-5.6-sol
  migrationGuide: /api/docs/guides/upgrading-to-gpt-5p6-sol.md
---
"""


def test_parse_openai_pricing_markdown_for_selected_tier() -> None:
    models = parse_openai_pricing_markdown(OPENAI_PRICING_FIXTURE, tier="standard")

    assert models["gpt-5.6-sol"] == {
        "input_per_million": 5.0,
        "cached_input_per_million": 0.5,
        "output_per_million": 30.0,
        "long_context_threshold_tokens": 272_000,
        "long_context_input_multiplier": 2.0,
        "long_context_output_multiplier": 1.5,
    }
    assert models["gpt-5.6-terra"]["output_per_million"] == 15
    assert models["gpt-5.6-luna"]["output_per_million"] == 6
    assert models["gpt-5.6-terra"]["long_context_threshold_tokens"] == 272_000
    assert models["gpt-5.6-luna"]["long_context_input_multiplier"] == 2
    assert models["gpt-5.5"]["input_per_million"] == 5
    assert models["gpt-5.5"]["cached_input_per_million"] == 0.5
    assert models["gpt-5.5"]["output_per_million"] == 30
    assert models["gpt-5.4-mini"]["output_per_million"] == 4.5
    assert models["gpt-5-pro"]["cached_input_per_million"] == 15


def test_parse_openai_pricing_markdown_uses_requested_tier() -> None:
    models = parse_openai_pricing_markdown(OPENAI_PRICING_FIXTURE, tier="batch")

    assert models == {
        "gpt-5.5": {
            "input_per_million": 2.5,
            "cached_input_per_million": 0.25,
            "output_per_million": 15.0,
            "long_context_threshold_tokens": 272_000,
            "long_context_input_multiplier": 2.0,
            "long_context_output_multiplier": 1.5,
        }
    }


def test_parse_openai_pricing_markdown_does_not_invent_priority_long_context_rates() -> None:
    source = (
        OPENAI_PRICING_FIXTURE
        + """
<TextTokenPricingTables
  client:load
  tier="priority"
  rows={[
    ["gpt-5.6-sol", 10, 1, 12.5, 60],
    ["gpt-5.5 (<272K context length)", 12.5, 1.25, "-", 75],
  ]}
/>
"""
    )
    models = parse_openai_pricing_markdown(source, tier="priority")

    assert "long_context_threshold_tokens" not in models["gpt-5.6-sol"]
    assert "long_context_input_multiplier" not in models["gpt-5.5"]


def test_parse_openai_latest_model_id_reads_front_matter() -> None:
    assert parse_openai_latest_model_id(OPENAI_LATEST_MODEL_FIXTURE) == "gpt-5.6-sol"
    assert OPENAI_LATEST_MODEL_MD_URL.endswith("/latest-model.md")


def test_parse_openai_latest_model_id_reports_schema_changes() -> None:
    try:
        parse_openai_latest_model_id("# Latest model\n")
    except PricingParseError as exc:
        assert "latestModelInfo.model" in str(exc)
    else:
        raise AssertionError("expected PricingParseError")


def test_parse_openai_pricing_markdown_reports_schema_changes() -> None:
    missing_tier = OPENAI_PRICING_FIXTURE.replace('tier="standard"', 'tier="other"')
    missing_rows = OPENAI_PRICING_FIXTURE.replace("rows={[", "items={[", 1)
    malformed_rows = """
<TextTokenPricingTables
  tier="standard"
  rows={[
    ["not-parseable"]
  ]}
/>
"""

    for source, expected in [
        (missing_tier, "tier marker"),
        (missing_rows, "rows"),
        (malformed_rows, "no parseable text-token pricing rows"),
    ]:
        try:
            parse_openai_pricing_markdown(source, tier="standard")
        except PricingParseError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("expected PricingParseError")


def test_update_pricing_from_openai_docs_writes_source_metadata(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"

    result = update_pricing_from_openai_docs(
        pricing_path,
        fetch_text=lambda url: OPENAI_PRICING_FIXTURE,
    )
    raw = json.loads(pricing_path.read_text(encoding="utf-8"))
    config = load_pricing_config(pricing_path)

    assert result.model_count == 8
    assert result.estimated_model_count == 2
    assert result.source_url == OPENAI_PRICING_MD_URL
    assert raw["_schema"] == PRICING_SCHEMA
    assert raw["_source"]["url"] == OPENAI_PRICING_MD_URL
    assert raw["_source"]["tier"] == "standard"
    assert raw["_source"]["estimated_model_count"] == 2
    assert raw["aliases"]["gpt-5.6"] == "gpt-5.6-sol"
    assert raw["models"]["codex-auto-review"] == ESTIMATED_MODEL_PRICES["codex-auto-review"]
    assert raw["models"]["gpt-5.3-codex-spark"] == ESTIMATED_MODEL_PRICES["gpt-5.3-codex-spark"]
    assert config.loaded
    assert config.source and config.source["name"] == "OpenAI Developers pricing docs"
    assert config.models["gpt-5.5"]["output_per_million"] == 30
    assert config.rates_for("gpt-5.6") == config.models["gpt-5.6-sol"]
    assert config.priced_as("gpt-5.6") == "gpt-5.6-sol"
    assert config.models["codex-auto-review"]["input_per_million"] == 1.5
    assert config.is_estimated_model("codex-auto-review")
    assert config.models["gpt-5.3-codex-spark"]["input_per_million"] == 1.75
    assert config.is_estimated_model("gpt-5.3-codex-spark")


def test_update_pricing_from_openai_docs_can_skip_estimates(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"

    result = update_pricing_from_openai_docs(
        pricing_path,
        fetch_text=lambda url: OPENAI_PRICING_FIXTURE,
        include_estimates=False,
    )
    raw = json.loads(pricing_path.read_text(encoding="utf-8"))

    assert result.model_count == 6
    assert result.estimated_model_count == 0
    assert "codex-auto-review" not in raw["models"]
    assert "gpt-5.3-codex-spark" not in raw["models"]


def test_estimate_cost_applies_long_context_pricing_to_individual_calls(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    update_pricing_from_openai_docs(
        pricing_path,
        fetch_text=lambda url: OPENAI_PRICING_FIXTURE,
        include_estimates=False,
    )
    pricing = load_pricing_config(pricing_path)
    row = {
        "record_id": "call-long-context",
        "model": "gpt-5.6-sol",
        "input_tokens": 300_000,
        "cached_input_tokens": 200_000,
        "uncached_input_tokens": 100_000,
        "output_tokens": 10_000,
    }

    assert estimate_cost_usd(row, pricing) == pytest.approx(1.65)


def test_estimate_cost_does_not_apply_call_threshold_to_aggregate_rows(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    update_pricing_from_openai_docs(
        pricing_path,
        fetch_text=lambda url: OPENAI_PRICING_FIXTURE,
        include_estimates=False,
    )
    pricing = load_pricing_config(pricing_path)
    aggregate = {
        "model": "gpt-5.6-sol",
        "input_tokens": 300_000,
        "cached_input_tokens": 200_000,
        "uncached_input_tokens": 100_000,
        "output_tokens": 10_000,
    }

    assert estimate_cost_usd(aggregate, pricing) == pytest.approx(0.9)


def test_pricing_coverage_marks_internal_estimates(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    update_pricing_from_openai_docs(
        pricing_path,
        fetch_text=lambda url: OPENAI_PRICING_FIXTURE,
    )
    coverage = summarize_pricing_coverage(
        [
            {
                "group_key": "codex-auto-review",
                "total_tokens": 2_000_000,
                "input_tokens": 1_000_000,
                "cached_input_tokens": 500_000,
                "uncached_input_tokens": 500_000,
                "output_tokens": 1_000_000,
            },
            {
                "group_key": "gpt-5.3-codex-spark",
                "total_tokens": 2_000_000,
                "input_tokens": 1_000_000,
                "cached_input_tokens": 500_000,
                "uncached_input_tokens": 500_000,
                "output_tokens": 1_000_000,
            },
        ],
        pricing=load_pricing_config(pricing_path),
    )

    assert coverage["priced_model_count"] == 2
    assert coverage["estimated_cost_usd"] == 21.9
    assert all(row["pricing_estimated"] is True for row in coverage["rows"])
    assert {row["priced_as"] for row in coverage["rows"]} == {
        "codex-auto-review",
        "gpt-5.3-codex-spark",
    }


def test_efficiency_annotation_includes_stable_flag_keys(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-test": {
                        "input_per_million": 1.0,
                        "cached_input_per_million": 0.1,
                        "output_per_million": 5.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rows = annotate_rows_with_efficiency(
        [
            {
                "model": "gpt-test",
                "input_tokens": 30_000,
                "cached_input_tokens": 0,
                "uncached_input_tokens": 30_000,
                "output_tokens": 80,
                "total_tokens": 30_080,
                "context_window_percent": 0.82,
            }
        ],
        pricing=load_pricing_config(pricing_path),
    )

    assert rows[0]["efficiency_flags"] == [
        "high context use",
        "low cache reuse",
        "expensive low-output call",
    ]
    assert rows[0]["efficiency_flag_keys"] == [
        "flag.high_context_use",
        "flag.low_cache_reuse",
        "flag.expensive_low_output_call",
    ]


def test_efficiency_flags_cover_remaining_thresholds() -> None:
    assert efficiency_flags(
        {
            "context_window_percent": 0.5,
            "reasoning_output_ratio": 0.75,
            "output_tokens": 100,
            "estimated_cost_usd": 1.0,
        }
    ) == [
        "elevated context use",
        "high reasoning share",
        "high estimated cost",
    ]
