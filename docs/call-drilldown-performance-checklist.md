# Call Drilldown Performance Hardening Checklist

This checklist tracks the focused `perf/call-drilldown-performance-hardening` branch built from `experimental/call-drilldown-diagnostics`.

## Goals

- Keep the useful call investigator, token accounting, cache diagnostics, compaction evidence, and call-origin concepts.
- Prevent normal dashboard rendering and `/api/usage` from opening or parsing raw source JSONL logs.
- Keep raw/source JSONL access limited to indexing/refresh, explicit one-call context loading, and explicit diagnostic or benchmark tools.
- Make large-history dashboard behavior measurable and progressively more SQLite-backed.
- Keep the static dashboard export path supported for compatibility.

## Non-goals

- Do not implement an evidence cache in this branch.
- Do not publish, tag, push to `main`, rename packages, or change the stable CLI command.
- Do not use real Codex logs in tests, docs, fixtures, screenshots, or benchmarks.
- Do not remove the existing static dashboard mode while live APIs are being hardened.

## Privacy Boundary

- Default SQLite may store aggregate counters and derived categorical diagnostics only.
- Default SQLite must not store prompts, assistant messages, tool output, raw JSONL fragments, compaction replacement text, raw context, or reconstructed transcript evidence.
- Any future evidence cache must be explicit opt-in, redacted, purgeable, and documented before implementation.
- Context evidence must remain on-demand for one selected call and redacted before display.

## Performance Invariants

- `dashboard_payload` must not open or parse source JSONL files.
- `/api/usage` must not do raw-log analysis.
- Source JSONL reads are allowed only in refresh/indexing, explicit `/api/context` for one selected call, and explicit diagnostic/benchmark tools.
- Live dashboard work should move toward SQLite-backed API slices instead of shipping all rows to the browser.
- Static dashboard generation remains supported as export/compat mode.

## Current Inventory

Milestone 0 inspection ran on `perf/call-drilldown-performance-hardening` after fast-forwarding `experimental/call-drilldown-diagnostics`.

Suspected hot paths confirmed by source inspection:

- M3 removed the `dashboard_payload` source-log call-origin scan. Call origin is now persisted as aggregate categorical metadata during parser refresh, with a cheap fallback for migrated rows.
- M3 converted `src/codex_usage_tracker/call_origin.py` to pure classifiers that do not open source JSONL files.
- `src/codex_usage_tracker/server.py` serves `/api/usage` by calling `dashboard_payload`; after M3, this no longer inherits call-origin source-log reads.
- M2 removed `_read_call_anchors(...)` from `load_call_context`, so explicit context loading no longer performs the extra anchor scan.
- M2 removed all dashboard reads of `payload.call_anchors` and `payload.thread_anchors`.
- `src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js` builds helper indexes, but adjacent-call lookup and render paths still need a focused large-history review.
- `scripts/benchmark_synthetic_history.py` benchmarks synthetic SQLite rows, but currently uses synthetic `source_file` paths that do not exercise source-log scanning.
- `.github/workflows/ci.yml`, `docs/development.md`, `docs/architecture.md`, and `AGENTS.md` run Node syntax checks for dashboard JS assets, but not yet for `dashboard_call_investigator.js`.

Already implemented before this branch:

- `scripts/check_release.py` already requires `src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js`.
- `scripts/check_release.py` already requires `codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js` in packaged distributions.
- `pyproject.toml` package-data coverage should include the dashboard asset through the existing dashboard asset glob; keep this verified in Milestone 1.

## Milestone Checklist

- [x] M0 inventory current state and create this checklist.
- [x] M0.1 contain calls-table horizontal overflow inside the table card.
- [x] M1 validate and package the call investigator dashboard asset in CI, docs, and release checks.
- [x] M2 remove low-value call/thread anchor diagnostics and their extra context source scan.
- [x] M3 persist aggregate call-origin metadata during indexing so dashboard payloads do not scan source logs.
- [ ] M4 persist cheap performance-critical dashboard query helper fields where feasible.
- [ ] M5 add optional timing diagnostics to `/api/usage` and `/api/context`.
- [ ] M6 make explicit context loading single-pass where practical.
- [ ] M7 precompute client-side call adjacency for investigator rendering.
- [ ] M8 add source-log-aware synthetic benchmark coverage.
- [ ] M9 add SQLite-backed live dashboard API slices while preserving `/api/usage`.
- [ ] M10 optionally materialize thread summaries after APIs are stable.
- [ ] M11 optionally add incremental source-file refresh metadata after parser-time call origin is stable.
- [ ] M12 finalize docs, validation, benchmark results, and merge-readiness notes.

## Validation Commands

Focused commands expected during this branch:

```bash
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_format.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js
python -m pytest tests/test_store_dashboard_mcp.py
python -m pytest tests/test_json_contracts.py
python -m pytest tests/test_privacy.py
python -m pytest tests/test_parser.py
python -m pytest tests/test_call_origin.py
python -m pytest tests/test_store_migrations.py
python scripts/check_release.py
python scripts/benchmark_synthetic_history.py --rows 10000 --json --enforce-thresholds
```

Full branch closeout should also run the release validation listed in `docs/development.md`.

## Files Touched

