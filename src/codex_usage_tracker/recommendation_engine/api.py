"""Application refresh entry points with recommendation fact maintenance."""

from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.core.models import RefreshResult
from codex_usage_tracker.core.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH
from codex_usage_tracker.recommendation_engine.materialization import (
    sync_refresh_recommendation_facts,
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
) -> RefreshResult:
    return _refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        progress_callback=progress_callback,
        derived_fact_sync=sync_refresh_recommendation_facts,
    )


def rebuild_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
) -> RefreshResult:
    return _rebuild_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        derived_fact_sync=sync_refresh_recommendation_facts,
    )
