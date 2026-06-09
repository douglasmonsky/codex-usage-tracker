# 1.0 Readiness

This checklist tracks the work needed to move from the first public PyPI releases toward a stable 1.0 contract. Keep all verification data synthetic or aggregate-only.

Each completed checkbox names the primary verification command inline. The evidence reference section at the end maps those commands to the concrete tests, scripts, workflow checks, or public-install smokes that prove the completed items.

## Compatibility Promise

- CLI command names documented in `docs/cli-reference.md` are stable after 1.0.
- JSON schema IDs documented in `docs/cli-json-schemas.md` are stable after 1.0.
- New JSON fields may be added in minor releases, but existing required fields should not be removed or change type without a new schema version.
- MCP tool names and response schemas are stable after 1.0.
- CSV export columns are stable after 1.0 unless a new export schema or version flag is introduced.
- Config file schemas for pricing, allowance, thresholds, projects, and rate cards are stable after 1.0.
- Privacy-mode semantics are stable after 1.0.
- SQLite migrations must support upgrade from the last pre-1.0 release to 1.0.

Not guaranteed:

- Codex upstream log format stability.
- OpenAI pricing or rate-card source stability.
- Automatic access to live account allowance.
- Exact billing equivalence.

## 1. Public Install And Package Metadata

- [x] Verify the current public PyPI version is visible as `0.4.0`: `python -c "import json, urllib.request; print(json.load(urllib.request.urlopen('https://pypi.org/pypi/codex-usage-tracking/json'))['info']['version'])"`.
- [x] Verify public venv install for `0.4.0`: `python -m venv /tmp/codex-usage-pypi-smoke && . /tmp/codex-usage-pypi-smoke/bin/activate && python -m pip install codex-usage-tracking==0.4.0 && codex-usage-tracker --version`.
- [x] Verify public pipx install path for `0.4.0`: `PIPX_HOME=/tmp/codex-usage-pipx-home PIPX_BIN_DIR=/tmp/codex-usage-pipx-bin pipx install codex-usage-tracking==0.4.0 && /tmp/codex-usage-pipx-bin/codex-usage-tracker --version`.
- [x] Verify installed package resources from a built wheel: `python scripts/smoke_installed_package.py`.
- [x] Verify installed package resources in Linux Docker: `python scripts/smoke_installed_package.py --docker`.
- [x] Verify public PyPI package in Docker: `python scripts/smoke_installed_package.py --docker --from-pypi --version 0.4.0`.
- [x] Verify PyPI metadata names remain unchanged: `python scripts/check_release.py`.
- [x] Add Python 3.14 as an official support target after CI, package classifiers, docs, and installed-package smoke coverage were added. Docker smoke coverage uses `python:3.14-slim` by default. Track this in issue #12.

## 2. Upgrade And Migration

- [x] Add synthetic legacy SQLite fixture test proving `init_db` upgrades without data loss: `python -m pytest tests/test_store_migrations.py`.
- [ ] Add synthetic v0.3-style SQLite fixture if schema drift requires it: `python -m pytest tests/test_store_migrations.py`.
- [x] Verify `schema_state` reports expected version and checksum after migration: `python -m pytest tests/test_store_migrations.py`.
- [x] Verify `rebuild-index` clears only tracker-owned aggregate tables: `python -m pytest tests/test_store_dashboard_mcp.py`.
- [x] Verify `reset-db` does not touch raw Codex logs: `python -m pytest tests/test_cli_lifecycle.py`.
- [x] Verify refresh metadata and parser diagnostics survive migration: `python -m pytest tests/test_store_migrations.py tests/test_parser.py`.
- [x] Verify CSV export columns after migration: `python -m pytest tests/test_store_migrations.py`.

## 3. CLI Compatibility

- [x] Confirm every documented command in `docs/cli-reference.md` exists: `python -m pytest tests/test_cli_release.py`.
- [x] Confirm no documented command is removed without a deprecation plan: manual diff review plus `python -m pytest tests/test_cli_release.py`.
- [x] Verify command help works from an installed wheel: `python scripts/smoke_installed_package.py`.
- [x] Verify lifecycle commands still return actionable errors without real logs: `python -m pytest tests/test_cli_lifecycle.py`.

## 4. MCP Compatibility

- [x] Verify MCP tool names remain documented in `docs/mcp.md`: `python -m pytest tests/test_cli_release.py`.
- [x] Verify MCP JSON responses use tracked schema IDs where applicable: `python -m pytest tests/test_store_dashboard_mcp.py`.
- [x] Verify companion skill packaged copy matches source skill: `python scripts/check_release.py`.
- [x] Verify plugin installer writes MCP config from an installed wheel: `python scripts/smoke_installed_package.py`.

## 5. JSON Contract Stability

