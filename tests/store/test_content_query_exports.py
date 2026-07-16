from __future__ import annotations

import csv
from pathlib import Path

from codex_usage_tracker.store import content_index
from codex_usage_tracker.store.api import export_usage_csv, upsert_usage_events
from codex_usage_tracker.store.content_index_models import ContentIndexPlan, ContentIndexResult
from codex_usage_tracker.store.content_persistence import (
    clear_content_index_rows,
    delete_content_index_rows_for_source_files,
)
from codex_usage_tracker.store.content_search import (
    ContentSearchResult,
    search_content_fragments,
)
from codex_usage_tracker.store.content_trace import ContentTraceResult, trace_thread_content
from tests.otel_helpers import synthetic_usage_event


def test_content_index_preserves_query_exports() -> None:
    assert content_index.ContentIndexPlan is ContentIndexPlan
    assert content_index.ContentIndexResult is ContentIndexResult
    assert content_index.ContentSearchResult is ContentSearchResult
    assert content_index.ContentTraceResult is ContentTraceResult
    assert content_index.search_content_fragments is search_content_fragments
    assert content_index.trace_thread_content is trace_thread_content
    assert content_index.clear_content_index_rows is clear_content_index_rows
    assert (
        content_index.delete_content_index_rows_for_source_files
        is delete_content_index_rows_for_source_files
    )


def test_csv_export_includes_additive_service_tier_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            synthetic_usage_event(
                "record-a", "conversation-a", (100, 40, 30, 10), fast=1
            )
        ],
        db_path=db_path,
    )
    output_path = tmp_path / "usage.csv"

    export_usage_csv(output_path, db_path=db_path)

    header = next(csv.reader(output_path.read_text(encoding="utf-8").splitlines()))
    assert [
        name for name in header if name.startswith("service_tier") or name == "fast"
    ] == [
        "service_tier",
        "fast",
        "service_tier_source",
        "service_tier_confidence",
    ]
