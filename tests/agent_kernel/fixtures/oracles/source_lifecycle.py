from __future__ import annotations

from collections import Counter
from typing import Any

from tests.agent_kernel.fixtures.generator.profile import FixtureProfile
from tests.agent_kernel.fixtures.generator.sources import source_specs
from tests.agent_kernel.fixtures.oracles.source_ledger import SourceLedger


def build_source_lifecycle_oracle(
    profile: FixtureProfile,
    *,
    ledger: SourceLedger,
) -> dict[str, Any]:
    """Derive source ownership and phased occurrence truth from source ledger."""

    specs = source_specs(profile)
    state_counts = Counter(spec.state for spec in specs)
    aggregates = ledger.stream_aggregates
    return {
        "archive_copy_count": 1,
        "canonical_model_calls": aggregates["canonical_model_calls"],
        "duplicate_occurrences_excluded": (
            aggregates["model_call_occurrences"]
            - aggregates["canonical_model_calls"]
        ),
        "manifestation_counts": {
            state: state_counts[state]
            for state in (
                "active",
                "archived",
                "deferred",
                "malformed",
                "replaced",
                "truncated",
            )
        },
        "model_call_occurrences": aggregates["model_call_occurrences"],
        "moving_tail_count": sum(spec.moving_tail for spec in specs),
        "owner_change_preserves_semantic_identity": True,
        "phase_occurrence_mappings": ledger.phase_occurrences,
        "recanonicalization_is_not_new_activity": True,
        "replacement_count": 1,
        "source_manifestations": [
            {
                "adapter_version": spec.adapter_version,
                "logical_source": spec.logical_source,
                "manifestation_id": spec.manifestation_id,
                "revision": spec.revision,
                "state": spec.state,
            }
            for spec in specs
        ],
        "truncation_count": 1,
        "uncertain_source_count": sum(
            spec.history_selection == "uncertain"
            for spec in specs
        ),
    }
