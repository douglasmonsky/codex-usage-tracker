"""Candidate persistence and paging for cached compression analyses."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

_SORT_SQL = {
    "adjusted_likely": "adjusted_likely DESC, rank ASC, candidate_id ASC",
    "confidence": "confidence_score DESC, adjusted_likely DESC, candidate_id ASC",
    "exposure": "observed_exposure_tokens DESC, candidate_id ASC",
    "recency": "COALESCE(last_seen, '') DESC, candidate_id ASC",
}

_CANDIDATE_INSERT_SQL = """
    INSERT INTO compression_candidates (
        candidate_id, run_id, family, pattern, pattern_key, rank,
        confidence_grade, confidence_score, observation_count,
        observed_exposure_tokens, observed_exposure_json,
        gross_low, gross_likely, gross_high,
        adjusted_low, adjusted_likely, adjusted_high,
        detector_version, estimator_version, estimator_tier, estimator_name,
        confidence_reasons_json, estimator_assumptions_json,
        evidence_handles_json, intervention_json, verification_json,
        warnings_json, overlaps_json, thread_keys_json, first_seen, last_seen
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?)
"""

_CLAIM_INSERT_SQL = """
    INSERT INTO compression_candidate_records (
        candidate_id, record_id, component, exposure_tokens,
        estimate_low, estimate_likely, estimate_high,
        evidence_role, trace_handle_json
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def replace_compression_candidates(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    run_id: str,
    candidates: Iterable[Mapping[str, Any]],
    supersede_run_id: str | None = None,
) -> int:
    """Replace a run's candidate set and claims in one transaction."""
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            -_nested_int(candidate, "adjusted_estimate", "likely"),
            str(candidate.get("candidate_id") or ""),
        ),
    )
    with connect(db_path) as conn:
        init_db(conn)
        if not _run_exists(conn, run_id):
            raise KeyError(f"unknown compression run: {run_id}")
        if supersede_run_id and supersede_run_id != run_id:
            conn.execute(
                """
                DELETE FROM compression_candidate_records
                WHERE candidate_id IN (
                    SELECT candidate_id FROM compression_candidates WHERE run_id = ?
                )
                """,
                (supersede_run_id,),
            )
            conn.execute(
                "DELETE FROM compression_candidates WHERE run_id = ?",
                (supersede_run_id,),
            )
            conn.execute("DELETE FROM compression_runs WHERE run_id = ?", (supersede_run_id,))
        conn.execute(
            """
            DELETE FROM compression_candidate_records
            WHERE candidate_id IN (
                SELECT candidate_id FROM compression_candidates WHERE run_id = ?
            )
            """,
            (run_id,),
        )
        conn.execute("DELETE FROM compression_candidates WHERE run_id = ?", (run_id,))
        conn.executemany(_CANDIDATE_INSERT_SQL, _candidate_rows(ordered, run_id=run_id))
        conn.executemany(_CLAIM_INSERT_SQL, _claim_rows(ordered))
        conn.execute(
            "UPDATE compression_runs SET candidate_count = ? WHERE run_id = ?",
            (len(ordered), run_id),
        )
    return len(ordered)


