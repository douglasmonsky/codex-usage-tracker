"""Conservative correlation of staged OTel tiers to canonical usage calls."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

_TIER_COLUMNS = (
    "service_tier",
    "fast",
    "service_tier_source",
    "service_tier_confidence",
)


@dataclass(frozen=True)
class OtelReconciliationResult:
    matched: int = 0
    pending: int = 0
    ambiguous: int = 0
    conflicts: int = 0
    updated_usage_rows: int = 0


@dataclass
class _MutableReconciliationTotals:
    matched: int = 0
    pending: int = 0
    ambiguous: int = 0
    conflicts: int = 0
    updated_usage_rows: int = 0

    def freeze(self) -> OtelReconciliationResult:
        return OtelReconciliationResult(
            matched=self.matched,
            pending=self.pending,
            ambiguous=self.ambiguous,
            conflicts=self.conflicts,
            updated_usage_rows=self.updated_usage_rows,
        )


def reconcile_otel_completions(
    conn: sqlite3.Connection,
) -> OtelReconciliationResult:
    """Enrich only completion identities that resolve to one canonical group."""

    totals = _MutableReconciliationTotals()
    rows = conn.execute(
        """
        SELECT *
        FROM otel_completion_events
        WHERE match_status IN ('pending', 'ambiguous', 'matched')
        ORDER BY source_path, source_line, fingerprint
        """
    ).fetchall()
    for completion in rows:
        candidates = _candidate_rows(conn, completion)
        group_ids = {
            str(row["canonical_record_id"] or row["record_id"]) for row in candidates
        }
        if not candidates:
            _set_match_state(conn, str(completion["fingerprint"]), "pending", None)
            totals.pending += 1
        elif len(group_ids) != 1:
            _set_match_state(conn, str(completion["fingerprint"]), "ambiguous", None)
            totals.ambiguous += 1
        else:
            _apply_to_canonical_group(conn, completion, group_ids.pop(), totals)
    return totals.freeze()


def reset_otel_completion_matches(conn: sqlite3.Connection) -> None:
    """Make every valid staged completion eligible for rebuild reconciliation."""

    conn.execute(
        """
        UPDATE otel_completion_events
        SET match_status = 'pending', matched_record_id = NULL
        WHERE match_status != 'invalid'
        """
    )


def _candidate_rows(
    conn: sqlite3.Connection, completion: sqlite3.Row
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT record_id, canonical_record_id
        FROM usage_events
        WHERE session_id = ?
          AND input_tokens = ?
          AND cached_input_tokens = ?
          AND output_tokens = ?
          AND reasoning_output_tokens = ?
          AND (? IS NULL OR model IS NULL OR lower(model) = lower(?))
          AND (? IS NULL OR effort IS NULL OR lower(effort) = lower(?))
        """,
        (
            completion["conversation_id"],
            completion["input_tokens"],
            completion["cached_input_tokens"],
            completion["output_tokens"],
            completion["reasoning_output_tokens"],
            completion["model"],
            completion["model"],
            completion["effort"],
            completion["effort"],
        ),
    ).fetchall()


def _apply_to_canonical_group(
    conn: sqlite3.Connection,
    completion: sqlite3.Row,
    canonical_id: str,
    totals: _MutableReconciliationTotals,
) -> None:
    clones = conn.execute(
        """
        SELECT record_id, service_tier, fast,
               service_tier_source, service_tier_confidence
        FROM usage_events
        WHERE coalesce(nullif(canonical_record_id, ''), record_id) = ?
        ORDER BY record_id
        """,
        (canonical_id,),
    ).fetchall()
    desired = tuple(completion[column] for column in _TIER_COLUMNS)
    contradiction = any(
        row[column] is not None and row[column] != expected
        for row in clones
        for column, expected in zip(_TIER_COLUMNS, desired, strict=True)
    )
    if contradiction:
        _set_match_state(conn, str(completion["fingerprint"]), "conflict", None)
        totals.conflicts += 1
        return

    cursor = conn.execute(
        """
        UPDATE usage_events
        SET service_tier = coalesce(service_tier, ?),
            fast = coalesce(fast, ?),
            service_tier_source = coalesce(service_tier_source, ?),
            service_tier_confidence = coalesce(service_tier_confidence, ?)
        WHERE coalesce(nullif(canonical_record_id, ''), record_id) = ?
        """,
        (*desired, canonical_id),
    )
    matched_record_id = str(clones[0]["record_id"])
    _set_match_state(
        conn,
        str(completion["fingerprint"]),
        "matched",
        matched_record_id,
    )
    totals.matched += 1
    totals.updated_usage_rows += max(cursor.rowcount, 0)


def _set_match_state(
    conn: sqlite3.Connection,
    fingerprint: str,
    status: str,
    matched_record_id: str | None,
) -> None:
    conn.execute(
        """
        UPDATE otel_completion_events
        SET match_status = ?, matched_record_id = ?
        WHERE fingerprint = ?
        """,
        (status, matched_record_id, fingerprint),
    )
