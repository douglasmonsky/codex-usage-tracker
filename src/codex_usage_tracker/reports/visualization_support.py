"""Shared row normalization and VisualizationSpecV1 assembly helpers."""

from __future__ import annotations

from math import isfinite
from typing import Any

VISUALIZATION_SPEC_SCHEMA = "codex-usage-visualization/v1"


def _cartesian_spec(
    source: dict[str, Any],
    *,
    identifier: str,
    title: str,
    description: str,
    rows: list[dict[str, Any]],
    include_archived: bool,
    y_field: str,
    y_label: str,
    y_unit: str,
    series: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    caveats: list[str],
    annotations: list[dict[str, Any]] | None = None,
    x_type: str = "category",
) -> dict[str, Any]:
    state: dict[str, Any] = (
        {"kind": "ready"}
        if rows
        else {
            "kind": "empty",
            "message": f"No aggregate evidence is available for {title.lower()}.",
        }
    )
    interactions: dict[str, Any] = {"selection": {"keyField": "id", "labelField": "label"}}
    if len(rows) > 12:
        interactions["zoom"] = {
            "axis": "x",
            "startPercent": round(100 - (12 / len(rows)) * 100),
            "endPercent": 100,
        }
        interactions["brush"] = {"axis": "x"}
    return {
        "schema": VISUALIZATION_SPEC_SCHEMA,
        "id": identifier,
        "title": title,
        "description": description,
        "state": state,
        "scope": {
            "label": f"{len(rows)} aggregate evidence rows",
            "rowCount": len(rows),
            "historyScope": "all" if include_archived else "active",
        },
        "freshness": {
            "generatedAt": str(
                source.get("generated_at") or source.get("latest_refresh_at") or "not reported"
            ),
            "sourceRevision": str(source.get("schema") or "unknown"),
        },
        "caveats": caveats,
        "accessibility": {
            "summary": f"{title} contains {len(rows)} aggregate evidence rows.",
            "details": caveats,
            "keyboardInstructions": "Use left and right arrow keys to inspect values, or switch to the table for exact data.",
        },
        "table": {"caption": f"{title} evidence", "columns": columns},
        "interactions": interactions,
        "annotations": annotations or [],
        "kind": "cartesian",
        "data": {"rows": rows},
        "axes": {
            "x": {
                "field": "label",
                "label": columns[0]["label"],
                "type": x_type,
                **({"unit": "timestamp"} if x_type == "time" else {}),
            },
            "y": {"field": y_field, "label": y_label, "type": "number", "unit": y_unit},
        },
        "series": series,
    }


