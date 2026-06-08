# AI Usage Tracker Claude Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generic provider-aware usage tracking with Codex preserved as the default adapter and Claude Code JSONL as the first new source.

**Architecture:** Keep the current package, CLI, plugin, and SQLite table name for compatibility, but add provider/app/source fields to every aggregate usage row. Move ingestion behind source adapters, wire Codex and Claude Code through one refresh service, then expose provider/app fields in reports, query filters, CSV, MCP, and the dashboard.

**Tech Stack:** Python 3.10+, SQLite stdlib, pytest, mypy-covered core modules, FastMCP, vanilla dashboard JavaScript.

---

## File Structure

- Create `src/codex_usage_tracker/adapters/__init__.py`: adapter exports.
- Create `src/codex_usage_tracker/adapters/base.py`: shared adapter protocol, source constants, diagnostics helper names.
- Create `src/codex_usage_tracker/adapters/codex_jsonl.py`: current Codex JSONL parser moved behind adapter methods.
- Create `src/codex_usage_tracker/adapters/claude_code_jsonl.py`: Claude Code local JSONL parser.
- Modify `src/codex_usage_tracker/models.py`: provider fields on `UsageEvent`, source result fields on `RefreshResult`.
- Modify `src/codex_usage_tracker/schema.py`: provider fields in persisted column metadata.
- Modify `src/codex_usage_tracker/store.py`: schema v3, multi-source refresh/rebuild, source filters, source summary groups.
- Modify `src/codex_usage_tracker/parser.py`: compatibility facade that delegates to `CodexJsonlAdapter`.
- Modify `src/codex_usage_tracker/paths.py`: add `DEFAULT_CLAUDE_HOME`.
- Modify `src/codex_usage_tracker/api_payloads.py`: include source results in refresh JSON payloads.
- Modify `src/codex_usage_tracker/reports.py`: provider/app summary choices and query filters.
- Modify `src/codex_usage_tracker/cli.py`: `--source`, `--claude-home`, provider/app query args.
- Modify `src/codex_usage_tracker/mcp_server.py`: provider/app query args and source-aware refresh.
- Modify `src/codex_usage_tracker/dashboard.py`: provider/app payload filter support and AI usage title.
- Modify `src/codex_usage_tracker/server.py`: source-aware live refresh.
- Modify `src/codex_usage_tracker/allowance.py`: Codex credits apply only to Codex/OpenAI rows.
- Modify `src/codex_usage_tracker/plugin_data/dashboard/dashboard_template.html`: provider/app filters and generic title text.
- Modify `src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`: provider/app helpers and Codex-only credit labels.
- Modify `src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js`: provider/app URL state.
- Modify `src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`: provider/app filtering, export fields, detail fields, labels.
- Modify docs after behavior works: `README.md`, `docs/architecture.md`, `docs/dashboard-guide.md`, `docs/cli-reference.md`, `docs/cli-json-schemas.md`, `docs/privacy.md`, `docs/development.md`, `AGENTS.md`.
- Modify tests: `tests/test_schema.py`, `tests/test_parser.py`, `tests/test_store_dashboard_mcp.py`, `tests/test_cli_lifecycle.py`, `tests/test_json_contracts.py`, `tests/test_allowance.py`, and add `tests/test_claude_adapter.py`.

## Task 1: Schema And Model Provider Fields

**Files:**
- Modify: `src/codex_usage_tracker/models.py`
- Modify: `src/codex_usage_tracker/schema.py`
- Modify: `src/codex_usage_tracker/store.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_store_dashboard_mcp.py`

- [ ] **Step 1: Write the failing model and migration tests**

Add these assertions to `tests/test_schema.py`:

```python
def test_usage_event_includes_source_identity_fields() -> None:
    event = _usage_event()

    row = event.to_row()

    assert row["source_provider"] == "openai"
    assert row["source_app"] == "codex"
    assert row["source_format"] == "codex-jsonl-v1"
    assert row["provider_request_id"] is None
    assert row["cache_creation_input_tokens"] == 0


def test_schema_columns_include_provider_identity() -> None:
    assert "source_provider" in USAGE_EVENT_COLUMN_NAMES
    assert "source_app" in USAGE_EVENT_COLUMN_NAMES
    assert "source_format" in USAGE_EVENT_COLUMN_NAMES
    assert "provider_request_id" in USAGE_EVENT_COLUMN_NAMES
    assert "cache_creation_input_tokens" in USAGE_EVENT_COLUMN_NAMES
```

Add this migration test to `tests/test_store_dashboard_mcp.py` after `test_init_db_repairs_version_zero_schema`:

```python
def test_init_db_backfills_provider_columns_for_existing_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(
            """
            CREATE TABLE usage_events (
                record_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                thread_name TEXT,
                session_updated_at TEXT,
                event_timestamp TEXT NOT NULL,
                source_file TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                turn_id TEXT,
                turn_timestamp TEXT,
                cwd TEXT,
                model TEXT,
                effort TEXT,
                current_date TEXT,
                timezone TEXT,
                thread_source TEXT,
                subagent_type TEXT,
                agent_role TEXT,
                agent_nickname TEXT,
                parent_session_id TEXT,
                parent_thread_name TEXT,
                parent_session_updated_at TEXT,
                model_context_window INTEGER,
                input_tokens INTEGER NOT NULL,
                cached_input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                reasoning_output_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                cumulative_input_tokens INTEGER NOT NULL,
                cumulative_cached_input_tokens INTEGER NOT NULL,
                cumulative_output_tokens INTEGER NOT NULL,
                cumulative_reasoning_output_tokens INTEGER NOT NULL,
                cumulative_total_tokens INTEGER NOT NULL,
                uncached_input_tokens INTEGER NOT NULL,
                cache_ratio REAL NOT NULL,
                reasoning_output_ratio REAL NOT NULL,
                context_window_percent REAL NOT NULL
            )
            """
        )
        raw.execute(
            """
            INSERT INTO usage_events (
                record_id, session_id, event_timestamp, source_file, line_number,
                input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens,
                total_tokens, cumulative_input_tokens, cumulative_cached_input_tokens,
                cumulative_output_tokens, cumulative_reasoning_output_tokens,
                cumulative_total_tokens, uncached_input_tokens, cache_ratio,
                reasoning_output_ratio, context_window_percent
            )
            VALUES (
                'legacy-record', 'session-a', '2026-05-17T18:58:27Z',
                '/tmp/log.jsonl', 1, 100, 20, 10, 0, 110, 100, 20, 10, 0,
                110, 80, 0.2, 0.0, 0.0
            )
            """
        )
        raw.commit()
    finally:
        raw.close()

    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute("SELECT * FROM usage_events WHERE record_id = 'legacy-record'").fetchone()

    assert row["source_provider"] == "openai"
    assert row["source_app"] == "codex"
    assert row["source_format"] == "codex-jsonl-v1"
    assert row["provider_request_id"] is None
    assert row["cache_creation_input_tokens"] == 0
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
python -m pytest tests/test_schema.py::test_usage_event_includes_source_identity_fields tests/test_schema.py::test_schema_columns_include_provider_identity tests/test_store_dashboard_mcp.py::test_init_db_backfills_provider_columns_for_existing_rows -v
```

Expected: FAIL because the new columns and `UsageEvent` fields do not exist.

- [ ] **Step 3: Add model fields**

Modify `UsageEvent` in `src/codex_usage_tracker/models.py` by inserting these fields after `line_number`:

```python
    source_provider: str
    source_app: str
    source_format: str
    provider_request_id: str | None
```

