"""Closed, kind-specific canonical evidence selectors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, TypeAlias

from codex_usage_tracker.core.dashboard_targets import (
    is_canonical_record_id,
    is_canonical_thread_key,
)

EvidenceSelectorKind: TypeAlias = Literal["finding", "call", "thread", "allowance", "analysis"]
_KINDS = {"finding", "call", "thread", "allowance", "analysis"}
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,255}\Z")


@dataclass(frozen=True)
class EvidenceSelector:
    kind: EvidenceSelectorKind
    selector_id: str

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"unsupported selector_kind: {self.kind}")
        valid = isinstance(self.selector_id, str) and _SAFE.fullmatch(self.selector_id) is not None
        if self.kind == "call":
            valid = isinstance(self.selector_id, str) and is_canonical_record_id(self.selector_id)
        if self.kind == "thread":
            valid = isinstance(self.selector_id, str) and is_canonical_thread_key(self.selector_id)
        if not valid:
            raise ValueError(f"selector_id is invalid for {self.kind}")
