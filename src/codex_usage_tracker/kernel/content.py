"""Opt-in context-composition metadata in an isolated local database."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from .database import open_read_snapshot
from .identity import stable_id
from .operational import load_cutover_control

CONTENT_SCHEMA_VERSION = 1
CONTENT_APPLICATION_ID = 0x43554331
MAX_REDACTED_FRAGMENT_CHARS = 1_024
CONTENT_FINGERPRINT_SAMPLE_BYTES = 4_096
_CATEGORIES = frozenset({"host", "mcp", "message", "tool", "unattributed"})
_STRUCTURAL_KEYS = frozenset(
    {
        "event_id",
        "id",
        "model",
        "name",
        "role",
        "server_name",
        "timestamp",
        "tool_name",
        "turn_id",
        "type",
    }
)
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|credential|password|secret|token)",
    re.IGNORECASE,
)
_SENSITIVE_FIELD_KEY = re.compile(
    r"(?:api[_-]?key|authorization|credential|cwd|directory|home|password|path|secret|token)",
    re.IGNORECASE,
)
_SENSITIVE_FIELD_COMPONENTS = frozenset(
    {
        "authorization",
        "credential",
        "cwd",
        "directory",
        "home",
        "key",
        "password",
        "path",
        "secret",
        "token",
    }
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|authorization|credential|password|secret|token)"
    r"([\"']?\s*[:=]\s*[\"']?)([^\"'\s,}]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_KNOWN_SECRET = re.compile(
    r"\b(?:gh[oprsu]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|"
    r"xox[baprs]-[A-Za-z0-9-]{8,})\b"
)

_SCHEMA_SQL = """
CREATE TABLE content_settings (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    store_redacted_fragments INTEGER NOT NULL CHECK (
        store_redacted_fragments IN (0, 1)
    ),
    privacy_confirmed_at TEXT NOT NULL,
    indexed_generation INTEGER,
    estimator_id TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE source_cursors (
    source_id TEXT PRIMARY KEY,
    prefix_fingerprint TEXT NOT NULL,
    parsed_byte_offset INTEGER NOT NULL CHECK (parsed_byte_offset >= 0),
    parsed_line_number INTEGER NOT NULL CHECK (parsed_line_number >= 0),
    logical_thread_id TEXT,
    turn_id TEXT
) STRICT;

CREATE TABLE composition_events (
    event_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    logical_thread_id TEXT,
    turn_id TEXT,
    event_at TEXT,
    category TEXT NOT NULL CHECK (
        category IN ('host', 'mcp', 'message', 'tool', 'unattributed')
    ),
    observed_bytes INTEGER NOT NULL CHECK (observed_bytes > 0),
    estimated_tokens INTEGER CHECK (estimated_tokens >= 0),
    source_offset INTEGER NOT NULL CHECK (source_offset >= 0),
    generation INTEGER NOT NULL CHECK (generation > 0)
) STRICT;

CREATE TABLE redacted_fragments (
    event_id TEXT PRIMARY KEY
        REFERENCES composition_events(event_id) ON DELETE CASCADE,
    redacted_text TEXT NOT NULL
) STRICT;

CREATE INDEX idx_composition_generation
ON composition_events(generation, event_id);
CREATE INDEX idx_composition_category
ON composition_events(category, generation);
CREATE INDEX idx_composition_thread
ON composition_events(logical_thread_id, generation);
CREATE INDEX idx_composition_time
ON composition_events(event_at, generation);
"""


class TokenEstimator(Protocol):
    """Optional tokenizer supplied by a future explicit capability owner."""

    identifier: str

    def estimate(self, value: str) -> int:
        """Return the tokenizer estimate for one observed string."""
        ...


class ContextComposition:
    """Own the isolated opt-in content lifecycle and committed-event consumer."""

    def __init__(self, content_path: Path, operational_path: Path) -> None:
        self._content_path = content_path.resolve()
        self._operational_path = operational_path.resolve()

    def status(self) -> dict[str, Any]:
        return content_status(self._content_path)

    def enable(
        self,
        *,
        privacy_confirmed: bool,
        store_redacted_fragments: bool = False,
    ) -> dict[str, Any]:
        if not privacy_confirmed:
            raise ValueError(
                "content indexing requires explicit privacy confirmation"
            )
        _initialize_content_database(self._content_path)
        with _open_content_writer(self._content_path) as connection:
            prior = connection.execute(
                """
                SELECT store_redacted_fragments
                FROM content_settings
                WHERE singleton = 1
                """
            ).fetchone()
            connection.execute(
                """
                INSERT INTO content_settings(
                    singleton,
                    enabled,
                    store_redacted_fragments,
                    privacy_confirmed_at
                )
                VALUES (1, 1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(singleton) DO UPDATE SET
                    enabled = 1,
                    store_redacted_fragments = excluded.store_redacted_fragments,
                    privacy_confirmed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (int(store_redacted_fragments),),
            )
            if prior is not None and not store_redacted_fragments:
                connection.execute("DELETE FROM redacted_fragments")
            if (
                prior is not None
                and not bool(prior["store_redacted_fragments"])
                and store_redacted_fragments
            ):
                connection.execute("DELETE FROM source_cursors")
        return self.status()

    def disable(self) -> dict[str, Any]:
        if not self._content_path.is_file():
            return self.status()
        with _open_content_writer(self._content_path) as connection:
            connection.execute(
                """
                UPDATE content_settings
                SET enabled = 0, updated_at = CURRENT_TIMESTAMP
                WHERE singleton = 1
                """
            )
        return self.status()

    def delete(self) -> dict[str, Any]:
        for suffix in ("-wal", "-shm", ""):
            self._content_path.with_name(self._content_path.name + suffix).unlink(
                missing_ok=True
            )
        return self.status()

    def index(
        self,
        *,
        estimator: TokenEstimator | None = None,
    ) -> dict[str, Any]:
        status = self.status()
        if status["state"] != "enabled":
            raise ValueError("context composition is disabled")
        control = load_cutover_control(self._operational_path)
        analytical = control.active_kernel_path
        generation = control.active_generation
        if analytical is None or generation is None:
            raise ValueError("no active analytical generation")
        targets = _source_targets(
            analytical,
            self._operational_path,
            generation=generation,
        )
        category_counts = {category: 0 for category in sorted(_CATEGORIES)}
        event_count = 0
        with _open_content_writer(self._content_path) as connection:
            settings = connection.execute(
                """
                SELECT
                    store_redacted_fragments,
                    indexed_generation,
                    estimator_id
                FROM content_settings
                WHERE singleton = 1 AND enabled = 1
                """
            ).fetchone()
            if settings is None:
                raise ValueError("context composition is disabled")
            retain_fragments = bool(settings["store_redacted_fragments"])
            estimator_id = estimator.identifier if estimator else None
            if (
                settings["indexed_generation"] is not None
                and settings["estimator_id"] != estimator_id
            ):
                connection.execute("DELETE FROM composition_events")
                connection.execute("DELETE FROM source_cursors")
            _retire_absent_sources(
                connection,
                {str(target["source_id"]) for target in targets},
            )
            for target in targets:
                rows = _scan_source(
                    connection,
                    target,
                    generation=generation,
                    retain_fragments=retain_fragments,
                    estimator=estimator,
                )
                event_count += len(rows)
                for row in rows:
                    category_counts[str(row["category"])] += 1
            connection.execute(
                """
                UPDATE content_settings
                SET indexed_generation = ?,
                    estimator_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE singleton = 1
                """,
                (generation, estimator_id),
            )
        return {
            "state": "enabled",
            "indexed_generation": generation,
            "events": event_count,
            "categories": {
                key: value for key, value in category_counts.items() if value
            },
            "estimator": estimator_id,
        }


def content_status(path: Path) -> dict[str, Any]:
    """Return bounded capability state without creating the content database."""

    target = path.resolve()
    disabled = {
        "state": "disabled",
        "store_redacted_fragments": False,
        "indexed_generation": None,
        "estimator": None,
    }
    if not target.is_file():
        return disabled
    try:
        with _open_content_readonly(target) as connection:
            row = connection.execute(
                """
                SELECT
                    enabled,
                    store_redacted_fragments,
                    indexed_generation,
                    estimator_id
                FROM content_settings
                WHERE singleton = 1
                """
            ).fetchone()
    except (sqlite3.Error, ValueError):
        return {
            **disabled,
            "state": "unavailable",
        }
    if row is None:
        return disabled
    return {
        "state": "enabled" if row["enabled"] else "disabled",
        "store_redacted_fragments": bool(row["store_redacted_fragments"]),
        "indexed_generation": row["indexed_generation"],
        "estimator": row["estimator_id"],
    }


@contextmanager
def open_content_snapshot(path: Path) -> Iterator[sqlite3.Connection]:
    """Open the enabled content database read-only for bounded query plans."""

    target = path.resolve()
    status = content_status(target)
    if status["state"] != "enabled":
        raise ValueError(
            "context composition is disabled; enable and index it explicitly"
        )
    with _open_content_readonly(target) as connection:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        try:
            yield connection
        finally:
            connection.rollback()


def _initialize_content_database(path: Path) -> None:
    target = path.resolve()
    if target.exists():
        with _open_content_readonly(target):
            pass
        target.chmod(0o600)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.building-{os.getpid()}")
    try:
        connection = sqlite3.connect(staging)
        try:
            connection.execute(f"PRAGMA application_id = {CONTENT_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {CONTENT_SCHEMA_VERSION}")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(_SCHEMA_SQL)
            connection.commit()
        finally:
            connection.close()
        staging.chmod(0o600)
        os.replace(staging, target)
        connection = sqlite3.connect(target)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.commit()
        finally:
            connection.close()
        target.chmod(0o600)
    finally:
        staging.unlink(missing_ok=True)


@contextmanager
def _open_content_writer(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@contextmanager
def _open_content_readonly(path: Path) -> Iterator[sqlite3.Connection]:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if (
            application_id != CONTENT_APPLICATION_ID
            or version != CONTENT_SCHEMA_VERSION
        ):
            raise ValueError("content database identity is invalid")
        yield connection
    finally:
        connection.close()


def _source_targets(
    analytical_path: Path,
    operational_path: Path,
    *,
    generation: int,
) -> tuple[dict[str, Any], ...]:
    with open_read_snapshot(analytical_path) as analytical:
        rows = analytical.execute(
            """
            SELECT
                source_id,
                parsed_byte_offset,
                parsed_line_number
            FROM sources
            WHERE last_generation <= ?
            ORDER BY source_id
            """,
            (generation,),
        ).fetchall()
    with sqlite3.connect(operational_path) as operational:
        locations = {
            str(row[0]): Path(str(row[1]))
            for row in operational.execute(
                "SELECT source_id, source_location FROM source_registry"
            )
        }
    return tuple(
        {
            **dict(row),
            "path": locations[str(row["source_id"])],
        }
        for row in rows
        if str(row["source_id"]) in locations
    )


def _scan_source(
    connection: sqlite3.Connection,
    target: dict[str, Any],
    *,
    generation: int,
    retain_fragments: bool,
    estimator: TokenEstimator | None,
) -> list[dict[str, Any]]:
    source_id = str(target["source_id"])
    end_offset = int(target["parsed_byte_offset"])
    end_line = int(target["parsed_line_number"])
    source = Path(target["path"])
    cursor = connection.execute(
        """
        SELECT *
        FROM source_cursors
        WHERE source_id = ?
        """,
        (source_id,),
    ).fetchone()
    cursor_offset = int(cursor["parsed_byte_offset"]) if cursor else 0
    cursor_digest = (
        _prefix_digest(source, cursor_offset)
        if cursor is not None and cursor_offset <= end_offset
        else None
    )
    cursor_is_valid = (
        cursor is not None
        and cursor_offset <= end_offset
        and cursor_digest == cursor["prefix_fingerprint"]
    )
    if not cursor_is_valid:
        connection.execute(
            "DELETE FROM composition_events WHERE source_id = ?",
            (source_id,),
        )
        start_offset = 0
        start_line = 0
        thread_id = None
        turn_id = None
    else:
        assert cursor is not None
        start_offset = cursor_offset
        start_line = int(cursor["parsed_line_number"])
        thread_id = cursor["logical_thread_id"]
        turn_id = cursor["turn_id"]
    rows: list[dict[str, Any]] = []
    offset = start_offset
    line_number = start_line
    with source.open("rb") as handle:
        handle.seek(start_offset)
        while offset < end_offset:
            line = handle.readline(end_offset - offset)
            if not line:
                raise OSError("committed content source ended before its cursor")
            try:
                envelope = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                offset += len(line)
                line_number += 1
                continue
            thread_id, turn_id = _identity_state(envelope, thread_id, turn_id)
            category = _category(envelope)
            values = _observed_values(envelope, category)
            if values:
                observed_bytes = sum(
                    len(value.encode("utf-8")) for _, value in values
                )
                estimated_tokens = (
                    sum(estimator.estimate(value) for _, value in values)
                    if estimator
                    else None
                )
                event_id = stable_id("ctx", source_id, offset, category)
                row = {
                    "event_id": event_id,
                    "source_id": source_id,
                    "logical_thread_id": thread_id,
                    "turn_id": turn_id,
                    "event_at": _timestamp(envelope),
                    "category": category,
                    "observed_bytes": observed_bytes,
                    "estimated_tokens": estimated_tokens,
                    "source_offset": offset,
                    "generation": generation,
                }
                connection.execute(
                    """
                    INSERT OR REPLACE INTO composition_events(
                        event_id,
                        source_id,
                        logical_thread_id,
                        turn_id,
                        event_at,
                        category,
                        observed_bytes,
                        estimated_tokens,
                        source_offset,
                        generation
                    )
                    VALUES (
                        :event_id,
                        :source_id,
                        :logical_thread_id,
                        :turn_id,
                        :event_at,
                        :category,
                        :observed_bytes,
                        :estimated_tokens,
                        :source_offset,
                        :generation
                    )
                    """,
                    row,
                )
                if retain_fragments:
                    redacted = "\n".join(
                        _redact_text(value, key=key) for key, value in values
                    )[:MAX_REDACTED_FRAGMENT_CHARS]
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO redacted_fragments(
                            event_id, redacted_text
                        )
                        VALUES (?, ?)
                        """,
                        (
                            event_id,
                            redacted,
                        ),
                    )
                rows.append(row)
            offset += len(line)
            line_number += 1
    connection.execute(
        """
        INSERT OR REPLACE INTO source_cursors(
            source_id,
            prefix_fingerprint,
            parsed_byte_offset,
            parsed_line_number,
            logical_thread_id,
            turn_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            (
                cursor_digest
                if cursor_is_valid and start_offset == end_offset
                else _prefix_digest(source, end_offset)
            ),
            end_offset,
            end_line,
            thread_id,
            turn_id,
        ),
    )
    return rows


def _retire_absent_sources(
    connection: sqlite3.Connection,
    current_source_ids: set[str],
) -> None:
    retained = {
        str(row["source_id"])
        for row in connection.execute("SELECT source_id FROM source_cursors")
    }
    for source_id in sorted(retained - current_source_ids):
        connection.execute(
            "DELETE FROM composition_events WHERE source_id = ?",
            (source_id,),
        )
        connection.execute(
            "DELETE FROM source_cursors WHERE source_id = ?",
            (source_id,),
        )


def _prefix_digest(path: Path, end_offset: int) -> str:
    sample_size = min(CONTENT_FINGERPRINT_SAMPLE_BYTES, end_offset)
    offsets = {
        0,
        max(0, (end_offset - sample_size) // 2),
        max(0, end_offset - sample_size),
    }
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for offset in sorted(offsets):
            handle.seek(offset)
            payload = handle.read(sample_size)
            if len(payload) != sample_size:
                raise OSError("committed content source ended before its cursor")
            digest.update(offset.to_bytes(8, "big"))
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return digest.hexdigest()


def _identity_state(
    envelope: Any,
    thread_id: str | None,
    turn_id: str | None,
) -> tuple[str | None, str | None]:
    if not isinstance(envelope, dict):
        return thread_id, turn_id
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return thread_id, turn_id
    if envelope.get("type") == "session_meta" and isinstance(payload.get("id"), str):
        thread_id = stable_id("thr", payload["id"])
    if envelope.get("type") == "turn_context" and isinstance(
        payload.get("turn_id"), str
    ):
        turn_id = stable_id("uturn", payload["turn_id"])
    return thread_id, turn_id


def _category(envelope: Any) -> str:
    if not isinstance(envelope, dict):
        return "unattributed"
    envelope_type = envelope.get("type")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return "unattributed"
    payload_type = str(payload.get("type", ""))
    if envelope_type == "turn_context":
        return "host"
    if envelope_type == "response_item":
        if payload_type == "message":
            return "message"
        if payload_type in {
            "custom_tool_call_output",
            "function_call",
            "function_call_output",
        }:
            return "tool"
    if envelope_type == "event_msg":
        if "mcp" in payload_type:
            return "mcp"
        if "tool" in payload_type or "function" in payload_type:
            return "tool"
        if payload_type == "context_compacted":
            return "message"
    return "unattributed"


def _observed_values(
    envelope: Any,
    category: str,
) -> list[tuple[str | None, str]]:
    if not isinstance(envelope, dict):
        return []
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return []
    if category == "unattributed":
        content_keys = {"arguments", "content", "instructions", "message", "output", "text"}
        if not content_keys.intersection(payload):
            return []
    return list(_string_values(payload))


def _string_values(
    value: Any,
    *,
    key: str | None = None,
) -> Iterator[tuple[str | None, str]]:
    if isinstance(value, str):
        if key not in _STRUCTURAL_KEYS and value:
            yield key, value
        return
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _string_values(child, key=str(child_key))
        return
    if isinstance(value, list):
        for child in value:
            yield from _string_values(child, key=key)


def _timestamp(envelope: Any) -> str | None:
    if not isinstance(envelope, dict):
        return None
    value = envelope.get("timestamp")
    return value if isinstance(value, str) else None


def _redact_text(value: str, *, key: str | None = None) -> str:
    if key is not None and _is_sensitive_field(key):
        return "[REDACTED]"
    redacted = _BEARER.sub("Bearer [REDACTED]", value)
    redacted = _OPENAI_KEY.sub("[REDACTED]", redacted)
    redacted = _KNOWN_SECRET.sub("[REDACTED]", redacted)
    redacted = _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        redacted,
    )
    return "[REDACTED]" if _SENSITIVE_KEY.fullmatch(redacted) else redacted


def _is_sensitive_field(key: str) -> bool:
    if _SENSITIVE_FIELD_KEY.fullmatch(key):
        return True
    snake_case = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    components = {
        component
        for component in re.split(r"[^A-Za-z0-9]+", snake_case.lower())
        if component
    }
    return (
        bool(components & _SENSITIVE_FIELD_COMPONENTS)
        or {"api", "key"} <= components
    )