Insert this token field after `model_context_window`:

```python
    cache_creation_input_tokens: int
```

`to_row()` already uses `asdict(self)`, so no extra serialization code is needed.

- [ ] **Step 4: Add schema columns and migration v3**

Modify `USAGE_EVENT_COLUMNS` in `src/codex_usage_tracker/schema.py` so the new persisted columns are included after `line_number`:

```python
    UsageColumn("source_provider", "TEXT NOT NULL DEFAULT 'openai'", "TEXT NOT NULL DEFAULT 'openai'", repairable=True),
    UsageColumn("source_app", "TEXT NOT NULL DEFAULT 'codex'", "TEXT NOT NULL DEFAULT 'codex'", repairable=True),
    UsageColumn("source_format", "TEXT NOT NULL DEFAULT 'codex-jsonl-v1'", "TEXT NOT NULL DEFAULT 'codex-jsonl-v1'", repairable=True),
    UsageColumn("provider_request_id", "TEXT", "TEXT", repairable=True),
```

Add `cache_creation_input_tokens` after `model_context_window`:

```python
    UsageColumn("cache_creation_input_tokens", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0", repairable=True),
```

Modify `src/codex_usage_tracker/store.py`:

```python
SCHEMA_VERSION = 3
MIGRATION_NAMES = {
    1: "create usage_events aggregate fact table",
    2: "track schema migration checksum metadata",
    3: "track source provider identity",
}
```

Add this migration function:

```python
def _migrate_v3(conn: sqlite3.Connection) -> None:
    _ensure_columns(conn, USAGE_EVENT_REPAIR_COLUMNS)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_usage_source ON usage_events(source_provider, source_app);
        CREATE INDEX IF NOT EXISTS idx_usage_source_format ON usage_events(source_format);
        """
    )
```

Call it from `init_db()` after v2:

```python
    if user_version < 3:
        _migrate_v3(conn)
        _record_migration(conn, 3)
    else:
        _migrate_v3(conn)
        _record_migration_if_missing(conn, 3)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
```

- [ ] **Step 5: Update test fixture constructors**

Update `_usage_event()` in `tests/test_schema.py` and direct `UsageEvent(...)` constructors in `tests/test_store_dashboard_mcp.py` with:

```python
            source_provider="openai",
            source_app="codex",
            source_format="codex-jsonl-v1",
            provider_request_id=None,
            cache_creation_input_tokens=0,
```

- [ ] **Step 6: Run schema tests**

Run:

```bash
python -m pytest tests/test_schema.py tests/test_store_dashboard_mcp.py::test_init_db_backfills_provider_columns_for_existing_rows tests/test_store_dashboard_mcp.py::test_init_db_repairs_version_zero_schema -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/codex_usage_tracker/models.py src/codex_usage_tracker/schema.py src/codex_usage_tracker/store.py tests/test_schema.py tests/test_store_dashboard_mcp.py
git commit -m "feat: add usage source identity columns"
```

## Task 2: Codex Adapter Extraction

**Files:**
- Create: `src/codex_usage_tracker/adapters/__init__.py`
- Create: `src/codex_usage_tracker/adapters/base.py`
- Create: `src/codex_usage_tracker/adapters/codex_jsonl.py`
- Modify: `src/codex_usage_tracker/parser.py`
- Modify: `tests/test_parser.py`
- Modify: `tests/test_store_dashboard_mcp.py`

- [ ] **Step 1: Write failing source-field assertions for Codex parsing**

In `tests/test_parser.py`, add these assertions to `test_parser_skips_missing_info_and_duplicate_snapshots`:

```python
    assert events[0].source_provider == "openai"
    assert events[0].source_app == "codex"
    assert events[0].source_format == "codex-jsonl-v1"
    assert events[0].provider_request_id is None
    assert events[0].cache_creation_input_tokens == 0
```

In `test_inspect_log_reports_aggregate_diagnostics_without_db_writes`, add:

```python
    assert payload["adapter"] == "codex-jsonl-v1"
    assert payload["source_provider"] == "openai"
    assert payload["source_app"] == "codex"
```

- [ ] **Step 2: Run failing parser assertions**

Run:

```bash
python -m pytest tests/test_parser.py::test_parser_skips_missing_info_and_duplicate_snapshots tests/test_parser.py::test_inspect_log_reports_aggregate_diagnostics_without_db_writes -v
```

Expected: FAIL until parser-created `UsageEvent` rows include source identity and `inspect_log()` exposes source metadata.

- [ ] **Step 3: Add adapter base**

Create `src/codex_usage_tracker/adapters/base.py`:

```python
"""Source adapter contracts for aggregate usage ingestion."""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from pathlib import Path
from typing import Protocol, TypeAlias

from codex_usage_tracker.models import SessionInfo, UsageEvent

SessionIndex: TypeAlias = dict[str, SessionInfo]

SOURCE_CODEX = "codex"
SOURCE_CLAUDE_CODE = "claude-code"
SOURCE_ALL = "all"
SOURCE_CHOICES = (SOURCE_CODEX, SOURCE_CLAUDE_CODE, SOURCE_ALL)


class UsageSourceAdapter(Protocol):
    source_provider: str
    source_app: str
    source_format: str

    def discover_logs(self, root: Path, *, include_archived: bool = False) -> list[Path]:
        """Return local log paths for this source."""

    def load_session_index(self, root: Path) -> SessionIndex:
        """Return source metadata keyed by session id without raw transcript content."""

    def parse_file(
        self,
        path: Path,
        session_index: SessionIndex | None = None,
        stats: MutableMapping[str, int] | None = None,
    ) -> list[UsageEvent]:
        """Parse one source log into aggregate usage events."""


def parse_files(
    adapter: UsageSourceAdapter,
    paths: Iterable[Path],
    session_index: SessionIndex | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    events: list[UsageEvent] = []
    for path in paths:
        events.extend(adapter.parse_file(path, session_index=session_index, stats=stats))
    return events
```

Create `src/codex_usage_tracker/adapters/__init__.py`:

```python
"""Aggregate usage source adapters."""

from codex_usage_tracker.adapters.base import (
    SOURCE_ALL,
    SOURCE_CHOICES,
    SOURCE_CLAUDE_CODE,
    SOURCE_CODEX,
    UsageSourceAdapter,
)
from codex_usage_tracker.adapters.codex_jsonl import CodexJsonlAdapter

__all__ = [
    "SOURCE_ALL",
    "SOURCE_CHOICES",
    "SOURCE_CLAUDE_CODE",
    "SOURCE_CODEX",
    "CodexJsonlAdapter",
    "UsageSourceAdapter",
]
```

- [ ] **Step 4: Move Codex parser logic into adapter module**

Create `src/codex_usage_tracker/adapters/codex_jsonl.py` by moving the Codex-specific constants and helpers from current `parser.py`. Keep function bodies unchanged except for:

```python
PARSER_ADAPTER_VERSION = "codex-jsonl-v1"


@dataclass(frozen=True)
class CodexJsonlAdapter:
    """Versioned parser adapter for Codex JSONL session logs."""

    source_provider: str = "openai"
    source_app: str = "codex"
    source_format: str = PARSER_ADAPTER_VERSION

    @property
    def version(self) -> str:
        return self.source_format

    def discover_logs(self, root: Path, *, include_archived: bool = False) -> list[Path]:
        paths = list((root / "sessions").glob("**/*.jsonl"))
        if include_archived:
            paths.extend((root / "archived_sessions").glob("*.jsonl"))
        return sorted(path for path in paths if path.is_file())

    def load_session_index(self, root: Path) -> dict[str, SessionInfo]:
        return load_session_index(root)

    def parse_file(
        self,
        path: Path,
        session_index: dict[str, SessionInfo] | None = None,
        stats: MutableMapping[str, int] | None = None,
    ) -> list[UsageEvent]:
        return _parse_codex_jsonl_v1(path, session_index=session_index, stats=stats)
```

