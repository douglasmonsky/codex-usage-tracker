# Clone/Copy Usage Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Count copied historical clone rows once while preserving every physical source row and counting genuinely new clone calls.

**Architecture:** Persist a versioned strict usage fingerprint and stable logical canonical ID on every physical `usage_events` row. Maintain exactly one indexed billable representative per fingerprint, expose it through `canonical_usage_events`, route all default aggregates through that relation, and expose physical rows only through a dedicated dedupe diagnostic contract.

**Tech Stack:** Python 3.10+, dataclasses, SQLite migrations/views/partial indexes, pytest, MCP Python SDK, localhost JSON API, vanilla dashboard JavaScript.

## Global Constraints

- Keep physical rows for provenance; do not change the existing physical `record_id` algorithm.
- Only exact upstream identifiers or the complete strict aggregate fingerprint may auto-exclude a row.
- Do not use transcript text, content-index tables, FTS, fuzzy matching, or token-count-only matching.
- Use a constant number of indexed fingerprint operations per parsed event.
- Existing report/API/MCP behavior is canonical by default; physical access is a separate diagnostic surface with no mode flag on ordinary tools.
- Preserve synthetic-only fixtures and aggregate-first privacy behavior.
- Schema version becomes 24 and existing databases are backfilled in place.

---

### Task 1: Versioned Usage Identity, Schema Migration, And Ingest Classification

**Files:**
- Create: `src/codex_usage_tracker/core/usage_identity.py`
- Create: `src/codex_usage_tracker/store/deduplication.py`
- Create: `src/codex_usage_tracker/store/deduplication_schema.py`
- Modify: `src/codex_usage_tracker/core/models.py`
- Modify: `src/codex_usage_tracker/core/schema.py`
- Modify: `src/codex_usage_tracker/parser/jsonl_values.py`
- Modify: `src/codex_usage_tracker/parser/jsonl_v1.py`
- Modify: `src/codex_usage_tracker/store/schema.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Modify: `src/codex_usage_tracker/store/source_replacement.py`
- Test: `tests/core/test_usage_identity.py`
- Test: `tests/parser/test_parser.py`
- Test: `tests/store/test_usage_deduplication.py`
- Test: `tests/store/test_store_migrations.py`

**Interfaces:**
- Produces: `UsageIdentity(upstream_usage_id, usage_fingerprint, canonical_record_id)`.
- Produces: `extract_upstream_usage_id(envelope, payload, info) -> str | None`.
- Produces: `usage_identity_from_values(values, upstream_usage_id=None) -> UsageIdentity`.
- Produces: `classify_usage_rows(conn, rows) -> list[dict[str, object]]` and `promote_orphaned_fingerprints(conn, fingerprints) -> set[str]`.
- Produces: SQLite view `canonical_usage_events` and migration 24.

- [ ] **Step 1: Write strict identity tests**

Create `tests/core/test_usage_identity.py` with these focused cases:

```python
from codex_usage_tracker.core.usage_identity import (
    FINGERPRINT_VERSION,
    extract_upstream_usage_id,
    usage_identity_from_values,
)


def _values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "event_timestamp": "2026-07-14T12:00:00Z",
        "turn_id": "turn-a",
        "turn_timestamp": "2026-07-14T11:59:00Z",
        "model": "gpt-5.5",
        "effort": "high",
        "model_context_window": 258400,
        "input_tokens": 90,
        "cached_input_tokens": 20,
        "output_tokens": 10,
        "reasoning_output_tokens": 5,
        "total_tokens": 100,
        "cumulative_input_tokens": 190,
        "cumulative_cached_input_tokens": 40,
        "cumulative_output_tokens": 20,
        "cumulative_reasoning_output_tokens": 10,
        "cumulative_total_tokens": 200,
        "rate_limit_plan_type": "pro",
        "rate_limit_limit_id": "codex",
        "rate_limit_primary_used_percent": 2.5,
        "rate_limit_primary_window_minutes": 300,
        "rate_limit_primary_resets_at": 1781562696,
        "rate_limit_secondary_used_percent": 29.0,
        "rate_limit_secondary_window_minutes": 10080,
        "rate_limit_secondary_resets_at": 1781887793,
    }
    values.update(overrides)
    return values


