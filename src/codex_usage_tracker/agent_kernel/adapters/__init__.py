"""Explicit adapter boundary for the clean agent-kernel implementation."""

from .contracts import (
    ADAPTER_CONTRACT,
    ADAPTER_ID,
    ADAPTER_VERSION,
    AdapterIdentity,
    AdapterObservation,
    Capability,
    CursorOutcome,
    IngestMetrics,
    ParseDiagnostic,
    SourceCursor,
    SourceInventory,
    SourceRange,
)

__all__ = [
    "ADAPTER_CONTRACT",
    "ADAPTER_ID",
    "ADAPTER_VERSION",
    "AdapterIdentity",
    "AdapterObservation",
    "Capability",
    "CursorOutcome",
    "IngestMetrics",
    "ParseDiagnostic",
    "SourceCursor",
    "SourceInventory",
    "SourceRange",
]
