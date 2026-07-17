# OTel Fast Usage Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich canonical Codex usage calls with exact Fast-versus-Standard service-tier metadata from the local OTLP completion stream and apply confirmed Fast multipliers to ChatGPT credit estimates.

**Architecture:** Session JSONL remains authoritative for usage calls and token totals. A pure parser converts allowlisted OTLP completion attributes into aggregate records, a persistent sidecar ingests them incrementally, and a conservative reconciler enriches one canonical usage group only when conversation and token identity are unique. Pricing and dashboard layers consume the additive tier fields while USD token estimates remain unchanged.

**Tech Stack:** Python 3.10+, dataclasses, SQLite, pytest, TypeScript, React, Vitest, existing Vite dashboard build.

## Global Constraints

- Persist only `conversation.id`, four token counters, model, effort, service tier, app version, timestamp, source path/line, fingerprint, and match state from OTLP.
- Never persist or expose OTLP bodies, arbitrary attributes, resource attributes, prompts, account data, tool content, trace IDs, or span IDs.
- Treat timestamp as a fingerprint and diagnostic field only; never use timestamp proximity for correlation.
- Enrich only when conversation ID and all four token counters match and candidates resolve to exactly one canonical usage group.
- Normalize explicit `priority` or `fast` as confirmed Fast; explicit `default` or `standard` as confirmed Standard.
- Treat omitted tier as protocol-confirmed Standard only for parseable `app.version >= 0.143.0`; older or unparseable omissions remain unknown.
- Preserve session JSONL as the canonical source of call identity and token totals.
- Apply Fast credit multipliers only to confirmed Fast calls: GPT-5.6 `2.5`, GPT-5.5 `2.5`, GPT-5.4 `2.0`.
- Do not change USD token-cost estimates from service-tier enrichment.
- Keep committed fixtures entirely synthetic and keep aggregate-only default output behavior.

---

## File structure

- `src/codex_usage_tracker/parser/otel.py`: pure OTLP traversal, allowlisted value coercion, version-aware tier normalization, and semantic fingerprinting.
- `src/codex_usage_tracker/store/otel_schema.py`: schema version 30 sidecar tables and indexes.
- `src/codex_usage_tracker/store/otel_ingest.py`: deterministic discovery, cursor handling, complete-line reads, and normalized staging upserts.
- `src/codex_usage_tracker/store/otel_reconciliation.py`: unique canonical-group matching, clone propagation, conflict handling, and match reset.
- `src/codex_usage_tracker/pricing/fast_tier.py`: shared documented Fast multiplier policy and credit provenance.
- Existing core/store/refresh/report modules: additive usage columns, orchestration, rebuild semantics, metadata, and privacy-safe support coverage.
- Existing React source: typed tier decoding, exact/proxy distinction, Calls column, detail labels, and CSV fields.
- `tests/otel_helpers.py`: synthetic UsageEvent, session JSONL, and OTLP factories shared by focused tests.
- Focused parser/store/pricing/dashboard tests: synthetic OTLP batches and databases only.

### Task 1: Add the aggregate tier schema and persistent sidecar tables

**Files:**
- Modify: `src/codex_usage_tracker/core/paths.py`
- Modify: `src/codex_usage_tracker/core/models.py`
- Modify: `src/codex_usage_tracker/core/schema.py`
- Create: `src/codex_usage_tracker/store/otel_schema.py`
- Modify: `src/codex_usage_tracker/store/schema.py`
- Test: `tests/core/test_schema.py`
- Create: `tests/store/test_otel_schema.py`
- Modify: `tests/store/test_store_migrations.py`

**Interfaces:**
- Produces: `DEFAULT_OTEL_COMPLETIONS_DIR: Path`.
- Produces: nullable `UsageEvent.service_tier`, `fast`, `service_tier_source`, and `service_tier_confidence` fields.
- Produces: `otel_completion_sources` and `otel_completion_events` tables through schema migration 30.
- Consumes: existing `UsageColumn`, migration recording, and repair-column behavior.

- [ ] **Step 1: Write failing schema-shape and migration tests**

```python
def test_usage_event_schema_includes_nullable_service_tier_fields() -> None:
    row = usage_event_fixture().to_row()
    assert row["service_tier"] is None
    assert row["fast"] is None
    assert row["service_tier_source"] is None
    assert row["service_tier_confidence"] is None


def test_schema_migration_creates_otel_sidecar_tables(tmp_path: Path) -> None:
    with connect(tmp_path / "usage.sqlite3") as conn:
        init_db(conn)
        source_columns = {
            str(row["name"]) for row in conn.execute("PRAGMA table_info(otel_completion_sources)")
        }
        event_columns = {
            str(row["name"]) for row in conn.execute("PRAGMA table_info(otel_completion_events)")
        }
    assert {"source_path", "device", "inode", "size", "parsed_offset", "parsed_line"} <= source_columns
    assert {"fingerprint", "conversation_id", "service_tier", "fast", "match_status"} <= event_columns


def test_legacy_migration_exports_unknown_tier_fields_as_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    csv_path = tmp_path / "usage.csv"
    _write_legacy_usage_database(db_path)
    export_usage_csv(csv_path, db_path=db_path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["service_tier"] == ""
    assert row["fast"] == ""
    assert row["service_tier_source"] == ""
    assert row["service_tier_confidence"] == ""
```

- [ ] **Step 2: Run the focused tests and verify the missing fields/tables fail**

Run: `.venv/bin/python -m pytest tests/core/test_schema.py tests/store/test_otel_schema.py -q`

Expected: FAIL because the four `UsageEvent` fields and OTel sidecar tables do not exist.

- [ ] **Step 3: Add the paths, nullable columns, and migration**

```python
# core/paths.py
DEFAULT_OTEL_COMPLETIONS_DIR = APP_DIR / "otel"

# core/models.py, after duplicate_reason
service_tier: str | None = None
fast: int | None = None
service_tier_source: str | None = None
service_tier_confidence: str | None = None

# core/schema.py, before derived numeric columns
UsageColumn("service_tier", "TEXT", "TEXT", repairable=True),
UsageColumn("fast", "INTEGER", "INTEGER", repairable=True),
UsageColumn("service_tier_source", "TEXT", "TEXT", repairable=True),
UsageColumn("service_tier_confidence", "TEXT", "TEXT", repairable=True),
```

Create `store/otel_schema.py` with one idempotent migration:

```python
MIGRATION_NAMES = {30: "persist OTel completion tier enrichment"}

OTEL_MATCH_STATUSES = ("pending", "matched", "ambiguous", "conflict", "invalid")


def migrate_otel_completion_tiers(conn: sqlite3.Connection) -> None:
    existing_usage_columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(usage_events)")
    }
    for column, column_type in {
        "service_tier": "TEXT",
        "fast": "INTEGER",
        "service_tier_source": "TEXT",
        "service_tier_confidence": "TEXT",
    }.items():
        if column not in existing_usage_columns:
            conn.execute(  # nosec B608 - fixed migration column names
                f"ALTER TABLE usage_events ADD COLUMN {column} {column_type}"
            )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS otel_completion_sources (
            source_path TEXT PRIMARY KEY,
            device INTEGER NOT NULL,
            inode INTEGER NOT NULL,
            size INTEGER NOT NULL,
            parsed_offset INTEGER NOT NULL,
            parsed_line INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS otel_completion_events (
            fingerprint TEXT PRIMARY KEY,
            conversation_id TEXT,
            event_timestamp TEXT,
            input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            reasoning_output_tokens INTEGER,
            model TEXT,
            effort TEXT,
            service_tier TEXT,
            fast INTEGER,
            service_tier_source TEXT,
            service_tier_confidence TEXT,
            app_version TEXT,
            source_path TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            match_status TEXT NOT NULL CHECK (
                match_status IN ('pending', 'matched', 'ambiguous', 'conflict', 'invalid')
            ),
            matched_record_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_otel_completion_match_status
            ON otel_completion_events(match_status);
        CREATE INDEX IF NOT EXISTS idx_otel_completion_identity
            ON otel_completion_events(
                conversation_id, input_tokens, cached_input_tokens,
                output_tokens, reasoning_output_tokens
            );
        """
    )
```

Set `SCHEMA_VERSION = 30`, merge `otel_schema.MIGRATION_NAMES`, and append `(30, otel_schema.migrate_otel_completion_tiers)` to `_schema_migrations()`.