- [x] Verify every documented `--json` command has a tracked schema: `python -m pytest tests/test_json_contracts.py`.
- [x] Verify every schema in `docs/cli-json-schemas.md` exists in `src/codex_usage_tracker/json_contracts.py`: `python -m pytest tests/test_json_contracts.py`.
- [x] Verify every schema in `json_contracts.py` is documented: `python -m pytest tests/test_json_contracts.py`.
- [x] Verify known payload examples pass `validate_json_payload_contract`: `python -m pytest tests/test_json_contracts.py`.
- [x] Verify invalid or missing required fields fail contract validation: `python -m pytest tests/test_json_contracts.py`.
- [x] Cover query, recommendations, summary, session, doctor, pricing-coverage, dashboard, export, support-bundle, and plugin lifecycle JSON payload contracts: `python -m pytest tests/test_json_contracts.py`.

## 6. CSV Export Stability

- [x] Verify expected CSV columns for aggregate exports: `python -m pytest tests/test_cli_lifecycle.py`.
- [x] Verify redacted and strict privacy CSV exports omit private metadata: `python -m pytest tests/test_privacy.py`.
- [x] Verify migration fixtures still export the expected CSV shape: `python -m pytest tests/test_store_migrations.py`.

## 7. Config File Stability

- [x] Verify pricing config initialization and parsing: `python -m pytest tests/test_pricing.py`.
- [x] Verify allowance and rate-card config initialization and parsing: `python -m pytest tests/test_allowance.py`.
- [x] Verify threshold config initialization and parsing: `python -m pytest tests/test_recommendations.py`.
- [x] Verify project alias/tag config initialization and parsing: `python -m pytest tests/test_projects.py`.
- [x] Document config schema changes before release: manual review of `docs/pricing-and-credits.md`, `docs/dashboard-guide.md`, and `docs/cli-reference.md`; enforced by `python -m pytest tests/test_cli_release.py`.

## 8. Dashboard Behavior

- [x] Verify dashboard aggregate payload remains raw-context-free: `python -m pytest tests/test_store_dashboard_mcp.py`.
- [x] Verify dashboard URL state round trips: `python -m pytest tests/test_dashboard_state.py`.
- [x] Verify dashboard formatting helpers: `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_format.js`.
- [x] Verify dashboard data helpers: `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`.
- [x] Verify active-history and all-history state labels: `python -m pytest tests/test_cli_release.py tests/test_store_dashboard_mcp.py`.
- [ ] Run a manual localhost dashboard smoke before release: `codex-usage-tracker serve-dashboard --open`.

## 9. Privacy And Sharing Safety

- [x] Verify dashboard payloads in normal, redacted, and strict modes: `python -m pytest tests/test_privacy.py`.
- [x] Verify query JSON in normal, redacted, and strict modes: `python -m pytest tests/test_privacy.py`.
- [x] Verify session JSON in normal, redacted, and strict modes: `python -m pytest tests/test_privacy.py`.
- [x] Verify CSV export in redacted and strict modes: `python -m pytest tests/test_privacy.py`.
- [x] Verify strict mode does not leak raw cwd, source paths, branch, remote labels, project tags, or synthetic private project names: `python -m pytest tests/test_privacy.py`.
- [x] Verify raw context fields never appear in SQLite, CSV, dashboard payloads, support bundles, generated static HTML, docs, or screenshots: `python -m pytest tests/test_privacy.py scripts/check_release.py`.

## 10. Support-Bundle Safety

- [x] Verify support bundles include package version, Python version, OS/platform, doctor status, schema state, parser diagnostics, pricing status, allowance status, threshold status, project config status, and privacy metadata: `python -m pytest tests/test_support.py`.
- [x] Verify support bundles exclude raw logs, prompt text, assistant text, tool output, context text, and raw source paths in strict mode: `python -m pytest tests/test_support.py`.
- [x] Update issue templates to request only strict-mode support bundles: `python scripts/check_release.py`.

## 11. Large-History Performance

- [x] Run synthetic 10k benchmark: `python scripts/benchmark_synthetic_history.py --rows 10000 --json --enforce-thresholds`.
- [x] Run synthetic 100k benchmark: `python scripts/benchmark_synthetic_history.py --rows 100000 --json --enforce-thresholds`.
- [x] Run synthetic 500k benchmark as a release gate when practical: `python scripts/benchmark_synthetic_history.py --rows 500000 --json --enforce-thresholds`.
- [x] Define thresholds for active-only dashboard query, all-history dashboard query, since/until, model/effort, min_tokens, recommendations, pricing coverage, and project summary.
- [x] Add a smaller CI-safe benchmark if it can stay fast and deterministic.

## 12. Release Process

