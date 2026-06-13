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
- M4 persists `is_archived`, `thread_key`, `thread_call_index`, `previous_record_id`, and `next_record_id` in `usage_events`.
- M4 updates active-history SQL filtering to use `is_archived` while still excluding migrated archived source paths when the new flag has only its default value.
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
- [x] M4 persist cheap performance-critical dashboard query helper fields where feasible.
- [x] M5 add optional timing diagnostics to `/api/usage` and `/api/context`.
- [x] M6 make explicit context loading single-pass where practical.
- [x] M7 precompute client-side call adjacency for investigator rendering.
- [x] M8 add source-log-aware synthetic benchmark coverage.
- [x] M9 add SQLite-backed live dashboard API slices while preserving `/api/usage`.
- [x] M10 optionally materialize thread summaries after APIs are stable.
- [x] M11 optionally add incremental source-file refresh metadata after parser-time call origin is stable.
- [x] M12 finalize docs, validation, benchmark results, and merge-readiness notes.

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
python scripts/benchmark_synthetic_history.py --rows 100 --batch-size 25 --with-source-logs --json --enforce-thresholds
```

Full branch closeout should also run the release validation listed in `docs/development.md`.

## Files Touched

- `docs/call-drilldown-performance-checklist.md`
- `.github/workflows/ci.yml`
- `AGENTS.md`
- `CHANGELOG.md`
- `docs/architecture.md`
- `docs/development.md`
- `scripts/benchmark_synthetic_history.py`
- `src/codex_usage_tracker/plugin_data/dashboard/dashboard.css`
- `src/codex_usage_tracker/context.py`
- `src/codex_usage_tracker/call_origin.py`
- `src/codex_usage_tracker/dashboard.py`
- `src/codex_usage_tracker/models.py`
- `src/codex_usage_tracker/parser.py`
- `src/codex_usage_tracker/schema.py`
- `src/codex_usage_tracker/store.py`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/json_contracts.py`
- `src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`
- `src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js`
- `src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`
- `docs/privacy.md`
- `docs/cli-json-schemas.md`
- `tests/test_dashboard_data.py`
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
- M4 dashboard query helper fields:
  - `python -m pytest tests/test_parser.py::test_parser_persists_dashboard_helper_metadata tests/test_store_dashboard_mcp.py::test_upsert_refreshes_thread_adjacency_fields tests/test_store_dashboard_mcp.py::test_dashboard_history_scope_excludes_archived_rows_by_default -q` failed before implementation because the helper fields were missing.
  - `python -m pytest tests/test_parser.py::test_parser_persists_dashboard_helper_metadata tests/test_store_dashboard_mcp.py::test_upsert_refreshes_thread_adjacency_fields tests/test_store_dashboard_mcp.py::test_dashboard_history_scope_excludes_archived_rows_by_default tests/test_store_migrations.py::test_init_db_migrates_legacy_aggregate_table_without_data_loss tests/test_schema.py -q`
  - `python -m pytest tests/test_store_migrations.py tests/test_store_dashboard_mcp.py tests/test_privacy.py -q`
  - `python scripts/check_release.py`
  - `git diff --check`
- M5 optional API timing diagnostics:
  - `python -m pytest tests/test_store_dashboard_mcp.py::test_dashboard_server_api_timing_diagnostics_are_opt_in_and_technical -q` failed before implementation because `diagnostics=true` did not return a diagnostics object.
  - `python -m pytest tests/test_store_dashboard_mcp.py::test_dashboard_server_api_timing_diagnostics_are_opt_in_and_technical -q`
  - `python -m pytest tests/test_store_dashboard_mcp.py -q`
  - `python -m pytest tests/test_privacy.py -q`
  - `python scripts/check_release.py`
- M6 single-pass context loading:
  - `python -m pytest tests/test_store_dashboard_mcp.py::test_context_loading_uses_one_source_scan_for_evidence_and_serialized_estimate -q` failed before implementation because one context load opened the same source JSONL twice.
  - `python -m pytest tests/test_store_dashboard_mcp.py::test_context_loading_uses_one_source_scan_for_evidence_and_serialized_estimate -q`
  - `python -m pytest tests/test_store_dashboard_mcp.py -q`
  - `python -m pytest tests/test_privacy.py -q`
  - `python -m pytest tests/test_json_contracts.py -q`
