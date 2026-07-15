"""Recommendation reports backed by materialized recommendation facts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import (
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.core.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    load_project_config,
    validate_privacy_mode,
)
from codex_usage_tracker.core.threads import annotate_thread_attachments
from codex_usage_tracker.pricing.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
)
from codex_usage_tracker.pricing.api import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.recommendation_engine.fact_config import (
    RECOMMENDATION_ALGORITHM_VERSION,
    RECOMMENDATION_FACTS_VERSION,
    load_recommendation_fact_config,
    recommendation_generation_fingerprint,
)
from codex_usage_tracker.reports.filters import query_row_matches
from codex_usage_tracker.reports.query import (
    RecommendationsReport,
)
from codex_usage_tracker.reports.recommendation_builder import (
    recommendation_sort_key,
    thread_recommendation_rows,
)
from codex_usage_tracker.store.compression_schema import read_compression_source_generation
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.recommendation_queries import (
    query_recommendation_fact_page,
    query_recommendation_thread_summaries,
)


class RecommendationFactsUnavailableError(RuntimeError):
    """Raised when indexed recommendations require a usage-index refresh."""


def build_recommendations_report(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    project: str | None = None,
    include_archived: bool = False,
    min_score: float | None = None,
    limit: int = 20,
    source_limit: int | None = None,
    privacy_mode: str = "normal",
) -> RecommendationsReport:
    """Build recommendations from current indexed facts only."""

    if source_limit is not None:
        raise ValueError(
            "source_limit is no longer supported by indexed recommendations; "
            "use since, until, and limit instead"
        )
    if not _recommendation_facts_are_current(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
    ):
        raise RecommendationFactsUnavailableError(
            "Recommendation facts are missing or stale; refresh the usage index and retry"
        )
    return build_indexed_recommendations_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        project=project,
        include_archived=include_archived,
        min_score=min_score,
        limit=limit,
        source_limit=source_limit,
        privacy_mode=privacy_mode,
    )


def build_indexed_recommendations_report(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    project: str | None = None,
    include_archived: bool = False,
    min_score: float | None = None,
    limit: int = 20,
    source_limit: int | None = None,
    privacy_mode: str = "normal",
) -> RecommendationsReport:
    """Build the legacy report contract from indexed actionable facts."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_limit = _normalize_report_limit(limit)
    thread_summaries = (
        query_recommendation_thread_summaries(
            db_path=db_path,
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            include_archived=include_archived,
            min_score=min_score,
            limit=normalized_limit,
        )
        if project is None and normalized_limit is not None
        else None
    )
    page = query_recommendation_fact_page(
        db_path=db_path,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        include_archived=include_archived,
        min_score=min_score,
        limit=normalized_limit if project is None else 0,
    )
    rows = annotate_thread_attachments(page.rows)
    rows = annotate_rows_with_allowance(
        annotate_rows_with_efficiency(rows, load_pricing_config(pricing_path)),
        load_allowance_config(allowance_path, rate_card_path=rate_card_path),
    )
    rows = [_restore_materialized_recommendations(row) for row in rows]
    rows = annotate_rows_with_project_identity(rows, load_project_config(projects_path))
    scored_rows = [row for row in rows if _matches_project(row, project)]
    scored_rows.sort(key=recommendation_sort_key)
    limited_rows = scored_rows[:normalized_limit]
    total_matched_rows = page.total_count if thread_summaries is not None else len(scored_rows)
    private_rows = apply_project_privacy_to_rows(limited_rows, privacy_mode=privacy_mode)
    return RecommendationsReport(
        {
            "schema": "codex-usage-tracker-recommendations-v1",
            "filters": {
                "since": since,
                "until": until,
                "model": model,
                "effort": effort,
                "thread": thread,
                "project": project,
                "include_archived": include_archived,
                "min_score": min_score,
                "limit": normalized_limit,
                "source_limit": source_limit,
                "privacy_mode": privacy_mode,
            },
            "row_count": len(private_rows),
            "total_matched_rows": total_matched_rows,
            "truncated": normalized_limit is not None and total_matched_rows > normalized_limit,
            "threads": _recommendation_thread_payload(
                thread_summaries, scored_rows, normalized_limit
            ),
            "rows": private_rows,
        }
    )


def _recommendation_thread_payload(
    summaries: list[dict[str, Any]] | None,
    rows: list[dict[str, Any]],
    limit: int | None,
) -> list[dict[str, Any]]:
    if summaries is not None:
        return summaries
    return thread_recommendation_rows(rows, limit=limit or 20)


def _normalize_report_limit(limit: int) -> int | None:
    return None if limit <= 0 else limit


def _restore_materialized_recommendations(row: dict[str, Any]) -> dict[str, Any]:
    copy = dict(row)
    recommendations = json.loads(str(copy.pop("fact_recommendations_json")))
    copy.pop("fact_primary_recommendation_key", None)
    copy.pop("fact_secondary_recommendation_keys_json", None)
    copy["recommendation_score"] = float(copy.pop("fact_recommendation_score"))
    copy["action_recommendations"] = recommendations
    copy["primary_recommendation"] = recommendations[0] if recommendations else None
    copy["secondary_recommendations"] = recommendations[1:]
    copy["primary_signal"] = recommendations[0]["key"] if recommendations else None
    copy["secondary_signals"] = [item["key"] for item in recommendations[1:]]
    copy["recommended_action"] = (
        recommendations[0]["action"]
        if recommendations
        else "No aggregate action is flagged; continue monitoring usage patterns."
    )
    copy["recommended_action_key"] = copy.pop("fact_recommended_action_key")
    copy["flag_explanations"] = [item["why"] for item in recommendations]
    copy["flag_explanation_keys"] = [item["why_key"] for item in recommendations]
    return copy


def _matches_project(row: dict[str, Any], project: str | None) -> bool:
    return query_row_matches(
        row,
        until=None,
        model=None,
        effort=None,
        thread=None,
        project=project,
        pricing_status=None,
        credit_confidence=None,
        min_tokens=None,
        min_credits=None,
    )


def _recommendation_facts_are_current(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
) -> bool:
    config = load_recommendation_fact_config(
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
    )
    try:
        with connect(db_path) as conn:
            state = conn.execute(
                "SELECT * FROM recommendation_fact_state WHERE singleton = 1"
            ).fetchone()
            if state is None:
                return False
            source_generation = read_compression_source_generation(conn)
            expected_generation = recommendation_generation_fingerprint(
                source_generation=source_generation,
                config_fingerprint=config.fingerprint,
            )
            fact_count = int(
                conn.execute("SELECT COUNT(*) FROM recommendation_facts").fetchone()[0]
            )
            usage_count = int(
                conn.execute("SELECT COUNT(*) FROM canonical_usage_events").fetchone()[0]
            )
    except sqlite3.Error:
        return False
    return (
        int(state["facts_version"]) == RECOMMENDATION_FACTS_VERSION
        and int(state["algorithm_version"]) == RECOMMENDATION_ALGORITHM_VERSION
        and int(state["source_generation"]) == source_generation
        and str(state["generation_fingerprint"]) == expected_generation
        and str(state["config_fingerprint"]) == config.fingerprint
        and int(state["record_count"]) == fact_count == usage_count
    )
