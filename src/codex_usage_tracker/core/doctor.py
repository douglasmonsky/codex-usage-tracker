"""Dependency-light diagnostic value types."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str
    remediation: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)