- M7 client-side call adjacency index:
  - `python -m pytest tests/test_dashboard_data.py -q`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`
  - `python scripts/check_release.py`
- M8 source-log-aware synthetic benchmark coverage:
  - `python scripts/benchmark_synthetic_history.py --rows 100 --batch-size 25 --with-source-logs --json --enforce-thresholds` could not run because bare `python` is not installed on this machine.
  - `.venv/bin/python scripts/benchmark_synthetic_history.py --rows 100 --batch-size 25 --with-source-logs --json --enforce-thresholds`
  - `.venv/bin/python -m pytest tests/test_cli_release.py -q`
  - `.venv/bin/python scripts/benchmark_synthetic_history.py --rows 2000 --with-source-logs --json --enforce-thresholds`
- M9 SQLite-backed live dashboard API slices:
  - `.venv/bin/python -m pytest tests/test_store_dashboard_mcp.py::test_dashboard_server_live_sql_api_slices_are_aggregate_only -q`
  - `.venv/bin/python -m pytest tests/test_store_dashboard_mcp.py -q`
  - `.venv/bin/python -m pytest tests/test_json_contracts.py -q` initially failed because the new live API schema ids were not tracked; after adding contracts and docs, it passed.
  - `.venv/bin/python -m pytest tests/test_privacy.py -q`
  - `.venv/bin/python scripts/check_release.py`
- M10 materialized thread summaries:
  - `.venv/bin/python -m pytest tests/test_store_dashboard_mcp.py::test_upsert_materializes_thread_summaries tests/test_store_dashboard_mcp.py::test_thread_summaries_keep_active_and_all_history_scopes_separate tests/test_store_dashboard_mcp.py::test_dashboard_server_live_sql_api_slices_are_aggregate_only tests/test_store_migrations.py::test_init_db_migrates_legacy_aggregate_table_without_data_loss -q`
  - `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py tests/test_store_dashboard_mcp.py tests/test_store_migrations.py`
- M11 incremental source-file refresh metadata:
  - `.venv/bin/python -m pytest tests/test_store_dashboard_mcp.py::test_refresh_is_idempotent_and_summary_works tests/test_store_dashboard_mcp.py::test_refresh_indexes_only_appended_token_events_when_source_grows tests/test_store_dashboard_mcp.py::test_refresh_reports_skipped_corrupt_token_events tests/test_store_migrations.py::test_refresh_is_idempotent_after_legacy_migration tests/test_store_migrations.py::test_init_db_migrates_legacy_aggregate_table_without_data_loss -q`
  - `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py tests/test_store_dashboard_mcp.py tests/test_store_migrations.py`
  - `.venv/bin/python -m pytest tests/test_store_dashboard_mcp.py tests/test_store_migrations.py tests/test_privacy.py -q`
  - `.venv/bin/python -m mypy`
- M12 final validation:
  - `.venv/bin/python -m ruff check .`
  - `.venv/bin/python -m mypy`
  - `.venv/bin/python -m pytest -q`
  - `.venv/bin/python -m pytest --cov=codex_usage_tracker --cov-report=term-missing`
  - `.venv/bin/python -m compileall src`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_format.js`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`
  - `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js`
  - `.venv/bin/python scripts/check_release.py`
  - `git diff --check`
  - `rm -rf dist build src/codex_usage_tracker.egg-info src/codex_usage_tracking.egg-info`
  - `.venv/bin/python -m build`
  - `.venv/bin/python -m twine check dist/*`
  - `.venv/bin/python scripts/check_release.py --dist`
  - `.venv/bin/python scripts/smoke_installed_package.py`
  - `.venv/bin/python scripts/smoke_installed_package.py --docker`

## Benchmarks Run

- M4:
  - `python scripts/benchmark_synthetic_history.py --rows 10000 --json --enforce-thresholds` initially failed after adjacency updates because population took `9.479820s` against a `1.600000s` threshold.
  - After deferring bulk link recomputation and materializing the link window update, the same command passed. Latest recorded 10k timings included `populate_seconds: 0.357407`, `active_dashboard_query_seconds: 0.017709`, `dashboard_payload_active_seconds: 0.072064`, and no threshold failures.
- M8:
  - `.venv/bin/python scripts/benchmark_synthetic_history.py --rows 100 --batch-size 25 --with-source-logs --json --enforce-thresholds` passed. Latest recorded source-log timings included `dashboard_payload_with_source_logs_seconds: 0.039320`, `context_load_early_line_seconds: 0.211319`, `context_load_middle_line_seconds: 0.003791`, and `context_load_late_line_seconds: 0.003682`, with `2` synthetic source logs and no threshold failures.
  - `.venv/bin/python scripts/benchmark_synthetic_history.py --rows 2000 --with-source-logs --json --enforce-thresholds` passed. Latest recorded source-log timings included `dashboard_payload_with_source_logs_seconds: 0.047490`, `context_load_early_line_seconds: 0.209456`, `context_load_middle_line_seconds: 0.002840`, and `context_load_late_line_seconds: 0.012454`, with `8` synthetic source logs and no threshold failures.
- M12:
  - `.venv/bin/python scripts/benchmark_synthetic_history.py --rows 10000 100000 --json --enforce-thresholds` initially failed only the `populate_seconds` threshold after M10/M11 made populate maintain materialized thread summaries and source-file metadata. The populate sentinel was recalibrated from `0.60` to `0.90` seconds per 10k rows while leaving read-path thresholds unchanged. Final 100k run passed with `populate_seconds: 6.887096`, `dashboard_payload_active_seconds: 0.163591`, `thread_summary_seconds: 0.144897`, and no threshold failures.
  - `.venv/bin/python scripts/benchmark_synthetic_history.py --rows 1000 --with-source-logs --json --enforce-thresholds` passed with `dashboard_payload_with_source_logs_seconds: 0.040977`, `context_load_early_line_seconds: 0.188511`, `context_load_middle_line_seconds: 0.002758`, `context_load_late_line_seconds: 0.011821`, `4` synthetic source logs, and no threshold failures.

## Known Remaining Slow Paths

- Normal `dashboard_payload` no longer runs source-file call-origin annotation.
- Live `/api/usage` still calls `dashboard_payload`, but after M3 it should not open source JSONL files for call-origin metadata. M9 preserves this compatibility endpoint while adding SQL-backed live API slices; only direct investigator hydration currently consumes `/api/call` from the frontend.
- Active/all-history filtering now has a persisted `is_archived` flag and path fallback; future SQLite-backed API slices should reuse that helper instead of reintroducing path-only filtering.
- Per-thread adjacency is persisted after upsert and M7 makes the browser build a `record_id` adjacency index once per payload. Investigator lookup now uses that index and prefers loaded `previous_record_id`/`next_record_id` neighbors when available.
- Context loading defaults to `mode=quick`, which reads selected-turn evidence in one source-file scan, omits tool output, and returns a fast serialized upper-bound estimate without building tokenizer-counted serialized groups. `mode=full` / `Run full serialized analysis` keeps the richer serialized group analysis available on demand and times it separately as `serialized_estimate_ms`.
- M8 source-log benchmark mode now generates synthetic JSONL files, points synthetic aggregate rows at matching `token_count` lines, measures early/middle/late explicit context loads, and wraps source-log dashboard payload assembly with a guard that fails if a synthetic source file is opened.
- M9 adds additive SQL-backed live endpoints: `/api/status`, `/api/calls`, `/api/call`, `/api/threads`, `/api/thread-calls`, `/api/summary`, and `/api/recommendations`. The list/table frontend still uses `/api/usage` until a later split, while direct call-investigator fallback uses `/api/call`.
- Direct `view=call&record=...` investigator links can hydrate the selected aggregate row through `/api/call` when the current dashboard payload is filtered, stale, or does not include that record.
- M10 materializes per-thread active and all-history summary rows in SQLite so `/api/threads` can read pre-aggregated thread totals without grouping every usage row on each request.
- M11 adds a `source_files` metadata table with aggregate-only parser cursors. Refresh skips unchanged logs, seeks to the last indexed byte for append-only growth when a cursor is available, and fully replaces aggregate rows for changed/truncated source files.
- M5 adds opt-in timing fields for `/api/usage?diagnostics=true` and `/api/context?...&diagnostics=true`; diagnostics are technical metrics only and are absent unless explicitly requested.
- Static dashboard generation remains supported as the export/compatibility path; M9 added live API slices without removing generated dashboard HTML.
- Source-log reads are limited to refresh/indexing, explicit `/api/context` loading for one selected call, and explicit benchmark/diagnostic tooling. Normal `dashboard_payload` and `/api/usage` must remain aggregate-only.
- No evidence cache was implemented in this branch.
- Per-call byte offsets for context loading remain future work. Late calls in very large source JSONL files can still require scanning to the selected token line, although the default quick mode avoids the previous serialized-group cost.

## Privacy Notes

- Milestone 0 made no product behavior changes.
- The branch must keep all test data synthetic and must not persist raw transcript content.
- Persisted call-origin stores only categorical labels, reasons, and confidence values. Parser tests and privacy tests cover this with synthetic secret-bearing message/tool/compaction payloads.
- M4 persisted only aggregate navigation/scope fields: archived flag, conservative thread key, call index, and adjacent aggregate record ids.
- M5 diagnostics do not include raw text, prompts, tool output, source paths, or JSONL filenames. Context diagnostics include source file byte count and source line number only because the context payload itself already requires explicit token-protected on-demand loading.
- M9 live dashboard APIs return aggregate SQLite data and explicitly keep raw context out of status, calls, call, threads, thread-calls, summary, recommendations, and compatibility usage payloads.

## Merge Blockers

- `dashboard_payload` and `/api/usage` must stop opening source JSONL files. M3 covers the call-origin path; future milestones must preserve that invariant as APIs are split.
- The call investigator asset must be syntax-checked in CI and release validation.
- Raw call/thread anchors are removed; keep regression tests proving `call_anchors` and `thread_anchors` stay out of context payloads.
- Focused privacy tests must prove no raw prompts, assistant messages, tool output, replacement history, or raw JSONL fragments are persisted by default.
- Release checks and focused dashboard/context tests must pass before merge.

## Deferred Work

- Evidence cache is explicitly deferred.
- Any frontend rewrite from `/api/usage` to the new SQLite-backed endpoints should be split if it becomes broad.

## Open Risks

- Persisting `previous_record_id` and `next_record_id` may require careful thread-key semantics to avoid misleading adjacency across attached sessions.
- Call-origin classification is heuristic and must be confidence-labeled.
- SQL-backed thread and recommendation endpoints may need additional indexes to avoid moving the bottleneck from browser JS to SQLite queries.
- Existing compatibility tests may encode static-dashboard assumptions that need narrow updates as live APIs are introduced.
