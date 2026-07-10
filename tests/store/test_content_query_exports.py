from codex_usage_tracker.store import content_index
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
