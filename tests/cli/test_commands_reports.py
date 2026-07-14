from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from codex_usage_tracker.cli import commands_reports


def test_run_recommendations_forwards_all_semantic_config_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> SimpleNamespace:
        calls.update(kwargs)
        return SimpleNamespace(payload={"schema": "recommendations"})

    monkeypatch.setattr(commands_reports, "build_recommendations_report", build_report)
    monkeypatch.setattr(commands_reports, "print_json", lambda _payload: None)
    args = argparse.Namespace(
        db=tmp_path / "usage.sqlite3",
        pricing=tmp_path / "pricing.json",
        allowance=tmp_path / "allowance.json",
        rate_card=tmp_path / "rate-card.json",
        thresholds=tmp_path / "thresholds.json",
        projects=tmp_path / "projects.json",
        since=None,
        until=None,
        model=None,
        effort=None,
        thread=None,
        project=None,
        include_archived=False,
        min_score=None,
        limit=20,
        privacy_mode="normal",
        as_json=True,
    )

    assert commands_reports._run_recommendations(args) == 0
    assert calls["rate_card_path"] == args.rate_card
    assert calls["thresholds_path"] == args.thresholds
