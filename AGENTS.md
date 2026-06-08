# Codex Usage Tracker Instructions

## Project Purpose

This repo builds a local Codex plugin and dashboard that track aggregate token usage from local AI coding-agent logs. It is evolving toward AI Usage Tracker while keeping the `codex-usage-tracker` package, CLI, and Codex plugin names for compatibility. Codex is the default source; Claude Code is supported as an opt-in source.

## Tech Stack

- Python 3.10+
- SQLite via the Python standard library
- MCP Python SDK for Codex tool exposure
- Pytest for tests

## Repo Layout

- `src/codex_usage_tracker/` - parser, SQLite store, reports, dashboard, CLI, and MCP server.
- `src/codex_usage_tracker/adapters/` - source-specific log adapters for Codex JSONL and Claude Code JSONL.
- `src/codex_usage_tracker/context.py` - on-demand raw-context reader for one selected usage record.
- `src/codex_usage_tracker/reports.py` - shared application/report services used by CLI and MCP wrappers.
- `src/codex_usage_tracker/api_payloads.py` - shared stable JSON payload builders for CLI and MCP surfaces.
- `src/codex_usage_tracker/schema.py` - single source of truth for persisted usage-event columns, including source provider/app/format identity.
- `src/codex_usage_tracker/threads.py` - thread attachment inference used by dashboard payload generation.
- `src/codex_usage_tracker/pricing_config.py`, `pricing_openai.py`, `pricing_estimates.py`, and `costing.py` - pricing config, source parsing, estimate policy, and cost calculations behind the `pricing.py` facade.
- `src/codex_usage_tracker/allowance.py` - Codex credit-rate and optional local allowance-window helpers.
- `src/codex_usage_tracker/plugin_installer.py` - package-owned local Codex plugin installer.
- `src/codex_usage_tracker/plugin_data/` - plugin assets, dashboard template/assets, local dashboard guide, screenshots, and skill files bundled into wheels.
- `skills/codex-usage-tracker/` and `src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/` - operational Codex skill for tracker setup, summaries, dashboard generation, and MCP tools.
- `skills/codex-usage-api/` and `src/codex_usage_tracker/plugin_data/skills/codex-usage-api/` - companion Codex skill for conversational analysis using the stable JSON API/MCP tools.
- `src/codex_usage_tracker/server.py` - localhost dashboard server with live aggregate refresh and lazy context endpoints.
- `~/.codex-usage-tracker/pricing.json` - optional local-only pricing config, never committed.
- `~/.codex-usage-tracker/allowance.json` - optional local-only copied allowance state, never committed.
- `.codex-plugin/plugin.json` - Codex plugin manifest.
- `.mcp.json` - MCP server configuration for Codex.
- `scripts/install_local_plugin.py` - compatibility wrapper around `codex-usage-tracker install-plugin`.
- `scripts/check_release.py` - release-readiness checks for docs, versions, packaging, wheel contents, and tracked secret patterns.
- `.github/workflows/ci.yml` - GitHub Actions test and package build workflow.
- `.github/workflows/pricing-compat.yml` - scheduled/manual non-blocking live pricing parser compatibility check.
- `docs/` - install, dashboard, CLI, pricing/credits, MCP, privacy, architecture, development, JSON-schema docs, and screenshots built from synthetic aggregate fixture data.
- `tests/` - synthetic fixtures and unit tests.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
codex-usage-tracker install-plugin --python .venv/bin/python
```

## Validation

Run the local CI gate before pushing to `main`:

```bash
python -m ruff check .
python -m mypy
python -m pytest
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m compileall src
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_format.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js
python scripts/check_release.py
git diff --check
python -m build
python scripts/check_release.py --dist
```

Additional smoke checks for touched CLI surfaces:

```bash
python -m pytest
python -m compileall src
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js
python -m build
python scripts/check_release.py --dist
git diff --check
codex-usage-tracker update-pricing --output /tmp/codex-usage-pricing.json
codex-usage-tracker update-rate-card --output /tmp/codex-usage-rate-card.json
codex-usage-tracker doctor
codex-usage-tracker doctor --suggest-repair
codex-usage-tracker dashboard --output /tmp/codex-usage-dashboard.html
codex-usage-tracker serve-dashboard --help
codex-usage-tracker init-allowance --output /tmp/codex-usage-allowance.json
codex-usage-tracker parse-allowance --output /tmp/codex-usage-allowance.json "5h 79% 6:50 PM Weekly 33% Jun 7"
codex-usage-tracker init-thresholds --output /tmp/codex-usage-thresholds.json
codex-usage-tracker init-projects --output /tmp/codex-usage-projects.json
codex-usage-tracker support-bundle --output /tmp/codex-usage-support.json
codex-usage-tracker pricing-coverage
codex-usage-tracker summary --preset by-subagent-role
codex-usage-tracker expensive --limit 5
```

## Privacy Rules

- Never commit real Codex, Claude Code, or other coding-agent session logs.
- Never store raw prompts, assistant text, tool outputs, pasted secrets, or message snippets.
- Raw context may be read only on demand from original local JSONL files; never persist it to SQLite, CSV, generated HTML, fixtures based on real logs, or commits.
- Store only selected aggregate session metadata for subagents, including parent thread labels; do not persist raw session instructions or source JSON.
- Keep fixture data synthetic.
- Keep local SQLite databases, CSV exports, HTML dashboards, caches, and virtualenvs out of git.
- Do not hard-code real current USD model pricing in source; refresh the local config from OpenAI's published pricing docs or use manual local overrides. Internal Codex model estimates must be explicitly marked as estimates with source and rationale metadata.
- Source-stamped Codex credit rate-card snapshots must include source/date metadata, confidence labels, and local override support. Codex credits apply only to Codex/OpenAI rows; non-Codex rows must stay clearly marked as not applicable. Manually copied allowance remaining values stay in local config only.

## Definition Of Done

- Parser adapters handle synthetic session logs without reading raw message content.
- SQLite refresh is idempotent.
- MCP tool functions return concise aggregate data.
- Dashboard is generated from aggregate-only JSON.
- Doctor, summary presets, dashboard, and expensive-call views work from CLI and MCP wrappers.
- `codex-usage-tracker install-plugin` can register the installed package without relying on a source-checkout symlink.
- `python -m codex_usage_tracker` and `codex-usage-tracker --version` both work.
- Wheel and source distribution builds include plugin assets and the Codex skill.
- `scripts/check_release.py --dist` passes before any public release.
- Pricing coverage clearly separates configured, estimated, and unpriced model usage across sources.
- Codex credit coverage clearly separates exact rate-card matches, inferred aliases, missing credit rates, and non-Codex rows where credits are not applicable.
- Source filters and source grouping work consistently across CLI, MCP, dashboard, CSV, and JSON payloads.
- Dashboard Calls and Threads views share filters, totals, and aggregate-only hover details.
- Dashboard usage docs are updated when the visible dashboard workflow changes, and screenshots must be generated from synthetic data only.
- Dashboard aggregate refresh is localhost-only and keeps generated HTML aggregate-only; context loading is lazy, localhost-only, explicit, redacted, and not embedded in the static HTML payload.
- Subagent calls preserve logged parent-session metadata, latch to parent thread labels when available, and auto-review attachment is clearly marked when inferred.
- Tests and compile checks pass.
