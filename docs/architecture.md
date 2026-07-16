# Architecture

Codex Usage Tracker is a local sidecar app. It reads Codex session JSONL logs, stores tracker-owned indexes in SQLite, and exposes usage data through CLI commands, MCP tools, CSV export, generated dashboards, and the localhost React dashboard.

The current storage model has three layers:

- Aggregate usage index: token counters, model/effort metadata, call origins, diagnostic labels, thread summaries, pricing/credit estimates, allowance snapshots, and safe report payloads.
- Canonical/materialized intelligence: physical usage provenance plus logical usage fingerprints and canonical pointers, reset-aware allowance observations/cycles/intervals, source revisions, and persisted analysis snapshots/jobs. Default totals read canonical rows; physical rows remain available for bounded local diagnostics.
- Local content index: normalized conversation turns, bounded content fragments, tool calls, command runs, file events, persisted investigation run summaries, and source provenance for explicit local MCP/API investigation.

The aggregate index preserves every parsed row in `usage_events` for source provenance. A versioned strict fingerprint links exact copies of the same logged model call, and the `canonical_usage_events` view selects one physical representative for default totals. Only high-confidence fingerprint matches are excluded; ambiguous or merely similar calls remain canonical. If the original source disappears, the surviving physical copy is promoted without changing the logical call identity.

Materialized facts may retain physical rows so source replacement and local evidence remain auditable. Unscoped aggregate and compression-fact reads join the canonical view, while explicit deduplication diagnostics report physical, canonical, and excluded counts separately.

Shareable outputs remain aggregate-first and must omit indexed/raw content unless an export is explicitly documented as a local raw/content export.

## Boundaries

- `parser.py` converts local JSONL events into aggregate `UsageEvent` records. It also attaches metadata-only call-origin categories, diagnostic facts from `diagnostic_facts.py`, archived-session flags, conservative thread keys, source cursors, and parser diagnostics.
- `parser/otel.py`, `store/otel_ingest.py`, and `store/otel_reconciliation.py`
  provide aggregate-only completion enrichment from local
  `~/.codex-usage-tracker/otel/codex-completions*.jsonl` files. The importer
  retains only approved completion identifiers, token counters, model/effort,
  application version, and service-tier metadata; response bodies and arbitrary
  OTLP attributes are never persisted. Reconciliation requires one canonical
  call group with the same conversation id and all four token counters. Model
  and effort narrow a match when both sides provide them, but timestamps are not
  identity evidence.
- `store/content_index.py` owns normalized local content-index population and cleanup. It may persist bounded local snippets, tool-call metadata, command roots/labels, file path hashes/basenames, parser adapter metadata, source provenance, parse warnings, and FTS5 search rows. Investigation/report builders may persist bounded run summaries in `investigation_runs`. These surfaces must not feed raw/indexed content into default CSV, dashboard HTML, support bundle, or aggregate report payloads.
- `call_origin.py` owns the pure call-origin classifier and migrated-row fallback. It must not open source JSONL files; source-log reads belong in refresh/indexing or explicit context loading.
- `schema.py` owns persisted SQLite columns and migrations. Add columns or tables there before changing refresh, export, or MCP behavior.
- `store.py` and `store/api.py` own SQLite setup, refresh, rebuild, query access, previous/next call links, materialized thread summaries, source-file refresh cursors, SQL-backed live dashboard API slices, and cleanup ordering.
- `source_records.py` owns source-file provenance, parser coverage, incremental cursors, and replacement on source-file changes.
- `dedupe.py` and store migrations own conservative logical identity. Indexed
  fingerprint lookup is O(1) per parsed event; only high-confidence identical
  events are linked to a canonical record. No raw-content or fuzzy token-count
  scan participates in default exclusion.
- `allowance_intelligence/` owns cohort selection, reset-aware cycle and interval
  materialization, prior-only calibration/forecasting, selection-corrected change
  detection, and the constant-size status/finite series/latest-first evidence
  services. `server/analysis_jobs.py` owns bounded asynchronous execution and
  revision-keyed persisted results.
- `reports.py` is the application-service layer for summaries, expensive-call reports, recommendations, pricing coverage, source coverage, allowance reports, and filtered query payloads. CLI and MCP wrappers should call this layer instead of duplicating report assembly.
- `api_payloads.py` owns stable JSON payload helpers shared by CLI and MCP. `json_contracts.py` owns lightweight contract checks for schema-versioned CLI/MCP payloads and localhost live API payloads.
- `costing.py`, `pricing_config.py`, `pricing_openai.py`, `pricing_estimates.py`, and `allowance.py` own cost, credit, rate-card, and allowance annotation. Keep estimate confidence and source metadata attached to rows.
- `projects.py`, `threads.py`, and `recommendations.py` annotate aggregate rows with project identity, thread relationships, and actionable signals. Project privacy redaction belongs in `projects.py` so CLI, MCP, dashboard, CSV, and support-bundle surfaces share behavior.
- `context.py` is the normal path for explicit selected-call raw context. It reads one selected source file on demand, applies redaction and size limits, omits tool output by default, and keeps full serialized group analysis explicit.
- `diagnostic_snapshots.py` owns persisted diagnostic snapshot refresh/load orchestration. Snapshot modules should stay synthetic-testable and avoid raw transcript persistence in aggregate diagnostic facts.
- `dashboard.py` builds aggregate-first static dashboard payloads and writes HTML/assets. `server.py` adds localhost refresh, compatibility `/api/usage`, SQL-backed live API slices, and explicit lazy context loading.
- `frontend/dashboard/` owns the React dashboard. It should render server/API payloads rather than becoming an independent source of usage calculations.
- `plugin_installer.py`, `.mcp.json`, `skills/`, `src/codex_usage_tracker/plugin_data/skills/`, and `scripts/check_release.py` own install and packaging behavior.
- `scripts/benchmark_synthetic_history.py` owns broad generated large-history query timing checks. `scripts/benchmark_dashboard_routes.py` owns deterministic cold/warm route budgets for the query pipeline. Both must stay synthetic-only and must not read real Codex logs.

