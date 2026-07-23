from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codex_usage_tracker.application.container import build_application_container
from codex_usage_tracker.application.paths import ApplicationPaths
from codex_usage_tracker.application.requests import RequestScope


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)


def _paths(tmp_path: Path) -> ApplicationPaths:
    return ApplicationPaths(
        codex_home=tmp_path / "codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
    )


def test_container_is_frozen_and_preserves_custom_paths(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    container = build_application_container(paths, clock=_FixedClock())

    assert container.paths is paths
    assert container.clock.now() == datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)
    with pytest.raises(FrozenInstanceError):
        container.paths = _paths(tmp_path / "other")  # type: ignore[misc]


def test_container_shares_one_job_repository_and_does_not_read_default_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda cls: (_ for _ in ()).throw(AssertionError("default home accessed"))),
    )

    container = build_application_container(_paths(tmp_path), clock=_FixedClock())

    assert container.repositories.jobs is container.jobs
    assert container.repositories.analysis_results is container.jobs
    context = container.request_context(RequestScope())
    assert context.freshness.state == "empty"
    assert context.application_paths is container.paths
    assert not tmp_path.joinpath("usage.sqlite3").exists()
