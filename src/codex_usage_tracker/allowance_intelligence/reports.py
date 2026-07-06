"""Allowance intelligence report builders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance_intelligence.model import (
    WINDOW_KIND_CHOICES,
    build_allowance_analysis,
)
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_RATE_CARD_PATH,
)
from codex_usage_tracker.core.projects import validate_privacy_mode
from codex_usage_tracker.pricing.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
)
from codex_usage_tracker.store.api import query_allowance_observations

ALLOWANCE_HISTORY_SCHEMA = "codex-usage-tracker-allowance-history-v1"
ALLOWANCE_DIAGNOSTICS_SCHEMA = "codex-usage-tracker-allowance-diagnostics-v1"
ALLOWANCE_EXPORT_SCHEMA = "codex-usage-tracker-allowance-evidence-export-v1"


@dataclass(frozen=True)
class AllowanceReport:
    """Resolved allowance intelligence report."""

    payload: dict[str, Any]

    def render(self) -> str:
        schema = self.payload.get("schema")
        if schema == ALLOWANCE_HISTORY_SCHEMA:
            return _render_history(self.payload)
        if schema == ALLOWANCE_EXPORT_SCHEMA:
            return _render_export(self.payload)
        return _render_diagnostics(self.payload)


def build_allowance_history_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    include_archived: bool = False,
    window_kind: str | None = None,
    limit: int | None = 1000,
    privacy_mode: str = "strict",
) -> AllowanceReport:
    """Build normalized observed allowance history."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    _validate_window_kind(window_kind)
    rows = _annotated_observation_rows(
        db_path=db_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=limit,
    )
    return AllowanceReport(
        {
            "schema": ALLOWANCE_HISTORY_SCHEMA,
            "generated_at": _generated_at(),
            "privacy_mode": privacy_mode,
            "include_archived": include_archived,
            "window_kind": window_kind,
            "row_count": len(rows),
            "rows": [_history_row(row, privacy_mode=privacy_mode) for row in rows],
            "notes": _privacy_notes(),
        }
    )


