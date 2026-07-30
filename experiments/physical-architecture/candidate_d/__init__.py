"""CK-04 Candidate D: typed facts plus a compact sequence index."""

from .adapter import Adapter
from .crash import CandidateDCrashDriver
from .store import (
    BuildStats,
    CandidateDIntegrityError,
    CandidateDStore,
    OrderKey,
    QueryResult,
    SequenceRow,
    StorageStats,
    copy_for_unsafe_change,
    load_current_store,
    publish_new_store,
)

__all__ = [
    "Adapter",
    "BuildStats",
    "CandidateDCrashDriver",
    "CandidateDIntegrityError",
    "CandidateDStore",
    "OrderKey",
    "QueryResult",
    "SequenceRow",
    "StorageStats",
    "copy_for_unsafe_change",
    "load_current_store",
    "publish_new_store",
]