In `_build_event(...)`, add the new `UsageEvent` fields:

```python
        source_provider="openai",
        source_app="codex",
        source_format=PARSER_ADAPTER_VERSION,
        provider_request_id=None,
        cache_creation_input_tokens=0,
```

- [ ] **Step 5: Replace parser.py with compatibility facade**

Keep the public imports and functions used by tests and callers in `src/codex_usage_tracker/parser.py`:

```python
"""Parse Codex JSONL session logs into aggregate usage records."""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from pathlib import Path

from codex_usage_tracker.adapters.base import parse_files
from codex_usage_tracker.adapters.codex_jsonl import (
    PARSER_ADAPTER_VERSION,
    PARSER_DIAGNOSTIC_KEYS,
    CodexJsonlAdapter,
    compact_parser_diagnostics,
    empty_parser_diagnostics,
)
from codex_usage_tracker.models import SessionInfo, UsageEvent
from codex_usage_tracker.paths import DEFAULT_CODEX_HOME

DEFAULT_PARSER_ADAPTER = CodexJsonlAdapter()
ParserAdapter = CodexJsonlAdapter


def load_session_index(codex_home: Path = DEFAULT_CODEX_HOME) -> dict[str, SessionInfo]:
    return DEFAULT_PARSER_ADAPTER.load_session_index(codex_home)


def find_session_logs(
    codex_home: Path = DEFAULT_CODEX_HOME, include_archived: bool = False
) -> list[Path]:
    return DEFAULT_PARSER_ADAPTER.discover_logs(codex_home, include_archived=include_archived)


def parse_usage_events(
    paths: Iterable[Path],
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    return parse_files(DEFAULT_PARSER_ADAPTER, paths, session_index=session_index, stats=stats)


def parse_usage_events_from_file(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    return DEFAULT_PARSER_ADAPTER.parse_file(path, session_index=session_index, stats=stats)
```

Keep `inspect_log()` in `parser.py`, but add source fields to its payload:

```python
        "source_provider": DEFAULT_PARSER_ADAPTER.source_provider,
        "source_app": DEFAULT_PARSER_ADAPTER.source_app,
        "source_format": DEFAULT_PARSER_ADAPTER.source_format,
```

- [ ] **Step 6: Run Codex parser and store tests**

Run:

```bash
python -m pytest tests/test_parser.py tests/test_store_dashboard_mcp.py::test_refresh_is_idempotent_and_summary_works -v
```

Expected: PASS with `parser_adapter` still `codex-jsonl-v1` for default Codex refresh.

- [ ] **Step 7: Commit**

```bash
git add src/codex_usage_tracker/adapters src/codex_usage_tracker/parser.py tests/test_parser.py tests/test_store_dashboard_mcp.py
git commit -m "refactor: move Codex parser into adapter"
```

## Task 3: Claude Code JSONL Adapter

**Files:**
- Create: `src/codex_usage_tracker/adapters/claude_code_jsonl.py`
- Modify: `src/codex_usage_tracker/adapters/__init__.py`
- Modify: `src/codex_usage_tracker/adapters/base.py`
- Add: `tests/test_claude_adapter.py`

- [ ] **Step 1: Write synthetic Claude parser tests**

Create `tests/test_claude_adapter.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.adapters.claude_code_jsonl import (
    CLAUDE_CODE_DIAGNOSTIC_KEYS,
    ClaudeCodeJsonlAdapter,
    compact_claude_diagnostics,
)


def test_claude_adapter_parses_aggregate_usage_without_text(tmp_path: Path) -> None:
    claude_home = _make_claude_home(tmp_path)
    adapter = ClaudeCodeJsonlAdapter()
    logs = adapter.discover_logs(claude_home)

    stats: dict[str, int] = {}
    events = adapter.parse_file(logs[0], stats=stats)

    assert len(events) == 2
    first = events[0]
    assert first.source_provider == "anthropic"
    assert first.source_app == "claude-code"
    assert first.source_format == "claude-code-jsonl-v1"
    assert first.provider_request_id == "msg-001"
    assert first.session_id == "claude-session-1"
    assert first.model == "claude-sonnet-4-20250514"
    assert first.cwd == "/tmp/claude-project"
    assert first.input_tokens == 170
    assert first.cached_input_tokens == 50
    assert first.cache_creation_input_tokens == 20
    assert first.uncached_input_tokens == 120
    assert first.output_tokens == 30
    assert first.total_tokens == 200
    assert first.cumulative_total_tokens == 200
    assert events[1].cumulative_total_tokens == 310
    assert "SECRET CLAUDE TEXT" not in json.dumps([event.to_row() for event in events])
    assert compact_claude_diagnostics(stats) == {}


def test_claude_adapter_reports_diagnostics_and_continues(tmp_path: Path) -> None:
    log_path = tmp_path / ".claude" / "projects" / "project-a" / "session.jsonl"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "{not json}",
                json.dumps({"type": "assistant", "message": {"usage": None}}),
                json.dumps(_assistant_entry("msg-good", input_tokens=10, output_tokens=5)),
                json.dumps(_assistant_entry("msg-bad", input_tokens="bad", output_tokens=5)),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    adapter = ClaudeCodeJsonlAdapter()
    stats: dict[str, int] = {}

    events = adapter.parse_file(log_path, stats=stats)

    assert len(events) == 1
    assert events[0].provider_request_id == "msg-good"
    assert stats["invalid_json"] == 1
    assert stats["missing_usage"] == 1
    assert stats["invalid_integer"] == 1
    assert stats["skipped_events"] == 2


def test_claude_log_discovery_uses_projects_tree(tmp_path: Path) -> None:
    claude_home = _make_claude_home(tmp_path)
    adapter = ClaudeCodeJsonlAdapter()

    logs = adapter.discover_logs(claude_home)

    assert [path.name for path in logs] == ["session.jsonl"]


def _make_claude_home(tmp_path: Path) -> Path:
    claude_home = tmp_path / ".claude"
    log_path = claude_home / "projects" / "project-a" / "session.jsonl"
    log_path.parent.mkdir(parents=True)
    rows = [
        {
            "type": "user",
            "message": {"role": "user", "content": "SECRET CLAUDE TEXT"},
        },
        _assistant_entry(
            "msg-001",
            input_tokens=100,
            cache_creation_input_tokens=20,
            cache_read_input_tokens=50,
            output_tokens=30,
        ),
        _assistant_entry(
            "msg-002",
            input_tokens=40,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=10,
            output_tokens=60,
        ),
    ]
    log_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return claude_home


def _assistant_entry(
    message_id: str,
    *,
    input_tokens: object,
    output_tokens: object,
    cache_creation_input_tokens: object = 0,
    cache_read_input_tokens: object = 0,
) -> dict[str, object]:
    return {
        "type": "assistant",
        "timestamp": "2026-06-08T12:00:00.000Z",
        "sessionId": "claude-session-1",
        "cwd": "/tmp/claude-project",
        "message": {
            "id": message_id,
            "role": "assistant",
            "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "SECRET CLAUDE TEXT"}],
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "output_tokens": output_tokens,
            },
        },
    }
```

- [ ] **Step 2: Run failing Claude tests**

Run:

