from __future__ import annotations

from dataclasses import dataclass, replace

from tests.agent_kernel.contracts.reference.identity import semantic_id
from tests.agent_kernel.fixtures.generator.profile import FixtureProfile


@dataclass(frozen=True)
class SourceSpec:
    index: int
    relative_path: str
    state: str
    materialized: bool
    history_selection: str
    moving_tail: bool = False
    duplicate_of: str | None = None
    adapter_version: str = "synthetic-jsonl-v1"
    logical_source: str = ""
    manifestation_id: str = ""
    revision: str = "revision-1"


def clustered_source_index(
    ordinal: int,
    *,
    model_calls: int,
    active_sources: int,
) -> int:
    """Map chronological call ordinals into contiguous active-source clusters."""
    if model_calls <= 0:
        raise ValueError("model_calls must be positive")
    if active_sources <= 0:
        raise ValueError("active_sources must be positive")
    if ordinal < 0 or ordinal >= model_calls:
        raise ValueError("ordinal outside model-call range")
    return min(active_sources - 1, ordinal * active_sources // model_calls)


def source_specs(profile: FixtureProfile) -> tuple[SourceSpec, ...]:
    """Return a stable source layout including every lifecycle edge case."""

    active_count = profile.source_manifestations - 5
    active: list[SourceSpec] = []
    for index in range(active_count):
        suffix = f"source-{index:04d}.jsonl"
        history_selection = "uncertain" if index == 1 else "selected"
        active.append(
            SourceSpec(
                index=index,
                relative_path=f"sources/active/{suffix}",
                state="active",
                materialized=True,
                history_selection=history_selection,
                moving_tail=index == active_count - 1,
            )
        )
    special = [
        SourceSpec(
            index=active_count,
            relative_path="sources/archived/exact-copy.jsonl",
            state="archived",
            materialized=True,
            history_selection="selected",
            duplicate_of=active[0].relative_path,
        ),
        SourceSpec(
            index=active_count + 1,
            relative_path="sources/replaced/revision-1.jsonl",
            state="replaced",
            materialized=True,
            history_selection="selected",
        ),
        SourceSpec(
            index=active_count + 2,
            relative_path="sources/truncated/truncated.jsonl",
            state="truncated",
            materialized=True,
            history_selection="selected",
        ),
        SourceSpec(
            index=active_count + 3,
            relative_path="sources/malformed/malformed.jsonl",
            state="malformed",
            materialized=True,
            history_selection="selected",
        ),
        SourceSpec(
            index=active_count + 4,
            relative_path="sources/deferred/deferred.jsonl",
            state="deferred",
            materialized=False,
            history_selection="deferred",
        ),
    ]
    normalized = []
    for spec in [*active, *special]:
        logical_source = spec.duplicate_of or spec.relative_path
        revision = (
            "revision-2"
            if spec.state == "truncated"
            else "revision-1"
        )
        normalized.append(
            replace(
                spec,
                logical_source=logical_source,
                manifestation_id=semantic_id(
                    "source-manifestation",
                    [profile.seed, logical_source, revision],
                ),
                revision=revision,
            )
        )
    return tuple(normalized)
