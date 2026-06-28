from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_recommendations


@dataclass
class _Report:
    payload: dict[str, object]


def test_recommendations_payload_normalizes_query_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"schema": "codex-usage-tracker-recommendations-v1"})

    monkeypatch.setattr(server_recommendations, "build_recommendations_report", build_report)

    payload = server_recommendations.recommendations_payload(
        "limit=7&min_score=0.25&model=gpt-5.5&project=tracker",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="redacted",
    )

    assert payload["schema"] == "codex-usage-tracker-recommendations-v1"
    assert payload["raw_context_included"] is False
    assert calls["limit"] == 7
    assert calls["min_score"] == 0.25
    assert calls["model"] == "gpt-5.5"
    assert calls["project"] == "tracker"
    assert calls["privacy_mode"] == "redacted"


def test_recommendations_payload_uses_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({})

    monkeypatch.setattr(server_recommendations, "build_recommendations_report", build_report)

    payload = server_recommendations.recommendations_payload(
        "",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
    )

    assert payload == {"raw_context_included": False}
    assert calls["limit"] == 20
    assert calls["min_score"] is None


def test_recommendations_payload_rejects_invalid_min_score(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="min_score must be a number"):
        server_recommendations.recommendations_payload(
            "min_score=not-a-number",
            db_path=tmp_path / "usage.sqlite3",
            pricing_path=tmp_path / "pricing.json",
            allowance_path=tmp_path / "allowance.json",
            projects_path=tmp_path / "projects.json",
            privacy_mode="normal",
        )
