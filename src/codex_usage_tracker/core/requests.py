"""Dependency-light request primitives shared by analytics and application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

HistoryScope: TypeAlias = Literal["active", "all"]
ExecutionMode: TypeAlias = Literal["auto", "sync", "async"]


@dataclass(frozen=True)
class QueryFilters:
    since: str | None = None
    until: str | None = None
    range: str | None = None
    model: str | None = None
    effort: str | None = None
    thread_key: str | None = None
    project: str | None = None
    origin: str | None = None
    service_tier: str | None = None
    subagent_role: str | None = None
    subagent_type: str | None = None
    parent_thread_key: str | None = None