- [ ] **Step 4: Run the focused schema tests and verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_schema.py tests/store/test_otel_schema.py tests/store/test_store_migrations.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the schema slice**

```bash
git add -- src/codex_usage_tracker/core/paths.py src/codex_usage_tracker/core/models.py src/codex_usage_tracker/core/schema.py src/codex_usage_tracker/store/otel_schema.py src/codex_usage_tracker/store/schema.py tests/core/test_schema.py tests/store/test_otel_schema.py tests/store/test_store_migrations.py
git commit -m "feat: add OTel completion tier schema"
```

### Task 2: Parse and normalize aggregate OTLP completions

**Files:**
- Create: `src/codex_usage_tracker/parser/otel.py`
- Modify: `src/codex_usage_tracker/parser/__init__.py`
- Create: `tests/otel_helpers.py`
- Create: `tests/parser/test_otel_parser.py`

**Interfaces:**
- Produces: `OtelCompletion` and `OtelParseResult` frozen dataclasses.
- Produces: `parse_otlp_json_line(raw: str) -> OtelParseResult`.
- Produces: `OTEL_DIAGNOSTIC_KEYS` for bounded refresh metadata.
- Consumes: one JSON line only; it never receives a database connection.

- [ ] **Step 1: Write failing parser tests for traversal, normalization, omission semantics, and privacy**

```python
def test_parse_otlp_batch_extracts_only_completion_allowlist() -> None:
    raw = synthetic_otlp_line(
        attributes={
            "event.name": "codex.sse_event",
            "event.kind": "response.completed",
            "conversation.id": "synthetic-conversation",
            "input_token_count": 120,
            "cached_token_count": 40,
            "output_token_count": 30,
            "reasoning_token_count": 10,
            "model": "gpt-5.6-sol",
            "model_reasoning_effort": "high",
            "service_tier": "priority",
            "app.version": "0.143.0",
            "secret.attribute": "must-not-survive",
        },
        body="synthetic private body that must not survive",
    )
    result = parse_otlp_json_line(raw)
    assert len(result.completions) == 1
    completion = result.completions[0]
    assert completion.service_tier == "fast"
    assert completion.fast == 1
    assert completion.service_tier_confidence == "exact"
    assert "private body" not in repr(completion)
    assert "secret.attribute" not in repr(completion)


@pytest.mark.parametrize(
    ("version", "tier", "fast", "confidence"),
    [("0.143.0", "standard", 0, "protocol"), ("0.142.9", None, None, None), ("bad", None, None, None)],
)
def test_missing_service_tier_uses_versioned_protocol_semantics(
    version: str,
    tier: str | None,
    fast: int | None,
    confidence: str | None,
) -> None:
    result = parse_otlp_json_line(
        synthetic_otlp_line(attributes=completion_attributes(app_version=version, service_tier=None))
    )
    completion = result.completions[0]
    assert (completion.service_tier, completion.fast, completion.service_tier_confidence) == (
        tier,
        fast,
        confidence,
    )
```

Add these concrete cases in the same test file:

```python
@pytest.mark.parametrize(
    ("raw_tier", "normalized_tier", "fast"),
    [
        ("fast", "fast", 1),
        ("default", "standard", 0),
        ("standard", "standard", 0),
        ("flex", "flex", 0),
    ],
)
def test_explicit_tier_aliases(raw_tier: str, normalized_tier: str, fast: int) -> None:
    attributes = completion_attributes(service_tier=raw_tier)
    completion = parse_otlp_json_line(synthetic_otlp_line(attributes=attributes)).completions[0]
    assert (completion.service_tier, completion.fast) == (normalized_tier, fast)


def test_multiple_resource_and_scope_groups_are_traversed() -> None:
    first = json.loads(synthetic_otlp_line(attributes=completion_attributes(conversation_id="a")))
    second = json.loads(synthetic_otlp_line(attributes=completion_attributes(conversation_id="b")))
    first["resourceLogs"].extend(second["resourceLogs"])
    result = parse_otlp_json_line(json.dumps(first))
    assert [item.conversation_id for item in result.completions] == ["a", "b"]


@pytest.mark.parametrize("raw", ["{", "[]", json.dumps({"resourceLogs": "bad"})])
def test_malformed_payloads_return_bounded_diagnostics(raw: str) -> None:
    result = parse_otlp_json_line(raw)
    assert not result.completions
    assert sum(result.diagnostics.values()) >= 1


def test_non_completion_and_missing_identity_never_become_pending_matches() -> None:
    unrelated = completion_attributes()
    unrelated["event.kind"] = "response.created"
    missing_identity = completion_attributes()
    missing_identity.pop("conversation.id")
    assert not parse_otlp_json_line(synthetic_otlp_line(attributes=unrelated)).completions
    completion = parse_otlp_json_line(
        synthetic_otlp_line(attributes=missing_identity)
    ).completions[0]
    assert completion.match_status == "invalid"
```

- [ ] **Step 2: Run the parser tests and verify the import fails**

Run: `.venv/bin/python -m pytest tests/parser/test_otel_parser.py -q`

Expected: FAIL because `codex_usage_tracker.parser.otel` does not exist.

- [ ] **Step 3: Implement pure allowlisted parsing and semantic fingerprinting**

```python
OTEL_DIAGNOSTIC_KEYS = (
    "otel_invalid_json",
    "otel_invalid_record",
    "otel_invalid_integer",
    "otel_unsupported_version",
    "otel_non_completion",
)


@dataclass(frozen=True)
class OtelCompletion:
    fingerprint: str
    conversation_id: str | None
    event_timestamp: str | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_output_tokens: int | None
    model: str | None
    effort: str | None
    service_tier: str | None
    fast: int | None
    service_tier_source: str | None
    service_tier_confidence: str | None
    app_version: str | None
    match_status: str


@dataclass(frozen=True)
class OtelParseResult:
    completions: Sequence[OtelCompletion]
    diagnostics: dict[str, int]


def parse_otlp_json_line(raw: str) -> OtelParseResult:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return OtelParseResult((), {"otel_invalid_json": 1})
    completions: list[OtelCompletion] = []
    diagnostics: Counter[str] = Counter()
    for record in _log_records(payload):
        attributes = _allowlisted_attributes(record.get("attributes"))
        if attributes.get("event.name") != "codex.sse_event" or attributes.get("event.kind") != "response.completed":
            diagnostics["otel_non_completion"] += 1
            continue
        completion, completion_diagnostics = _completion_from_attributes(record, attributes)
        diagnostics.update(completion_diagnostics)
        completions.append(completion)
    return OtelParseResult(tuple(completions), dict(diagnostics))
```

`_allowlisted_attributes()` must decode only the ten approved keys; `_otlp_value()` must accept only scalar `stringValue`, `intValue`, `doubleValue`, and `boolValue`. `_normalize_tier()` returns `(tier, fast, source, confidence)` and `_semantic_fingerprint()` hashes a versioned, sorted JSON object containing only the normalized allowlist fields. A syntactically valid completion without usable identity or tier semantics receives `match_status = "invalid"`.

Create `tests/otel_helpers.py` with synthetic-only factories used by later tasks:

```python
def completion_attributes(
    *,
    conversation_id: str = "synthetic-conversation",
    tokens: tuple[int, int, int, int] = (120, 40, 30, 10),
    model: str = "gpt-5.6-sol",
    effort: str = "high",
    service_tier: str | None = "priority",
    app_version: str = "0.143.0",
) -> dict[str, object]:
    input_tokens, cached_tokens, output_tokens, reasoning_tokens = tokens
    values: dict[str, object] = {
        "event.name": "codex.sse_event",
        "event.kind": "response.completed",
        "conversation.id": conversation_id,
        "input_token_count": input_tokens,
        "cached_token_count": cached_tokens,
        "output_token_count": output_tokens,
        "reasoning_token_count": reasoning_tokens,
        "model": model,
        "model_reasoning_effort": effort,
        "app.version": app_version,
    }
    if service_tier is not None:
        values["service_tier"] = service_tier
    return values


def synthetic_otlp_line(*, attributes: dict[str, object], body: str = "synthetic body") -> str:
    encoded = [
        {"key": key, "value": {"intValue" if isinstance(value, int) else "stringValue": str(value)}}
        for key, value in attributes.items()
    ]
    return json.dumps(
        {"resourceLogs": [{"scopeLogs": [{"logRecords": [{
            "timeUnixNano": "1784160000000000000",
            "body": {"stringValue": body},
            "attributes": encoded,
        }]}]}]}
    )


def synthetic_fast_completion(conversation_id: str, input_tokens: int) -> str:
    return synthetic_otlp_line(
        attributes=completion_attributes(
            conversation_id=conversation_id,
            tokens=(input_tokens, 0, 20, 5),
            service_tier="priority",
        )
    )


def synthetic_standard_completion(conversation_id: str, input_tokens: int) -> str:
    return synthetic_otlp_line(
        attributes=completion_attributes(
            conversation_id=conversation_id,
            tokens=(input_tokens, 0, 20, 5),
            service_tier=None,
        )
    )


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def append_text(path: Path, value: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(value)


@contextmanager
def initialized_connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "usage.sqlite3") as conn:
        init_db(conn)
        yield conn
```

