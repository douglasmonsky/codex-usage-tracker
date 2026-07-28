"""Bounded generation-consistent kernel query engine."""

from .catalog import (
    exploration_guidance,
    materialize_query_requests,
    query_template_context_keys,
    query_template_context_required,
)
from .contracts import (
    ComparisonWindow,
    Filter,
    Operation,
    QueryRequest,
    QueryResult,
)
from .service import QueryService, snapshot_query_template_context

__all__ = [
    "ComparisonWindow",
    "Filter",
    "Operation",
    "QueryRequest",
    "QueryResult",
    "QueryService",
    "exploration_guidance",
    "materialize_query_requests",
    "query_template_context_keys",
    "query_template_context_required",
    "snapshot_query_template_context",
]