- [x] Verify publish workflow publishes `codex-usage-tracking`, not `codex-usage-tracker`: `python scripts/check_release.py`.
- [x] Verify publish workflow uses Trusted Publishing, not API tokens: `python scripts/check_release.py`.
- [x] Verify TestPyPI and PyPI jobs exist and publish only on workflow dispatch or release events: `python scripts/check_release.py`.
- [x] Verify manual PyPI workflow dispatch is restricted to `main` or tag refs: `python scripts/check_release.py`.
- [ ] Verify PyPI job is gated by environment `pypi`: manual GitHub environment check.
- [x] Verify dist filenames match `codex_usage_tracking`: `python -m build && python scripts/check_release.py --dist`.
- [ ] Verify TestPyPI process: run `Publish Python package` with `target=testpypi` only when intentionally testing release publication.
- [ ] Verify PyPI process: publish a GitHub Release or run workflow dispatch with `target=pypi` only when intentionally publishing a reviewed release.
- [x] Document release recovery by cutting a new patch version when an uploaded artifact is wrong: see `docs/development.md`.

## 13. Known Limitations

- [x] Document that Codex upstream log formats can change and parser compatibility may require updates.
- [x] Document that pricing and rate-card sources can change outside this project.
- [x] Document that live account allowance cannot be read automatically by this local tracker.
- [x] Document that cost and credit estimates are not guaranteed to match exact billing.
- [x] Document platform/plugin discovery limitations separately from the core Python CLI/dashboard support.

## Evidence References

These references are the concrete proof behind completed checklist items. Public package smoke commands are version-specific to `0.4.0`; all repo tests use synthetic or aggregate-only data.

### Public Install And Package Metadata

- Public PyPI version, public venv install, and public pipx install are proven by the exact public-install commands in section 1.
- Built-wheel and installed-resource coverage is proven by `scripts/smoke_installed_package.py` and `tests/test_cli_release.py::test_installed_package_smoke_checks_help_for_stable_commands`.
- Linux package-resource coverage is proven by `scripts/smoke_installed_package.py --docker`.
- Public PyPI Docker coverage is proven by `scripts/smoke_installed_package.py --docker --from-pypi --version 0.4.0`.
- PyPI metadata, package/distribution names, package resources, source/wheel member names, Python 3.10-3.14 support metadata, CI workflow requirements, publish workflow safety text, and tracked secret patterns are proven by `scripts/check_release.py`, `scripts/check_release.py --dist`, and `tests/test_cli_release.py::test_release_check_script_passes`.

### Upgrade And Migration

- Legacy SQLite migration, schema state, migration idempotence, malformed legacy schema handling, and migration CSV shape are proven by `tests/test_store_migrations.py`.
- `rebuild-index` clearing only tracker-owned aggregate rows is proven by `tests/test_store_dashboard_mcp.py::test_rebuild_index_clears_aggregate_rows_before_rescan`.
- `reset-db` preserving raw Codex logs is proven by `tests/test_cli_lifecycle.py::test_setup_support_bundle_and_reset_db_cli`.
- Refresh metadata and parser diagnostics are proven by `tests/test_store_migrations.py`, `tests/test_parser.py`, and `tests/test_store_dashboard_mcp.py::test_refresh_reports_skipped_corrupt_token_events`.

### CLI Compatibility

- Documented CLI command existence and stable command coverage are proven by `tests/test_cli_release.py::test_cli_reference_documents_only_existing_stable_commands` and `tests/test_cli_release.py::test_stable_cli_commands_are_not_removed_without_a_deprecation_plan`.
- Installed-wheel subcommand help coverage is proven by `scripts/smoke_installed_package.py` and guarded by `tests/test_cli_release.py::test_installed_package_smoke_checks_help_for_stable_commands`.
- Lifecycle actionable errors without real logs are proven by `tests/test_cli_lifecycle.py::test_lifecycle_commands_return_actionable_errors_without_real_logs`.

### MCP Compatibility

- MCP tool documentation parity is proven by `tests/test_cli_release.py::test_mcp_tool_names_remain_documented`.
- MCP JSON response schema IDs and wrapper payload contracts are proven by `tests/test_store_dashboard_mcp.py::test_mcp_wrappers_smoke`.
- Companion skill source/package parity is proven by `scripts/check_release.py`.
- Installed-wheel plugin MCP config is proven by `scripts/smoke_installed_package.py`.

### JSON Contract Stability

- Documented schema table parity, runtime schema ID tracking, example validation, invalid-payload rejection, and minimal payload validation are proven by `tests/test_json_contracts.py`.
- README and CLI schema doc references are additionally guarded by `tests/test_cli_release.py::test_cli_json_schema_doc_lists_tracked_contracts`.

### CSV Export Stability

