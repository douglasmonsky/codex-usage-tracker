from __future__ import annotations

from typing import Any


def crash_state_oracle() -> list[dict[str, Any]]:
    """Return the publication truth expected at every admitted crash boundary."""

    boundaries = (
        ("before_staging", False, "none"),
        ("during_parse", False, "abandon_staging"),
        ("during_fact_writes", False, "abandon_candidate"),
        ("after_facts_before_projections", False, "abandon_candidate"),
        ("during_projection_update", False, "abandon_candidate"),
        ("after_validation_before_promotion", False, "retain_valid_candidate"),
        ("during_promotion", False, "reconcile_pointer_or_rollback"),
        ("after_promotion_before_sidecar_reconciliation", True, "reconcile_sidecar"),
        ("during_old_artifact_cleanup", True, "defer_cleanup"),
    )
    return [
        {
            "boundary": boundary,
            "prior_publication_queryable": True,
            "rollback_available": True,
            "candidate_publication_committed": committed,
            "abandoned_artifact_disposition": disposition,
            "sidecar_terminal_state": "failed" if not committed else "succeeded",
            "subsequent_operation_succeeds": True,
        }
        for boundary, committed, disposition in boundaries
    ]