def build_allowance_diagnostics_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    include_archived: bool = False,
    window_kind: str | None = None,
    limit: int | None = None,
    privacy_mode: str = "strict",
) -> AllowanceReport:
    """Build evidence-graded allowance change diagnostics."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    _validate_window_kind(window_kind)
    rows = _annotated_observation_rows(
        db_path=db_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=limit,
    )
    analysis = build_allowance_analysis(rows)
    payload = {
        "schema": ALLOWANCE_DIAGNOSTICS_SCHEMA,
        "generated_at": _generated_at(),
        "privacy_mode": privacy_mode,
        "include_archived": include_archived,
        "window_kind": window_kind,
        **_privacy_filtered_analysis(analysis, privacy_mode=privacy_mode),
    }
    return AllowanceReport(payload)


def build_allowance_export_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    include_archived: bool = False,
    window_kind: str | None = None,
    limit: int | None = None,
) -> AllowanceReport:
    """Build a strict-privacy local evidence bundle for manual sharing."""

    diagnostics = build_allowance_diagnostics_report(
        db_path=db_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=limit,
        privacy_mode="strict",
    ).payload
    export = {
        "schema": ALLOWANCE_EXPORT_SCHEMA,
        "generated_at": diagnostics["generated_at"],
        "privacy_mode": "strict",
        "include_archived": include_archived,
        "summary": diagnostics["summary"],
        "windows": [
            _export_window(window) for window in diagnostics.get("windows", [])
        ],
        "change_candidates": diagnostics.get("change_candidates", []),
        "notes": [
            *_privacy_notes(),
            "This bundle is local evidence only and is not an official OpenAI usage ledger.",
            "Exact timestamps are bucketed to dates and local record identifiers are omitted.",
        ],
    }
    return AllowanceReport(export)


def _annotated_observation_rows(
    *,
    db_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived: bool,
    window_kind: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    rows = query_allowance_observations(
        db_path=db_path,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=limit,
    )
    allowance = load_allowance_config(allowance_path, rate_card_path=rate_card_path)
    return annotate_rows_with_allowance(rows, allowance)


def _history_row(row: dict[str, Any], *, privacy_mode: str) -> dict[str, Any]:
    payload = {
        "observed_at": row.get("event_timestamp"),
        "observed_date": _date_bucket(row.get("event_timestamp")),
        "source": row.get("source"),
        "window_key": row.get("window_key"),
        "window_kind": row.get("window_kind"),
        "window_minutes": row.get("window_minutes"),
        "used_percent": row.get("used_percent"),
        "remaining_percent": row.get("remaining_percent"),
        "resets_at": row.get("resets_at"),
        "plan_type": row.get("plan_type"),
        "limit_id": row.get("limit_id"),
        "model": row.get("model"),
        "effort": row.get("effort"),
        "total_tokens": row.get("total_tokens"),
        "usage_credits": row.get("usage_credits"),
        "usage_credit_confidence": row.get("usage_credit_confidence"),
    }
    if privacy_mode != "strict":
        payload["record_id"] = row.get("record_id")
        payload["session_id"] = row.get("session_id")
        payload["line_number"] = row.get("line_number")
    return payload


def _privacy_filtered_analysis(
    analysis: dict[str, Any], *, privacy_mode: str
) -> dict[str, Any]:
    return {
        "summary": analysis["summary"],
        "windows": [
            _privacy_filtered_window(window, privacy_mode=privacy_mode)
            for window in analysis["windows"]
        ],
        "spans": [
            _privacy_filtered_span(span, privacy_mode=privacy_mode)
            for span in analysis["spans"]
        ],
        "change_candidates": analysis["change_candidates"],
        "notes": [*analysis["notes"], *_privacy_notes()],
    }


def _privacy_filtered_window(
    window: dict[str, Any], *, privacy_mode: str
) -> dict[str, Any]:
    return {
        "window_kind": window.get("window_kind"),
        "plan_type": window.get("plan_type"),
        "limit_id": window.get("limit_id"),
        "observation_count": window.get("observation_count"),
        "positive_span_count": window.get("positive_span_count"),
        "evidence_grade": window.get("evidence_grade"),
        "span_stats": window.get("span_stats"),
        "change_candidates": window.get("change_candidates"),
        "spans": [
            _privacy_filtered_span(span, privacy_mode=privacy_mode)
            for span in window.get("spans", [])
        ],
    }


def _privacy_filtered_span(
    span: dict[str, Any], *, privacy_mode: str
) -> dict[str, Any]:
    payload = dict(span)
    payload["start_observed_date"] = _date_bucket(payload.get("start_observed_at"))
    payload["end_observed_date"] = _date_bucket(payload.get("end_observed_at"))
    if privacy_mode == "strict":
        payload.pop("record_id", None)
        payload.pop("start_observed_at", None)
        payload.pop("end_observed_at", None)
    return payload


def _export_window(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "window_kind": window.get("window_kind"),
        "plan_type": window.get("plan_type"),
        "limit_id": window.get("limit_id"),
        "observation_count": window.get("observation_count"),
        "positive_span_count": window.get("positive_span_count"),
        "evidence_grade": window.get("evidence_grade"),
        "span_stats": window.get("span_stats"),
        "change_candidates": window.get("change_candidates"),
        "spans": [
            {
                key: value
                for key, value in span.items()
                if key
                in {
                    "window_kind",
                    "plan_type",
                    "limit_id",
                    "start_observed_date",
                    "end_observed_date",
                    "start_used_percent",
                    "end_used_percent",
                    "delta_usage_percent",
                    "estimated_usage_credits",
                    "credits_per_percent",
                    "row_count",
                    "credit_confidence_mix",
                }
            }
            for span in window.get("spans", [])
        ],
    }


def _validate_window_kind(window_kind: str | None) -> None:
    if window_kind is not None and window_kind not in WINDOW_KIND_CHOICES:
        allowed = ", ".join(WINDOW_KIND_CHOICES)
        raise ValueError(f"window_kind must be one of: {allowed}")


def _privacy_notes() -> list[str]:
    return [
        "Allowance intelligence uses aggregate token counters and observed usage percentages only.",
        "Strict privacy output omits prompts, assistant text, tool output, file paths, thread names, and record identifiers.",
    ]


def _render_history(payload: dict[str, Any]) -> str:
    return (
        "Allowance history: "
        f"{payload.get('row_count', 0)} normalized observations "
        f"({payload.get('privacy_mode')} privacy)."
    )


def _render_diagnostics(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        return "Allowance diagnostics unavailable."
    return (
        "Allowance diagnostics: "
        f"{summary.get('primary_evidence_grade')} across "
        f"{summary.get('observation_count', 0)} observations and "
        f"{summary.get('positive_span_count', 0)} positive spans."
    )


def _render_export(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    grade = summary.get("primary_evidence_grade") if isinstance(summary, dict) else None
    return f"Allowance evidence export ready with strict privacy ({grade})."


def _generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _date_bucket(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:10]
