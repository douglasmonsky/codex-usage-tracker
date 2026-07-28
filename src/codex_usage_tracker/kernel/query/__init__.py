"""Bounded generation-consistent kernel query engine."""

from .catalog import exploration_guidance, materialize_query_requests
from .contracts import (
    ComparisonWindow,
    Filter,
    Operation,
    QueryRequest,
    QueryResult,
)
from .service import QueryService

__all__ = [
    "ComparisonWindow",
    "Filter",
    "Operation",
    "QueryRequest",
    "QueryResult",
    "QueryService",
    "exploration_guidance",
    "materialize_query_requests",
]