- [ ] **Step 4: Run parser tests and static checks**

Run: `.venv/bin/python -m pytest tests/parser/test_otel_parser.py -q`

Run: `.venv/bin/python -m ruff check src/codex_usage_tracker/parser/otel.py tests/parser/test_otel_parser.py`

Expected: PASS.

- [ ] **Step 5: Commit the parser slice**

```bash
git add -- src/codex_usage_tracker/parser/otel.py src/codex_usage_tracker/parser/__init__.py tests/otel_helpers.py tests/parser/test_otel_parser.py
git commit -m "feat: parse aggregate OTel completions"
```

### Task 3: Incrementally ingest current and rotated completion files

**Files:**
- Create: `src/codex_usage_tracker/store/otel_ingest.py`
- Create: `tests/store/test_otel_ingest.py`

**Interfaces:**
- Consumes: `parse_otlp_json_line()` and an initialized SQLite connection.
- Produces: `discover_otel_sources(directory: Path) -> list[Path]`.
- Produces: `ingest_otel_completion_files(conn, directory: Path) -> OtelIngestResult`.
- Persists: normalized rows in `otel_completion_events` and complete-line cursors in `otel_completion_sources`.

- [ ] **Step 1: Write failing ingestion tests for append, partial lines, rotation, truncation, and semantic deduplication**

```python
def test_incremental_ingest_reads_each_complete_line_once(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    write_lines(source, [synthetic_fast_completion("conversation-a", 100)])
    with initialized_connection(tmp_path) as conn:
        first = ingest_otel_completion_files(conn, directory)
        append_text(source, synthetic_standard_completion("conversation-b", 200) + "\n")
        second = ingest_otel_completion_files(conn, directory)
        rows = conn.execute("SELECT fingerprint FROM otel_completion_events").fetchall()
    assert first.imported == 1
    assert second.imported == 1
    assert len(rows) == 2


def test_partial_last_line_is_retried_after_append(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    complete = synthetic_otlp_line(attributes=completion_attributes())
    source.parent.mkdir(parents=True)
    source.write_text(complete[:-1], encoding="utf-8")
    with initialized_connection(tmp_path) as conn:
        assert ingest_otel_completion_files(conn, directory).imported == 0
        source.write_text(complete + "\n", encoding="utf-8")
        assert ingest_otel_completion_files(conn, directory).imported == 1


def test_rotation_and_reread_do_not_duplicate_semantic_completion(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    current = directory / "codex-completions.jsonl"
    rotated = directory / "codex-completions-20260716.jsonl"
    line = synthetic_otlp_line(attributes=completion_attributes()) + "\n"
    current.parent.mkdir(parents=True)
    current.write_text(line, encoding="utf-8")
    with initialized_connection(tmp_path) as conn:
        ingest_otel_completion_files(conn, directory)
        current.replace(rotated)
        current.write_text(line, encoding="utf-8")
        result = ingest_otel_completion_files(conn, directory)
        count = conn.execute("SELECT COUNT(*) FROM otel_completion_events").fetchone()[0]
    assert count == 1
    assert result.duplicates >= 1


def test_truncation_or_inode_replacement_resets_cursor_safely(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        synthetic_otlp_line(attributes=completion_attributes(conversation_id="synthetic-a")) + "\n",
        encoding="utf-8",
    )
    with initialized_connection(tmp_path) as conn:
        ingest_otel_completion_files(conn, directory)
        source.unlink()
        source.write_text(
            synthetic_otlp_line(attributes=completion_attributes(conversation_id="synthetic-b")) + "\n",
            encoding="utf-8",
        )
        assert ingest_otel_completion_files(conn, directory).imported == 1


def test_ingest_never_persists_body_or_arbitrary_attributes(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    attributes = completion_attributes()
    attributes["secret.attribute"] = "synthetic-secret-value"
    write_lines(
        directory / "codex-completions.jsonl",
        [synthetic_otlp_line(attributes=attributes, body="synthetic-private-body")],
    )
    with initialized_connection(tmp_path) as conn:
        ingest_otel_completion_files(conn, directory)
        rows = conn.execute("SELECT * FROM otel_completion_events").fetchall()
        encoded = json.dumps([dict(row) for row in rows], sort_keys=True)
    assert "synthetic-private-body" not in encoded
    assert "synthetic-secret-value" not in encoded
    assert "secret.attribute" not in encoded
```

- [ ] **Step 2: Run the ingestion tests and verify the module is missing**

Run: `.venv/bin/python -m pytest tests/store/test_otel_ingest.py -q`

Expected: FAIL because `store.otel_ingest` does not exist.

- [ ] **Step 3: Implement deterministic discovery, cursor reset, and staging upserts**

```python
@dataclass(frozen=True)
class OtelIngestResult:
    files_scanned: int = 0
    imported: int = 0
    duplicates: int = 0
    diagnostics: dict[str, int] = field(default_factory=dict)


def discover_otel_sources(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("codex-completions*.jsonl") if path.is_file())


def ingest_otel_completion_files(conn: sqlite3.Connection, directory: Path) -> OtelIngestResult:
    totals = _MutableIngestTotals()
    for path in discover_otel_sources(directory):
        state = _source_state(conn, path)
        stat = path.stat()
        offset, line_number = _resume_position(state, stat)
        next_offset, next_line = _ingest_complete_lines(conn, path, offset, line_number, totals)
        _upsert_source_cursor(conn, path, stat, next_offset, next_line)
        totals.files_scanned += 1
    return totals.freeze()
```

Open sources in binary mode, seek to the stored offset, and advance the cursor only after a newline-terminated record is decoded and handled. Insert each completion with `ON CONFLICT(fingerprint) DO NOTHING`; count a zero rowcount as a semantic duplicate. Store the source path and line only in the sidecar table, never in public payloads.

- [ ] **Step 4: Run ingestion and migration tests**

Run: `.venv/bin/python -m pytest tests/store/test_otel_ingest.py tests/store/test_otel_schema.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the incremental ingestion slice**

```bash
git add -- src/codex_usage_tracker/store/otel_ingest.py tests/store/test_otel_ingest.py
git commit -m "feat: ingest OTel completions incrementally"
```

### Task 4: Reconcile exactly one canonical call group and preserve enrichment

**Files:**
- Create: `src/codex_usage_tracker/store/otel_reconciliation.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Modify: `src/codex_usage_tracker/store/source_replacement.py`
- Create: `tests/store/test_otel_reconciliation.py`

**Interfaces:**
- Consumes: staged rows with `match_status IN ('pending', 'ambiguous', 'matched')`.
- Produces: `reconcile_otel_completions(conn) -> OtelReconciliationResult`.
- Produces: `reset_otel_completion_matches(conn) -> None` for rebuilds.
- Preserves: non-null tier fields during record upsert and source replacement.

- [ ] **Step 1: Write failing reconciliation tests for uniqueness, clones, ambiguity, conflicts, and preservation**