def test_strict_identity_ignores_physical_session_and_source_fields() -> None:
    original = usage_identity_from_values(
        {**_values(), "session_id": "original", "source_file": "/original.jsonl"}
    )
    clone = usage_identity_from_values(
        {**_values(), "session_id": "clone", "source_file": "/clone.jsonl"}
    )
    assert original == clone
    assert original.usage_fingerprint.startswith(f"{FINGERPRINT_VERSION}:")


def test_equal_tokens_with_different_timestamp_do_not_match() -> None:
    original = usage_identity_from_values(_values())
    new_call = usage_identity_from_values(
        _values(event_timestamp="2026-07-14T12:01:00Z")
    )
    assert original.usage_fingerprint != new_call.usage_fingerprint


def test_recognized_upstream_id_takes_precedence() -> None:
    upstream = extract_upstream_usage_id(
        {"event_id": "evt-123"},
        {"type": "token_count"},
        {},
    )
    first = usage_identity_from_values(_values(), upstream_usage_id=upstream)
    second = usage_identity_from_values(
        _values(event_timestamp="2026-07-14T13:00:00Z"),
        upstream_usage_id=upstream,
    )
    assert first.usage_fingerprint == second.usage_fingerprint


def test_generic_id_is_not_an_upstream_usage_id() -> None:
    assert extract_upstream_usage_id({"id": "session-id"}, {}, {}) is None
```

- [ ] **Step 2: Run the identity tests and verify RED**

Run: `.venv/bin/python -m pytest tests/core/test_usage_identity.py -q`

Expected: collection fails because `codex_usage_tracker.core.usage_identity` does not exist.

- [ ] **Step 3: Implement the versioned identity module**

Implement `UsageIdentity`, fixed `STRICT_IDENTITY_FIELDS`, recognized paths for only `usage_id`, `event_id`, and `call_id`, canonical JSON with `sort_keys=True` and compact separators, and SHA-256 helpers. The public implementation must follow this shape:

```python
FINGERPRINT_VERSION = "usage-fingerprint-v1"
CANONICAL_ID_VERSION = "canonical-usage-v1"


@dataclass(frozen=True)
class UsageIdentity:
    upstream_usage_id: str | None
    usage_fingerprint: str
    canonical_record_id: str


def usage_identity_from_values(
    values: Mapping[str, object],
    *,
    upstream_usage_id: str | None = None,
) -> UsageIdentity:
    basis = (
        {"upstream_usage_id": upstream_usage_id}
        if upstream_usage_id
        else {name: values.get(name) for name in STRICT_IDENTITY_FIELDS}
    )
    digest = _sha256_json({"version": FINGERPRINT_VERSION, "basis": basis})
    fingerprint = f"{FINGERPRINT_VERSION}:{digest}"
    canonical = hashlib.sha256(
        f"{CANONICAL_ID_VERSION}|{fingerprint}".encode("utf-8")
    ).hexdigest()
    return UsageIdentity(upstream_usage_id, fingerprint, canonical)
```

Store the recognized upstream value as `"<path>:<value>"` so identical raw values under different identifier types cannot collide. Ignore empty, non-string, and generic `id` values.

- [ ] **Step 4: Run identity tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_usage_identity.py -q`

Expected: all identity tests pass.

- [ ] **Step 5: Write parser tests for copied and new clone events**

Extend `tests/parser/test_parser.py` with synthetic original and clone JSONL files. Assert copied historical events have different physical `record_id` values but equal fingerprint/canonical IDs, while a new clone token event has a distinct fingerprint. Add one token envelope with `event_id` and assert `upstream_usage_id == "envelope.event_id:evt-123"`. Do not use real logs.

- [ ] **Step 6: Run parser tests and verify RED**

Run: `.venv/bin/python -m pytest tests/parser/test_parser.py -q`

Expected: new assertions fail because `UsageEvent` has no identity fields and the parser does not inspect the token envelope ID.

- [ ] **Step 7: Thread identity through parser and model**

Add optional additive fields at the end of `UsageEvent` so existing synthetic constructors remain compatible:

