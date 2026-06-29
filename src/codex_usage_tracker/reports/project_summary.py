"""Project and project-tag summary report helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    load_project_config,
)
from codex_usage_tracker.pricing.api import PricingConfig, annotate_rows_with_efficiency
from codex_usage_tracker.store.api import query_dashboard_events

TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def project_summary_rows(
    *,
    db_path: Path,
    pricing: PricingConfig,
    group_by: str,
    limit: int,
    since: str | None,
    projects_path: Path,
    privacy_mode: str,
) -> list[dict[str, Any]]:
    """Build project or project-tag grouped usage summary rows."""

    rows = _project_rows(
        db_path=db_path,
        pricing=pricing,
        since=since,
        projects_path=projects_path,
        privacy_mode=privacy_mode,
    )
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        for key in _project_group_keys(row, group_by):
            _add_project_summary_row(buckets, str(key), row)
    summaries = [_final_project_summary_bucket(bucket) for bucket in buckets.values()]
    summaries.sort(key=lambda row: (-int(row["total_tokens"]), str(row["group_key"])))
    return summaries[:limit]


def _project_rows(
    *,
    db_path: Path,
    pricing: PricingConfig,
    since: str | None,
    projects_path: Path,
    privacy_mode: str,
) -> list[dict[str, Any]]:
    rows = query_dashboard_events(db_path, limit=0, since=since)
    rows = annotate_rows_with_efficiency(rows, pricing)
    rows = annotate_rows_with_project_identity(rows, load_project_config(projects_path))
    return apply_project_privacy_to_rows(rows, privacy_mode=privacy_mode)


def _project_group_keys(row: dict[str, Any], group_by: str) -> list[object]:
    if group_by == "project_tag":
        return list(row.get("project_tags") or ["untagged"])
    return [row.get("project_name") or "Unknown project"]


def _add_project_summary_row(
    buckets: dict[str, dict[str, Any]],
    key: str,
    row: dict[str, Any],
) -> None:
    bucket = buckets.setdefault(key, _new_project_bucket(key))
    bucket["model_calls"] += 1
    bucket["sessions"].add(row.get("session_id"))
    if row.get("turn_id"):
        bucket["turns"].add(row.get("turn_id"))
    _add_token_totals(bucket, row)
    _add_ratio_totals(bucket, row)
    bucket["estimated_cost_usd"] += float(row.get("estimated_cost_usd") or 0)
    bucket["latest_event"] = max(bucket["latest_event"], str(row.get("event_timestamp") or ""))


def _new_project_bucket(key: str) -> dict[str, Any]:
    return {
        "group_key": key,
        "model_calls": 0,
        "sessions": set(),
        "turns": set(),
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "uncached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "_cache_ratio_sum": 0.0,
        "_reasoning_ratio_sum": 0.0,
        "_context_sum": 0.0,
        "latest_event": "",
    }


def _add_token_totals(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    for token_key in TOKEN_FIELDS:
        bucket[token_key] += int(row.get(token_key) or 0)


def _add_ratio_totals(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    bucket["_cache_ratio_sum"] += float(row.get("cache_ratio") or 0)
    bucket["_reasoning_ratio_sum"] += float(row.get("reasoning_output_ratio") or 0)
    bucket["_context_sum"] += float(row.get("context_window_percent") or 0)


def _final_project_summary_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    calls = max(int(bucket["model_calls"]), 1)
    bucket["sessions"] = len(bucket["sessions"])
    bucket["turns"] = len(bucket["turns"])
    bucket["avg_cache_ratio"] = bucket.pop("_cache_ratio_sum") / calls
    bucket["avg_reasoning_output_ratio"] = bucket.pop("_reasoning_ratio_sum") / calls
    bucket["avg_context_window_percent"] = bucket.pop("_context_sum") / calls
    return bucket
