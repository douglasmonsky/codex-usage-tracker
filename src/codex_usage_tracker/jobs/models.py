"""Transport-independent generic job contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol, TypeAlias, cast

from codex_usage_tracker.core.contracts import MessageV1, payload_mapping
from codex_usage_tracker.core.contracts.common import immutable_snapshot

JobKind: TypeAlias = Literal["refresh", "analysis", "allowance", "compression", "diagnostic"]
JobState: TypeAlias = Literal["queued", "running", "completed", "failed", "cancelled"]
_REQUEST_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SAFE_STAGE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")
_SAFE_JOB_ID = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.:-]{0,255}\Z")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,255}\Z")
MAX_RESULT_BUDGET_BYTES = 1024 * 1024


class JobAdapter(Protocol):
    """Read one existing subsystem registry without mutating it."""

    def status(self, job_id: str, *, include_result: bool = False) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class JobStatusV1:
    """One normalized generic job status."""

    schema: Literal["codex-usage-tracker.job.v1"] = field(
        default="codex-usage-tracker.job.v1", init=False
    )
    job_id: str
    kind: JobKind
    state: JobState
    progress_percent: int
    stage: str
    source_revision: str | None
    request_hash: str
    created_at: str
    updated_at: str
    completed_at: str | None
    retryable: bool
    error: MessageV1 | None
    result_schema: str | None
    result: object | None

    def __post_init__(self) -> None:
        if not _SAFE_JOB_ID.fullmatch(self.job_id):
            raise ValueError("job_id must be a safe identifier")
        if self.kind not in {"refresh", "analysis", "allowance", "compression", "diagnostic"}:
            raise ValueError("kind is invalid")
        if self.state not in {"queued", "running", "completed", "failed", "cancelled"}:
            raise ValueError("state is invalid")
        if type(self.progress_percent) is not int or not 0 <= self.progress_percent <= 100:
            raise ValueError("progress_percent must be between 0 and 100")
        if not _SAFE_STAGE.fullmatch(self.stage):
            raise ValueError("stage must be a bounded safe identifier")
        if not _REQUEST_HASH.fullmatch(self.request_hash):
            raise ValueError("request_hash must be a sha256 fingerprint")
        if self.error is not None and not isinstance(self.error, MessageV1):
            raise TypeError("error must be a MessageV1")
        if type(self.retryable) is not bool:
            raise TypeError("retryable must be a bool")
        if self.source_revision is not None and not _SAFE_IDENTIFIER.fullmatch(
            self.source_revision
        ):
            raise ValueError("source_revision must be a safe identifier")
        if self.result_schema is not None and not _SAFE_IDENTIFIER.fullmatch(self.result_schema):
            raise ValueError("result_schema must be a safe identifier")
        object.__setattr__(self, "created_at", _canonical_timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _canonical_timestamp(self.updated_at, "updated_at"))
        if self.completed_at is not None:
            object.__setattr__(
                self,
                "completed_at",
                _canonical_timestamp(self.completed_at, "completed_at"),
            )
        object.__setattr__(self, "result", immutable_snapshot(self.result))

    def to_payload(self) -> dict[str, object]:
        return payload_mapping(self)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> JobStatusV1:
        return cls(
            job_id=cast(str, payload["job_id"]),
            kind=cast(JobKind, payload["kind"]),
            state=cast(JobState, payload["state"]),
            progress_percent=cast(int, payload["progress_percent"]),
            stage=cast(str, payload["stage"]),
            source_revision=cast(str | None, payload.get("source_revision")),
            request_hash=cast(str, payload["request_hash"]),
            created_at=cast(str, payload["created_at"]),
            updated_at=cast(str, payload["updated_at"]),
            completed_at=cast(str | None, payload.get("completed_at")),
            retryable=cast(bool, payload["retryable"]),
            error=cast(MessageV1 | None, payload.get("error")),
            result_schema=cast(str | None, payload.get("result_schema")),
            result=payload.get("result"),
        )


@dataclass(frozen=True)
class JobHandle:
    """Facade registration with an explicit originating result budget."""

    kind: JobKind
    job_id: str
    adapter: JobAdapter
    result_schema: str | None = None
    result_budget: int = 64 * 1024

    def __post_init__(self) -> None:
        if self.kind not in {"refresh", "analysis", "allowance", "compression", "diagnostic"}:
            raise ValueError("kind is invalid")
        if not _SAFE_JOB_ID.fullmatch(self.job_id):
            raise ValueError("job_id must be a safe identifier")
        if (
            type(self.result_budget) is not int
            or self.result_budget <= 0
            or self.result_budget > MAX_RESULT_BUDGET_BYTES
        ):
            raise ValueError(
                f"result_budget must be an integer from 1 through {MAX_RESULT_BUDGET_BYTES}"
            )


def _canonical_timestamp(value: str, field_name: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a canonical timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be a canonical timestamp")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