```bash
python -m pytest tests/test_claude_adapter.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `codex_usage_tracker.adapters.claude_code_jsonl`.

- [ ] **Step 3: Implement Claude adapter**

Create `src/codex_usage_tracker/adapters/claude_code_jsonl.py`:

```python
"""Parse Claude Code local JSONL history into aggregate usage records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.models import SessionInfo, UsageEvent

CLAUDE_CODE_ADAPTER_VERSION = "claude-code-jsonl-v1"
CLAUDE_CODE_DIAGNOSTIC_KEYS = (
    "invalid_json",
    "unknown_event_shape",
    "missing_usage",
    "invalid_integer",
    "duplicate_record",
    "skipped_events",
)


@dataclass(frozen=True)
class ClaudeCodeJsonlAdapter:
    source_provider: str = "anthropic"
    source_app: str = "claude-code"
    source_format: str = CLAUDE_CODE_ADAPTER_VERSION

    def discover_logs(self, root: Path, *, include_archived: bool = False) -> list[Path]:
        del include_archived
        return sorted(path for path in (root / "projects").glob("**/*.jsonl") if path.is_file())

    def load_session_index(self, root: Path) -> dict[str, SessionInfo]:
        del root
        return {}

    def parse_file(
        self,
        path: Path,
        session_index: dict[str, SessionInfo] | None = None,
        stats: MutableMapping[str, int] | None = None,
    ) -> list[UsageEvent]:
        del session_index
        events: list[UsageEvent] = []
        seen: set[str] = set()
        cumulative = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": 0,
        }
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    envelope = json.loads(line)
                except json.JSONDecodeError:
                    _increment_stat(stats, "invalid_json")
                    continue
                if not isinstance(envelope, dict):
                    _increment_stat(stats, "unknown_event_shape")
                    continue
                message = _message_payload(envelope)
                if message is None:
                    continue
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    _increment_stat(stats, "missing_usage")
                    _increment_stat(stats, "skipped_events")
                    continue
                try:
                    event = _build_event(path, line_number, envelope, message, usage, cumulative)
                except ValueError:
                    _increment_stat(stats, "invalid_integer")
                    _increment_stat(stats, "skipped_events")
                    continue
                if event.record_id in seen:
                    _increment_stat(stats, "duplicate_record")
                    continue
                seen.add(event.record_id)
                events.append(event)
        return events


def compact_claude_diagnostics(stats: MutableMapping[str, int]) -> dict[str, int]:
    return {
        key: int(stats.get(key, 0))
        for key in CLAUDE_CODE_DIAGNOSTIC_KEYS
        if stats.get(key, 0)
    }


def _message_payload(envelope: dict[str, Any]) -> dict[str, Any] | None:
    message = envelope.get("message")
    if isinstance(message, dict) and message.get("role") == "assistant":
        return message
    if envelope.get("type") == "assistant" and isinstance(message, dict):
        return message
    if envelope.get("role") == "assistant":
        return envelope
    return None


def _build_event(
    path: Path,
    line_number: int,
    envelope: dict[str, Any],
    message: dict[str, Any],
    usage: dict[str, Any],
    cumulative: dict[str, int],
) -> UsageEvent:
    normal_input = _usage_int(usage, "input_tokens")
    cache_creation = _usage_int(usage, "cache_creation_input_tokens", default=0)
    cache_read = _usage_int(usage, "cache_read_input_tokens", default=0)
    output_tokens = _usage_int(usage, "output_tokens")
    reasoning_output = _usage_int(usage, "thinking_tokens", default=0)
    input_tokens = normal_input + cache_creation + cache_read
    total_tokens = input_tokens + output_tokens
    cumulative["input_tokens"] += input_tokens
    cumulative["cached_input_tokens"] += cache_read
    cumulative["cache_creation_input_tokens"] += cache_creation
    cumulative["output_tokens"] += output_tokens
    cumulative["reasoning_output_tokens"] += reasoning_output
    cumulative["total_tokens"] += total_tokens
    session_id = _optional_str(envelope.get("sessionId")) or _optional_str(envelope.get("session_id")) or path.stem
    request_id = _optional_str(message.get("id")) or _optional_str(envelope.get("uuid"))
    event_timestamp = _optional_str(envelope.get("timestamp")) or ""
    record_id = _record_id(session_id, request_id, event_timestamp, line_number)
    return UsageEvent(
        record_id=record_id,
        session_id=session_id,
        thread_name=_optional_str(envelope.get("summary")),
        session_updated_at=None,
        event_timestamp=event_timestamp,
        source_file=str(path),
        line_number=line_number,
        source_provider="anthropic",
        source_app="claude-code",
        source_format=CLAUDE_CODE_ADAPTER_VERSION,
        provider_request_id=request_id,
        turn_id=_optional_str(envelope.get("uuid")) or request_id,
        turn_timestamp=event_timestamp or None,
        cwd=_optional_str(envelope.get("cwd")),
        model=_optional_str(message.get("model")),
        effort=None,
        current_date=None,
        timezone=None,
        thread_source="user",
        subagent_type=None,
        agent_role=None,
        agent_nickname=None,
        parent_session_id=None,
        parent_thread_name=None,
        parent_session_updated_at=None,
        model_context_window=None,
        cache_creation_input_tokens=cache_creation,
        input_tokens=input_tokens,
        cached_input_tokens=cache_read,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output,
        total_tokens=total_tokens,
        cumulative_input_tokens=cumulative["input_tokens"],
        cumulative_cached_input_tokens=cumulative["cached_input_tokens"],
        cumulative_output_tokens=cumulative["output_tokens"],
        cumulative_reasoning_output_tokens=cumulative["reasoning_output_tokens"],
        cumulative_total_tokens=cumulative["total_tokens"],
    )


def _record_id(session_id: str, request_id: str | None, timestamp: str, line_number: int) -> str:
    raw = "|".join(["claude-code", session_id, request_id or "", timestamp, str(line_number)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _usage_int(values: dict[str, Any], key: str, *, default: int | None = None) -> int:
    if key not in values or values.get(key) is None:
        if default is not None:
            return default
        raise ValueError(f"missing usage field: {key}")
    return _strict_int(values.get(key))


def _strict_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError(f"invalid integer value: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    raise ValueError(f"invalid integer value: {value!r}")


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _increment_stat(stats: MutableMapping[str, int] | None, key: str) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + 1
```

Update `src/codex_usage_tracker/adapters/__init__.py`:

```python
from codex_usage_tracker.adapters.claude_code_jsonl import ClaudeCodeJsonlAdapter
```

and add `"ClaudeCodeJsonlAdapter"` to `__all__`.

- [ ] **Step 4: Run Claude adapter tests**

Run:

```bash
python -m pytest tests/test_claude_adapter.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/codex_usage_tracker/adapters tests/test_claude_adapter.py
git commit -m "feat: parse Claude Code usage logs"
```

## Task 4: Multi-Source Refresh And Metadata

**Files:**
- Modify: `src/codex_usage_tracker/models.py`
- Modify: `src/codex_usage_tracker/paths.py`
- Modify: `src/codex_usage_tracker/store.py`
- Modify: `src/codex_usage_tracker/api_payloads.py`
- Modify: `tests/test_store_dashboard_mcp.py`
- Modify: `tests/test_cli_lifecycle.py`

- [ ] **Step 1: Write failing mixed refresh tests**

In `tests/test_store_dashboard_mcp.py`, import `DEFAULT_CLAUDE_HOME` only if needed by the test. Add:

```python
def test_refresh_all_indexes_codex_and_claude_sources(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    claude_home = _make_claude_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    result = refresh_usage_index(
        codex_home=codex_home,
        claude_home=claude_home,
        db_path=db_path,
        source="all",
    )
    second = refresh_usage_index(
        codex_home=codex_home,
        claude_home=claude_home,
        db_path=db_path,
        source="all",
    )
    rows = query_dashboard_events(db_path=db_path, limit=0, include_archived=True)

    assert result.source_results["codex"]["parsed_events"] == 4
    assert result.source_results["claude-code"]["parsed_events"] == 2
    assert result.parsed_events == 6
    assert second.inserted_or_updated_events == 6
    assert {row["source_app"] for row in rows} == {"codex", "claude-code"}
```

Add the helper below `_make_codex_home`:

```python
def _make_claude_home(tmp_path: Path) -> Path:
    claude_home = tmp_path / ".claude"
    log_path = claude_home / "projects" / "project-a" / "session.jsonl"
    log_path.parent.mkdir(parents=True)
    rows = [
        {
            "type": "assistant",
            "timestamp": "2026-06-08T12:00:00.000Z",
            "sessionId": "claude-session-1",
            "cwd": "/tmp/claude-project",
            "message": {
                "id": "msg-001",
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "usage": {
                    "input_tokens": 100,
                    "cache_creation_input_tokens": 20,
                    "cache_read_input_tokens": 50,
                    "output_tokens": 30,
                },
                "content": [{"type": "text", "text": "SECRET CLAUDE TEXT"}],
            },
        },
        {
            "type": "assistant",
            "timestamp": "2026-06-08T12:05:00.000Z",
            "sessionId": "claude-session-1",
            "cwd": "/tmp/claude-project",
            "message": {
                "id": "msg-002",
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 40, "cache_read_input_tokens": 10, "output_tokens": 60},
            },
        },
    ]
    log_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return claude_home
```

- [ ] **Step 2: Run failing mixed refresh test**

Run:

```bash
python -m pytest tests/test_store_dashboard_mcp.py::test_refresh_all_indexes_codex_and_claude_sources -v
```

Expected: FAIL because `refresh_usage_index()` has no `claude_home` or `source` parameters.

- [ ] **Step 3: Add source result model and default path**

Modify `src/codex_usage_tracker/models.py`:

```python
@dataclass(frozen=True)
class RefreshResult:
    scanned_files: int
    parsed_events: int
    inserted_or_updated_events: int
    db_path: str
    skipped_events: int = 0
    parser_diagnostics: dict[str, int] = field(default_factory=dict)
    source_results: dict[str, dict[str, object]] = field(default_factory=dict)
```

Modify `src/codex_usage_tracker/paths.py`:

```python
DEFAULT_CLAUDE_HOME = Path.home() / ".claude"
```

- [ ] **Step 4: Implement source adapter selection in store**

In `src/codex_usage_tracker/store.py`, import source constants and adapters:

```python
from codex_usage_tracker.adapters.base import SOURCE_ALL, SOURCE_CHOICES, SOURCE_CLAUDE_CODE, SOURCE_CODEX
from codex_usage_tracker.adapters.claude_code_jsonl import ClaudeCodeJsonlAdapter, compact_claude_diagnostics
from codex_usage_tracker.adapters.codex_jsonl import CodexJsonlAdapter
from codex_usage_tracker.paths import DEFAULT_CLAUDE_HOME
```

Add:

```python
def _adapters_for_source(source: str) -> list[tuple[str, object]]:
    if source not in SOURCE_CHOICES:
        raise ValueError(f"source must be one of: {', '.join(SOURCE_CHOICES)}")
    adapters = {
        SOURCE_CODEX: CodexJsonlAdapter(),
        SOURCE_CLAUDE_CODE: ClaudeCodeJsonlAdapter(),
    }
    if source == SOURCE_ALL:
        return [(SOURCE_CODEX, adapters[SOURCE_CODEX]), (SOURCE_CLAUDE_CODE, adapters[SOURCE_CLAUDE_CODE])]
    return [(source, adapters[source])]


def _root_for_source(source_name: str, *, codex_home: Path, claude_home: Path) -> Path:
    if source_name == SOURCE_CLAUDE_CODE:
        return claude_home
    return codex_home
```

Update `refresh_usage_index()` signature:

```python
def refresh_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    *,
    claude_home: Path = DEFAULT_CLAUDE_HOME,
    source: str = SOURCE_CODEX,
) -> RefreshResult:
```

Replace the body with adapter iteration:

```python
    all_events: list[UsageEvent] = []
    source_results: dict[str, dict[str, object]] = {}
    combined_stats: dict[str, int] = {}
    scanned_files = 0
    skipped_events = 0
    for source_name, adapter in _adapters_for_source(source):
        root = _root_for_source(source_name, codex_home=codex_home, claude_home=claude_home)
        logs = adapter.discover_logs(root, include_archived=include_archived)
        session_index = adapter.load_session_index(root)
        stats: dict[str, int] = {}
        events = []
        for log_path in logs:
            events.extend(adapter.parse_file(log_path, session_index=session_index, stats=stats))
        diagnostics = (
            compact_claude_diagnostics(stats)
            if source_name == SOURCE_CLAUDE_CODE
            else compact_parser_diagnostics(stats)
        )
        source_results[source_name] = {
            "source_provider": adapter.source_provider,
            "source_app": adapter.source_app,
            "source_format": adapter.source_format,
            "scanned_files": len(logs),
            "parsed_events": len(events),
            "skipped_events": int(stats.get("skipped_events", 0)),
            "parser_diagnostics": diagnostics,
        }
        scanned_files += len(logs)
        skipped_events += int(stats.get("skipped_events", 0))
        for key, value in diagnostics.items():
            combined_stats[key] = combined_stats.get(key, 0) + int(value)
        all_events.extend(events)
    inserted = upsert_usage_events(all_events, db_path=db_path)
    diagnostics = compact_parser_diagnostics(combined_stats)
```

Keep the existing `record_refresh_metadata(...)` call, passing `source=source` and `source_results=source_results`. Return:

```python
    return RefreshResult(
        scanned_files=scanned_files,
        parsed_events=len(all_events),
        inserted_or_updated_events=inserted,
        db_path=str(db_path),
        skipped_events=skipped_events,
        parser_diagnostics=diagnostics,
        source_results=source_results,
    )
```

Extend `record_refresh_metadata()` to accept `source` and `source_results` and write:

```python
        "source": source,
        "source_results": json.dumps(source_results, sort_keys=True),
```

Import `json` at the top of `store.py`.

Update `rebuild_usage_index()` with the same `claude_home` and `source` keyword parameters and pass them through to `refresh_usage_index()`.

- [ ] **Step 5: Include source results in refresh JSON payloads**

Modify `src/codex_usage_tracker/api_payloads.py`:

```python
        "source_results": getattr(result, "source_results", {}),
```

Add this field to `REFRESH_RESULT_FIELDS` in `src/codex_usage_tracker/json_contracts.py`:

```python
    "source_results": dict,
```

- [ ] **Step 6: Run mixed refresh tests**

Run:

```bash
python -m pytest tests/test_store_dashboard_mcp.py::test_refresh_all_indexes_codex_and_claude_sources tests/test_store_dashboard_mcp.py::test_refresh_is_idempotent_and_summary_works tests/test_json_contracts.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/codex_usage_tracker/models.py src/codex_usage_tracker/paths.py src/codex_usage_tracker/store.py src/codex_usage_tracker/api_payloads.py src/codex_usage_tracker/json_contracts.py tests/test_store_dashboard_mcp.py tests/test_json_contracts.py
git commit -m "feat: refresh usage from multiple sources"
```

## Task 5: CLI And MCP Source Options

**Files:**
- Modify: `src/codex_usage_tracker/cli.py`
- Modify: `src/codex_usage_tracker/mcp_server.py`
- Modify: `src/codex_usage_tracker/server.py`
- Modify: `tests/test_cli_lifecycle.py`
- Modify: `tests/test_store_dashboard_mcp.py`

- [ ] **Step 1: Write failing CLI test for Claude source**

In `tests/test_cli_lifecycle.py`, add:

```python
def test_refresh_cli_accepts_claude_source(tmp_path: Path) -> None:
    claude_home = _make_claude_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    result = _run_cli(
        [
            "--db",
            str(db_path),
            "refresh",
            "--source",
            "claude-code",
            "--claude-home",
            str(claude_home),
            "--json",
        ],
        tmp_path=tmp_path,
    )
    payload = json.loads(result.stdout)

    assert payload["schema"] == "codex-usage-tracker-refresh-v1"
    assert payload["parsed_events"] == 2
    assert payload["source_results"]["claude-code"]["source_provider"] == "anthropic"
```

Copy the `_make_claude_home()` helper from Task 4 into this test file.

- [ ] **Step 2: Run failing CLI test**

Run:

```bash
python -m pytest tests/test_cli_lifecycle.py::test_refresh_cli_accepts_claude_source -v
```

Expected: FAIL because CLI lacks `--source` and `--claude-home`.

- [ ] **Step 3: Wire CLI source args**

In `src/codex_usage_tracker/cli.py`, import:

```python
from codex_usage_tracker.adapters.base import SOURCE_CHOICES, SOURCE_CODEX
from codex_usage_tracker.paths import DEFAULT_CLAUDE_HOME
```

Add to `_add_refresh_parser()`, `_add_rebuild_index_parser()`, `open-dashboard`, and `serve-dashboard`:

```python
    refresh.add_argument("--source", choices=SOURCE_CHOICES, default=SOURCE_CODEX)
    refresh.add_argument("--claude-home", type=Path, default=DEFAULT_CLAUDE_HOME)
```

Use the relevant parser variable name in each function.

Update `_run_refresh()`:

```python
    result = refresh_usage_index(
        codex_home=args.codex_home,
        claude_home=args.claude_home,
        db_path=args.db,
        include_archived=args.include_archived,
        source=args.source,
    )
```

Apply the same pass-through to `_run_rebuild_index()`, `_run_open_dashboard()` refresh branch, and `_run_serve_dashboard()` refresh branch and `serve_dashboard(...)` call.

- [ ] **Step 4: Wire server refresh source**

In `src/codex_usage_tracker/server.py`, add parameters:

```python
    claude_home: Path = DEFAULT_CLAUDE_HOME,
    source: str = SOURCE_CODEX,
```

Store them on `_UsageDashboardHandler`:

```python
        self._claude_home = claude_home
        self._source = source
```

Update `/api/usage` refresh:

```python
                    result = refresh_usage_index(
                        codex_home=self._codex_home,
                        claude_home=self._claude_home,
                        db_path=self._db_path,
                        include_archived=include_archived,
                        source=self._source,
                    )
```

- [ ] **Step 5: Wire MCP refresh source**

Modify `mcp_server.refresh_usage_index()`:

```python
def refresh_usage_index(source: str = "codex", include_archived: bool = False) -> dict[str, Any]:
    """Scan local usage logs and upsert aggregate usage metrics into SQLite."""

    result = refresh_index(
        codex_home=DEFAULT_CODEX_HOME,
        claude_home=DEFAULT_CLAUDE_HOME,
        db_path=DEFAULT_DB_PATH,
        include_archived=include_archived,
        source=source,
    )
    return refresh_result_payload(result, schema="codex-usage-tracker-refresh-v1")
```

Import `DEFAULT_CLAUDE_HOME`.

- [ ] **Step 6: Run CLI and MCP smoke tests**

Run:

```bash
python -m pytest tests/test_cli_lifecycle.py::test_refresh_cli_accepts_claude_source tests/test_store_dashboard_mcp.py::test_mcp_wrappers_smoke -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/codex_usage_tracker/cli.py src/codex_usage_tracker/mcp_server.py src/codex_usage_tracker/server.py tests/test_cli_lifecycle.py tests/test_store_dashboard_mcp.py
git commit -m "feat: expose usage source selection"
```

## Task 6: Provider/App Query, Summary, CSV, And Contracts

**Files:**
- Modify: `src/codex_usage_tracker/store.py`
- Modify: `src/codex_usage_tracker/reports.py`
- Modify: `src/codex_usage_tracker/cli.py`
- Modify: `src/codex_usage_tracker/mcp_server.py`
- Modify: `src/codex_usage_tracker/json_contracts.py`
- Modify: `tests/test_store_dashboard_mcp.py`
- Modify: `tests/test_cli_lifecycle.py`
- Modify: `tests/test_json_contracts.py`

- [ ] **Step 1: Write failing provider/app query tests**

In `tests/test_store_dashboard_mcp.py`, add to the mixed refresh test or a new test:

```python
def test_provider_and_app_filters_work_for_dashboard_queries(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    claude_home = _make_claude_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, claude_home=claude_home, db_path=db_path, source="all")

    anthropic_rows = query_dashboard_events(db_path=db_path, limit=0, source_provider="anthropic")
    claude_rows = query_dashboard_events(db_path=db_path, limit=0, source_app="claude-code")
    app_summary = query_summary(db_path=db_path, group_by="source_app")

    assert len(anthropic_rows) == 2
    assert len(claude_rows) == 2
    assert {row["group_key"] for row in app_summary} == {"codex", "claude-code"}
```

In `tests/test_json_contracts.py`, add provider/app filters to the query payload fixture:

```python
            "source_provider": "anthropic",
            "source_app": "claude-code",
```

- [ ] **Step 2: Run failing query tests**

Run:

```bash
python -m pytest tests/test_store_dashboard_mcp.py::test_provider_and_app_filters_work_for_dashboard_queries tests/test_json_contracts.py -v
```

Expected: FAIL because query functions and JSON contracts do not know source filters.

- [ ] **Step 3: Add SQL group and filters**

Modify `_group_expression()` in `src/codex_usage_tracker/store.py`:

```python
        "source_provider": "coalesce(source_provider, 'unknown provider')",
        "source_app": "coalesce(source_app, 'unknown app')",
```

Add parameters to `query_dashboard_events()`, `query_dashboard_event_count()`, and `_usage_where_clause()`:

```python
    source_provider: str | None = None,
    source_app: str | None = None,
```

In `_usage_where_clause()`:

```python
    if source_provider:
        clauses.append(f"{prefix}source_provider = ?")
        params.append(source_provider)
    if source_app:
        clauses.append(f"{prefix}source_app = ?")
        params.append(source_app)
```

Pass these through from caller functions.

- [ ] **Step 4: Add report and CLI query fields**

In `reports.py`, extend choices:

```python
SUMMARY_GROUP_BY_CHOICES = (
    "date",
    "source_provider",
    "source_app",
    ...
)
```

Add `source_provider` and `source_app` parameters to `build_query_report()` and `build_recommendations_report()`. Include them in filters and `_query_row_matches()`.

In `cli.py`, add to `_add_query_parser()` and `_add_recommendations_parser()`:

```python
    query.add_argument("--source-provider")
    query.add_argument("--source-app")
```

Pass args into report builders.

In `mcp_server.py`, add the same optional arguments to `usage_query()` and `usage_recommendations()`.

- [ ] **Step 5: Update JSON contracts**

In `src/codex_usage_tracker/json_contracts.py`, add to query and recommendation nested filters:

```python
                "source_provider": (str, NoneType),
                "source_app": (str, NoneType),
```

- [ ] **Step 6: Run query/report tests**

Run:

```bash
python -m pytest tests/test_store_dashboard_mcp.py::test_provider_and_app_filters_work_for_dashboard_queries tests/test_cli_lifecycle.py tests/test_json_contracts.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/codex_usage_tracker/store.py src/codex_usage_tracker/reports.py src/codex_usage_tracker/cli.py src/codex_usage_tracker/mcp_server.py src/codex_usage_tracker/json_contracts.py tests/test_store_dashboard_mcp.py tests/test_cli_lifecycle.py tests/test_json_contracts.py
git commit -m "feat: filter usage by source"
```

## Task 7: Codex-Only Credit Annotation

**Files:**
- Modify: `src/codex_usage_tracker/allowance.py`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`
- Modify: `tests/test_allowance.py`
- Modify: `tests/test_store_dashboard_mcp.py`

- [ ] **Step 1: Write failing non-Codex credit test**

In `tests/test_allowance.py`, add:

```python
def test_allowance_does_not_apply_codex_credits_to_claude_rows() -> None:
    config = load_allowance_config(Path("missing-allowance.json"))
    rows = [
        {
            "source_provider": "anthropic",
            "source_app": "claude-code",
            "model": "gpt-5.3-codex",
            "input_tokens": 100,
            "cached_input_tokens": 0,
            "uncached_input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        }
    ]

    annotated = annotate_rows_with_allowance(rows, config)

    assert annotated[0]["usage_credits"] is None
    assert annotated[0]["usage_credit_confidence"] == "not_applicable"
    assert "only apply to Codex" in annotated[0]["usage_credit_note"]
```

- [ ] **Step 2: Run failing allowance test**

Run:

```bash
python -m pytest tests/test_allowance.py::test_allowance_does_not_apply_codex_credits_to_claude_rows -v
```

Expected: FAIL because Claude rows can still match a Codex model label.

- [ ] **Step 3: Add Codex row guard**

In `allowance.py`, add:

```python
def _row_supports_codex_credits(row: dict[str, Any]) -> bool:
    source_app = row.get("source_app")
    source_provider = row.get("source_provider")
    if source_app is None and source_provider is None:
        return True
    return source_provider == "openai" and source_app == "codex"
```

At the start of the `for row in rows:` loop in `annotate_rows_with_allowance()`:

```python
        if not _row_supports_codex_credits(copy):
            copy.update(
                {
                    "usage_credits": None,
                    "usage_credit_model": None,
                    "usage_credit_confidence": "not_applicable",
                    "usage_credit_source": "Codex credit rates",
                    "usage_credit_source_url": None,
                    "usage_credit_fetched_at": None,
                    "usage_credit_tier": None,
                    "usage_credit_note": "Codex credit rates only apply to Codex rows.",
                }
            )
            annotated.append(copy)
            continue
```

- [ ] **Step 4: Update dashboard credit labels**

In `dashboard_data.js`, update `usageCreditStatus(row)`:

```javascript
    if (row.usage_credit_confidence === 'not_applicable') return 'Not applicable';
```

In `dashboard.js`, update credit-missing matching:

```javascript
          || (pricingStatus === 'credit-missing' && row.usage_credit_confidence === 'unpriced');
```

Do not include `not_applicable` in missing credit filters.

- [ ] **Step 5: Run allowance and dashboard aggregate tests**

Run:

```bash
python -m pytest tests/test_allowance.py tests/test_store_dashboard_mcp.py::test_dashboard_and_csv_are_aggregate_only -v
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/codex_usage_tracker/allowance.py src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js src/codex_usage_tracker/plugin_data/dashboard/dashboard.js tests/test_allowance.py tests/test_store_dashboard_mcp.py
git commit -m "fix: limit Codex credits to Codex rows"
```

## Task 8: Dashboard Provider/App UI

**Files:**
- Modify: `src/codex_usage_tracker/dashboard.py`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/dashboard_template.html`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`
- Modify: `tests/test_store_dashboard_mcp.py`

- [ ] **Step 1: Write failing dashboard assertions**

In `tests/test_store_dashboard_mcp.py::test_dashboard_and_csv_are_aggregate_only`, add:

```python
    assert "AI Usage Dashboard" in dashboard
    assert "source_provider" in dashboard
    assert "source_app" in dashboard
    assert "Source" in dashboard
    assert "providerEl" in dashboard_js
    assert "appEl" in dashboard_js
    assert "source_app" in csv_text
    assert "cache_creation_input_tokens" in csv_text
```

- [ ] **Step 2: Run failing dashboard test**

Run:

```bash
python -m pytest tests/test_store_dashboard_mcp.py::test_dashboard_and_csv_are_aggregate_only -v
```

Expected: FAIL because dashboard and CSV do not yet expose source fields everywhere the test expects.

- [ ] **Step 3: Update dashboard title payload**

In `dashboard.py`, change the HTML title replacement:

```python
        template.replace("__TITLE__", html.escape("AI Usage Dashboard"))
```

- [ ] **Step 4: Add provider/app controls to template**

In `dashboard_template.html`, update search placeholder:

```html
<label>Search<input id="search" type="search" placeholder="Thread, cwd, model, source"></label>
```

Add filters after Model:

```html
<label>Provider<select id="sourceProvider"><option value="">All providers</option></select></label>
<label>App<select id="sourceApp"><option value="">All apps</option></select></label>
```

Add a Source column before Model:

```html
<th data-sort-header="source"><button class="sort-header" type="button" data-sort-key="source">Source <span class="sort-indicator" data-sort-indicator="source"></span></button></th>
```

- [ ] **Step 5: Add URL state fields**

In `dashboard_state.js`, include:

```javascript
      sourceProvider: clean(params.get('provider')),
      sourceApp: clean(params.get('app')),
```

When writing params:

```javascript
    setParam(params, 'provider', state.sourceProvider);
    setParam(params, 'app', state.sourceApp);
```

- [ ] **Step 6: Add dashboard data helpers**

In `dashboard_data.js`, add:

```javascript
  function usageSourceLabel(row) {
    return [row.source_app, row.source_provider].filter(Boolean).join(' / ') || 'unknown source';
  }
```

Export `usageSourceLabel` in `window.CodexUsageDashboardData`.

- [ ] **Step 7: Wire dashboard filtering and rendering**

In `dashboard.js`, add elements:

```javascript
    const providerEl = document.getElementById('sourceProvider');
    const appEl = document.getElementById('sourceApp');
```

In initial control setup:

```javascript
      rebuildSelectOptions(providerEl, data.map(row => row.source_provider), 'All providers');
      rebuildSelectOptions(appEl, data.map(row => row.source_app), 'All apps');
      if (optionValueExists(providerEl, initialState.sourceProvider)) providerEl.value = initialState.sourceProvider;
      if (optionValueExists(appEl, initialState.sourceApp)) appEl.value = initialState.sourceApp;
```

In `filtered()`:

```javascript
      const sourceProvider = providerEl.value;
      const sourceApp = appEl.value;
```

Add source fields to haystack:

```javascript
          row.source_provider,
          row.source_app,
          row.source_format,
```

Add source match to the return expression:

```javascript
          && (!sourceProvider || row.source_provider === sourceProvider)
          && (!sourceApp || row.source_app === sourceApp)
```

In `currentDashboardState()`:

```javascript
        sourceProvider: providerEl.value,
        sourceApp: appEl.value,
```

In `renderCalls()`, add a Source cell before Model:

```javascript
          <td><span class="pill" data-full-label="${escapeHtml(short(usageSourceLabel(row)))}">${escapeHtml(short(usageSourceLabel(row)))}</span></td>
```

Add `source` sort handling:

```javascript
      if (key === 'source') return textValue(usageSourceLabel(row));
```

In `exportCurrentRows()`, add fields:

```javascript
        { label: 'source_provider', field: 'source_provider' },
        { label: 'source_app', field: 'source_app' },
        { label: 'source_format', field: 'source_format' },
        { label: 'provider_request_id', field: 'provider_request_id' },
        { label: 'cache_creation_input_tokens', field: 'cache_creation_input_tokens' },
```

In call detail primary or raw identifiers, add:

```javascript
              ['Source app', row.source_app || 'Unknown'],
              ['Source provider', row.source_provider || 'Unknown'],
              ['Source format', row.source_format || 'Unknown'],
              ['Provider request id', row.provider_request_id || 'None'],
              ['Cache creation input', tokens(row.cache_creation_input_tokens || 0)],
```

Add provider/app elements to event listener list:

```javascript
    [searchEl, modelEl, providerEl, appEl, effortEl, pricingStatusEl].forEach(el => el.addEventListener('input', () => {
```

- [ ] **Step 8: Run dashboard tests and JS checks**

Run:

```bash
python -m pytest tests/test_store_dashboard_mcp.py::test_dashboard_and_csv_are_aggregate_only -v
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_format.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/codex_usage_tracker/dashboard.py src/codex_usage_tracker/plugin_data/dashboard/dashboard_template.html src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js src/codex_usage_tracker/plugin_data/dashboard/dashboard.js tests/test_store_dashboard_mcp.py
git commit -m "feat: show usage source in dashboard"
```

## Task 9: Docs And Skill Copy Updates

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/architecture.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `docs/cli-reference.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `docs/privacy.md`
- Modify: `docs/development.md`
- Modify: `skills/codex-usage-tracker/SKILL.md`
- Modify: `skills/codex-usage-api/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md`
- Modify: `tests/test_cli_release.py`

- [ ] **Step 1: Write failing docs release expectations**

In `tests/test_cli_release.py`, update command references so `refresh --source claude-code --claude-home` is considered documented. Add a test:

```python
def test_docs_mention_claude_source_support() -> None:
    docs = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            Path("docs/cli-reference.md").read_text(encoding="utf-8"),
            Path("docs/privacy.md").read_text(encoding="utf-8"),
        ]
    )

    assert "AI Usage Tracker" in docs
    assert "--source claude-code" in docs
    assert "~/.claude/projects" in docs
    assert "Claude Code" in docs
```

- [ ] **Step 2: Run failing docs test**

Run:

```bash
python -m pytest tests/test_cli_release.py::test_docs_mention_claude_source_support -v
```

Expected: FAIL because docs still describe only Codex.

- [ ] **Step 3: Update user-facing docs**

Make these exact content changes:

In `README.md`, change the opening description to:

```markdown
Local-first dashboard, Codex plugin, and companion skill for understanding where your AI coding-agent tokens and usage credits are going.
```

Add a section under Platform Support:

```markdown
## Source Support

The tracker is evolving into AI Usage Tracker. The current CLI and package name remain `codex-usage-tracker` for compatibility.

- Codex: default source, read from `~/.codex/sessions`.
- Claude Code: opt-in source, read from `~/.claude/projects`.

Use `codex-usage-tracker refresh --source all` to index both supported sources, or `codex-usage-tracker refresh --source claude-code --claude-home ~/.claude` for Claude Code only.
```

In `docs/cli-reference.md`, document:

```markdown
codex-usage-tracker refresh --source claude-code --claude-home ~/.claude
codex-usage-tracker refresh --source all
codex-usage-tracker query --source-app claude-code
codex-usage-tracker summary --group-by source_app
```

In `docs/privacy.md`, add:

```markdown
Claude Code support follows the same aggregate-only rule. The indexer reads local JSONL files under `~/.claude/projects`, extracts usage counters and metadata-like identifiers, and does not persist prompts, assistant text, or tool output.
```

In `docs/architecture.md`, add the adapter boundary and new adapter files from the design spec.

Update both source and bundled skill files with matching language when they mention Codex-only usage. Keep Codex-specific setup instructions for plugin installation.

- [ ] **Step 4: Run docs checks**

Run:

```bash
python -m pytest tests/test_cli_release.py -v
python scripts/check_release.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md docs/architecture.md docs/dashboard-guide.md docs/cli-reference.md docs/cli-json-schemas.md docs/privacy.md docs/development.md skills/codex-usage-tracker/SKILL.md skills/codex-usage-api/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md tests/test_cli_release.py
git commit -m "docs: describe AI usage sources"
```

## Task 10: Final Verification And Release Gate

**Files:**
- No planned source edits.

- [ ] **Step 1: Run focused Python tests**

Run:

```bash
python -m pytest tests/test_schema.py tests/test_parser.py tests/test_claude_adapter.py tests/test_store_dashboard_mcp.py tests/test_cli_lifecycle.py tests/test_json_contracts.py tests/test_allowance.py -v
```

Expected: PASS.

- [ ] **Step 2: Run static Python checks**

Run:

```bash
python -m ruff check .
python -m mypy
python -m compileall src
```

Expected: all commands exit 0.

- [ ] **Step 3: Run dashboard syntax checks**

Run:

```bash
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_format.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js
```

Expected: all commands exit 0.

- [ ] **Step 4: Run release checks**

Run:

```bash
python scripts/check_release.py
git diff --check
python -m build
python scripts/check_release.py --dist
```

Expected: all commands exit 0.

- [ ] **Step 5: Run CLI smokes on synthetic temp data**

Run with temporary output paths valid for the platform:

```bash
codex-usage-tracker refresh --source codex --json
codex-usage-tracker summary --group-by source_app --json
codex-usage-tracker query --source-app codex --limit 5
codex-usage-tracker dashboard --output /tmp/ai-usage-dashboard.html --json
codex-usage-tracker pricing-coverage --json
```

Expected: commands exit 0. If the installed `codex-usage-tracker` command points at an older package, use `python -m codex_usage_tracker` from the checkout and note that in the completion report.

- [ ] **Step 6: Commit any verification-only doc fixes**

If release checks require documentation or package-data fixes, commit those fixes:

```bash
git add README.md AGENTS.md docs/architecture.md docs/dashboard-guide.md docs/cli-reference.md docs/cli-json-schemas.md docs/privacy.md docs/development.md pyproject.toml MANIFEST.in scripts/check_release.py
git commit -m "chore: satisfy release checks"
```

Skip this step when there are no verification-driven changes.

## Self-Review Checklist

- Spec coverage: Tasks 1-8 implement provider fields, adapters, Claude JSONL parsing, source refresh, filters, dashboard visibility, and Codex-only credits. Task 9 covers docs and skill copies. Task 10 covers verification.
- Privacy coverage: Claude tests include raw text that must not appear in aggregate rows; dashboard and CSV aggregate-only tests remain part of the plan.
- Compatibility coverage: Codex default refresh remains source `codex`; parser facade keeps existing `parser.py` imports; CLI/package names stay unchanged.
- Pricing coverage: First slice keeps OpenAI `update-pricing`; Claude rows use manual pricing only through existing `pricing.json`.
