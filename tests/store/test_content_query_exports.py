from codex_usage_tracker.store import content_index
from codex_usage_tracker.store.content_search import (
    ContentSearchResult,
    search_content_fragments,
)
from codex_usage_tracker.store.content_trace import ContentTraceResult, trace_thread_content


def test_content_index_preserves_query_exports() -> None:
    assert content_index.ContentSearchResult is ContentSearchResult
    assert content_index.ContentTraceResult is ContentTraceResult
    assert content_index.search_content_fragments is search_content_fragments
    assert content_index.trace_thread_content is trace_thread_content
