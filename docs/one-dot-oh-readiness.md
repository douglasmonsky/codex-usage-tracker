# 1.0 Readiness

This checklist tracks the work needed to move from the first public PyPI releases toward a stable 1.0 contract. Keep all verification data synthetic or aggregate-only.

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

- [x] Verify the current public PyPI version is visible: `python -c "import json, urllib.request; print(json.load(urllib.request.urlopen('https://pypi.org/pypi/codex-usage-tracking/json'))['info']['version'])"`.
- [x] Verify public venv install: `python -m venv /tmp/codex-usage-pypi-smoke && . /tmp/codex-usage-pypi-smoke/bin/activate && python -m pip install codex-usage-tracking && codex-usage-tracker --version`.
- [x] Verify public pipx install path: `pipx install codex-usage-tracking && codex-usage-tracker --version`, with `pipx ensurepath` or the printed pipx app directory when needed.
- [x] Verify installed package resources from a built wheel: `python scripts/smoke_installed_package.py`.
- [x] Verify installed package resources in Linux Docker: `python scripts/smoke_installed_package.py --docker`.
- [x] Verify public PyPI package in Docker: `python scripts/smoke_installed_package.py --docker --from-pypi --version <version>`.
- [ ] Verify PyPI metadata names remain unchanged: `python scripts/check_release.py`.

## 2. Upgrade And Migration

- [ ] Add synthetic v0.2-style SQLite fixture test proving `init_db` upgrades without data loss: `python -m pytest tests/test_store_migrations.py`.
- [ ] Add synthetic v0.3-style SQLite fixture if schema drift requires it: `python -m pytest tests/test_store_migrations.py`.
- [ ] Verify `schema_state` reports expected version and checksum after migration: `python -m pytest tests/test_store_migrations.py`.
- [ ] Verify `rebuild-index` clears only tracker-owned aggregate tables: `python -m pytest tests/test_cli_lifecycle.py`.
- [ ] Verify `reset-db` does not touch raw Codex logs: `python -m pytest tests/test_cli_lifecycle.py`.
- [ ] Verify refresh metadata and parser diagnostics survive migration: `python -m pytest tests/test_store_migrations.py tests/test_parser.py`.
- [ ] Verify CSV export columns after migration: `python -m pytest tests/test_cli_lifecycle.py`.

## 3. CLI Compatibility

- [ ] Confirm every documented command in `docs/cli-reference.md` exists: `python -m pytest tests/test_cli_release.py`.
- [ ] Confirm no documented command is removed without a deprecation plan: manual diff review plus `python -m pytest tests/test_cli_release.py`.
- [ ] Verify command help works from an installed wheel: `python scripts/smoke_installed_package.py`.
- [ ] Verify lifecycle commands still return actionable errors without real logs: `python -m pytest tests/test_cli_lifecycle.py`.

## 4. MCP Compatibility

- [ ] Verify MCP tool names remain documented in `docs/mcp.md`: `python scripts/check_release.py`.
- [ ] Verify MCP JSON responses use tracked schema IDs where applicable: `python -m pytest tests/test_store_dashboard_mcp.py`.
- [ ] Verify companion skill packaged copy matches source skill: `python scripts/check_release.py`.
- [ ] Verify plugin installer writes MCP config from an installed wheel: `python scripts/smoke_installed_package.py`.

## 5. JSON Contract Stability

- [ ] Verify every documented `--json` command has a tracked schema: `python -m pytest tests/test_json_contracts.py`.
- [ ] Verify every schema in `docs/cli-json-schemas.md` exists in `src/codex_usage_tracker/json_contracts.py`: `python -m pytest tests/test_cli_release.py`.
- [ ] Verify every schema in `json_contracts.py` is documented: `python -m pytest tests/test_json_contracts.py`.
- [ ] Verify known payload examples pass `validate_json_payload_contract`: `python -m pytest tests/test_json_contracts.py`.
- [ ] Verify invalid or missing required fields fail contract validation: `python -m pytest tests/test_json_contracts.py`.
- [ ] Cover query, recommendations, summary, session, doctor, pricing-coverage, dashboard, export, support-bundle, and plugin lifecycle JSON payloads: `python -m pytest tests/test_json_contracts.py`.

## 6. CSV Export Stability

- [ ] Verify expected CSV columns for aggregate exports: `python -m pytest tests/test_cli_lifecycle.py`.
- [ ] Verify redacted and strict privacy CSV exports omit private metadata: `python -m pytest tests/test_privacy.py`.
- [ ] Verify migration fixtures still export the expected CSV shape: `python -m pytest tests/test_store_migrations.py`.

## 7. Config File Stability

