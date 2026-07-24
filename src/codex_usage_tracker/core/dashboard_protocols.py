"""Structural contracts shared by dashboard-target builders."""

from __future__ import annotations

from typing import Protocol


class DashboardServiceStatusLike(Protocol):
    """Status fields needed to resolve an active dashboard origin."""

    @property
    def reachable(self) -> bool: ...

    @property
    def url(self) -> str: ...
