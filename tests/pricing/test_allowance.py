from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.pricing.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
    parse_allowance_text,
    update_rate_card,
    write_allowance_from_text,
    write_allowance_template,
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
    assert (
        rows[0]["usage_credit_source_url"]
        == "https://help.openai.com/en/articles/20001106-codex-rate-card"
    )
    assert rows[0]["usage_credit_fetched_at"] == "2026-06-03"
    assert rows[0]["usage_credit_tier"] == "standard"
    assert rows[0]["usage_credits"] == 0.1775


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

    assert result.model_count == 5
    assert result.alias_count == 1
    assert raw["schema"] == "codex-usage-tracker-codex-rate-card-v1"
    assert config.rate_card_loaded is True
    assert config.source["fetched_at"] == "2026-06-03"


def test_write_allowance_template_refuses_to_overwrite(tmp_path: Path) -> None:
    path = write_allowance_template(tmp_path / "allowance.json")

    try:
        write_allowance_template(path)
    except FileExistsError as exc:
        assert "Allowance config already exists" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")
