from __future__ import annotations

import json

from codex_usage_tracker.diagnostic_fact_classifiers import structured_tool_and_skill_facts
from codex_usage_tracker.models import DiagnosticFact


def test_structured_diagnostic_classifier_keeps_command_labels_aggregate() -> None:
    facts = structured_tool_and_skill_facts(
        entry_type="response_item",
        payload={
            "type": "function_call",
            "name": "functions.exec_command",
            "arguments": json.dumps({"cmd": "git status SECRET_VALUE"}),
        },
        payload_type="function_call",
        timestamp="2026-05-17T18:58:27Z",
        line_number=42,
        fact_factory=_fact_factory,
    )

    labels = {(fact.fact_type, fact.fact_name) for fact in facts}
    assert ("function", "functions.exec_command") in labels
    assert ("command_family", "git") in labels
    assert "SECRET_VALUE" not in json.dumps([fact.to_row() for fact in facts])

    search_facts = structured_tool_and_skill_facts(
        entry_type="response_item",
        payload={
            "type": "function_call",
            "name": "functions.exec_command",
            "arguments": json.dumps({"cmd": "rg SECRET_VALUE /private/project"}),
        },
        payload_type="function_call",
        timestamp="2026-05-17T18:58:27Z",
        line_number=43,
        fact_factory=_fact_factory,
    )

    search_labels = {(fact.fact_type, fact.fact_name) for fact in search_facts}
    assert ("activity", "search_read_command") in search_labels
    assert "SECRET_VALUE" not in json.dumps([fact.to_row() for fact in search_facts])


def _fact_factory(
    *,
    fact_type: str,
    fact_name: str,
    category: str,
    confidence: str,
    timestamp: str | None,
    line_number: int,
) -> DiagnosticFact:
    return DiagnosticFact(
        record_id="record",
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=category,
        confidence=confidence,
        first_event_timestamp=timestamp,
        last_event_timestamp=timestamp,
        first_source_line=line_number,
        last_source_line=line_number,
    )
