from __future__ import annotations

from enum import Enum


class RunOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    STOPPED = "stopped"
    UNSUPPORTED = "unsupported"
