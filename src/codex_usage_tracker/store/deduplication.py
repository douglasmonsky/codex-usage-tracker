"""Database-relative canonical usage classification."""
from __future__ import annotations
import sqlite3
from collections.abc import Iterable, Mapping
from codex_usage_tracker.core.usage_identity import usage_identity_from_values

def classify_usage_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    for row in rows:
        if not row.get("usage_fingerprint") or not row.get("canonical_record_id"):
            identity = usage_identity_from_values(row, upstream_usage_id=_string(row.get("upstream_usage_id")))
            row.update(upstream_usage_id=identity.upstream_usage_id, usage_fingerprint=identity.usage_fingerprint, canonical_record_id=identity.canonical_record_id)
        fingerprint = str(row["usage_fingerprint"])
        existing = conn.execute("SELECT 1 FROM usage_events WHERE usage_fingerprint = ? AND is_duplicate = 0 AND record_id != ? LIMIT 1", (fingerprint, row["record_id"])).fetchone()
        duplicate = fingerprint in seen or existing is not None
        row["is_duplicate"] = int(duplicate)
        row["duplicate_reason"] = "copied_usage_fingerprint" if duplicate else None
        seen.add(fingerprint)
    return rows

def promote_orphaned_fingerprints(conn: sqlite3.Connection, fingerprints: Iterable[str]) -> set[str]:
    keys: set[str] = set()
    for fingerprint in set(fingerprints):
        if conn.execute("SELECT 1 FROM usage_events WHERE usage_fingerprint=? AND is_duplicate=0", (fingerprint,)).fetchone(): continue
        row = conn.execute("SELECT record_id, thread_key, session_id FROM usage_events WHERE usage_fingerprint=? ORDER BY event_timestamp, source_file, line_number, record_id LIMIT 1", (fingerprint,)).fetchone()
        if row:
            conn.execute("UPDATE usage_events SET is_duplicate=0, duplicate_reason=NULL WHERE record_id=?", (row["record_id"],))
            keys.add(str(row["thread_key"] or f"session:{row['session_id']}"))
    return keys

def _string(value: object) -> str | None: return value if isinstance(value, str) and value else None
