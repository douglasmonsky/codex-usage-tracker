"""Production database-v1 replay seam for CK-08R1 qualification."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from tests.agent_kernel.fixtures.oracles import database_replay


def evaluate_published_case(
    connection: sqlite3.Connection,
    case: Mapping[str, Any],
    question: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute the declared R1B consumer against one synthetic publication."""
    request = case.get("request")
    evidence = case.get("required_evidence")
    if not isinstance(request, Mapping) or not isinstance(evidence, list):
        raise ValueError("synthetic case request or evidence is malformed")
    result = database_replay.evaluate_published_question_case(
        connection,
        request,
        evidence,
        question,
        oracle_id=str(case["oracle_id"]),
        variant=str(case["variant"]),
    )
    return {
        "rows": result["rows"],
        "references": result["references"],
    }
