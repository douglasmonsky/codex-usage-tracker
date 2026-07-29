"""CK-04 Candidate A: typed facts with indexed multi-table evidence merge."""

from .adapter import Adapter
from .evidence import (
    EvidenceContractError,
    EvidencePage,
    all_evidence_rows,
    evidence_page,
    resolve_selector,
)
from .ingest import BuildArtifact, IngestStats, build_artifact
from .maintenance import (
    MaintenanceStats,
    TailFoldRequired,
    apply_ordinary_change,
    apply_source_phase,
)
from .publication import CandidateACrashDriver, publish_artifact
from .schema import (
    MODEL_CALL_TAIL_MAX_ROWS,
    SCHEMA_ID,
    SCHEMA_VERSION,
    database,
    open_database,
)

__all__ = [
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "MODEL_CALL_TAIL_MAX_ROWS",
    "Adapter",
    "BuildArtifact",
    "CandidateACrashDriver",
    "EvidenceContractError",
    "EvidencePage",
    "IngestStats",
    "MaintenanceStats",
    "TailFoldRequired",
    "all_evidence_rows",
    "apply_ordinary_change",
    "apply_source_phase",
    "build_artifact",
    "database",
    "evidence_page",
    "open_database",
    "publish_artifact",
    "resolve_selector",
]