def list_compression_candidates(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    run_id: str,
    family: str | None = None,
    confidence_grade: str | None = None,
    min_exposure: int = 0,
    min_likely_savings: int = 0,
    sort: str = "adjusted_likely",
    limit: int | None = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Page compact candidate rows without loading nested claims."""
    normalized_family = family or None
    normalized_confidence = confidence_grade or None
    normalized_sort = sort if sort in _SORT_SQL else "adjusted_likely"
    normalized_limit = -1 if limit in (None, 0) else max(1, int(limit))
    normalized_offset = max(0, int(offset))
    filter_params: list[Any] = [
        run_id,
        max(0, min_exposure),
        max(0, min_likely_savings),
        normalized_family,
        normalized_family,
        normalized_confidence,
        normalized_confidence,
    ]
    with connect(db_path) as conn:
        init_db(conn)
        total = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM compression_candidates
                WHERE run_id = ?
                    AND observed_exposure_tokens >= ?
                    AND adjusted_likely >= ?
                    AND (? IS NULL OR family = ?)
                    AND (? IS NULL OR confidence_grade = ?)
                """,
                filter_params,
            ).fetchone()[0]
        )
        rows = conn.execute(
            """
            SELECT * FROM compression_candidates
            WHERE run_id = ?
                AND observed_exposure_tokens >= ?
                AND adjusted_likely >= ?
                AND (? IS NULL OR family = ?)
                AND (? IS NULL OR confidence_grade = ?)
            ORDER BY
                CASE WHEN ? = 'confidence' THEN confidence_score END DESC,
                CASE WHEN ? = 'exposure' THEN observed_exposure_tokens END DESC,
                CASE WHEN ? = 'recency' THEN COALESCE(last_seen, '') END DESC,
                adjusted_likely DESC,
                rank ASC,
                candidate_id ASC
            LIMIT ? OFFSET ?
            """,
            [
                *filter_params,
                normalized_sort,
                normalized_sort,
                normalized_sort,
                normalized_limit,
                normalized_offset,
            ],
        ).fetchall()
    decoded = [_decode_candidate_row(row, include_detail=False) for row in rows]
    return {
        "rows": decoded,
        "total": total,
        "offset": normalized_offset,
        "limit": None if limit in (None, 0) else max(1, int(limit)),
        "truncated": normalized_offset + len(decoded) < total,
    }


def get_compression_candidate(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    candidate_id: str,
) -> dict[str, Any] | None:
    """Return one candidate with bounded claim and trace metadata."""
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            "SELECT * FROM compression_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            return None
        claim_rows = conn.execute(
            """
            SELECT * FROM compression_candidate_records
            WHERE candidate_id = ?
            ORDER BY record_id, component
            """,
            (candidate_id,),
        ).fetchall()
    result = _decode_candidate_row(row, include_detail=True)
    result["claims"] = [_decode_claim_row(claim) for claim in claim_rows]
    return result


def _candidate_rows(
    candidates: list[Mapping[str, Any]],
    *,
    run_id: str,
) -> Iterable[tuple[Any, ...]]:
    for rank, candidate in enumerate(candidates, start=1):
        candidate_id = _text(candidate, "candidate_id")
        handles = _mapping_list(candidate.get("evidence_handles"))
        yield _candidate_insert_values(
            candidate,
            candidate_id=candidate_id,
            run_id=run_id,
            rank=rank,
            handles=handles,
        )


def _claim_rows(candidates: list[Mapping[str, Any]]) -> Iterable[tuple[Any, ...]]:
    for candidate in candidates:
        candidate_id = _text(candidate, "candidate_id")
        for claim in _mapping_list(candidate.get("claims")):
            yield _claim_insert_values(
                candidate_id=candidate_id,
                claim=claim,
            )


def _candidate_insert_values(
    candidate: Mapping[str, Any],
    *,
    candidate_id: str,
    run_id: str,
    rank: int,
    handles: list[dict[str, Any]],
) -> tuple[Any, ...]:
    confidence = _mapping(candidate.get("confidence"))
    estimator = _mapping(candidate.get("estimator"))
    observed = _mapping(candidate.get("observed_exposure"))
    gross = _mapping(candidate.get("gross_estimate"))
    adjusted = _mapping(candidate.get("adjusted_estimate"))
    return (
        candidate_id,
        run_id,
        _text(candidate, "family"),
        _text(candidate, "pattern"),
        _text(candidate, "pattern_key"),
        rank,
        _text(confidence, "grade", default="unknown"),
        _float(confidence, "score"),
        _integer(candidate, "observation_count"),
        sum(_integer_value(value) for value in observed.values()),
        _json_dump(observed),
        _integer(gross, "low"),
        _integer(gross, "likely"),
        _integer(gross, "high"),
        _integer(adjusted, "low"),
        _integer(adjusted, "likely"),
        _integer(adjusted, "high"),
        _text(candidate, "detector_version"),
        _first_text(candidate.get("estimator_version"), estimator.get("version")),
        _text(estimator, "tier"),
        _text(estimator, "name"),
        _json_dump(_list_value(confidence, "reasons")),
        _json_dump(_list_value(estimator, "assumptions")),
        _json_dump(handles),
        _json_dump(_mapping(candidate.get("intervention"))),
        _json_dump(_mapping(candidate.get("verification"))),
        _json_dump(_list_value(candidate, "data_quality_warnings")),
        _json_dump(_list_value(candidate, "overlapping_candidate_ids")),
        _json_dump(_list_value(candidate, "thread_keys")),
        candidate.get("first_seen"),
        candidate.get("last_seen"),
    )


