# Architecture

Codex Usage Tracker is a local sidecar app. It reads aggregate token counters from Codex session JSONL logs, stores only aggregate metrics in SQLite, and exposes those metrics through CLI commands, MCP tools, CSV export, and a static or localhost-served dashboard.

## Boundaries

- `parser.py` converts local JSONL events into aggregate `UsageEvent` records. It also attaches metadata-only call-origin categories, archived-session flags, and conservative thread keys. It must not persist prompts, assistant text, tool output, or transcript snippets.
- `call_origin.py` owns the pure call-origin classifier and migrated-row fallback. It must not open source JSONL files; source-log reads belong in parser refresh or explicit context loading only.
- `schema.py` owns persisted `usage_events` columns. Add columns there before changing SQLite migrations or export behavior.
- `store.py` owns SQLite setup, refresh, rebuild, query access, persisted per-thread previous/next call links, materialized thread summaries, source-file refresh cursors, and SQL-backed live dashboard API slices. Keep filesystem scanning, database writes, SQL prefilters, counts, limits, offsets, and incremental refresh decisions here.
- `reports.py` is the application-service layer for summaries, expensive-call reports, recommendations, pricing coverage, and filtered query payloads. CLI and MCP should call this layer instead of duplicating report assembly.
- `api_payloads.py` owns stable JSON payload helpers shared by CLI and MCP. `json_contracts.py` owns the lightweight contract checks for schema-versioned CLI/MCP payloads and localhost live API payloads. Add payload builders and contract entries together when surfaces need the same shape.
- `costing.py`, `pricing_config.py`, `pricing_openai.py`, `pricing_estimates.py`, and `allowance.py` own cost, credit, rate-card, and allowance annotation. Keep estimate confidence and source metadata attached to rows.
- `projects.py`, `threads.py`, and `recommendations.py` annotate aggregate rows with project identity, thread relationships, and actionable signals. Project privacy redaction also belongs in `projects.py` so CLI, MCP, dashboard, CSV, and support-bundle surfaces share the same behavior.
- `dashboard.py` builds aggregate-only static dashboard payloads and writes HTML/assets. `server.py` adds localhost refresh, the compatibility `/api/usage` endpoint, SQL-backed live API slices, and explicit lazy context loading.
- `plugin_data/dashboard/dashboard_format.js` owns dashboard formatting primitives. `dashboard_data.js` owns row payload and thread relationship helpers. `dashboard_analysis.js` owns scoring, sorting, recommendation, and thread grouping logic. `dashboard_cells.js` owns reusable table/cell HTML helpers. `dashboard_details.js` owns sidebar detail and thread narrative rendering. `dashboard_tables.js` owns Calls, Threads, and expanded thread-call table rendering. `dashboard_filters.js` owns date range parsing and row date matching. `dashboard_state.js` owns URL, CSV, and download state utilities. `dashboard_i18n.js`, `dashboard_payload_cache.js`, and `dashboard_tooltips.js` own localization, session aggregate cache, and fast tooltip helpers. `dashboard_call_investigator.js` owns the dedicated call drilldown surface. `dashboard.js` owns top-level DOM rendering, event handling, and API refresh orchestration.
- `context.py` is the only normal path that reads raw log context, and it does so only for one selected record on demand with redaction and size limits. Its default quick mode omits tool output and serialized groups; full serialized JSONL group analysis is explicit.
- `plugin_installer.py`, `.mcp.json`, `skills/`, and `scripts/check_release.py` own install and packaging behavior.
- `scripts/benchmark_synthetic_history.py` owns generated large-history query timing and threshold enforcement for 10k, 100k, and 500k aggregate-row fixtures. Its optional `--with-source-logs` mode writes synthetic JSONL source logs to time explicit context loading and to guard normal dashboard payload assembly against source-log reads. It must stay synthetic-only and must not read real Codex logs.
- `skills/codex-usage-tracker/` is the source copy for the operational Codex skill. It should stay focused on setup, dashboard, export, doctor, and direct MCP workflows.
- `skills/codex-usage-api/` is the source copy for the conversational analyst skill. It should stay focused on aggregate-only API routing, interpretation, and limitations.
- `src/codex_usage_tracker/plugin_data/skills/` contains the wheel-bundled copies installed by `codex-usage-tracker install-plugin`.

## Extension Rules

1. Add new persisted usage-event metrics through `UsageEvent`, `schema.py`, migrations, store queries, dashboard payload tests, and CSV/export checks. Add auxiliary aggregate tables such as `thread_summaries` or `source_files` through `store.py` migrations plus focused migration/privacy tests.
2. Add new report views through `reports.py` first, then wire CLI and MCP wrappers to that shared service.
3. Add new machine-readable outputs through `api_payloads.py` or report payload methods with a `schema` value, a `json_contracts.py` entry, and focused tests.
4. Add dashboard-only interactions in `plugin_data/dashboard/dashboard.js` and keep URL state in `dashboard_state.js`.
5. Keep all examples, screenshots, mocks, and tests synthetic. Never derive fixtures from real logs.
6. When editing skill instructions, update both the source `skills/...` file and the bundled `src/codex_usage_tracker/plugin_data/skills/...` copy. `scripts/check_release.py` verifies that installable plugin assets stay complete and synced.
7. When adding fields derived from `cwd`, Git metadata, source paths, or log-event metadata, decide how they behave in `normal`, `redacted`, and `strict` privacy modes before exposing them in dashboard, JSON, CSV, MCP, or support-bundle output.

## Validation

Use the narrowest useful check first, then the release suite before committing:

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
```

Dashboard UI changes should also be opened in a browser and checked on desktop and mobile widths for overlap, stale state, and aggregate-only output.

Run `python scripts/benchmark_synthetic_history.py --rows 10000 100000 --json --enforce-thresholds` after changing SQLite filters, dashboard payload loading, or indexes. Run `python scripts/benchmark_synthetic_history.py --rows 1000 --with-source-logs --json --enforce-thresholds` after changing explicit context loading or source-log diagnostics. Run the 500k benchmark before release work when practical.