def _call_rows(source: dict[str, Any], *, evidence_limit: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    evidence = source.get("evidence")
    if isinstance(evidence, dict):
        for payload in evidence.values():
            for row in payload.get("rows", []) if isinstance(payload, dict) else []:
                record_id = str(row.get("record_id") or "")
                dedupe_key = record_id or repr(sorted(row.items()))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                candidates.append(row)
    if not candidates:
        candidates = list(source.get("rows", []))
    return [
        _call_row(row, index)
        for index, row in enumerate(candidates[: max(evidence_limit * 4, evidence_limit)])
    ]


def _call_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    input_tokens = _number(row, "input_tokens")
    cached_tokens = _number(row, "cached_input_tokens")
    uncached_tokens = _number(row, "uncached_input_tokens") or max(input_tokens - cached_tokens, 0)
    record_id = str(row.get("record_id") or f"call-{index + 1}")
    thread = str(row.get("thread_name") or row.get("thread_key") or record_id)
    return {
        "id": record_id,
        "label": f"{thread} - {index + 1}",
        "record_id": record_id,
        "uncached_input_tokens": round(uncached_tokens),
        "output_tokens": round(
            _number(row, "output_tokens") + _number(row, "reasoning_output_tokens")
        ),
        "total_tokens": round(_number(row, "total_tokens")),
        "cached_percent": round((cached_tokens / input_tokens * 100) if input_tokens else 0, 2),
        "estimated_cost_usd": round(_number(row, "estimated_cost_usd"), 6),
        "usage_credits": round(_number(row, "usage_credits"), 4),
    }


def _allowance_row(span: dict[str, Any], index: int, grade: str) -> dict[str, Any] | None:
    credits_per_percent = _optional_number(span.get("credits_per_percent"))
    if credits_per_percent is None:
        return None
    label = str(span.get("end_observed_at") or span.get("end_observed_date") or f"Span {index + 1}")
    return {
        "id": str(span.get("record_id") or f"weekly-span-{index + 1}"),
        "label": label,
        "capacity_proxy": round(credits_per_percent * 100, 4),
        "delta_usage_percent": round(_number(span, "delta_usage_percent"), 4),
        "estimated_credits": round(_number(span, "estimated_usage_credits"), 4),
        "evidence_grade": grade,
    }


def _allowance_annotations(candidate: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(candidate, dict):
        return []
    observed_at = candidate.get("candidate_start_observed_at")
    if not observed_at:
        return []
    return [
        {
            "id": "candidate-regime-shift",
            "label": "Candidate weekly regime shift",
            "kind": "reference-line",
            "axis": "x",
            "value": observed_at,
            "severity": "critical"
            if candidate.get("statistical_evidence", {}).get("public_claim_ready")
            else "warning",
            "evidenceKeys": [str(row["id"]) for row in rows],
        }
    ]


def _thread_call_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    input_tokens = _number(row, "input_tokens")
    cached_tokens = _number(row, "cached_input_tokens")
    return {
        "id": str(row.get("record_id") or f"call-{index + 1}"),
        "label": str(
            row.get("call_started_at") or row.get("event_timestamp") or f"Call {index + 1}"
        ),
        "total_tokens": round(_number(row, "total_tokens")),
        "call_count": 1,
        "cached_percent": round((cached_tokens / input_tokens * 100) if input_tokens else 0, 2),
        "estimated_cost_usd": round(_number(row, "estimated_cost_usd"), 6),
    }


def _thread_summary_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    cache_ratio = _number(row, "avg_cache_ratio")
    cached_percent = cache_ratio * 100 if cache_ratio <= 1 else cache_ratio
    return {
        "id": str(row.get("thread_key") or f"thread-{index + 1}"),
        "label": str(row.get("thread_label") or row.get("thread_key") or f"Thread {index + 1}"),
        "total_tokens": round(_number(row, "total_tokens")),
        "call_count": round(_number(row, "call_count")),
        "cached_percent": round(cached_percent, 2),
        "estimated_cost_usd": round(_number(row, "estimated_cost_usd"), 6),
    }


def _series(identifier: str, label: str, y_field: str, mark: str, color: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": label,
        "mark": mark,
        "xField": "label",
        "yField": y_field,
        "color": color,
        "smooth": False,
    }


def _call_columns() -> list[dict[str, Any]]:
    return [
        _column("label", "Call", "category"),
        _column("uncached_input_tokens", "Uncached input", "number", "tokens", "right"),
        _column("output_tokens", "Output", "number", "tokens", "right"),
        _column("total_tokens", "Total tokens", "number", "tokens", "right"),
        _column("cached_percent", "Cached", "number", "percent", "right"),
        _column("estimated_cost_usd", "Estimated cost", "number", "usd", "right"),
        _column("usage_credits", "Credits", "number", "credits", "right"),
        {**_column("record_id", "Record", "text"), "hiddenByDefault": True},
    ]


def _column(
    field: str, label: str, field_type: str, unit: str | None = None, align: str = "left"
) -> dict[str, Any]:
    return {
        "field": field,
        "label": label,
        "type": field_type,
        "align": align,
        **({"unit": unit} if unit else {}),
    }


def _number(row: dict[str, Any], key: str) -> float:
    return _optional_number(row.get(key)) or 0.0


def _optional_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None