def _claim_insert_values(
    *,
    candidate_id: str,
    claim: Mapping[str, Any],
) -> tuple[Any, ...]:
    estimate = _mapping(claim.get("estimate"))
    record_id = str(claim.get("record_id") or "")
    return (
        candidate_id,
        record_id,
        str(claim.get("component") or ""),
        int(claim.get("exposure_tokens") or 0),
        int(estimate.get("low") or 0),
        int(estimate.get("likely") or 0),
        int(estimate.get("high") or 0),
        "supporting",
        _json_dump({"record_id": record_id}),
    )


def _decode_candidate_row(row: sqlite3.Row, *, include_detail: bool) -> dict[str, Any]:
    result = {
        "candidate_id": row["candidate_id"],
        "run_id": row["run_id"],
        "family": row["family"],
        "pattern": row["pattern"],
        "pattern_key": row["pattern_key"],
        "rank": int(row["rank"]),
        "confidence": {
            "grade": row["confidence_grade"],
            "score": float(row["confidence_score"]),
        },
        "observation_count": int(row["observation_count"]),
        "observed_exposure_tokens": int(row["observed_exposure_tokens"]),
        "gross_estimate": _range_from_row(row, "gross"),
        "adjusted_estimate": _range_from_row(row, "adjusted"),
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
    }
    if include_detail:
        result.update(_candidate_detail_fields(row))
    return result


def _candidate_detail_fields(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "observed_exposure": _json_load(row["observed_exposure_json"]),
        "detector_version": row["detector_version"],
        "estimator": {
            "version": row["estimator_version"],
            "tier": row["estimator_tier"],
            "name": row["estimator_name"],
            "assumptions": _json_load(row["estimator_assumptions_json"]),
        },
        "confidence_reasons": _json_load(row["confidence_reasons_json"]),
        "evidence_handles": _json_load(row["evidence_handles_json"]),
        "intervention": _json_load(row["intervention_json"]),
        "verification": _json_load(row["verification_json"]),
        "data_quality_warnings": _json_load(row["warnings_json"]),
        "overlapping_candidate_ids": _json_load(row["overlaps_json"]),
        "thread_keys": _json_load(row["thread_keys_json"]),
    }


def _decode_claim_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "record_id": row["record_id"],
        "component": row["component"],
        "exposure_tokens": int(row["exposure_tokens"]),
        "estimate": _range_from_row(row, "estimate"),
        "evidence_role": row["evidence_role"],
        "trace_handle": _json_load(row["trace_handle_json"]),
    }


def _range_from_row(row: sqlite3.Row, prefix: str) -> dict[str, int]:
    return {
        "low": int(row[f"{prefix}_low"]),
        "likely": int(row[f"{prefix}_likely"]),
        "high": int(row[f"{prefix}_high"]),
    }


def _run_exists(conn: sqlite3.Connection, run_id: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM compression_runs WHERE run_id = ?", (run_id,)).fetchone()
        is not None
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_mapping(item) for item in value if isinstance(item, Mapping)]


def _text(value: Mapping[str, Any], key: str, *, default: str = "") -> str:
    raw = value.get(key)
    return str(raw) if raw is not None and raw != "" else default


def _integer(value: Mapping[str, Any], key: str) -> int:
    return _integer_value(value.get(key))


def _integer_value(value: Any) -> int:
    return int(value) if value is not None else 0


def _float(value: Mapping[str, Any], key: str) -> float:
    raw = value.get(key)
    return float(raw) if raw is not None else 0.0


def _first_text(*values: Any) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def _list_value(value: Mapping[str, Any], key: str) -> list[Any]:
    raw = value.get(key)
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _nested_int(value: Mapping[str, Any], outer: str, inner: str) -> int:
    return _integer(_mapping(value.get(outer)), inner)


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_load(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