```python
def test_unique_token_identity_enriches_every_clone_in_one_canonical_group(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(conn, conversation_id="conversation-a", tokens=(100, 40, 30, 10))
        stage_completion(conn, conversation_id="conversation-a", tokens=(100, 40, 30, 10), fast=1)
        result = reconcile_otel_completions(conn)
        rows = conn.execute("SELECT service_tier, fast FROM usage_events ORDER BY record_id").fetchall()
    assert result.matched == 1
    assert [(row["service_tier"], row["fast"]) for row in rows] == [("fast", 1), ("fast", 1)]


def test_same_tokens_in_two_canonical_groups_remain_ambiguous(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(conn, "conversation-a", (100, 40, 30, 10), canonical="canonical-a")
        insert_usage_clone_group(conn, "conversation-a", (100, 40, 30, 10), canonical="canonical-b")
        fingerprint = stage_completion(conn, "conversation-a", (100, 40, 30, 10), fast=1)
        reconcile_otel_completions(conn)
        status = conn.execute(
            "SELECT match_status FROM otel_completion_events WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()[0]
        tiers = conn.execute("SELECT service_tier FROM usage_events").fetchall()
    assert status == "ambiguous"
    assert all(row[0] is None for row in tiers)


def test_timestamp_distance_does_not_affect_matching(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(conn, "conversation-a", (100, 40, 30, 10))
        stage_completion(
            conn,
            "conversation-a",
            (100, 40, 30, 10),
            fast=1,
            event_timestamp="2099-01-01T00:00:00Z",
        )
        assert reconcile_otel_completions(conn).matched == 1


def test_model_or_effort_mismatch_prevents_match_when_both_are_present(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(conn, "conversation-a", (100, 40, 30, 10), model="gpt-5.5")
        stage_completion(conn, "conversation-a", (100, 40, 30, 10), fast=1, model="gpt-5.6")
        assert reconcile_otel_completions(conn).pending == 1


def test_contradictory_existing_tier_is_preserved_and_marks_conflict(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as conn:
        insert_usage_clone_group(
            conn, "conversation-a", (100, 40, 30, 10), service_tier="standard", fast=0
        )
        fingerprint = stage_completion(conn, "conversation-a", (100, 40, 30, 10), fast=1)
        assert reconcile_otel_completions(conn).conflicts == 1
        row = conn.execute("SELECT service_tier, fast FROM usage_events LIMIT 1").fetchone()
        status = conn.execute(
            "SELECT match_status FROM otel_completion_events WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()[0]
    assert tuple(row) == ("standard", 0)
    assert status == "conflict"


def test_usage_upsert_and_source_replacement_preserve_non_null_tier(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    original = synthetic_usage_event("record-a", "conversation-a", (100, 40, 30, 10), fast=1)
    upsert_usage_events([original], db_path=db_path)
    reparsed = replace(original, thread_name="reparsed", service_tier=None, fast=None)
    upsert_usage_events([reparsed], db_path=db_path, replace_source_files=[Path(original.source_file)])
    row = query_usage_record(db_path=db_path, record_id="record-a")
    assert row is not None
    assert (row["service_tier"], row["fast"]) == ("fast", 1)
```

Extend `tests/otel_helpers.py` with the complete aggregate-row factory:

```python
def synthetic_usage_event(
    record_id: str,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
    *,
    canonical: str = "canonical-a",
    model: str = "gpt-5.6-sol",
    effort: str = "high",
    service_tier: str | None = None,
    fast: int | None = None,
    duplicate: int = 0,
) -> UsageEvent:
    input_tokens, cached_tokens, output_tokens, reasoning_tokens = tokens
    total_tokens = input_tokens + output_tokens
    return UsageEvent(
        record_id=record_id,
        session_id=conversation_id,
        thread_name="Synthetic thread",
        session_updated_at="2026-07-16T00:00:00Z",
        event_timestamp="2026-07-16T00:00:00Z",
        source_file="/synthetic/session.jsonl",
        line_number=1,
        turn_id="synthetic-turn",
        turn_timestamp="2026-07-16T00:00:00Z",
        cwd="/synthetic/project",
        model=model,
        effort=effort,
        current_date="2026-07-16",
        timezone="UTC",
        call_initiator="user",
        call_initiator_reason="user_message",
        call_initiator_confidence="high",
        is_archived=0,
        thread_key="thread:Synthetic",
        thread_call_index=None,
        previous_record_id=None,
        next_record_id=None,
        thread_source="user",
        subagent_type=None,
        agent_role=None,
        agent_nickname=None,
        parent_session_id=None,
        parent_thread_name=None,
        parent_session_updated_at=None,
        model_context_window=258_400,
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        cumulative_input_tokens=input_tokens,
        cumulative_cached_input_tokens=cached_tokens,
        cumulative_output_tokens=output_tokens,
        cumulative_reasoning_output_tokens=reasoning_tokens,
        cumulative_total_tokens=total_tokens,
        usage_fingerprint=f"synthetic-fingerprint-{canonical}",
        canonical_record_id=canonical,
        is_duplicate=duplicate,
        duplicate_reason="copied_usage_fingerprint" if duplicate else None,
        service_tier=service_tier or ("fast" if fast == 1 else "standard" if fast == 0 else None),
        fast=fast,
        service_tier_source="otel_response_completed" if fast is not None else None,
        service_tier_confidence="exact" if fast is not None else None,
    )
```

Define `insert_usage_clone_group()` and `stage_completion()` in `test_otel_reconciliation.py`; insert rows using `UsageEvent.to_row()`/`EVENT_COLUMNS` and the exact sidecar columns from Task 1. `insert_usage_clone_group()` creates two physical rows with one canonical ID and `is_duplicate` values `0` and `1`; `stage_completion()` returns its deterministic synthetic fingerprint. These helpers contain no raw-log fields.

```python
def insert_usage_clone_group(
    conn: sqlite3.Connection,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
    *,
    canonical: str = "canonical-a",
    model: str = "gpt-5.6-sol",
    service_tier: str | None = None,
    fast: int | None = None,
) -> None:
    events = [
        synthetic_usage_event(
            f"{canonical}-record-{index}",
            conversation_id,
            tokens,
            canonical=canonical,
            model=model,
            service_tier=service_tier,
            fast=fast,
            duplicate=int(index == 1),
        )
        for index in range(2)
    ]
    placeholders = ", ".join("?" for _column in EVENT_COLUMNS)
    conn.executemany(
        f"INSERT INTO usage_events ({', '.join(EVENT_COLUMNS)}) VALUES ({placeholders})",
        [[event.to_row()[column] for column in EVENT_COLUMNS] for event in events],
    )


def stage_completion(
    conn: sqlite3.Connection,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
    *,
    fast: int,
    model: str = "gpt-5.6-sol",
    event_timestamp: str = "2026-07-16T00:00:00Z",
) -> str:
    input_tokens, cached_tokens, output_tokens, reasoning_tokens = tokens
    fingerprint = hashlib.sha256(
        repr((conversation_id, tokens, fast, model, event_timestamp)).encode("utf-8")
    ).hexdigest()
    conn.execute(
        """
        INSERT INTO otel_completion_events (
            fingerprint, conversation_id, event_timestamp,
            input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens,
            model, effort, service_tier, fast, service_tier_source,
            service_tier_confidence, app_version, source_path, source_line,
            match_status, matched_record_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'high', ?, ?, 'otel_response_completed',
                  'exact', '0.143.0', '/synthetic/codex-completions.jsonl', 1, 'pending', NULL)
        """,
        (
            fingerprint,
            conversation_id,
            event_timestamp,
            input_tokens,
            cached_tokens,
            output_tokens,
            reasoning_tokens,
            model,
            "fast" if fast == 1 else "standard",
            fast,
        ),
    )
    return fingerprint
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv/bin/python -m pytest tests/store/test_otel_reconciliation.py -q`

Expected: FAIL because the reconciler and enrichment-preserving merge behavior do not exist.

- [ ] **Step 3: Implement canonical matching, clone propagation, and conflict state**

```python
@dataclass(frozen=True)
class OtelReconciliationResult:
    matched: int = 0
    pending: int = 0
    ambiguous: int = 0
    conflicts: int = 0
    updated_usage_rows: int = 0


def reconcile_otel_completions(conn: sqlite3.Connection) -> OtelReconciliationResult:
    totals = _MutableReconciliationTotals()
    rows = conn.execute(
        "SELECT * FROM otel_completion_events "
        "WHERE match_status IN ('pending', 'ambiguous', 'matched') ORDER BY source_path, source_line"
    ).fetchall()
    for completion in rows:
        candidates = _candidate_rows(conn, completion)
        group_ids = {str(row["canonical_record_id"] or row["record_id"]) for row in candidates}
        if not candidates:
            _set_match_state(conn, completion["fingerprint"], "pending", None)
            totals.pending += 1
        elif len(group_ids) != 1:
            _set_match_state(conn, completion["fingerprint"], "ambiguous", None)
            totals.ambiguous += 1
        else:
            _apply_to_canonical_group(conn, completion, group_ids.pop(), totals)
    return totals.freeze()
```