- `docs/call-drilldown-performance-checklist.md`
- `.github/workflows/ci.yml`
- `AGENTS.md`
- `CHANGELOG.md`
- `docs/architecture.md`
- `docs/development.md`
- `src/codex_usage_tracker/plugin_data/dashboard/dashboard.css`
- `src/codex_usage_tracker/context.py`
- `src/codex_usage_tracker/call_origin.py`
- `src/codex_usage_tracker/dashboard.py`
- `src/codex_usage_tracker/models.py`
- `src/codex_usage_tracker/parser.py`
- `src/codex_usage_tracker/schema.py`
- `src/codex_usage_tracker/store.py`
- `src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`
- `src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js`
- `docs/privacy.md`
- `tests/test_privacy.py`
- `tests/test_call_origin.py`
- `tests/test_parser.py`
- `tests/test_schema.py`
- `tests/test_store_dashboard_mcp.py`
- `tests/test_store_migrations.py`

## Tests Run

- M0 inventory:
  - `git status --short --branch`
  - `wc -l` over the requested source, docs, script, and CI files
  - `rg` source inspection for raw-log, context, dashboard payload, and JS validation hot paths
- M0.1 table overflow containment:
  - `python -m pytest tests/test_store_dashboard_mcp.py -q`
- M1 asset validation:
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js`
  - `python scripts/check_release.py`
- M2 anchor removal:
  - `python -m pytest tests/test_store_dashboard_mcp.py::test_dashboard_and_csv_are_aggregate_only tests/test_store_dashboard_mcp.py::test_context_loads_raw_log_only_on_demand tests/test_privacy.py::test_context_loading_is_explicit_redacted_and_not_static_html -q`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`
  - `python -m pytest tests/test_json_contracts.py -q`
  - `python -m pytest tests/test_privacy.py -q`
  - `python -m pytest tests/test_store_dashboard_mcp.py -q`
  - `python scripts/check_release.py`
- M3 persisted call-origin metadata:
  - `python -m pytest tests/test_call_origin.py tests/test_parser.py::test_parser_ignores_known_non_token_context_compaction_event tests/test_parser.py::test_parser_persists_call_origin_from_metadata_segments tests/test_store_dashboard_mcp.py::test_dashboard_payload_uses_persisted_call_origin_without_source_scan -q` failed before implementation because the pure classifier API was missing.
  - `python -m pytest tests/test_call_origin.py tests/test_parser.py::test_parser_ignores_known_non_token_context_compaction_event tests/test_parser.py::test_parser_persists_call_origin_from_metadata_segments tests/test_schema.py tests/test_store_migrations.py::test_init_db_migrates_legacy_aggregate_table_without_data_loss tests/test_store_migrations.py::test_csv_export_keeps_current_columns_after_legacy_migration tests/test_store_dashboard_mcp.py::test_dashboard_payload_uses_persisted_call_origin_without_source_scan -q`
  - `python -m pytest tests/test_parser.py tests/test_call_origin.py tests/test_store_migrations.py tests/test_privacy.py tests/test_store_dashboard_mcp.py -q`
  - `python scripts/check_release.py`

## Benchmarks Run

- None yet. M3 removed a source-log scan path and added regression tests; benchmark coverage starts in M8.

## Known Remaining Slow Paths

- Normal `dashboard_payload` no longer runs source-file call-origin annotation.
- Live `/api/usage` still calls `dashboard_payload`, but after M3 it should not open source JSONL files for call-origin metadata.
- Context loading still does selected-turn evidence and serialized-evidence work; Milestone 6 must verify whether that can be reduced to one source-file pass.
- Large-history live dashboard still ships broad payloads before the SQLite-backed API slice work.

## Privacy Notes

- Milestone 0 made no product behavior changes.
- The branch must keep all test data synthetic and must not persist raw transcript content.
- Persisted call-origin stores only categorical labels, reasons, and confidence values. Parser tests and privacy tests cover this with synthetic secret-bearing message/tool/compaction payloads.

## Merge Blockers

- `dashboard_payload` and `/api/usage` must stop opening source JSONL files. M3 covers the call-origin path; future milestones must preserve that invariant as APIs are split.
- The call investigator asset must be syntax-checked in CI and release validation.
- Raw call/thread anchors are removed; keep regression tests proving `call_anchors` and `thread_anchors` stay out of context payloads.
- Focused privacy tests must prove no raw prompts, assistant messages, tool output, replacement history, or raw JSONL fragments are persisted by default.
- Release checks and focused dashboard/context tests must pass before merge.

## Deferred Work

- Evidence cache is explicitly deferred.
- Materialized thread summaries are deferred until the SQLite-backed API path is stable.
- Incremental source-file refresh metadata is deferred until parser-time call origin is stable.
- Any frontend rewrite from `/api/usage` to the new SQLite-backed endpoints should be split if it becomes broad.

## Open Risks

- Persisting `previous_record_id` and `next_record_id` may require careful thread-key semantics to avoid misleading adjacency across attached sessions.
- Call-origin classification is heuristic and must be confidence-labeled.
- SQL-backed thread and recommendation endpoints may need additional indexes to avoid moving the bottleneck from browser JS to SQLite queries.
- Existing compatibility tests may encode static-dashboard assumptions that need narrow updates as live APIs are introduced.