- [ ] Verify pricing config initialization and parsing: `python -m pytest tests/test_pricing.py`.
- [ ] Verify allowance and rate-card config initialization and parsing: `python -m pytest tests/test_allowance.py`.
- [ ] Verify threshold config initialization and parsing: `python -m pytest tests/test_recommendations.py`.
- [ ] Verify project alias/tag config initialization and parsing: `python -m pytest tests/test_projects.py`.
- [ ] Document config schema changes before release: manual review of `docs/pricing-and-credits.md`, `docs/dashboard-guide.md`, and `docs/cli-reference.md`.

## 8. Dashboard Behavior

- [ ] Verify dashboard aggregate payload remains raw-context-free: `python -m pytest tests/test_store_dashboard_mcp.py`.
- [ ] Verify dashboard URL state round trips: `python -m pytest tests/test_dashboard_state.py`.
- [ ] Verify dashboard formatting helpers: `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_format.js`.
- [ ] Verify dashboard data helpers: `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`.
- [ ] Verify active-history and all-history state labels: `python -m pytest tests/test_store_dashboard_mcp.py`.
- [ ] Run a manual localhost dashboard smoke before release: `codex-usage-tracker serve-dashboard --open`.

## 9. Privacy And Sharing Safety

- [ ] Verify dashboard payloads in normal, redacted, and strict modes: `python -m pytest tests/test_privacy.py`.
- [ ] Verify query JSON in normal, redacted, and strict modes: `python -m pytest tests/test_privacy.py`.
- [ ] Verify session JSON in normal, redacted, and strict modes: `python -m pytest tests/test_privacy.py`.
- [ ] Verify CSV export in redacted and strict modes: `python -m pytest tests/test_privacy.py`.
- [ ] Verify strict mode does not leak raw cwd, source paths, branch, remote labels, project tags, or synthetic private project names: `python -m pytest tests/test_privacy.py`.
- [ ] Verify raw context fields never appear in SQLite, CSV, dashboard payloads, support bundles, docs, screenshots, or synthetic fixtures: `python -m pytest tests/test_privacy.py scripts/check_release.py`.

## 10. Support-Bundle Safety

- [ ] Verify support bundles include package version, Python version, OS/platform, doctor status, schema state, parser diagnostics, pricing status, allowance status, threshold status, project config status, and privacy metadata: `python -m pytest tests/test_support.py`.
- [ ] Verify support bundles exclude raw logs, prompt text, assistant text, tool output, context text, and raw source paths in strict mode: `python -m pytest tests/test_support.py`.
- [ ] Update issue templates to request only strict-mode support bundles: manual review of `.github/ISSUE_TEMPLATE/`.

## 11. Large-History Performance

- [ ] Run synthetic 10k benchmark: `python scripts/benchmark_synthetic_history.py --rows 10000 --json`.
- [ ] Run synthetic 100k benchmark: `python scripts/benchmark_synthetic_history.py --rows 100000 --json`.
- [ ] Run synthetic 500k benchmark as a release gate when practical: `python scripts/benchmark_synthetic_history.py --rows 500000 --json`.
- [ ] Define thresholds for active-only dashboard query, all-history dashboard query, since/until, model/effort, min_tokens, recommendations, pricing coverage, and project summary.
- [ ] Add a smaller CI-safe benchmark if it can stay fast and deterministic.

## 12. Release Process

- [ ] Verify publish workflow publishes `codex-usage-tracking`, not `codex-usage-tracker`: `python scripts/check_release.py`.
- [ ] Verify publish workflow uses Trusted Publishing, not API tokens: `python scripts/check_release.py`.
- [ ] Verify TestPyPI and PyPI jobs exist and publish only on workflow dispatch or release events: `python scripts/check_release.py`.
- [ ] Verify PyPI job is gated by environment `pypi`: manual GitHub environment check.
- [ ] Verify dist filenames match `codex_usage_tracking`: `python -m build && python scripts/check_release.py --dist`.
- [ ] Verify TestPyPI process: run `Publish Python package` with `target=testpypi` only when intentionally testing release publication.
- [ ] Verify PyPI process: publish a GitHub Release or run workflow dispatch with `target=pypi` only when intentionally publishing a reviewed release.
- [ ] Document release recovery by cutting a new patch version when an uploaded artifact is wrong.

## 13. Known Limitations

- [ ] Document that Codex upstream log formats can change and parser compatibility may require updates.
- [ ] Document that pricing and rate-card sources can change outside this project.
- [ ] Document that live account allowance cannot be read automatically by this local tracker.
- [ ] Document that cost and credit estimates are not guaranteed to match exact billing.
- [ ] Document platform/plugin discovery limitations separately from the core Python CLI/dashboard support.