`_candidate_rows()` must require exact conversation and token equality, add model/effort equality only when both sides are non-null, and omit timestamp entirely. `_apply_to_canonical_group()` must inspect all physical clones before writing: agreement is idempotent, all-null values receive the normalized tier, and any contradictory non-null value marks the staged completion `conflict` without changing usage rows.

```python
def _candidate_rows(conn: sqlite3.Connection, completion: sqlite3.Row) -> list[sqlite3.Row]:
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
        SELECT record_id, service_tier, fast, service_tier_source, service_tier_confidence
        FROM usage_events
        WHERE coalesce(nullif(canonical_record_id, ''), record_id) = ?
        ORDER BY record_id
        """,
        (canonical_id,),
    ).fetchall()
    desired = (
        completion["service_tier"],
        completion["fast"],
        completion["service_tier_source"],
        completion["service_tier_confidence"],
    )
    tier_columns = (
        "service_tier", "fast", "service_tier_source", "service_tier_confidence"
    )
    contradiction = any(
        row[column] is not None and row[column] != expected
        for row in clones
        for column, expected in zip(tier_columns, desired, strict=True)
    )
    if contradiction:
        _set_match_state(conn, completion["fingerprint"], "conflict", None)
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
    _set_match_state(conn, completion["fingerprint"], "matched", str(clones[0]["record_id"]))
    totals.matched += 1
    totals.updated_usage_rows += max(cursor.rowcount, 0)
```

- [ ] **Step 4: Add enrichment-owned merge semantics to existing upserts and replacements**

```python
OTEL_ENRICHMENT_COLUMNS = {
    "service_tier", "fast", "service_tier_source", "service_tier_confidence"
}


def _usage_event_upsert_sql() -> str:
    placeholders = ", ".join("?" for _column in EVENT_COLUMNS)
    update_clause = ", ".join(
        f"{column}=COALESCE(usage_events.{column}, excluded.{column})"
        if column in OTEL_ENRICHMENT_COLUMNS
        else f"{column}=excluded.{column}"
        for column in EVENT_COLUMNS
        if column != "record_id"
    )
    return (
        f"INSERT INTO usage_events ({', '.join(EVENT_COLUMNS)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT(record_id) DO UPDATE SET {update_clause}"
    )
```

Before `_delete_usage_events_for_source_files()`, capture one consistent tier tuple per `canonical_record_id`. After `_insert_usage_event_rows()`, restore those tuples to all rows in the same canonical group. If the captured group is internally inconsistent, do not restore it; the staged completion will be re-evaluated by reconciliation.

- [ ] **Step 5: Run reconciliation, deduplication, and source replacement tests**

Run: `.venv/bin/python -m pytest tests/store/test_otel_reconciliation.py tests/store/test_usage_deduplication.py tests/store/test_store_large_batches.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the correlation slice**

```bash
git add -- src/codex_usage_tracker/store/otel_reconciliation.py src/codex_usage_tracker/store/api.py src/codex_usage_tracker/store/source_replacement.py tests/store/test_otel_reconciliation.py
git commit -m "feat: correlate OTel tiers to canonical calls"
```

### Task 5: Integrate OTel ingestion with refresh, rebuild, metadata, and support diagnostics

**Files:**
- Modify: `src/codex_usage_tracker/store/refresh.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Modify: `src/codex_usage_tracker/core/api_payloads.py`
- Modify: `src/codex_usage_tracker/reports/support.py`
- Create: `tests/store/test_otel_refresh.py`
- Modify: `tests/reports/test_support.py`
- Modify: `tests/core/test_api_payloads.py`

**Interfaces:**
- Extends: `refresh_usage_index()` with keyword `otel_dir: Path = DEFAULT_OTEL_COMPLETIONS_DIR`.
- Extends: `rebuild_usage_index()` with keyword `otel_dir: Path = DEFAULT_OTEL_COMPLETIONS_DIR`.
- Extends: `record_refresh_metadata()` with keyword `otel_diagnostics: dict[str, int] | None = None`.
- Keeps: existing refresh-result JSON fields and adds non-zero `otel_*` keys under `parser_diagnostics`.

- [ ] **Step 1: Write failing refresh-order, no-op, rebuild, and support privacy tests**

```python
def test_refresh_ingests_session_rows_before_reconciling_otel(tmp_path: Path) -> None:
    codex_home = write_usage_session(tmp_path, conversation_id="conversation-a", tokens=(100, 40, 30, 10))
    otel_dir = tmp_path / "otel"
    write_lines(
        otel_dir / "codex-completions.jsonl",
        [synthetic_otlp_line(attributes=completion_attributes(
            conversation_id="conversation-a", tokens=(100, 40, 30, 10), service_tier="priority"
        ))],
    )
    result = refresh_usage_index(codex_home=codex_home, db_path=tmp_path / "usage.sqlite3", otel_dir=otel_dir)
    with connect(tmp_path / "usage.sqlite3") as conn:
        record_id = str(conn.execute("SELECT record_id FROM usage_events").fetchone()[0])
    row = query_usage_record(db_path=tmp_path / "usage.sqlite3", record_id=record_id)
    assert row is not None
    assert row["service_tier"] == "fast"
    assert result.parser_diagnostics["otel_matched"] == 1


def test_absent_otel_directory_is_a_supported_noop(tmp_path: Path) -> None:
    result = refresh_usage_index(
        codex_home=tmp_path / "codex", db_path=tmp_path / "usage.sqlite3", otel_dir=tmp_path / "missing"
    )
    assert result.parser_diagnostics.get("otel_files_scanned", 0) == 0


def test_refresh_records_protocol_confirmed_standard(tmp_path: Path) -> None:
    codex_home = write_usage_session(tmp_path, "conversation-standard", (100, 40, 30, 10))
    otel_dir = tmp_path / "otel"
    write_lines(
        otel_dir / "codex-completions.jsonl",
        [synthetic_otlp_line(attributes=completion_attributes(
            conversation_id="conversation-standard",
            tokens=(100, 40, 30, 10),
            service_tier=None,
            app_version="0.143.0",
        ))],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT service_tier, fast, service_tier_confidence FROM usage_events"
        ).fetchone()
    assert tuple(row) == ("standard", 0, "protocol")


def test_refresh_keeps_older_omitted_tier_unknown(tmp_path: Path) -> None:
    codex_home = write_usage_session(tmp_path, "conversation-legacy", (100, 40, 30, 10))
    otel_dir = tmp_path / "otel"
    write_lines(
        otel_dir / "codex-completions.jsonl",
        [synthetic_otlp_line(attributes=completion_attributes(
            conversation_id="conversation-legacy",
            tokens=(100, 40, 30, 10),
            service_tier=None,
            app_version="0.142.9",
        ))],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)
    with connect(db_path) as conn:
        row = conn.execute("SELECT service_tier, fast FROM usage_events").fetchone()
    assert tuple(row) == (None, None)


def test_otel_before_jsonl_matches_on_a_later_refresh(tmp_path: Path) -> None:
    otel_dir = tmp_path / "otel"
    write_lines(
        otel_dir / "codex-completions.jsonl",
        [synthetic_otlp_line(attributes=completion_attributes(
            conversation_id="conversation-a", tokens=(100, 40, 30, 10)
        ))],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=tmp_path / "empty", db_path=db_path, otel_dir=otel_dir)
    codex_home = write_usage_session(tmp_path, "conversation-a", (100, 40, 30, 10))
    refresh_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)
    with connect(db_path) as conn:
        assert conn.execute("SELECT service_tier FROM usage_events").fetchone()[0] == "fast"


def test_rebuild_retains_staging_resets_match_pointer_and_reapplies_tier(tmp_path: Path) -> None:
    codex_home = write_usage_session(tmp_path, "conversation-a", (100, 40, 30, 10))
    otel_dir = write_otel_directory(tmp_path, "conversation-a", (100, 40, 30, 10))
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)
    rebuild_usage_index(codex_home=codex_home, db_path=db_path, otel_dir=otel_dir)
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM otel_completion_events").fetchone()[0] == 1
        assert conn.execute("SELECT service_tier FROM usage_events").fetchone()[0] == "fast"


def test_support_bundle_exposes_counts_without_otel_identifiers(tmp_path: Path) -> None:
    payload = support_bundle_payload(db_path=tmp_path / "usage.sqlite3", codex_home=tmp_path / "codex")
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["otel"]["completion_directory_exists"] in {True, False}
    assert "conversation-a" not in encoded
    assert "fingerprint" not in encoded
    assert "source_path" not in encoded
```

