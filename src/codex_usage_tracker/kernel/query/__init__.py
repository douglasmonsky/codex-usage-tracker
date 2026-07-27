"""Bounded generation-consistent kernel query engine."""

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
]
