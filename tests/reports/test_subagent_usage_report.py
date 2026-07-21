from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.reports import subagent_usage as report_module
from codex_usage_tracker.reports.subagent_usage import build_subagent_usage_report
from tests.store_dashboard_helpers import _write_pricing


def _bucket(total_tokens: int, calls: int, turns: int, spawns: int) -> dict[str, Any]:
    metrics = {
        "calls": calls,
        "turns": turns,
        "observed_spawns": spawns,
        "input_tokens": total_tokens,
        "cached_input_tokens": total_tokens // 2,
        "uncached_input_tokens": total_tokens - (total_tokens // 2),
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": total_tokens,
        "latest_event": "2026-07-21T12:00:00Z",
    }
    return {
        "metrics": metrics,
        "model_buckets": [{**metrics, "model": "gpt-5.5", "service_tier": "standard"}],
    }


def query_fixture() -> dict[str, Any]:
    subagent = _bucket(300, 4, 3, 2)
    direct = _bucket(600, 5, 4, 0)
    return {
        "cohorts": {
            "direct": direct,
            "subagent": subagent,
            "attributable_subagent": subagent,
        },
        "breakdowns": {
            "role": [{"group_key": "worker", **subagent}],
            "type": [{"group_key": "thread_spawn", **subagent}],
            "parent": [{"group_key": "Synthetic parent", **subagent}],
        },
        "coverage": {
            "missing_session_rows": 0,
            "missing_session_tokens": 0,
            "missing_role_spawns": 0,
            "missing_type_spawns": 0,
        },
    }


def _empty_fixture() -> dict[str, Any]:
    empty = _bucket(0, 0, 0, 0)
    empty["metrics"]["latest_event"] = None
    empty["model_buckets"] = []
    return {
        "cohorts": {
            "direct": empty,
            "subagent": empty,
            "attributable_subagent": empty,
        },
        "breakdowns": {"role": [], "type": [], "parent": []},
        "coverage": {
            "missing_session_rows": 0,
            "missing_session_tokens": 0,
            "missing_role_spawns": 0,
            "missing_type_spawns": 0,
        },
    }


def _patch_query(monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]) -> None:
    monkeypatch.setattr(
        report_module,
        "query_subagent_usage_buckets",
        lambda *args, **kwargs: result,
    )


def test_report_builds_v1_spawn_and_comparison_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_query(monkeypatch, query_fixture())
    pricing_path = _write_pricing(tmp_path / "pricing.json")

    report = build_subagent_usage_report(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=pricing_path,
    ).payload()

    assert report["schema_id"] == "codex-usage-tracker.subagent-usage.v1"
    assert report["definitions"]["observed_comparison_not_causal"] is True
    assert report["summary"]["observed_spawns"] == 2
    assert report["summary"]["total_tokens_per_observed_spawn"] == 150.0
    assert report["comparison"]["subagent"]["total_tokens"] == 300
    assert report["comparison"]["direct"]["total_tokens"] == 600
    assert report["summary"]["subagent_token_share"] == pytest.approx(1 / 3)


def test_report_uses_only_attributable_usage_for_per_spawn_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = query_fixture()
    fixture["cohorts"]["attributable_subagent"] = _bucket(240, 3, 2, 2)
    _patch_query(monkeypatch, fixture)

    summary = build_subagent_usage_report(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=_write_pricing(tmp_path / "pricing.json"),
    ).payload()["summary"]

    assert summary["total_tokens"] == 300
    assert summary["calls"] == 4
    assert summary["total_tokens_per_observed_spawn"] == 120.0
    assert summary["calls_per_observed_spawn"] == 1.5
    assert summary["turns_per_observed_spawn"] == 1.0


def test_zero_denominators_render_as_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = query_fixture()
    fixture["cohorts"]["attributable_subagent"] = _bucket(300, 4, 3, 0)
    fixture["cohorts"]["direct"] = _bucket(0, 0, 0, 0)
    fixture["cohorts"]["subagent"] = _bucket(0, 0, 0, 0)
    _patch_query(monkeypatch, fixture)

    summary = build_subagent_usage_report(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=_write_pricing(tmp_path / "pricing.json"),
    ).payload()["summary"]

    assert summary["total_tokens_per_observed_spawn"] is None
    assert summary["calls_per_observed_spawn"] is None
    assert summary["turns_per_observed_spawn"] is None
    assert summary["estimated_cost_usd_per_observed_spawn"] is None
    assert summary["subagent_token_share"] is None


