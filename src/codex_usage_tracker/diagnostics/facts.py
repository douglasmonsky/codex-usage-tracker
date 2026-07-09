"""Aggregate-only diagnostic fact classification for Codex JSONL events."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from codex_usage_tracker.core.models import DiagnosticFact
from codex_usage_tracker.diagnostics.fact_classifiers import structured_tool_and_skill_facts

EVIDENCE_SCOPE_BETWEEN_TOKEN_COUNTS = "between_token_counts"

CONFIDENCE_ORDER = {
    "unknown": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


def diagnostic_facts_from_envelope(
    envelope: object,
    *,
    line_number: int,
) -> tuple[DiagnosticFact, ...]:
    """Return safe diagnostic facts from one JSONL envelope."""

    if not isinstance(envelope, dict):
        return ()
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    entry_type = envelope.get("type")
    payload_type = _optional_str(payload.get("type"))
    timestamp = _optional_str(envelope.get("timestamp"))
    if payload_type is None:
        return ()

    facts: list[DiagnosticFact] = []
    if entry_type == "event_msg":
        mapping = {
            "context_compacted": ("compaction", "post_compaction", "context", "high"),
            "patch_apply_end": ("outcome", "patch_applied", "patch", "high"),
            "task_complete": ("outcome", "task_complete", "task", "high"),
            "thread_rolled_back": ("outcome", "thread_rolled_back", "failure", "high"),
            "turn_aborted": ("outcome", "turn_aborted", "turn", "high"),
            "mcp_tool_call_end": ("tool", "mcp_tool_call_end", "mcp", "medium"),
            "web_search_end": ("tool", "web_search_end", "search", "medium"),
            "image_generation_end": ("tool", "image_generation_end", "media", "medium"),
        }
        classification = mapping.get(payload_type)
        if classification is not None:
            fact_type, fact_name, category, confidence = classification
            facts.append(
                _fact(
                    fact_type=fact_type,
                    fact_name=fact_name,
                    category=category,
                    confidence=confidence,
                    timestamp=timestamp,
                    line_number=line_number,
                )
            )
        facts.extend(
            structured_tool_and_skill_facts(
                entry_type=entry_type,
                payload=payload,
                payload_type=payload_type,
                timestamp=timestamp,
                line_number=line_number,
                fact_factory=_fact,
            )
        )
        return tuple(facts)

    if entry_type == "response_item":
        mapping = {
            "function_call": ("tool", "function_call", "function", "low"),
            "function_call_output": ("tool", "function_call_output", "function", "medium"),
            "tool_search_call": ("tool", "tool_search_call", "search", "low"),
            "tool_search_output": ("tool", "tool_search_output", "search", "medium"),
        }
        classification = mapping.get(payload_type)
        if classification is not None:
            fact_type, fact_name, category, confidence = classification
            facts.append(
                _fact(
                    fact_type=fact_type,
                    fact_name=fact_name,
                    category=category,
                    confidence=confidence,
                    timestamp=timestamp,
                    line_number=line_number,
                )
            )
        facts.extend(
            structured_tool_and_skill_facts(
                entry_type=entry_type,
                payload=payload,
                payload_type=payload_type,
                timestamp=timestamp,
                line_number=line_number,
                fact_factory=_fact,
            )
        )
        return tuple(facts)

    return ()


def _with_derived_loop_facts(
    segment: tuple[DiagnosticFact, ...],
) -> tuple[DiagnosticFact, ...]:
    enriched = tuple(segment)
    for loop_spec in _derived_loop_specs(segment):
        if loop_spec["event_count"] >= loop_spec["threshold"]:
            enriched = add_diagnostic_fact(
                enriched,
                _derived_loop_fact(
                    fact_name=loop_spec["fact_name"],
                    category=loop_spec["category"],
                    event_count=loop_spec["event_count"],
                    source_facts=loop_spec["source_facts"],
                ),
            )
    return enriched


def _derived_loop_specs(
    segment: tuple[DiagnosticFact, ...],
) -> tuple[dict[str, Any], ...]:
    search_read_facts = _loop_source_facts(segment, kind="search_read")
    retry_facts = _loop_source_facts(segment, kind="retry")
    return (
        {
            "fact_name": "search_read_loop",
            "category": "search",
            "threshold": 3,
            "event_count": _fact_event_total(search_read_facts),
            "source_facts": search_read_facts,
        },
        {
            "fact_name": "retry_or_abort_loop",
            "category": "failure",
            "threshold": 2,
            "event_count": _fact_event_total(retry_facts),
            "source_facts": retry_facts,
        },
    )


def _loop_source_facts(segment: tuple[DiagnosticFact, ...], *, kind: str) -> list[DiagnosticFact]:
    if kind == "search_read":
        return [fact for fact in segment if _is_search_read_fact(fact)]
    if kind == "retry":
        return [fact for fact in segment if _is_retry_or_abort_fact(fact)]
    return []


def _is_search_read_fact(fact: DiagnosticFact) -> bool:
    return fact.fact_category in {"read", "search"} or (
        fact.fact_type == "activity" and fact.fact_name == "search_read_command"
    )


def _is_retry_or_abort_fact(fact: DiagnosticFact) -> bool:
    return fact.fact_category in {"failure", "retry"} or fact.fact_name in {
        "thread_rolled_back",
        "turn_aborted",
    }


def _fact_event_total(facts: list[DiagnosticFact]) -> int:
    return sum(fact.event_count for fact in facts)


def _derived_loop_fact(
    *,
    fact_name: str,
    category: str,
    event_count: int,
    source_facts: list[DiagnosticFact],
) -> DiagnosticFact:
    first_source_line = _min_optional_int(*[fact.first_source_line for fact in source_facts])
    last_source_line = _max_optional_int(*[fact.last_source_line for fact in source_facts])
    return DiagnosticFact(
        record_id=None,
        fact_type="loop",
        fact_name=fact_name,
        fact_category=category,
        event_count=event_count,
        confidence="medium",
        first_event_timestamp=_timestamp_for_source_line(
            source_facts,
            source_line=first_source_line,
            first=True,
        ),
        last_event_timestamp=_timestamp_for_source_line(
            source_facts,
            source_line=last_source_line,
            first=False,
        ),
        first_source_line=first_source_line,
        last_source_line=last_source_line,
        evidence_scope=EVIDENCE_SCOPE_BETWEEN_TOKEN_COUNTS,
        raw_content_included=0,
    )


def _timestamp_for_source_line(
    facts: list[DiagnosticFact],
    *,
    source_line: int | None,
    first: bool,
) -> str | None:
    for fact in sorted(
        facts,
        key=lambda item: _source_line_sort_key(
            item.first_source_line if first else item.last_source_line
        ),
    ):
        candidate_line = fact.first_source_line if first else fact.last_source_line
        if candidate_line == source_line:
            return fact.first_event_timestamp if first else fact.last_event_timestamp
    return None


def add_diagnostic_fact(
    segment: tuple[DiagnosticFact, ...],
    fact: DiagnosticFact,
) -> tuple[DiagnosticFact, ...]:
    """Merge one fact into the pending between-token-count segment."""

    by_key = {(item.fact_type, item.fact_name): item for item in segment}
    key = (fact.fact_type, fact.fact_name)
    existing = by_key.get(key)
    by_key[key] = fact if existing is None else merge_diagnostic_facts(existing, fact)
    return tuple(by_key.values())


def merge_diagnostic_facts(
    existing: DiagnosticFact,
    incoming: DiagnosticFact,
) -> DiagnosticFact:
    """Combine repeated facts without storing raw evidence."""

    return replace(
        existing,
        event_count=existing.event_count + incoming.event_count,
        confidence=strongest_confidence([existing.confidence, incoming.confidence]),
        first_event_timestamp=_earliest_event_timestamp(existing, incoming),
        last_event_timestamp=_latest_event_timestamp(existing, incoming),
        first_source_line=_min_optional_int(existing.first_source_line, incoming.first_source_line),
        last_source_line=_max_optional_int(existing.last_source_line, incoming.last_source_line),
        raw_content_included=max(existing.raw_content_included, incoming.raw_content_included),
    )


def assign_record_id_to_diagnostic_facts(
    segment: tuple[DiagnosticFact, ...],
    *,
    record_id: str,
) -> tuple[DiagnosticFact, ...]:
    """Attach pending segment facts to the token-count row they describe."""

    enriched_segment = _with_derived_loop_facts(segment)
    return tuple(
        replace(fact, record_id=record_id)
        for fact in sorted(enriched_segment, key=lambda item: (item.fact_type, item.fact_name))
    )


def diagnostic_fact_to_json(fact: DiagnosticFact) -> dict[str, Any]:
    """Encode a pending diagnostic fact for parser-state persistence."""

    payload = asdict(fact)
    payload.pop("record_id", None)
    return payload


def diagnostic_fact_from_json(value: object) -> DiagnosticFact | None:
    """Decode a pending diagnostic fact from aggregate-only parser state."""

    if not isinstance(value, dict):
        return None
    fact_type = _optional_str(value.get("fact_type"))
    fact_name = _optional_str(value.get("fact_name"))
    if not fact_type or not fact_name:
        return None
    event_count = _positive_int(value.get("event_count")) or 1
    return DiagnosticFact(
        record_id=None,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=_optional_str(value.get("fact_category")),
        event_count=event_count,
        confidence=_optional_str(value.get("confidence")) or "medium",
        first_event_timestamp=_optional_str(value.get("first_event_timestamp")),
        last_event_timestamp=_optional_str(value.get("last_event_timestamp")),
        first_source_line=_positive_int(value.get("first_source_line")),
        last_source_line=_positive_int(value.get("last_source_line")),
        evidence_scope=(
            _optional_str(value.get("evidence_scope")) or EVIDENCE_SCOPE_BETWEEN_TOKEN_COUNTS
        ),
        raw_content_included=1 if value.get("raw_content_included") == 1 else 0,
    )


def strongest_confidence(values: list[str]) -> str:
    """Return the strongest confidence label in a stable order."""

    if not values:
        return "unknown"
    return max(values, key=lambda value: CONFIDENCE_ORDER.get(value, 0))


def _fact(
    *,
    fact_type: str,
    fact_name: str,
    category: str,
    confidence: str,
    timestamp: str | None,
    line_number: int,
) -> DiagnosticFact:
    return DiagnosticFact(
        record_id=None,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=category,
        event_count=1,
        confidence=confidence,
        first_event_timestamp=timestamp,
        last_event_timestamp=timestamp,
        first_source_line=line_number,
        last_source_line=line_number,
        evidence_scope=EVIDENCE_SCOPE_BETWEEN_TOKEN_COUNTS,
        raw_content_included=0,
    )


def _earliest_event_timestamp(
    existing: DiagnosticFact,
    incoming: DiagnosticFact,
) -> str | None:
    if _source_line_sort_key(incoming.first_source_line) < _source_line_sort_key(
        existing.first_source_line
    ):
        return incoming.first_event_timestamp
    return existing.first_event_timestamp


def _latest_event_timestamp(
    existing: DiagnosticFact,
    incoming: DiagnosticFact,
) -> str | None:
    if _source_line_sort_key(incoming.last_source_line) >= _source_line_sort_key(
        existing.last_source_line
    ):
        return incoming.last_event_timestamp
    return existing.last_event_timestamp


def _source_line_sort_key(value: int | None) -> int:
    return value if value is not None else -1


def _min_optional_int(*items: int | None) -> int | None:
    values = [value for value in items if value is not None]
    return min(values) if values else None


def _max_optional_int(*items: int | None) -> int | None:
    values = [value for value in items if value is not None]
    return max(values) if values else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None