- Aggregate CSV columns are proven by `tests/test_cli_lifecycle.py::test_report_json_and_query_cli`.
- Redacted and strict privacy CSV behavior is proven by `tests/test_privacy.py::test_privacy_modes_cover_dashboard_query_session_and_csv` and `tests/test_privacy.py::test_aggregate_outputs_exclude_raw_transcript_content`.
- Migration CSV shape is proven by `tests/test_store_migrations.py::test_csv_export_keeps_current_columns_after_legacy_migration`.

### Config File Stability

- Pricing config initialization and parsing are proven by `tests/test_pricing.py` and `tests/test_cli_lifecycle.py::test_rate_card_allowance_and_pricing_snapshot_cli`.
- Allowance and Codex rate-card config initialization/parsing are proven by `tests/test_allowance.py` and `tests/test_cli_lifecycle.py::test_rate_card_allowance_and_pricing_snapshot_cli`.
- Threshold config initialization/parsing is proven by `tests/test_recommendations.py::test_threshold_template_and_overrides`.
- Project alias, ignored-path, tag, and privacy behavior is proven by `tests/test_projects.py`.
- Config schema documentation coverage is proven by `tests/test_cli_release.py::test_local_config_schema_docs_reference_stable_fields`.

### Dashboard Behavior

- Aggregate-only dashboard payloads and CSV are proven by `tests/test_store_dashboard_mcp.py::test_dashboard_and_csv_are_aggregate_only` and `tests/test_privacy.py::test_aggregate_outputs_exclude_raw_transcript_content`.
- URL-state round trips are proven by `tests/test_dashboard_state.py::test_dashboard_url_state_round_trips`.
- Dashboard helper syntax is proven by the `node --check` commands in section 8 and the CI dashboard JavaScript syntax job.
- Active/all-history payload behavior is proven by `tests/test_store_dashboard_mcp.py::test_dashboard_history_scope_excludes_archived_rows_by_default` and `tests/test_store_dashboard_mcp.py::test_dashboard_server_usage_api_switches_history_scope`.
- Active/all-history user-facing labels are proven by `tests/test_cli_release.py::test_dashboard_history_scope_labels_remain_user_facing`.
- No-context startup and runtime context enablement are proven by `tests/test_store_dashboard_mcp.py::test_dashboard_server_can_enable_context_api_at_runtime` and `tests/test_privacy.py::test_context_server_requires_loopback_origin_token_and_enablement`.

### Privacy And Sharing Safety

- Dashboard, query, session, CSV, support-bundle, and generated-static-HTML privacy behavior is proven by `tests/test_privacy.py`.
- Strict project metadata redaction is proven by `tests/test_privacy.py::test_privacy_modes_cover_dashboard_query_session_and_csv` and `tests/test_projects.py::test_project_privacy_modes_redact_sensitive_metadata`.
- Raw context exclusion and explicit context loading are proven by `tests/test_privacy.py::test_context_loading_is_explicit_redacted_and_not_static_html`, `tests/test_privacy.py::test_context_server_requires_loopback_origin_token_and_enablement`, and `tests/test_store_dashboard_mcp.py::test_context_loads_raw_log_only_on_demand`.
- Tracked-file secret scanning is proven by `scripts/check_release.py`.

### Support-Bundle Safety

- Support-bundle payload shape and secret safety are proven by `tests/test_support.py::test_support_bundle_default_mode_contract_and_secret_safety`.
- Strict support-bundle path and doctor-text redaction is proven by `tests/test_support.py::test_support_bundle_strict_mode_redacts_local_paths_and_doctor_text`.
- Safe issue-template requests are proven by `scripts/check_release.py`.

### Large-History Performance

- Benchmark command behavior and threshold contract are smoke-tested by `tests/test_cli_release.py::test_synthetic_history_benchmark_script_smoke`.
- Release-size 10k, 100k, and 500k benchmark claims are proven by running `python scripts/benchmark_synthetic_history.py --rows 10000 100000 500000 --json --enforce-thresholds` before release work when practical.
- CI-safe benchmark coverage is proven by the CI `Release readiness` job through `tests/test_cli_release.py::test_synthetic_history_benchmark_script_smoke`.

### Release Process

- Normal CI package build plus `twine check` and dist verification are proven by `.github/workflows/ci.yml` and enforced by `scripts/check_release.py::_check_ci_workflow`.
- Publish workflow package name, Trusted Publishing, TestPyPI/PyPI job presence, event guards, no push/PR publishing, no token/password publishing, and manual PyPI main/tag preflight are proven by `scripts/check_release.py::_check_publish_workflow`.
- Dist filename and wheel/sdist member checks are proven by `python -m build`, `python -m twine check dist/*`, and `python scripts/check_release.py --dist`.
- Release recovery documentation is proven by `scripts/check_release.py` required-file and docs checks.

### Known Limitations

- Parser-format drift, pricing/rate-card drift, live allowance, non-billing-equivalence, and plugin-discovery boundary documentation are proven by `tests/test_cli_release.py::test_known_limitations_are_documented`.