Extend `tests/otel_helpers.py` with concrete session and directory factories:

```python
def write_usage_session(
    tmp_path: Path,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
) -> Path:
    input_tokens, cached_tokens, output_tokens, reasoning_tokens = tokens
    total_tokens = input_tokens + output_tokens
    codex_home = tmp_path / "codex"
    log_path = codex_home / "sessions" / "2026" / "07" / "16" / "synthetic.jsonl"
    rows = [
        {
            "timestamp": "2026-07-16T00:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": conversation_id},
        },
        {
            "timestamp": "2026-07-16T00:00:01.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": input_tokens,
                        "cached_input_tokens": cached_tokens,
                        "output_tokens": output_tokens,
                        "reasoning_output_tokens": reasoning_tokens,
                        "total_tokens": total_tokens,
                    },
                    "last_token_usage": {
                        "input_tokens": input_tokens,
                        "cached_input_tokens": cached_tokens,
                        "output_tokens": output_tokens,
                        "reasoning_output_tokens": reasoning_tokens,
                        "total_tokens": total_tokens,
                    },
                    "model_context_window": 258_400,
                },
            },
        },
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return codex_home


def write_otel_directory(
    tmp_path: Path,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
) -> Path:
    directory = tmp_path / "otel"
    write_lines(
        directory / "codex-completions.jsonl",
        [synthetic_otlp_line(attributes=completion_attributes(
            conversation_id=conversation_id,
            tokens=tokens,
            service_tier="priority",
        ))],
    )
    return directory
```

- [ ] **Step 2: Run focused refresh and support tests and verify failures**

Run: `.venv/bin/python -m pytest tests/store/test_otel_refresh.py tests/reports/test_support.py tests/core/test_api_payloads.py -q`

Expected: FAIL because refresh does not run the OTel phases or expose bounded diagnostics.

- [ ] **Step 3: Add the refresh phase after session persistence**

```python
def _refresh_otel_completions(*, db_path: Path, otel_dir: Path) -> dict[str, int]:
    with connect(db_path) as conn:
        init_db(conn)
        ingest = ingest_otel_completion_files(conn, otel_dir)
        reconciled = reconcile_otel_completions(conn)
        if reconciled.updated_usage_rows:
            touch_compression_revisions(conn, {"calls", "threads"})
    return {
        "otel_files_scanned": ingest.files_scanned,
        "otel_imported": ingest.imported,
        "otel_duplicates": ingest.duplicates,
        "otel_matched": reconciled.matched,
        "otel_pending": reconciled.pending,
        "otel_ambiguous": reconciled.ambiguous,
        "otel_conflicts": reconciled.conflicts,
        **ingest.diagnostics,
    }
```

Define the persistence allowlist once and use it in `record_refresh_metadata()`:

```python
OTEL_REFRESH_COUNTER_KEYS = (
    "otel_files_scanned",
    "otel_imported",
    "otel_duplicates",
    "otel_matched",
    "otel_pending",
    "otel_ambiguous",
    "otel_conflicts",
    *OTEL_DIAGNOSTIC_KEYS,
)
```

Call this after `write_refresh_stream()` and before `_finalize_refresh_result()`. Merge only non-zero OTel counters into `RefreshResult.parser_diagnostics`, and store every allowlisted OTel counter under `refresh_meta` with its existing `otel_` name. Add an `otel` progress phase without changing existing phase meanings.

- [ ] **Step 4: Preserve staging during rebuild and add support presence**

In `rebuild_usage_index()`, call `reset_otel_completion_matches(conn)` before deleting canonical usage tables and deliberately omit both OTel sidecar tables from the deletion list. Pass `otel_dir` through to the final refresh. In support payloads, add only:

```python
"otel": {
    "completion_directory_exists": DEFAULT_OTEL_COMPLETIONS_DIR.is_dir(),
    "refresh_counts": {key: value for key, value in refresh.items() if key.startswith("otel_")},
}
```

Do not include the directory path, source paths, fingerprints, record IDs, conversations, timestamps, or token tuples.

- [ ] **Step 5: Run refresh, payload, support, and callback tests**

Run: `.venv/bin/python -m pytest tests/store/test_otel_refresh.py tests/store/test_refresh_callbacks.py tests/core/test_api_payloads.py tests/reports/test_support.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the refresh integration slice**

```bash
git add -- src/codex_usage_tracker/store/refresh.py src/codex_usage_tracker/store/api.py src/codex_usage_tracker/core/api_payloads.py src/codex_usage_tracker/reports/support.py tests/store/test_otel_refresh.py tests/reports/test_support.py tests/core/test_api_payloads.py
git commit -m "feat: reconcile OTel tiers during refresh"
```

### Task 6: Apply confirmed Fast credit multipliers without changing USD estimates

**Files:**
- Create: `src/codex_usage_tracker/pricing/fast_tier.py`
- Modify: `src/codex_usage_tracker/pricing/allowance_usage.py`
- Modify: `src/codex_usage_tracker/pricing/allowance.py`
- Modify: `src/codex_usage_tracker/usage_drain/types.py`
- Modify: `src/codex_usage_tracker/usage_drain/spans.py`
- Modify: `tests/pricing/test_allowance.py`
- Modify: `tests/pricing/test_pricing.py`
- Modify: `tests/usage_drain/test_usage_drain_model.py`

**Interfaces:**
- Produces: `DOCUMENTED_FAST_CREDIT_MULTIPLIERS` and `documented_fast_credit_multiplier(model)`.
- Produces: `usage_credit_multiplier`, `usage_credit_multiplier_source`, and `standard_usage_credits` annotations.
- Preserves: `estimated_cost_usd` and usage-drain Standard-baseline modeling.

- [ ] **Step 1: Write failing multiplier, unknown, Standard, USD, and usage-drain compatibility tests**

```python
@pytest.mark.parametrize(
    ("model", "multiplier"),
    [("gpt-5.6", 2.5), ("gpt-5.6-sol", 2.5), ("gpt-5.5", 2.5), ("gpt-5.4", 2.0)],
)
def test_confirmed_fast_multiplies_standard_credit_estimate(model: str, multiplier: float) -> None:
    row = credit_row(model=model, fast=1, service_tier="fast")
    annotated = annotate_rows_with_allowance([row], synthetic_allowance_config())[0]
    assert annotated["usage_credits"] == pytest.approx(annotated["standard_usage_credits"] * multiplier)
    assert annotated["usage_credit_multiplier"] == multiplier
    assert annotated["usage_credit_multiplier_source"] == "otel_response_completed"


@pytest.mark.parametrize("fast", [0, None])
def test_standard_and_unknown_rows_keep_multiplier_one(fast: int | None) -> None:
    row = credit_row(model="gpt-5.6", fast=fast, service_tier="standard" if fast == 0 else None)
    annotated = annotate_rows_with_allowance([row], synthetic_allowance_config())[0]
    assert annotated["usage_credits"] == annotated["standard_usage_credits"]
    assert annotated["usage_credit_multiplier"] == 1.0


def test_confirmed_fast_unknown_model_does_not_invent_multiplier() -> None:
    row = credit_row(model="synthetic-unknown", fast=1, service_tier="fast")
    annotated = annotate_rows_with_allowance([row], synthetic_allowance_config())[0]
    assert annotated["usage_credit_multiplier"] == 1.0
    assert annotated["usage_credit_multiplier_source"] == "no_documented_fast_multiplier"


def test_service_tier_does_not_change_estimated_cost_usd() -> None:
    pricing = synthetic_pricing_config()
    row = credit_row(model="gpt-5.6", fast=0, service_tier="standard")
    standard = estimate_cost_usd(row, pricing)
    fast = estimate_cost_usd({**row, "fast": 1, "service_tier": "fast"}, pricing)
    assert fast == standard


def test_usage_drain_uses_standard_usage_credits_after_fast_annotation() -> None:
    row = annotate_rows_with_allowance(
        [credit_row(model="gpt-5.6", fast=1, service_tier="fast")],
        synthetic_allowance_config(),
    )[0]
    span = span_from_single_row_for_test(row)
    assert span.standard_usage_credits == row["standard_usage_credits"]
