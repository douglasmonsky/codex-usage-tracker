from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codex_usage_tracker.allowance_intelligence.analysis import build_allowance_analysis
from codex_usage_tracker.application.allowance import get_allowance
from codex_usage_tracker.application.allowance_models import AllowanceRequest
from codex_usage_tracker.store.connection import connect
from tests.application.test_allowance import _seed

ANCHOR = datetime(2026, 7, 22, 11, tzinfo=timezone.utc)
START_8W = "2026-05-27T11:00:00+00:00"
END = "2026-07-22T11:00:00+00:00"


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        return ANCHOR if tz is not None else ANCHOR.replace(tzinfo=None)


@pytest.fixture
def allowance_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from codex_usage_tracker.allowance_intelligence import service
    from codex_usage_tracker.cli import mcp_allowance
    from codex_usage_tracker.server import allowance_v2

    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)
    monkeypatch.setattr(mcp_allowance, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(allowance_v2, "datetime", _FrozenDateTime)
    monkeypatch.setattr(service, "datetime", _FrozenDateTime)
    return db_path


def test_legacy_allowance_public_signatures_are_unchanged() -> None:
    from codex_usage_tracker.cli.mcp_allowance import (
        usage_allowance_analysis,
        usage_allowance_evidence,
        usage_allowance_series,
        usage_allowance_status,
    )

    assert tuple(inspect.signature(usage_allowance_status).parameters) == (
        "include_archived",
        "privacy_mode",
        "since_revision",
    )
    assert tuple(inspect.signature(usage_allowance_series).parameters) == (
        "range_preset",
        "start_at",
        "end_at",
        "granularity",
        "window_kind",
        "cohort_id",
        "include_archived",
    )
    assert tuple(inspect.signature(usage_allowance_evidence).parameters) == (
        "limit",
        "before",
        "order",
        "window_kind",
        "cohort_id",
        "start_at",
        "end_at",
        "include_archived",
        "privacy_mode",
    )
    assert tuple(inspect.signature(usage_allowance_analysis).parameters) == (
        "window_kind",
        "cohort_id",
        "forecast_horizon",
        "include_archived",
        "min_cycles_per_side",
        "permutation_count",
        "start_if_missing",
    )
    for function, operation in (
        (usage_allowance_status, "status"),
        (usage_allowance_series, "series"),
        (usage_allowance_evidence, "evidence"),
        (usage_allowance_analysis, "analysis"),
    ):
        docstring = inspect.getdoc(function) or ""
        assert "Compatibility tool" in docstring
        assert f'usage_allowance(operation="{operation}")' in docstring


def test_legacy_status_equals_canonical_application_payload(allowance_fixture: Path) -> None:
    from codex_usage_tracker.cli.mcp_allowance import usage_allowance_status

    legacy = usage_allowance_status(
        include_archived=False,
        privacy_mode="strict",
        since_revision=None,
    )
    canonical = get_allowance(
        AllowanceRequest("status"), db_path=allowance_fixture, now=ANCHOR
    ).payload

    assert legacy == canonical


def test_legacy_series_equals_canonical_application_payload(allowance_fixture: Path) -> None:
    from codex_usage_tracker.cli.mcp_allowance import usage_allowance_series

    legacy = usage_allowance_series(
        range_preset="8w",
        start_at=None,
        end_at=None,
        granularity="auto",
        window_kind="weekly",
        cohort_id=None,
        include_archived=False,
    )
    canonical = get_allowance(
        AllowanceRequest("series", window="weekly", range="8w"),
        db_path=allowance_fixture,
        now=ANCHOR,
    ).payload

    assert legacy == canonical


def test_legacy_terminal_evidence_equals_canonical_application_payload(
    allowance_fixture: Path,
) -> None:
    from codex_usage_tracker.cli.mcp_allowance import usage_allowance_evidence

    legacy = usage_allowance_evidence(
        limit=50,
        before=None,
        order="desc",
        window_kind="weekly",
        cohort_id=None,
        start_at=START_8W,
        end_at=END,
        include_archived=False,
        privacy_mode="strict",
    )
    canonical = get_allowance(
        AllowanceRequest("evidence", window="weekly", range="8w", limit=50),
        db_path=allowance_fixture,
        now=ANCHOR,
    ).payload

    assert legacy["next_cursor"] is None
    assert legacy == canonical


def test_legacy_persisted_analysis_equals_canonical_application_payload(
    allowance_fixture: Path,
) -> None:
    from codex_usage_tracker.cli.mcp_allowance import usage_allowance_analysis

    with connect(allowance_fixture) as connection:
        build_allowance_analysis(connection, now=ANCHOR)
    legacy = usage_allowance_analysis(
        window_kind="weekly",
        cohort_id="codex",
        forecast_horizon=1,
        include_archived=False,
        min_cycles_per_side=None,
        permutation_count=None,
        start_if_missing=True,
    )
    canonical = get_allowance(
        AllowanceRequest("analysis", window="weekly", range="8w"),
        db_path=allowance_fixture,
        now=ANCHOR,
    ).payload

    assert legacy == canonical