def test_pricing_coverage_separates_priced_estimated_and_unpriced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = query_fixture()
    bucket = fixture["cohorts"]["subagent"]
    bucket["model_buckets"] = [
        {**_bucket(100, 1, 1, 1)["metrics"], "model": "official", "service_tier": "standard"},
        {**_bucket(80, 1, 1, 1)["metrics"], "model": "estimated", "service_tier": "standard"},
        {**_bucket(120, 1, 1, 1)["metrics"], "model": "unknown", "service_tier": "standard"},
    ]
    _patch_query(monkeypatch, fixture)
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "official": {
                        "input_per_million": 2.0,
                        "cached_input_per_million": 0.5,
                        "output_per_million": 10.0,
                    },
                    "estimated": {
                        "input_per_million": 2.0,
                        "cached_input_per_million": 0.5,
                        "output_per_million": 10.0,
                        "estimated": True,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    summary = build_subagent_usage_report(
        db_path=tmp_path / "usage.sqlite3", pricing_path=pricing_path
    ).payload()["summary"]

    assert summary["estimated_cost_usd"] is not None
    assert summary["pricing_coverage"] == {
        "priced_model_count": 1,
        "estimated_model_count": 1,
        "unpriced_model_count": 1,
        "priced_tokens": 100,
        "estimated_tokens": 80,
        "unpriced_tokens": 120,
    }


@pytest.mark.parametrize("privacy_mode", ["redacted", "strict"])
def test_redacted_and_strict_modes_pseudonymize_parent_labels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    privacy_mode: str,
) -> None:
    _patch_query(monkeypatch, query_fixture())

    payload = build_subagent_usage_report(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=_write_pricing(tmp_path / "pricing.json"),
        privacy_mode=privacy_mode,
    ).payload()

    label = payload["top_parent_threads"][0]["group_key"]
    assert label.startswith("Parent ")
    assert len(label) == len("Parent ") + 8
    assert "Synthetic parent" not in json.dumps(payload)


def test_normal_mode_preserves_parent_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_query(monkeypatch, query_fixture())

    payload = build_subagent_usage_report(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=_write_pricing(tmp_path / "pricing.json"),
    ).payload()

    assert payload["top_parent_threads"][0]["group_key"] == "Synthetic parent"


def test_empty_report_keeps_stable_v1_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_query(monkeypatch, _empty_fixture())

    report = build_subagent_usage_report(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "missing-pricing.json",
    )
    payload = report.payload()

    assert list(payload) == [
        "schema_id",
        "generated_at",
        "filters",
        "definitions",
        "summary",
        "comparison",
        "by_role",
        "by_type",
        "top_parent_threads",
        "coverage",
        "warnings",
    ]
    assert payload["summary"]["total_tokens"] == 0
    assert payload["comparison"]["direct"]["total_tokens"] == 0
    assert payload["comparison"]["subagent"]["total_tokens"] == 0
    assert payload["by_role"] == []
    assert payload["by_type"] == []
    assert payload["top_parent_threads"] == []
    assert "No observed subagent usage matched these filters." in report.render()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"since": ""}, "since must be a non-empty ISO-8601 date or datetime"),
        ({"since": "not-a-date"}, "since must be an ISO-8601 date or datetime"),
        ({"limit": 0}, "limit must be an integer from 1 through 100"),
        ({"limit": True}, "limit must be an integer from 1 through 100"),
        ({"privacy_mode": "private"}, "privacy_mode must be one of"),
    ],
)
def test_invalid_since_limit_and_privacy_mode_raise_value_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kwargs: dict[str, Any],
    message: str,
) -> None:
    _patch_query(monkeypatch, query_fixture())

    with pytest.raises(ValueError, match=message):
        build_subagent_usage_report(
            db_path=tmp_path / "usage.sqlite3",
            pricing_path=tmp_path / "pricing.json",
            **kwargs,
        )


def test_markdown_is_compact_and_states_non_causal_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_query(monkeypatch, query_fixture())

    markdown = build_subagent_usage_report(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=_write_pricing(tmp_path / "pricing.json"),
    ).render()

    assert (
        "Observed comparison only; it does not show that subagents caused the difference."
        in markdown
    )
    assert "## By role" in markdown
    assert "## By type" in markdown
    assert "## Top parent threads" in markdown
    assert markdown.count("- ") == 3
    assert len(markdown.splitlines()) <= 18


def test_payload_never_contains_session_ids_or_agent_nicknames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = query_fixture()
    fixture["cohorts"]["subagent"]["metrics"].update(
        {"session_id": "session-secret", "agent_nickname": "nickname-secret"}
    )
    fixture["cohorts"]["subagent"]["model_buckets"][0].update(
        {"session_id": "model-session-secret", "agent_nickname": "model-nickname-secret"}
    )
    _patch_query(monkeypatch, fixture)

    payload_text = json.dumps(
        build_subagent_usage_report(
            db_path=tmp_path / "usage.sqlite3",
            pricing_path=_write_pricing(tmp_path / "pricing.json"),
        ).payload()
    )

    assert "session_id" not in payload_text
    assert "session-secret" not in payload_text
    assert "agent_nickname" not in payload_text
    assert "nickname-secret" not in payload_text