```python
upstream_usage_id: str | None = None
usage_fingerprint: str | None = None
canonical_record_id: str | None = None
is_duplicate: int = 0
duplicate_reason: str | None = None
```

Pass the complete token envelope into `_handle_token_count_event` and `_build_token_count_event`. Extract a recognized upstream ID, build the token values once, call `usage_identity_from_values`, and populate the three parser-owned identity fields. Do not set duplicate status in the parser; status is database-relative.

- [ ] **Step 8: Run parser and identity tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_usage_identity.py tests/parser/test_parser.py -q`

Expected: all selected tests pass.

- [ ] **Step 9: Write migration and store classification tests**

Create `tests/store/test_usage_deduplication.py` with synthetic `UsageEvent` builders covering:

```python
def test_clone_copy_is_physical_but_not_billable(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events([original_event(), copied_clone_event(), new_clone_event()], db_path)
    with connect(db_path) as conn:
        physical = conn.execute("SELECT count(*) FROM usage_events").fetchone()[0]
        canonical = conn.execute("SELECT count(*) FROM canonical_usage_events").fetchone()[0]
        duplicate = conn.execute(
            "SELECT duplicate_reason FROM usage_events WHERE is_duplicate = 1"
        ).fetchone()[0]
    assert physical == 3
    assert canonical == 2
    assert duplicate == "copied_usage_fingerprint"


def test_source_replacement_promotes_surviving_copy(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events([original_event(), copied_clone_event()], db_path)
    upsert_usage_events([], db_path, replace_source_files=[original_path()])
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT record_id, is_duplicate, duplicate_reason FROM usage_events"
        ).fetchall()
    assert [(row["record_id"], row["is_duplicate"], row["duplicate_reason"]) for row in rows] == [
        (copied_clone_event().record_id, 0, None)
    ]
```

Extend `tests/store/test_store_migrations.py` to expect schema version 24, the five new columns, three ordinary indexes plus one partial unique index, `canonical_usage_events`, and deterministic backfill of duplicate legacy rows.

- [ ] **Step 10: Run store tests and verify RED**

Run: `.venv/bin/python -m pytest tests/store/test_usage_deduplication.py tests/store/test_store_migrations.py -q`

Expected: failures for missing migration 24, columns, view, indexes, and canonical classification.

- [ ] **Step 11: Implement migration 24 and indexed classification**

Add the five columns to `USAGE_EVENT_COLUMNS`, using repairable nullable declarations for migration compatibility and application-level validation after backfill. Create `deduplication_schema.migrate_usage_deduplication(conn)` to:

1. add missing columns;
2. backfill identities using `usage_identity_from_values(dict(row))`;
3. set every row duplicate, then promote the deterministic first row per fingerprint;
4. create the indexes and partial unique index;
5. recreate `canonical_usage_events AS SELECT * FROM usage_events WHERE is_duplicate = 0`.

Register migration 24 and its name in `store/schema.py` without adding the migration implementation to the already-large schema module.

Implement `deduplication.classify_usage_rows` using one indexed representative lookup per row/fingerprint and an in-batch fingerprint map. Blank identities from legacy/manual `UsageEvent` constructors must be normalized through `usage_identity_from_values` before classification. Update `_insert_usage_event_rows` to consume classified rows.

Before source deletion, collect distinct affected fingerprints. After deletion, call `promote_orphaned_fingerprints`, choosing the first surviving physical row by event timestamp, source file, line number, and record ID. Return promoted thread keys so summaries and derivatives refresh.

- [ ] **Step 12: Run store tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/store/test_usage_deduplication.py tests/store/test_store_migrations.py tests/store/test_source_records.py -q`

Expected: all selected tests pass; source-record rows still preserve both physical records.

- [ ] **Step 13: Commit Task 1**

Run:

```bash
git add -- src/codex_usage_tracker/core/models.py src/codex_usage_tracker/core/schema.py src/codex_usage_tracker/core/usage_identity.py src/codex_usage_tracker/parser/jsonl_v1.py src/codex_usage_tracker/parser/jsonl_values.py src/codex_usage_tracker/store/api.py src/codex_usage_tracker/store/deduplication.py src/codex_usage_tracker/store/deduplication_schema.py src/codex_usage_tracker/store/schema.py src/codex_usage_tracker/store/source_replacement.py tests/core/test_usage_identity.py tests/parser/test_parser.py tests/store/test_store_migrations.py tests/store/test_usage_deduplication.py
git commit -m "feat: add canonical usage identity"
```

---

### Task 2: Canonical Default Queries And Derived Materializations

**Files:**
- Modify: `src/codex_usage_tracker/store/dashboard_queries.py`
- Modify: `src/codex_usage_tracker/store/usage_api_queries.py`
- Modify: `src/codex_usage_tracker/store/summary_queries.py`
- Modify: `src/codex_usage_tracker/store/usage_record_queries.py`
- Modify: `src/codex_usage_tracker/store/thread_summaries.py`
- Modify: `src/codex_usage_tracker/store/allowance_observations.py`
- Modify: `src/codex_usage_tracker/recommendation_engine/materialization.py`
- Modify: `src/codex_usage_tracker/recommendation_engine/query.py`
- Modify: `src/codex_usage_tracker/recommendation_engine/summary_materialization.py`
- Modify: `src/codex_usage_tracker/diagnostics/snapshot_analysis.py`
- Modify: `src/codex_usage_tracker/diagnostics/snapshot_concentration.py`
- Modify: `src/codex_usage_tracker/diagnostics/snapshot_overview.py`
- Modify: `src/codex_usage_tracker/store/compression_candidate_metadata.py`
- Modify: `src/codex_usage_tracker/store/compression_evidence.py`
- Modify: `src/codex_usage_tracker/store/compression_fact_queries.py`
- Modify: `src/codex_usage_tracker/store/content_patterns.py`
- Modify: `src/codex_usage_tracker/store/diagnostic_call_queries.py`
- Modify: `src/codex_usage_tracker/store/diagnostic_queries.py`
- Modify: `src/codex_usage_tracker/store/exports.py`
- Modify: `src/codex_usage_tracker/store/large_low_output.py`
- Modify: `src/codex_usage_tracker/store/recommendation_queries.py`
- Modify: `src/codex_usage_tracker/store/repeated_files.py`
- Modify: `src/codex_usage_tracker/store/shell_churn.py`
- Test: `tests/store/test_store_dashboard_queries.py`
- Test: `tests/store/test_store_dashboard_mcp.py`
- Test: `tests/store/test_usage_deduplication.py`
- Test: `tests/allowance_intelligence/test_allowance_intelligence.py`
- Test: `tests/reports/test_indexed_recommendations.py`
- Test: `tests/server/test_server_threads.py`

**Interfaces:**
- Consumes: `canonical_usage_events` from Task 1.
- Produces: canonical-only default counts/tokens across reports, dashboard, API, MCP, recommendations, allowance, and thread summaries.
- Preserves: physical source-record and explicit record-ID provenance queries.

- [ ] **Step 1: Add cross-surface failing regression tests**

Add one original/copy/new fixture to shared store test helpers. Assert default dashboard events/count/token summary, `query_summary`, expensive calls, thread summaries, recommendation materialization, and allowance observations report 2 calls rather than 3. Assert `query_source_records` still reports all 3 physical rows.

For each surface, assert both call count and total-token sum so a row-filter bug cannot hide behind a count-only assertion.

- [ ] **Step 2: Run focused consumer tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/store/test_store_dashboard_queries.py tests/store/test_store_dashboard_mcp.py tests/allowance_intelligence/test_allowance_intelligence.py tests/reports/test_indexed_recommendations.py tests/server/test_server_threads.py -q
```

Expected: new assertions show physical count/token totals instead of canonical totals.

- [ ] **Step 3: Route live/default reads through the canonical view**

In default query SQL, replace physical reads with an alias that preserves existing expressions:

```sql
FROM canonical_usage_events AS usage_events
```

Apply this to dashboard queries, usage API queries, summaries, expensive-call ranking, and default session/call lists. Keep direct physical `record_id` detail lookup and `source_records` joins on `usage_events` because they are provenance surfaces.

Update status payloads to distinguish canonical default counts from physical diagnostic counts only through the dedupe status service introduced in Task 3.

- [ ] **Step 4: Rebuild derived tables from canonical rows**

Change thread summary insertion and latest-record subqueries to read `canonical_usage_events`. In allowance synchronization, delete any observation whose `record_id` belongs to an excluded row and insert observations only by joining canonical rows. In recommendation fact and summary materialization, select candidate records from the canonical view.

After the changes, review the remaining production `FROM usage_events` matches. Keep these physical persistence/provenance modules on `usage_events`: `store/api.py`, `store/source_records.py`, `store/source_replacement.py`, `store/refresh_stream.py`, `store/content_persistence.py`, `store/content_provenance.py`, `store/compression_fact_ingest.py`, `store/compression_fact_sync.py`, `store/compression_facts.py`, `store/schema.py`, and physical parent/timing lookups in `store/usage_timing.py`. Keep explicit content investigation in `store/content_search.py` and `store/content_trace.py` physical. Every other default aggregate match must use `canonical_usage_events`.

The classification rule is:

- physical provenance/per-record persistence: keep and add a short code comment where intent is unclear; or
- billable/default aggregate: change to the canonical view.

Do not change content/source provenance queries merely to eliminate search matches.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 command plus:

```bash
.venv/bin/python -m pytest tests/store/test_usage_deduplication.py tests/store/test_source_records.py tests/server/test_server_call_lists.py -q
```

Expected: default consumers agree on canonical totals and provenance tests retain physical rows.

- [ ] **Step 6: Commit Task 2**

Run `git add --` with only the modified query/materialization and test files, then:

```bash
git commit -m "fix: use canonical rows for usage totals"
```

---

### Task 3: Dedicated Dedupe Diagnostics, Contracts, Dashboard Disclosure, And Verification

**Files:**
- Create: `src/codex_usage_tracker/store/dedupe_queries.py`
- Create: `src/codex_usage_tracker/diagnostics/dedupe.py`
- Create: `src/codex_usage_tracker/server/dedupe.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Modify: `src/codex_usage_tracker/diagnostics/api.py`
- Modify: `src/codex_usage_tracker/diagnostics/mcp.py`
- Modify: `src/codex_usage_tracker/cli/mcp_server.py`
- Modify: `src/codex_usage_tracker/cli/commands_reports.py`
- Modify: `src/codex_usage_tracker/cli/parser_reports.py`
- Modify: `src/codex_usage_tracker/server/routes.py`
- Modify: `src/codex_usage_tracker/server/route_inventory.py`
- Modify: `src/codex_usage_tracker/server/handler.py` or the diagnostics route mixin used by `handler.py`.
- Modify: `src/codex_usage_tracker/core/json_contract_diagnostics.py`
- Modify: `src/codex_usage_tracker/dashboard/api.py`
- Modify: `src/codex_usage_tracker/server/status.py`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/dashboard_status.js`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/DiagnosticsPage.js`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/diagnosticsQueries.js`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/OverviewPage.js`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/overviewQueries.js`
- Modify: `docs/architecture.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `docs/cli-reference.md`
- Modify: `docs/mcp.md`
- Modify: `docs/privacy.md`
- Modify: `docs/dashboard-guide.md`
- Test: `tests/store/test_usage_deduplication.py`
- Test: `tests/cli/test_mcp_integration.py`
- Test: `tests/dashboard/test_dashboard_payload.py`
- Test: `tests/server/test_route_inventory.py`
- Test: `tests/server/test_server_api.py`
- Test: `tests/core/test_privacy.py`

**Interfaces:**
- Consumes: physical/canonical columns and view from Task 1.
- Produces: `query_dedupe_summary(db_path) -> dict[str, Any]`.
- Produces: `query_physical_duplicate_rows(db_path, limit=100) -> list[dict[str, Any]]`.
- Produces: dedicated CLI JSON report, localhost `/api/diagnostics/dedupe`, and MCP tool `usage_dedupe_diagnostics`.
- Produces: additive default payload field `dedupe_status` with excluded-copy count.

- [ ] **Step 1: Write failing diagnostic contract and privacy tests**

Assert the summary payload equals this additive shape for the original/copy/new fixture:

```python
{
    "dedupe_enabled": True,
    "fingerprint_version": "usage-fingerprint-v1",
    "physical_rows": 3,
    "canonical_rows": 2,
    "excluded_copied_rows": 1,
    "duplicate_fingerprint_groups": 1,
    "physical_total_tokens": 300,
    "excluded_total_tokens": 100,
    "canonical_total_tokens": 200,
    "duplicate_reasons": {"copied_usage_fingerprint": 1},
}
```

Assert physical duplicate rows are bounded and contain only the approved provenance/aggregate keys. Add forbidden-value assertions proving synthetic prompt/response/tool-output strings cannot appear.

Add route inventory, localhost API, CLI JSON, MCP, and dashboard-payload assertions. Assert ordinary tools expose no `view` or `physical` mode parameter.

- [ ] **Step 2: Run diagnostic tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/store/test_usage_deduplication.py tests/cli/test_mcp_integration.py tests/dashboard/test_dashboard_payload.py tests/server/test_route_inventory.py tests/server/test_server_api.py tests/core/test_privacy.py -q
```

Expected: missing query service, route, MCP tool, payload field, and contract registration failures.

- [ ] **Step 3: Implement aggregate and bounded physical diagnostic queries**

Implement a single aggregate SQL query over `usage_events` using conditional sums and a grouped reason query. Implement the physical list with `WHERE is_duplicate = 1`, deterministic ordering, and `normalize_limit` capped to the repository's diagnostic maximum. Select only:

```text
record_id, canonical_record_id, usage_fingerprint, upstream_usage_id,
is_duplicate, duplicate_reason, source_file, line_number, session_id,
turn_id, turn_timestamp, event_timestamp, model, effort,
input_tokens, cached_input_tokens, output_tokens,
reasoning_output_tokens, total_tokens, cumulative_total_tokens
```

Never join content tables.

- [ ] **Step 4: Add dedicated CLI/API/MCP contracts**

Build one shared `diagnostics.dedupe.build_dedupe_diagnostics_report` payload service. Expose it through:

- CLI command `dedupe-diagnostics --limit N --json` following existing report parser/handler conventions;
- MCP tool `usage_dedupe_diagnostics(limit: int = 100)`;
- GET `/api/diagnostics/dedupe?limit=N`;
- route inventory and stable diagnostic JSON schema registration.

Existing summary/report tools remain parameter-compatible and canonical-only.

- [ ] **Step 5: Add dashboard disclosure**

Add the small `dedupe_status` summary to dashboard/server status payloads. Show a concise diagnostics/status indicator such as “1 copied clone row excluded”; show nothing alarming when zero rows are excluded. Keep the bounded physical list inside the diagnostics view and do not embed raw content in generated HTML.

- [ ] **Step 6: Run diagnostic tests and verify GREEN**

Run the Step 2 command.

Expected: all selected tests pass and privacy assertions confirm aggregate/provenance-only output.

- [ ] **Step 7: Update documentation and bundled skill contracts**

Document canonical totals, physical provenance, exact-only exclusion, fuzzy-diagnostic-only policy, schema 24, the new route/CLI/MCP surface, and the dashboard disclosure. Update both source and bundled skill copies if their documented tool inventory changes.

- [ ] **Step 8: Run targeted static and architecture checks**

Run:

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
.venv/bin/python -m compileall src
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 9: Run the repository broad verification gate**

Run: `just full`

If trusted hooks already ran the identical `full` profile on the same tree, use that recorded result and do not duplicate it. On failure, read `.verify-logs/LAST_FAILURE.md` before changing code.

Expected: full verifier passes, including coverage, architecture, secret scanning, schema checks, dashboard checks, and release readiness.

- [ ] **Step 10: Perform final requirements and privacy review**

Review `git status --short --branch`, `git diff --stat`, and the complete task diff. Confirm:

- copied historical rows are physical but excluded once;
- new clone calls remain billable;
- equal-token fuzzy cases remain billable;
- all requested default consumers are canonical;
- the diagnostic count and physical provenance surface are explicit;
- no real logs, raw content, secrets, local databases, or generated private artifacts are tracked.

- [ ] **Step 11: Commit Task 3**

Stage only intentional files with explicit paths and commit:

```bash
git commit -m "feat: disclose clone usage deduplication"
```

Record the three task commit hashes and verification commands in the final report. Do not push unless explicitly requested.
