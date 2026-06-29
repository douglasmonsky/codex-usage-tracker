"""Shared row predicates for usage reports."""

from __future__ import annotations

from typing import Any


def query_row_matches(
    row: dict[str, Any],
    *,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    project: str | None,
    pricing_status: str | None,
    credit_confidence: str | None,
    min_tokens: int | None,
    min_credits: float | None,
) -> bool:
    """Return whether an annotated row satisfies report-level filters."""

    checks = (
        _matches_until(row, until),
        _matches_value(row, "model", model),
        _matches_value(row, "effort", effort),
        _matches_thread(row, thread),
        _matches_project(row, project),
        _matches_pricing_status(row, pricing_status),
        _matches_value(row, "usage_credit_confidence", credit_confidence),
        _matches_minimum(row, "total_tokens", min_tokens, int),
        _matches_minimum(row, "usage_credits", min_credits, float),
    )
    return all(checks)


def _matches_until(row: dict[str, Any], until: str | None) -> bool:
    return until is None or str(row.get("event_timestamp") or "") <= until


def _matches_value(row: dict[str, Any], field: str, expected: str | None) -> bool:
    return expected is None or str(row.get(field) or "") == expected


def _matches_thread(row: dict[str, Any], thread: str | None) -> bool:
    if not thread:
        return True
    return thread in _text_values(
        row,
        (
            "thread_name",
            "parent_thread_name",
            "resolved_parent_thread_name",
            "thread_attachment_label",
            "session_id",
        ),
    )


def _matches_project(row: dict[str, Any], project: str | None) -> bool:
    if not project:
        return True
    return project in _text_values(
        row, ("project_name", "project_key", "project_relative_cwd")
    ) or project in (row.get("project_tags") or [])


def _text_values(row: dict[str, Any], fields: tuple[str, ...]) -> set[str]:
    return {str(row.get(field) or "") for field in fields}


def _matches_pricing_status(row: dict[str, Any], pricing_status: str | None) -> bool:
    if pricing_status == "priced":
        return bool(row.get("pricing_model"))
    if pricing_status == "estimated":
        return bool(row.get("pricing_estimated"))
    if pricing_status == "unpriced":
        return not row.get("pricing_model")
    return True


def _matches_minimum(
    row: dict[str, Any],
    field: str,
    minimum: int | float | None,
    parser: type[int] | type[float],
) -> bool:
    return minimum is None or parser(row.get(field) or 0) >= minimum
