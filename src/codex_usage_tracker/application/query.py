"""Canonical bounded usage query application service."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from codex_usage_tracker.application.context import RequestContext
from codex_usage_tracker.application.errors import RequestContextError
from codex_usage_tracker.application.query_models import (
    DashboardTargetV2,
    QueryRequest,
    QueryResult,
)
from codex_usage_tracker.application.query_validation import (
    QueryValidationError,
    decode_cursor,
    validate_query_request,
)
from codex_usage_tracker.application.requests import RequestScope
from codex_usage_tracker.pricing.allowance_usage import annotate_rows_with_allowance
from codex_usage_tracker.pricing.config import PricingConfig, load_pricing_config
from codex_usage_tracker.pricing.costing import estimate_cost_usd
from codex_usage_tracker.store.api import query_canonical_usage_v2
from codex_usage_tracker.store.compression_schema import read_compression_source_generation
from codex_usage_tracker.store.connection import connect, connect_read_only
from codex_usage_tracker.store.schema import init_db


def query_usage(
    request: QueryRequest,
    *,
    db_path: Path,
    pricing_path: Path | None = None,
    allowance_path: Path | None = None,
    context: RequestContext | None = None,
) -> QueryResult:
    """Execute one validated canonical query with revision-bound keyset pagination."""
    resolved_pricing_path = pricing_path or db_path.with_name("pricing.json")
    resolved_allowance_path = allowance_path or db_path.with_name("allowance.json")
    normalized = validate_query_request(request)
    scope = RequestScope(
        since=normalized.filters.since,
        until=normalized.filters.until,
        history=normalized.history,
        project=normalized.filters.project,
        thread_key=normalized.filters.thread_key,
        model=normalized.filters.model,
        effort=normalized.filters.effort,
    )
    if context is not None and context.scope != scope.to_contract():
        raise RequestContextError("query context scope does not match the normalized request")
    source_revision = (
        context.source_revision
        if context is not None
        else _source_revision(db_path)
    )
    fingerprint = _query_fingerprint(normalized)
    cursor_sort: object | None = None
    cursor_identity: str | None = None
    if normalized.cursor is not None:
        cursor = decode_cursor(normalized.cursor)
        if cursor.get("f") != fingerprint:
            raise QueryValidationError("cursor does not match query scope")
        if cursor.get("r") != source_revision:
            raise QueryValidationError("cursor is stale for the current source revision")
        cursor_sort = cursor.get("s")
        identity = cursor.get("i")
        if not isinstance(identity, str) or not identity:
            raise QueryValidationError("cursor is malformed")
        cursor_identity = identity
    rows = query_canonical_usage_v2(
        db_path=db_path,
        entity=normalized.entity,
        measures=normalized.measures,
        filters=asdict(normalized.filters),
        group_by=normalized.group_by,
        order_by=normalized.order_by or normalized.measures[0],
        order=normalized.order,
        include_archived=normalized.history == "all",
        limit=normalized.limit,
        cursor_sort=cursor_sort,
        cursor_identity=cursor_identity,
    )
    has_more = len(rows) > normalized.limit
    page = rows[: normalized.limit]
    total_matched = int(page[0].pop("_total_matched")) if page else 0
    pricing = load_pricing_config(resolved_pricing_path)
    for row in page:
        row.pop("_total_matched", None)
        _attach_estimates(
            row,
            normalized.measures,
            pricing=pricing,
            allowance_path=resolved_allowance_path,
        )
    next_cursor = None
    if has_more and page:
        identity_name = "record_id" if normalized.entity == "call" else normalized.entity
        next_cursor = _encode_cursor(
            fingerprint=fingerprint,
            source_revision=source_revision,
            sort_value=page[-1][normalized.order_by or normalized.measures[0]],
            identity=str(page[-1][identity_name]),
        )
    if normalized.entity == "call" and normalized.order_by == "time":
        for row in page:
            row.pop("time", None)
    columns = ["record_id" if normalized.entity == "call" else normalized.entity]
    columns.extend(normalized.group_by)
    columns.extend(normalized.measures)
    for measure in ("estimated_cost", "estimated_credits"):
        if measure in normalized.measures:
            columns.extend((f"{measure}_coverage", f"{measure}_confidence"))
    return QueryResult(
        entity=normalized.entity,
        columns=tuple(columns),
        rows=tuple(page),
        next_cursor=next_cursor,
        total_matched=total_matched,
        dashboard_target=DashboardTargetV2(
            view="explore",
            arguments={"entity": normalized.entity, "history": normalized.history},
        ),
    )


def _query_fingerprint(request: QueryRequest) -> str:
    payload = asdict(request)
    payload["cursor"] = None
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_revision(db_path: Path) -> str:
    try:
        with connect_read_only(db_path) as connection:
            generation = read_compression_source_generation(connection)
    except sqlite3.OperationalError as exc:
        missing_generation_table = "no such table: compression_source_state"
        if db_path.exists() and missing_generation_table not in str(exc):
            raise
        with connect(db_path) as connection:
            init_db(connection)
            generation = read_compression_source_generation(connection)
    return f"generation:{generation}"


def _encode_cursor(
    *, fingerprint: str, source_revision: str | None, sort_value: object, identity: str
) -> str:
    payload = {"v": 1, "f": fingerprint, "r": source_revision, "s": sort_value, "i": identity}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _attach_estimates(
    row: dict[str, object],
    measures: tuple[str, ...],
    *,
    pricing: PricingConfig,
    allowance_path: Path,
) -> None:
    materialized_cost_coverage = row.pop(
        "_materialized_estimated_cost_coverage",
        None,
    )
    materialized_cost_confidence = row.pop(
        "_materialized_estimated_cost_confidence",
        None,
    )
    materialized_credit_coverage = row.pop(
        "_materialized_estimated_credits_coverage",
        None,
    )
    materialized_credit_confidence = row.pop(
        "_materialized_estimated_credits_confidence",
        None,
    )
    pricing_row = {
        "model": row.get("_pricing_model"),
        "service_tier": row.get("_pricing_service_tier"),
        "input_tokens": row.get("_pricing_input_tokens"),
        "cached_input_tokens": row.get("_pricing_cached_input_tokens"),
        "uncached_input_tokens": row.get("_pricing_uncached_input_tokens"),
        "output_tokens": row.get("_pricing_output_tokens"),
    }
    one_pricing_class = (
        row.get("_pricing_model_count") == 1 and row.get("_pricing_tier_count", 1) == 1
    )
    if "estimated_cost" in measures:
        if materialized_cost_coverage is not None:
            row["estimated_cost_coverage"] = materialized_cost_coverage
            row["estimated_cost_confidence"] = materialized_cost_confidence
        else:
            estimated_cost = estimate_cost_usd(pricing_row, pricing) if one_pricing_class else None
            row["estimated_cost"] = estimated_cost
            row["estimated_cost_coverage"] = 1.0 if estimated_cost is not None else 0.0
            row["estimated_cost_confidence"] = (
                "estimated"
                if estimated_cost is not None and pricing.is_estimated_model(pricing_row["model"])
                else "exact"
                if estimated_cost is not None
                else "unknown"
            )
    if "estimated_credits" in measures:
        if materialized_credit_coverage is not None:
            row["estimated_credits_coverage"] = materialized_credit_coverage
            row["estimated_credits_confidence"] = materialized_credit_confidence
        else:
            annotated = (
                annotate_rows_with_allowance([pricing_row], allowance_path=allowance_path)[0]
                if one_pricing_class
                else {}
            )
            estimated_credits = annotated.get("usage_credits")
            row["estimated_credits"] = estimated_credits
            row["estimated_credits_coverage"] = (
                1.0 if estimated_credits is not None else 0.0
            )
            row["estimated_credits_confidence"] = (
                annotated.get("usage_credit_confidence", "unknown")
                if estimated_credits is not None
                else "unknown"
            )
    for key in tuple(row):
        if key.startswith("_pricing_"):
            row.pop(key)
