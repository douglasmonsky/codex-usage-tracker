# Changelog

## Unreleased

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