```

Use these local synthetic helpers in the focused tests:

```python
def credit_row(*, model: str, fast: int | None, service_tier: str | None) -> dict[str, object]:
    return {
        "model": model,
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "uncached_input_tokens": 80,
        "output_tokens": 10,
        "total_tokens": 110,
        "fast": fast,
        "service_tier": service_tier,
        "service_tier_source": "otel_response_completed" if fast is not None else None,
        "service_tier_confidence": "exact" if fast is not None else None,
    }


def synthetic_allowance_config() -> UsageAllowanceConfig:
    rates = {"input_per_million": 10.0, "cached_input_per_million": 1.0, "output_per_million": 50.0}
    models = ("gpt-5.6", "gpt-5.6-sol", "gpt-5.5", "gpt-5.4", "synthetic-unknown")
    return UsageAllowanceConfig(
        path=Path("/synthetic/allowance.json"),
        rate_card_path=Path("/synthetic/rate-card.json"),
        credit_rates={model: dict(rates) for model in models},
        aliases={},
        rate_metadata={model: {} for model in models},
        alias_metadata={},
        windows=[],
        loaded=True,
        rate_card_loaded=True,
        source={"name": "Synthetic credit rates"},
    )


def synthetic_pricing_config() -> PricingConfig:
    return PricingConfig(
        path=Path("/synthetic/pricing.json"),
        models={"gpt-5.6": {
            "input_per_million": 10.0,
            "cached_input_per_million": 1.0,
            "output_per_million": 50.0,
        }},
        loaded=True,
    )


def span_from_single_row_for_test(row: dict[str, object]) -> UsageDeltaSpan:
    return _span_from_rows([row], baseline_percent=0.0, end_used_percent=1.0, proxies={})
```

- [ ] **Step 2: Run focused pricing tests and verify failures**

Run: `.venv/bin/python -m pytest tests/pricing/test_allowance.py tests/pricing/test_pricing.py tests/usage_drain/test_usage_drain_model.py -q`

Expected: FAIL because credit annotation has no exact-tier multiplier policy.

- [ ] **Step 3: Implement shared documented model-family multipliers**

```python
DOCUMENTED_FAST_CREDIT_MULTIPLIERS = {
    "gpt-5.6": 2.5,
    "gpt-5.5": 2.5,
    "gpt-5.4": 2.0,
}


def documented_fast_credit_multiplier(model: object) -> float | None:
    normalized = str(model or "").strip().lower()
    for family, multiplier in DOCUMENTED_FAST_CREDIT_MULTIPLIERS.items():
        if normalized == family or normalized.startswith(f"{family}-") or normalized.startswith(f"{family} "):
            return multiplier
    return None


def credit_multiplier_for_row(row: Mapping[str, object]) -> tuple[float, str]:
    if row.get("fast") != 1:
        fallback = "confirmed_standard" if row.get("fast") == 0 else "tier_unknown"
        return 1.0, str(row.get("service_tier_source") or fallback)
    multiplier = documented_fast_credit_multiplier(row.get("model"))
    if multiplier is None:
        return 1.0, "no_documented_fast_multiplier"
    return multiplier, str(row.get("service_tier_source") or "confirmed_fast")
```

Move the existing usage-drain constant/function to this pricing module and re-export them from `usage_drain/types.py` to preserve imports.

- [ ] **Step 4: Split Standard and effective credit estimates**

```python
standard_credits = estimate_standard_usage_credits(copy, rates)
multiplier, multiplier_source = credit_multiplier_for_row(copy)
copy.update(
    usage_credits=standard_credits * multiplier,
    standard_usage_credits=standard_credits,
    usage_credit_multiplier=multiplier,
    usage_credit_multiplier_source=multiplier_source,
)
```

Rename the existing calculation body to `estimate_standard_usage_credits()` and keep `estimate_usage_credits()` as the effective wrapper for compatibility. Add `standard_usage_credits`, `usage_credit_multiplier`, and `usage_credit_multiplier_source` in both priced and unpriced annotation branches; unpriced rows keep `usage_credits = None` and `standard_usage_credits = None`. In usage-drain span construction, read `standard_usage_credits` with a fallback to `usage_credits` for older injected rows. Do not modify `pricing/costing.py`.

- [ ] **Step 5: Run pricing and usage-drain tests**

Run: `.venv/bin/python -m pytest tests/pricing tests/usage_drain/test_usage_drain_model.py tests/usage_drain/test_usage_drain_reports.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the credit-accounting slice**

```bash
git add -- src/codex_usage_tracker/pricing/fast_tier.py src/codex_usage_tracker/pricing/allowance_usage.py src/codex_usage_tracker/pricing/allowance.py src/codex_usage_tracker/usage_drain/types.py src/codex_usage_tracker/usage_drain/spans.py tests/pricing/test_allowance.py tests/pricing/test_pricing.py tests/usage_drain/test_usage_drain_model.py
git commit -m "feat: price confirmed Fast credit usage"
```

### Task 7: Expose exact tiers in calls, exports, and the dashboard

**Files:**
- Modify: `tests/store/test_content_query_exports.py`
- Modify: `tests/dashboard/test_dashboard_payload.py`
- Modify: `tests/server/test_server_call_detail.py`
- Modify: `frontend/dashboard/src/api/types.ts`
- Modify: `frontend/dashboard/src/api/client.ts`
- Modify: `frontend/dashboard/src/api/client.test.ts`
- Modify: `frontend/dashboard/src/test-fixtures/dashboardFixture.ts`
- Create: `frontend/dashboard/src/features/calls/serviceTier.ts`
- Create: `frontend/dashboard/src/features/calls/serviceTier.test.ts`
- Modify: `frontend/dashboard/src/features/shared/tables.tsx`
- Modify: `frontend/dashboard/src/features/shared/tables.test.ts`
- Modify: `frontend/dashboard/src/features/calls/CallInspector.tsx`
- Modify: `frontend/dashboard/src/features/call-investigator/CallInvestigatorPage.tsx`
- Regenerate: `src/codex_usage_tracker/plugin_data/dashboard/react/`

**Interfaces:**
- Consumes: additive backend row fields already selected by `usage_events.*` and exported through schema-driven CSV.
- Produces: nullable exact `fast`, `serviceTier`, `serviceTierSource`, `serviceTierConfidence`, and separate `fastProxyCandidate` in `CallRow`.
- Produces: Calls table/CSV tier labels and exact-first detail wording.

- [ ] **Step 1: Write failing backend export and frontend decoding tests**

```python
def test_csv_export_includes_additive_service_tier_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [synthetic_usage_event("record-a", "conversation-a", (100, 40, 30, 10), fast=1)],
        db_path=db_path,
    )
    output_path = tmp_path / "usage.csv"
    export_usage_csv(output_path, db_path=db_path)
    header = next(csv.reader(output_path.read_text(encoding="utf-8").splitlines()))
    assert [name for name in header if name.startswith("service_tier") or name == "fast"] == [
        "service_tier", "fast", "service_tier_source", "service_tier_confidence"
    ]


def test_dashboard_payload_keeps_tier_fields_aggregate_only(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [synthetic_usage_event("record-a", "conversation-a", (100, 40, 30, 10), fast=1)],
        db_path=db_path,
    )
    row = dashboard_payload(db_path=db_path)["rows"][0]
    assert row["service_tier"] == "fast"
    assert row["fast"] == 1
    assert "otel_source_path" not in row


def test_call_detail_exposes_tier_without_sidecar_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [synthetic_usage_event("record-a", "conversation-a", (100, 40, 30, 10), fast=1)],
        db_path=db_path,
    )
    payload = call_detail_payload(
        "record_id=record-a", db_path=db_path, annotate_rows=lambda rows: rows
    )
    record = payload["record"]
    assert record["service_tier"] == "fast"
    assert record["service_tier_confidence"] == "exact"
    assert "source_path" not in record
```

```typescript
it('keeps exact tier separate from throughput proxy', () => {
  const call = usageRowToCall({ service_tier: 'standard', fast: 0, service_tier_confidence: 'protocol', duration_seconds: 1, total_tokens: 9000 }, 0);
  expect(call.fast).toBe(false);
  expect(call.fastProxyCandidate).toBe(true);
  expect(serviceTierDetail(call)).toBe('confirmed Standard · protocol');
});
```

