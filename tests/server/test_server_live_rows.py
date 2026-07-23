from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.server import live_rows as server_live_rows


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "db_path": tmp_path / "usage.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "allowance_path": tmp_path / "allowance.json",
        "rate_card_path": tmp_path / "rate-card.json",
        "thresholds_path": tmp_path / "thresholds.json",
        "projects_path": tmp_path / "projects.json",
    }


def _query_params(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": 2,
        "offset": 1,
        "search": None,
        "since": None,
        "until": None,
        "model": None,
        "effort": None,
        "source": None,
        "thread": None,
        "thread_key": None,
        "include_archived": False,
        "sort": "time",
        "direction": "desc",
    }
    params.update(overrides)
    return params


def test_query_live_call_rows_counts_normal_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_rows(**kwargs: Any) -> list[dict[str, Any]]:
        calls["rows"] = kwargs
        return [{"record_id": "r1"}]

    def query_count(**kwargs: Any) -> int:
        calls["count"] = kwargs
        return 12

    monkeypatch.setattr(server_live_rows, "query_usage_api_events", query_rows)
    monkeypatch.setattr(server_live_rows, "query_usage_api_event_count", query_count)
    monkeypatch.setattr(
        server_live_rows,
        "annotate_live_rows",
        lambda rows, **_kwargs: rows,
    )

    rows, total = server_live_rows.query_live_call_rows(
        **_paths(tmp_path),
        query_params=_query_params(limit=3, offset=4, search="needle"),
        pricing_status=None,
        credit_confidence=None,
        privacy_mode="normal",
    )

    assert rows == [{"record_id": "r1"}]
    assert total == 12
    assert calls["rows"]["limit"] == 3
    assert calls["rows"]["offset"] == 4
    assert calls["rows"]["search"] == "needle"
    assert calls["count"]["search"] == "needle"


def test_query_live_call_rows_delegates_confidence_filters_to_focused_store_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_rows(**kwargs: Any) -> list[dict[str, Any]]:
        calls["rows"] = kwargs
        return [{"record_id": "r3", "pricing_model": "gpt-5.5"}]

    def query_count(**kwargs: Any) -> int:
        calls["count"] = kwargs
        return 2

    monkeypatch.setattr(server_live_rows, "query_usage_api_events", query_rows)
    monkeypatch.setattr(server_live_rows, "query_usage_api_event_count", query_count)
    monkeypatch.setattr(
        server_live_rows,
        "annotate_live_rows",
        lambda rows, **_kwargs: rows,
    )

    rows, total = server_live_rows.query_live_call_rows(
        **_paths(tmp_path),
        query_params=_query_params(limit=1, offset=1),
        pricing_status="priced",
        credit_confidence="exact",
        privacy_mode="normal",
    )

    assert rows == [{"record_id": "r3", "pricing_model": "gpt-5.5"}]
    assert total == 2
    assert calls["rows"]["limit"] == 1
    assert calls["rows"]["offset"] == 1
    assert calls["rows"]["pricing_status"] == "priced"
    assert calls["rows"]["credit_confidence"] == "exact"
    assert calls["count"]["pricing_status"] == "priced"
    assert calls["count"]["credit_confidence"] == "exact"


def test_query_live_call_rows_resolves_git_cwds_before_bounded_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_rows(**kwargs: Any) -> list[dict[str, Any]]:
        calls["rows"] = kwargs
        return [{"record_id": "git", "git_branch": "main"}]

    monkeypatch.setattr(server_live_rows, "query_usage_api_events", query_rows)
    monkeypatch.setattr(
        server_live_rows,
        "query_usage_api_distinct_cwds",
        lambda **_kwargs: ["/repo", "/plain"],
    )
    monkeypatch.setattr(
        server_live_rows,
        "load_project_config",
        lambda _path: None,
    )
    monkeypatch.setattr(
        server_live_rows,
        "project_identity_for_cwd",
        lambda cwd, _projects: {"git_branch": "main" if cwd == "/repo" else None},
    )
    monkeypatch.setattr(
        server_live_rows,
        "query_usage_api_event_count",
        lambda **_kwargs: 1,
    )
    monkeypatch.setattr(
        server_live_rows,
        "annotate_live_rows",
        lambda rows, **_kwargs: rows,
    )

    rows, total = server_live_rows.query_live_call_rows(
        **_paths(tmp_path),
        query_params=_query_params(limit=2, offset=0, source="git"),
        pricing_status=None,
        credit_confidence=None,
        privacy_mode="normal",
    )

    assert [row["record_id"] for row in rows] == ["git"]
    assert total == 1
    assert calls["rows"]["source"] is None
    assert calls["rows"]["cwds"] == ["/repo"]
    assert calls["rows"]["limit"] == 2


def test_query_live_call_rows_delegates_cost_sort_to_focused_store_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_rows(**kwargs: Any) -> list[dict[str, Any]]:
        calls["rows"] = kwargs
        return [
            {"record_id": "high", "estimated_cost_usd": 4.5},
            {"record_id": "mid", "estimated_cost_usd": 1.0},
        ]

    monkeypatch.setattr(server_live_rows, "query_usage_api_events", query_rows)
    monkeypatch.setattr(
        server_live_rows,
        "query_usage_api_event_count",
        lambda **_kwargs: 3,
    )
    monkeypatch.setattr(
        server_live_rows,
        "annotate_live_rows",
        lambda rows, **_kwargs: rows,
    )

    rows, total = server_live_rows.query_live_call_rows(
        **_paths(tmp_path),
        query_params=_query_params(limit=2, offset=0, sort="cost", direction="desc"),
        pricing_status=None,
        credit_confidence=None,
        privacy_mode="normal",
    )

    assert [row["record_id"] for row in rows] == ["high", "mid"]
    assert total == 3
    assert calls["rows"]["limit"] == 2
    assert calls["rows"]["offset"] == 0
    assert calls["rows"]["sort"] == "cost"


def test_annotate_live_rows_returns_empty_without_loading_configs(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    assert (
        server_live_rows.annotate_live_rows(
            [],
            pricing_path=paths["pricing_path"],
            allowance_path=paths["allowance_path"],
            rate_card_path=paths["rate_card_path"],
            thresholds_path=paths["thresholds_path"],
            projects_path=paths["projects_path"],
            privacy_mode="normal",
        )
        == []
    )
