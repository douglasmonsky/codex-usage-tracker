"""CK-04 Candidate C: immutable event backbone plus typed facts."""

from .adapter import Adapter, CandidateCCrashDriver
from .database import CandidateCDatabase, CandidateCError, QueryPage
from .schema import CANDIDATE_ID, SCHEMA_VERSION

__all__ = [
    "CANDIDATE_ID",
    "SCHEMA_VERSION",
    "Adapter",
    "CandidateCCrashDriver",
    "CandidateCDatabase",
    "CandidateCError",
    "QueryPage",
]
