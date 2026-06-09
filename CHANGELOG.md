# Changelog

## Unreleased

## 0.4.1 - 2026-06-09

- Harden the production PyPI workflow so manual publishing must run from `main` or a tag ref before artifacts are downloaded and uploaded.
- Skip TestPyPI/PyPI uploads when the exact distribution version already exists on the target index, allowing a GitHub Release to be reconciled after a workflow-dispatch publish.
- Strengthen `scripts/check_release.py` so it validates the publish-ref preflight inside both the TestPyPI and PyPI jobs.
- Check off completed 1.0 readiness items with evidence for migration coverage, localhost dashboard smoke testing, and the protected GitHub `pypi` environment.
- Pin the marketplace MCP runtime launcher to the exact `codex-usage-tracking==0.4.1` package.

## 0.4.0 - 2026-06-09

- Add official Python 3.14 support across CI, package classifiers, README/install docs, and installed-package Docker smoke coverage.
- Add a release recovery runbook for failed publish workflows, stale PyPI/TestPyPI pages, Trusted Publishing issues, bad artifacts, and patch-forward recovery.
- Add synthetic large-history benchmark thresholds for active/all-history dashboard queries, date filtering, model/effort filtering, recommendations, pricing coverage, and project summaries.
- Add stricter privacy regression coverage for generated dashboards, CSV exports, API payloads, and support bundles.
- Redact sensitive strings and local diagnostic paths in support bundles, including nested doctor output in redacted and strict privacy modes.
- Add aggregate schema migration, JSON contract parity, installed-package smoke, and protected-main workflow readiness coverage.
- Pin the marketplace MCP runtime launcher to the exact `codex-usage-tracking==0.4.0` package.

## 0.3.2 - 2026-06-08

- Make `open-dashboard` and `serve-dashboard` refresh active-session logs by default, with `--no-refresh` as the explicit cached-index mode.
- Add a token-protected dashboard action for enabling context loading without restarting a localhost server that started with context loading off.

## 0.3.1 - 2026-06-08

- Fix packaged Codex Usage Tracker skills so dashboard-open requests start the live localhost dashboard instead of a static snapshot.
- Mirror live-dashboard skill guidance between source-tree skills and packaged plugin-data copies so release and wheel checks stay green.
- Use the valid explicit context API flag form, `serve-dashboard --refresh --context-api explicit --open`, for live dashboard launches.

## 0.3.0 - 2026-06-08

0.3.0 is a stabilization and public-preview release for the dashboard, CLI, MCP tools, local privacy model, packaged Codex plugin, and companion usage skills. The PyPI/TestPyPI distribution name is now `codex-usage-tracking`; the GitHub repository remains `douglasmonsky/codex-usage-tracker`, the Python import package remains `codex_usage_tracker`, and the installed CLI command remains `codex-usage-tracker`.

- Add tested JSON contract validation for stable CLI and MCP payload schemas.
- Add schema markers to doctor, pricing coverage, MCP dashboard/export/config, and opt-in context payloads.
- Add ranked CLI/MCP recommendations with severity score, primary recommendation, secondary signals, and thread rollups.
- Add offset-aware localhost dashboard usage API responses for paged aggregate-row automation.
- Add a synthetic large-history benchmark script for 10k, 100k, and 500k aggregate-row SQLite fixtures.
- Add focused mypy coverage for core JSON contract, recommendation, report, schema, model, and store modules.
- Add Ruff, coverage, and dashboard JavaScript syntax checks to CI.
- Split dashboard JavaScript helpers into formatting, data, state, and rendering/runtime assets.
- Add issue templates for bugs, parser compatibility, pricing/allowance issues, and feature requests.
- Expand security guidance for project metadata privacy, support bundles, and localhost dashboard tokens.

## 0.2.0

- Add project metadata privacy modes for dashboard, query, session, summary, CSV export, MCP, and support-bundle surfaces.
- Add Codex credit estimates and optional local allowance-window context to the dashboard.
- Add prominent unofficial-project disclaimers to docs, dashboard output, and plugin metadata.
- Harden malformed token-count parsing, SQLite concurrency, MCP raw-context opt-in, pricing parser diagnostics, bundled dashboard docs, and schema migrations.
- Fix Python 3.10 compatibility for UTC timestamps and release checks.
- Add package-owned Codex plugin installation with `codex-usage-tracker install-plugin`.
- Package plugin assets and the Codex skill into the Python wheel.
- Add a companion `codex-usage-api` skill for conversational analysis through aggregate-only API/MCP data.
- Add distribution metadata, source distribution manifest, and CI build checks.
- Add `python -m codex_usage_tracker` support and CLI `--version` output.
- Add release-readiness checks for version alignment, required docs, package data, built wheels, and tracked secret patterns.
- Harden marketplace MCP runtime bootstrapping so cached runtimes refresh when the bundled package pin changes.
- Harden local dashboard server responses with browser security headers and safer IPv6 localhost URLs.
- Tighten the dashboard header copy, add click/keyboard row inspection, and keep detailed usage guidance out of the primary UI.
- Keep call details sticky while scrolling and render timestamps as local human-readable date/time values.
- Prefer non-review models in mixed thread model summaries, add fit-to-width model labels, and add a scroll-aware `Top` button.
- Hide single-page dashboard pagination and keep multi-page controls compact in the toolbar.
- Render fetched and refreshed timestamps as local human-readable date-times and make the call details scrollbar visible.
- Rewrite the README around practical usage investigations, long-chat context growth, and pre-release limitations.
- Add a screenshot-driven dashboard guide built from synthetic aggregate fixture data.
- Preserve requested virtualenv Python paths during plugin install instead of resolving through interpreter symlinks.
- Keep generated dashboards, SQLite databases, CSV exports, and raw Codex logs out of git.

## 0.1.13

- Add dashboard load limits, API limits, and pagination for larger Codex histories.
