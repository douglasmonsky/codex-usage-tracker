"""Recommendation payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.core.paths import DEFAULT_RATE_CARD_PATH, DEFAULT_THRESHOLDS_PATH
from codex_usage_tracker.recommendation_engine.query import (
    RecommendationFactsUnavailableError,
    build_recommendations_report,
)
from codex_usage_tracker.server.query_cache import (
    AggregateQueryCache,
    cached_aggregate_payload,
)
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_optional_float,
    parse_report_limit,
)

ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]

_MAX_CACHEABLE_RECOMMENDATIONS = 100


def handle_recommendations_request(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    projects_path: Path,
    privacy_mode: str,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
    query_cache: AggregateQueryCache | None = None,
) -> None:
    """Handle recommendation route errors and response writing."""
    try:
        cacheable = _recommendations_cacheable(query)
        payload = cached_aggregate_payload(
            query_cache,
            route="/api/recommendations",
            query=query,
            db_path=db_path,
            privacy_mode=privacy_mode,
            dependencies=(
                pricing_path,
                allowance_path,
                rate_card_path,
                thresholds_path,
                projects_path,
            ),
            cacheable=cacheable,
            build=lambda: recommendations_payload(
                query,
                db_path=db_path,
                pricing_path=pricing_path,
                allowance_path=allowance_path,
                rate_card_path=rate_card_path,
                thresholds_path=thresholds_path,
                projects_path=projects_path,
                privacy_mode=privacy_mode,
            ),
        )
    except RecommendationFactsUnavailableError as exc:
        send_error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        return
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading recommendations", exc)
        return
    send_json(HTTPStatus.OK, payload)


def _recommendations_cacheable(query: str) -> bool:
    params = parse_qs(query)
    limit = parse_report_limit(first_query_value(params.get("limit")), 20)
    return limit <= _MAX_CACHEABLE_RECOMMENDATIONS


def recommendations_payload(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    projects_path: Path,
    privacy_mode: str,
) -> dict[str, object]:
    """Build the recommendations API payload."""
    params = parse_qs(query)
    report = build_recommendations_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
        since=first_query_value(params.get("since")),
        until=first_query_value(params.get("until")),
        model=first_query_value(params.get("model")),
        effort=first_query_value(params.get("effort")),
        thread=first_query_value(params.get("thread")),
        project=first_query_value(params.get("project")),
        include_archived=first_query_value(params.get("include_archived"))
        in {"1", "true", "yes", "on"},
        min_score=parse_optional_float(first_query_value(params.get("min_score")), "min_score"),
        limit=parse_report_limit(first_query_value(params.get("limit")), 20),
        privacy_mode=privacy_mode,
    )
    payload = dict(report.payload)
    payload["raw_context_included"] = False
    return payload