- [ ] **Step 2: Run backend and frontend focused tests and verify failures**

Run: `.venv/bin/python -m pytest tests/store/test_content_query_exports.py tests/dashboard/test_dashboard_payload.py tests/server/test_server_call_detail.py -q`

Run: `npm run dashboard:test -- --run frontend/dashboard/src/api/client.test.ts frontend/dashboard/src/features/calls/serviceTier.test.ts frontend/dashboard/src/features/shared/tables.test.ts`

Expected: FAIL because the dashboard model does not decode or label exact service tiers.

- [ ] **Step 3: Decode exact tier fields and retain the historical proxy separately**

```typescript
// UsageRow
service_tier?: string | null;
fast?: number | boolean | null;
service_tier_source?: string | null;
service_tier_confidence?: string | null;
standard_usage_credits?: number | null;
usage_credit_multiplier?: number | null;
usage_credit_multiplier_source?: string | null;

// CallRow
serviceTier: string;
fast: boolean | null;
serviceTierSource: string;
serviceTierConfidence: string;
fastProxyCandidate: boolean;
usageCreditMultiplier: number;
usageCreditMultiplierSource: string;

// usageRowToCall()
const rawFast = row.fast;
const exactFast = rawFast === true || rawFast === 1
  ? true
  : rawFast === false || rawFast === 0
    ? false
    : null;

serviceTier: String(row.service_tier ?? ''),
fast: exactFast,
serviceTierSource: String(row.service_tier_source ?? ''),
serviceTierConfidence: String(row.service_tier_confidence ?? ''),
fastProxyCandidate: durationSeconds > 0 && totalTokens / Math.max(durationSeconds, 1) > 4_000,
usageCreditMultiplier: Number(row.usage_credit_multiplier ?? 1),
usageCreditMultiplierSource: String(row.usage_credit_multiplier_source ?? ''),
```

In `usageRowToCall()`, decode `fast` as `true`, `false`, or `null`; compute the current throughput heuristic into `fastProxyCandidate`; never let the proxy overwrite exact `fast`. Add the required defaults to `test-fixtures/dashboardFixture.ts` so hand-built `CallRow` fixtures remain type-complete.

- [ ] **Step 4: Add exact-first labels, Calls column, details, and CSV fields**

```typescript
export function serviceTierLabel(call: CallRow): 'Fast' | 'Standard' | 'Unknown' {
  if (call.fast === true) return 'Fast';
  if (call.fast === false) return 'Standard';
  return 'Unknown';
}

export function serviceTierDetail(call: CallRow): string {
  if (call.fast !== null) {
    return `confirmed ${serviceTierLabel(call)} · ${call.serviceTierConfidence || 'exact'}`;
  }
  return call.fastProxyCandidate ? 'tier unknown · Fast proxy candidate' : 'tier unknown · normal throughput proxy';
}
```

Add a `Service Tier` Calls column, add the four persisted tier fields plus credit multiplier fields to `callCsvColumns`, and replace both existing duration details with `serviceTierDetail(call)`. Keep duration itself unchanged.

- [ ] **Step 5: Run focused frontend tests, typecheck, and regenerate bundled assets**

Run: `npm run dashboard:test -- --run frontend/dashboard/src/api/client.test.ts frontend/dashboard/src/features/calls/serviceTier.test.ts frontend/dashboard/src/features/shared/tables.test.ts`

Run: `npm run dashboard:typecheck`

Run: `npm run dashboard:build`

Expected: PASS and deterministic assets regenerated under `src/codex_usage_tracker/plugin_data/dashboard/react/`.

- [ ] **Step 6: Run backend payload/export privacy tests**

Run: `.venv/bin/python -m pytest tests/store/test_content_query_exports.py tests/dashboard/test_dashboard_payload.py tests/dashboard/test_dashboard_payload_privacy.py tests/server/test_server_call_detail.py tests/server/test_server_dashboard_shell.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the public-surface slice**

```bash
git add -- tests/store/test_content_query_exports.py tests/dashboard/test_dashboard_payload.py tests/server/test_server_call_detail.py frontend/dashboard/src/api/types.ts frontend/dashboard/src/api/client.ts frontend/dashboard/src/api/client.test.ts frontend/dashboard/src/test-fixtures/dashboardFixture.ts frontend/dashboard/src/features/calls/serviceTier.ts frontend/dashboard/src/features/calls/serviceTier.test.ts frontend/dashboard/src/features/shared/tables.tsx frontend/dashboard/src/features/shared/tables.test.ts frontend/dashboard/src/features/calls/CallInspector.tsx frontend/dashboard/src/features/call-investigator/CallInvestigatorPage.tsx src/codex_usage_tracker/plugin_data/dashboard/react
git commit -m "feat: show exact Fast tiers in Calls"
```

### Task 8: Document the behavior and run the complete verification gate

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/database-schema.md`
- Modify: `docs/pricing-and-credits.md`
- Modify: `docs/privacy.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Documents: exact-versus-proxy behavior, the v30 tables/columns, cursor/rebuild semantics, credit multiplier provenance, unchanged USD estimates, and aggregate-only privacy guarantees.
- Verifies: Python, dashboard, packaging, schema, privacy, generated assets, and release readiness.

- [ ] **Step 1: Update user and maintainer documentation with exact semantics**

Document these concrete points in the named files:

```text
The tracker reads only local codex-completions*.jsonl OTLP exporter files.
Fast/Standard is exact only when service_tier is explicit or Standard is established by Codex >= 0.143.0 omission semantics.
Older unmatched history remains Unknown; latency and reasoning effort are not proof of Fast.
Confirmed Fast changes ChatGPT credit estimates by the documented model multiplier but never changes USD token estimates.
Raw OTLP bodies and arbitrary attributes are neither persisted nor exported.
```

Add an Unreleased changelog entry covering local OTel ingestion, exact tier labels, conservative correlation, and credit-accounting changes.

- [ ] **Step 2: Run focused Python and frontend suites**

Run: `.venv/bin/python -m pytest tests/parser/test_otel_parser.py tests/store/test_otel_schema.py tests/store/test_otel_ingest.py tests/store/test_otel_reconciliation.py tests/store/test_otel_refresh.py tests/pricing/test_allowance.py tests/reports/test_support.py tests/dashboard/test_dashboard_payload.py -q`

Run: `npm run dashboard:test -- --run frontend/dashboard/src/api/client.test.ts frontend/dashboard/src/features/calls/serviceTier.test.ts frontend/dashboard/src/features/shared/tables.test.ts`

Expected: PASS.

- [ ] **Step 3: Run the complete Python and dashboard gates**

Run: `.venv/bin/python -m ruff check .`

Run: `.venv/bin/python -m mypy`

Run: `.venv/bin/python -m pytest`

Run: `.venv/bin/python -m pytest --cov=codex_usage_tracker --cov-report=term-missing`

Run: `.venv/bin/python -m compileall src`

Run: `npm run dashboard:verify`

Run: `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`

Run: `.venv/bin/python scripts/check_release.py`

Run: `git diff --check`

Expected: every command exits 0.

- [ ] **Step 4: Build and inspect release artifacts**

Run: `.venv/bin/python -m build`

Run: `.venv/bin/python -m twine check dist/*`

Run: `.venv/bin/python scripts/check_release.py --dist`

Expected: wheel and sdist build successfully, Twine reports both valid, and bundled parser/dashboard/skill assets pass release inspection.

- [ ] **Step 5: Perform the final privacy and Git review**

Run: `git status --short --branch`

Run: `git diff --stat main..HEAD`

Run: `git diff main..HEAD -- . ':(exclude)src/codex_usage_tracker/plugin_data/dashboard/react/assets/*.js'`

Run: `rg -n "conversation.id|secret.attribute|private body|/Users/|source_path" tests docs src/codex_usage_tracker/plugin_data --glob '!docs/superpowers/**'`

Expected: only synthetic identifiers and documented schema field names appear; no real log content, local OTel paths, secrets, or private records are staged.

- [ ] **Step 6: Commit documentation and verification evidence**

```bash
git add -- docs/architecture.md docs/database-schema.md docs/pricing-and-credits.md docs/privacy.md docs/dashboard-guide.md docs/cli-json-schemas.md CHANGELOG.md
git commit -m "docs: explain exact Fast usage tracking"
```
