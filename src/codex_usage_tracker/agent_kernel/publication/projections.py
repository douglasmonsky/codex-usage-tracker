"""Current-only projection port; CK-07 intentionally admits no projections."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, order=True, slots=True)
class DirtyKey:
    kind: str
    value: str

    def __post_init__(self) -> None:
        if not self.kind or not self.value:
            raise ValueError("dirty keys require a kind and value")


@dataclass(frozen=True, slots=True)
class ProjectionUpdate:
    projection_id: str
    dirty_key_count: int
    rows_read: int
    rows_written: int
    rows_deleted: int
    elapsed_ns: int


class ProjectionMaintainer(Protocol):
    projection_id: str
    version: str
    consumed_key_kinds: frozenset[str]

    def expand_dirty_keys(self, keys: frozenset[DirtyKey]) -> frozenset[DirtyKey]: ...

    def apply(self, keys: frozenset[DirtyKey]) -> ProjectionUpdate: ...

    def validate(self) -> None: ...


class ProjectionFanoutError(RuntimeError):
    """A projection attempted more work than the proven-small plan allowed."""


class ProjectionRegistry:
    """Deterministic empty-capable registry owned by later CK-09 admission."""

    def __init__(self, maintainers: Iterable[ProjectionMaintainer] = ()) -> None:
        items = tuple(sorted(maintainers, key=lambda item: item.projection_id))
        if len({item.projection_id for item in items}) != len(items):
            raise ValueError("projection IDs must be unique")
        self._maintainers = items

    @property
    def versions(self) -> Mapping[str, str]:
        return {item.projection_id: item.version for item in self._maintainers}

    def apply(
        self,
        keys: Iterable[DirtyKey],
        *,
        maximum_dirty_keys: int,
        maximum_rows_written: int,
    ) -> tuple[ProjectionUpdate, ...]:
        deduplicated = frozenset(keys)
        if len(deduplicated) > maximum_dirty_keys:
            raise ProjectionFanoutError("dirty-key fanout exceeds the publication plan")
        updates: list[ProjectionUpdate] = []
        rows_written = 0
        for maintainer in self._maintainers:
            selected = frozenset(
                key for key in deduplicated if key.kind in maintainer.consumed_key_kinds
            )
            expanded = maintainer.expand_dirty_keys(selected)
            if len(expanded) > maximum_dirty_keys:
                raise ProjectionFanoutError(
                    f"{maintainer.projection_id} dirty-key expansion exceeds the plan"
                )
            update = maintainer.apply(expanded)
            rows_written += update.rows_written + update.rows_deleted
            if rows_written > maximum_rows_written:
                raise ProjectionFanoutError("projection row fanout exceeds the plan")
            maintainer.validate()
            updates.append(update)
        return tuple(updates)


EMPTY_PROJECTION_REGISTRY = ProjectionRegistry()
