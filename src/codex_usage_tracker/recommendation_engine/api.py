"""Recommendation query and refresh entry points."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from codex_usage_tracker.core.models import RefreshResult
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.recommendation_engine.materialization import (
    sync_refresh_recommendation_facts,
)
from codex_usage_tracker.recommendation_engine.query import (
    build_recommendations_report as build_recommendations_report,
)
from codex_usage_tracker.store.api import rebuild_usage_index as _rebuild_usage_index
from codex_usage_tracker.store.api import refresh_usage_index as _refresh_usage_index
from codex_usage_tracker.store.refresh_parse import RefreshProgressCallback


def refresh_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    progress_callback: RefreshProgressCallback | None = None,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
) -> RefreshResult:
    return _refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        progress_callback=progress_callback,
        derived_fact_sync=partial(
            sync_refresh_recommendation_facts,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            thresholds_path=thresholds_path,
        ),
    )


def rebuild_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
) -> RefreshResult:
    return _rebuild_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        derived_fact_sync=partial(
            sync_refresh_recommendation_facts,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            thresholds_path=thresholds_path,
        ),
    )