## Extension Rules

1. Add new aggregate usage-event metrics through `UsageEvent`, `schema.py`, migrations, store writers, privacy behavior, export behavior, and focused migration/privacy tests.
2. Add new content-index records through `schema.py`, `store/content_index.py`, source provenance tests, cleanup tests, and shareable-output tests proving indexed content does not leak through default exports.
3. Add new report views through `reports.py` first, then wire CLI and MCP wrappers to the shared service.
4. Add new machine-readable outputs through `api_payloads.py`, a `schema` value, `json_contracts.py`, and focused contract tests when the output is stable.
5. Add dashboard-only interactions in the narrowest dashboard module and keep URL state in dashboard state helpers.
6. Keep examples, screenshots, mocks, and fixtures synthetic. Never derive committed fixtures from real logs.
7. When editing skill instructions, update both the source `skills/...` file and the bundled `src/codex_usage_tracker/plugin_data/skills/...` copy. `scripts/check_release.py` verifies installable plugin assets stay complete and synced.
8. When adding fields derived from `cwd`, Git metadata, source paths, log-event metadata, or indexed content, decide how they behave in `normal`, `redacted`, and `strict` privacy modes before exposing them in dashboard, JSON, CSV, MCP, support-bundle, or shareable export output.
9. Diagnostic snapshot refresh must remain explicit on demand. Normal usage refresh paths may load stored snapshots, but must not rescan source logs for diagnostic sections unless the user calls diagnostics `--refresh` or a `/api/diagnostics/<section>/refresh` endpoint.
10. Register each new dashboard query in `dashboardQueryContracts.json` with one stable identity, endpoint, data class, and response schema. Query keys must include source, source revision, scope, and every payload-changing option.
11. Register each dashboard route in `server.route_inventory`. Interactive routes must be bounded and index-backed; unavoidable all-history detector work uses the shared asynchronous job lifecycle.
12. Cache only immutable aggregate responses. Server keys include source generation and semantic/configuration inputs; browser persistence rejects raw or indexed content.
13. Add or change a route budget only from repeatable synthetic evidence. Database indexes require an additive migration, query-plan or timing evidence, and focused migration coverage.
14. Preserve physical usage rows for provenance, but route default dashboard,
    API, report, recommendation, diagnostic, thread-summary, detector, and MCP
    totals through `canonical_usage_events`. New physical-row investigation
    surfaces must be bounded, explicitly labeled, and tested against an
    original/copy/new-call fixture.
15. Treat service tier as exact only when a completion explicitly reports it, or
    when Codex `0.143.0` or newer omits it under the documented Standard
    protocol. Older or unmatched calls remain Unknown. Latency and reasoning
    effort are useful throughput signals, not proof of Fast usage.

Normal aggregate responses use a 64-entry, 256-KiB-per-entry process cache.
Allowance history and diagnostics use a separate four-entry, 8-MiB-per-entry
cache because their bounded evidence payloads are materially larger. Both caches
invalidate on source revision and semantic/configuration inputs; neither stores
raw or indexed content.

Recommendation-fact refresh identity includes the active pricing, allowance,
rate-card, and threshold configuration paths. Every refresh entry point must
forward those paths; after any of those configurations changes, refresh the
index before serving indexed recommendations.

## Validation

Use the narrowest useful check first, then the release suite before committing shared parser, schema, MCP, dashboard, packaging, or privacy changes:

```bash
python -m pytest
python -m compileall src
python -m mypy
for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do
  node --check "$file"
done
python scripts/check_release.py
python -m build
python scripts/check_release.py --dist
git diff --check
python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /tmp/dashboard-route-budget
```

Dashboard UI changes should also be opened in a browser and checked at desktop and mobile widths for overflow, overlap, stale state, and shareable-output behavior.

Run the enforced dashboard route budget after changing focused query services, response caching, or frontend query orchestration. Run `python scripts/benchmark_synthetic_history.py --rows 10000 100000 --json --enforce-thresholds` after changing broader SQLite filters, dashboard payload loading, or indexes. Run `python scripts/benchmark_synthetic_history.py --rows 1000 --with-source-logs --json --enforce-thresholds` after changing source-log refresh, content indexing, explicit context loading, or source-log diagnostics. Run the 500k benchmark before release work when practical.
