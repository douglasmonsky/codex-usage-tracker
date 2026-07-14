from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.recommendation_engine.materialization import (
    backfill_recommendation_facts,
)
from codex_usage_tracker.recommendation_engine.query import (
    RecommendationFactsUnavailableError,
    build_indexed_recommendations_report,
)
from codex_usage_tracker.recommendation_engine.query import (
    build_recommendations_report as build_engine_recommendations_report,
)
from codex_usage_tracker.reports.query import build_recommendations_report
from codex_usage_tracker.store.api import upsert_usage_events
from codex_usage_tracker.store.connection import connect
from tests.store_dashboard_helpers import _usage_event, _write_pricing


def _materialize_actionable_event(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    allowance_path = tmp_path / "allowance.json"
    projects_path = tmp_path / "projects.json"
    event = replace(
        _usage_event(
            record_id="indexed",
            session_id="session-indexed",
            thread_key="thread:indexed",
            event_timestamp="2026-07-13T12:00:00Z",
            cumulative_total_tokens=900_000,
        ),
        input_tokens=250_000,
        cached_input_tokens=1_000,
        total_tokens=250_050,
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        backfill_recommendation_facts(
            conn,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
        )
    return db_path, pricing_path, allowance_path, projects_path


def test_indexed_recommendations_match_legacy_payload(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    allowance_path = tmp_path / "allowance.json"
    projects_path = tmp_path / "projects.json"
    events = [
        replace(
            _usage_event(
                record_id="high-context",
                session_id="session-a",
                thread_key="thread:alpha",
                event_timestamp="2026-07-13T12:00:00Z",
                cumulative_total_tokens=900_000,
            ),
            model_context_window=1_000,
            input_tokens=950,
            cached_input_tokens=100,
            total_tokens=975,
        ),
        replace(
            _usage_event(
                record_id="large-call",
                session_id="session-b",
                thread_key="thread:beta",
                event_timestamp="2026-07-13T13:00:00Z",
                cumulative_total_tokens=900_000,
            ),
            input_tokens=250_000,
            cached_input_tokens=1_000,
            output_tokens=50,
            reasoning_output_tokens=40_000,
            total_tokens=250_050,
        ),
        replace(
            _usage_event(
                record_id="archived-call",
                session_id="session-archived",
                thread_key="thread:archived",
                event_timestamp="2026-07-12T13:00:00Z",
                cumulative_total_tokens=900_000,
            ),
            input_tokens=250_000,
            cached_input_tokens=1_000,
            total_tokens=250_050,
            is_archived=1,
        ),
    ]
    upsert_usage_events(events, db_path=db_path)
    with connect(db_path) as conn:
        backfill_recommendation_facts(
            conn,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
        )

    arguments: dict[str, Any] = {
        "db_path": db_path,
        "pricing_path": pricing_path,
        "allowance_path": allowance_path,
        "projects_path": projects_path,
        "limit": 10,
    }
    legacy = build_recommendations_report(**arguments)
    indexed = build_indexed_recommendations_report(**arguments)

    assert indexed.payload == legacy.payload

    archived_arguments = {**arguments, "include_archived": True}
    archived_legacy = build_recommendations_report(**archived_arguments)
    archived_indexed = build_indexed_recommendations_report(**archived_arguments)

    assert archived_indexed.payload == archived_legacy.payload


def test_recommendations_require_materialized_facts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    allowance_path = tmp_path / "allowance.json"
    projects_path = tmp_path / "projects.json"
    event = replace(
        _usage_event(
            record_id="legacy-only",
            session_id="session-legacy",
            thread_key="thread:legacy",
            event_timestamp="2026-07-13T12:00:00Z",
            cumulative_total_tokens=900_000,
        ),
        input_tokens=250_000,
        cached_input_tokens=1_000,
        total_tokens=250_050,
    )
    upsert_usage_events([event], db_path=db_path)
    arguments: dict[str, Any] = {
        "db_path": db_path,
        "pricing_path": pricing_path,
        "allowance_path": allowance_path,
        "projects_path": projects_path,
    }

    with pytest.raises(RecommendationFactsUnavailableError, match="refresh"):
        build_engine_recommendations_report(**arguments)


def test_recommendations_use_current_materialized_facts(
    tmp_path: Path,
) -> None:
    db_path, pricing_path, allowance_path, projects_path = _materialize_actionable_event(tmp_path)

    report = build_engine_recommendations_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        projects_path=projects_path,
    )

    assert report.payload["row_count"] == 1


def test_recommendations_require_refresh_when_config_changes(
    tmp_path: Path,
) -> None:
    db_path, pricing_path, allowance_path, projects_path = _materialize_actionable_event(tmp_path)
    pricing = json.loads(pricing_path.read_text(encoding="utf-8"))
    pricing["models"]["gpt-5.5"]["input_per_million"] = 3.0
    pricing_path.write_text(json.dumps(pricing), encoding="utf-8")

    with pytest.raises(RecommendationFactsUnavailableError, match="refresh"):
        build_engine_recommendations_report(
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            projects_path=projects_path,
        )


def test_recommendations_require_refresh_when_threshold_fingerprint_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    allowance_path = tmp_path / "allowance.json"
    rate_card_path = tmp_path / "rate-card.json"
    thresholds_path = tmp_path / "thresholds.json"
    projects_path = tmp_path / "projects.json"
    thresholds_path.write_text('{"high_uncached_input_tokens": 10000}\n', encoding="utf-8")
    event = replace(
        _usage_event(
            record_id="threshold-indexed",
            session_id="session-threshold",
            thread_key="thread:threshold",
            event_timestamp="2026-07-13T12:00:00Z",
            cumulative_total_tokens=900_000,
        ),
        input_tokens=250_000,
        cached_input_tokens=1_000,
        total_tokens=250_050,
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        backfill_recommendation_facts(
            conn,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            thresholds_path=thresholds_path,
        )
    arguments: dict[str, Any] = {
        "db_path": db_path,
        "pricing_path": pricing_path,
        "allowance_path": allowance_path,
        "rate_card_path": rate_card_path,
        "thresholds_path": thresholds_path,
        "projects_path": projects_path,
    }

    assert build_engine_recommendations_report(**arguments).payload["row_count"] == 1

    thresholds_path.write_text('{"high_uncached_input_tokens": 300000}\n', encoding="utf-8")
    with pytest.raises(RecommendationFactsUnavailableError, match="refresh"):
        build_engine_recommendations_report(**arguments)


def test_recommendations_reject_retired_source_limit_fallback(
    tmp_path: Path,
) -> None:
    db_path, pricing_path, allowance_path, projects_path = _materialize_actionable_event(tmp_path)

    with pytest.raises(ValueError, match="source_limit is no longer supported"):
        build_engine_recommendations_report(
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            projects_path=projects_path,
            source_limit=1,
        )
