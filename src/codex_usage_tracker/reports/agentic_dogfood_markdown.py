"""Markdown rendering for agentic dogfood reports."""

from __future__ import annotations

from typing import Any


def _hypothesis_lines(rows: list[dict[str, Any]]) -> list[str]:
    return [
        f"- **{row.get('family')}**: {row.get('status')} ({row.get('confidence')})" for row in rows
    ]


def render_agentic_dogfood_markdown(payload: dict[str, Any]) -> str:
    """Render a compact Markdown artifact from a dogfood payload."""

    lines = [
        "# Agentic Dogfood Summary",
        "",
        f"Generated: {payload.get('generated_at')}",
        f"Privacy mode: `{payload.get('privacy_mode')}`",
        f"Include archived: `{payload.get('filters', {}).get('include_archived')}`",
        "",
        "## Family Checks",
        "",
        f"- Old hypotheses: `{payload['family_checks']['old_passed']}`",
        f"- New hypotheses: `{payload['family_checks']['new_passed']}`",
        "",
        "## Old Hypotheses",
        "",
        *_hypothesis_lines(payload.get("old_hypotheses", [])),
        "",
        "## New Hypotheses",
        "",
        *_hypothesis_lines(payload.get("new_hypotheses", [])),
        "",
        "## Direct Evidence",
        "",
        f"- Large low-output candidates: {payload['summary'].get('large_low_output_candidates')}",
        f"- Shell churn candidates: {payload['summary'].get('shell_churn_candidates')}",
        f"- Repeated file candidates: {payload['summary'].get('repeated_file_candidates')}",
        (
            "- Allowance evidence grade: "
            f"{payload['summary'].get('allowance_primary_evidence_grade')}"
        ),
        "",
        "## Privacy Checks",
        "",
        f"- Passed: `{payload['privacy_checks'].get('passed')}`",
        f"- Forbidden marker hits: {payload['privacy_checks'].get('forbidden_marker_hits')}",
    ]
    return "\n".join(lines) + "\n"
