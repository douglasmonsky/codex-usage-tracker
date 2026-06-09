# Codex Usage Tracker Instructions

## Project Purpose

This repo builds a local Codex plugin and dashboard that track aggregate token usage from Codex session logs.

## Tech Stack

- Python 3.10+
- SQLite via the Python standard library
- MCP Python SDK for Codex tool exposure
- Pytest for tests

## Repo Layout

- `src/codex_usage_tracker/` - parser, SQLite store, reports, dashboard, CLI, and MCP server.
- `src/codex_usage_tracker/context.py` - on-demand raw-context reader for one selected usage record.
- `src/codex_usage_tracker/reports.py` - shared application/report services used by CLI and MCP wrappers.
- `src/codex_usage_tracker/api_payloads.py` - shared stable JSON payload builders for CLI and MCP surfaces.
- `src/codex_usage_tracker/schema.py` - single source of truth for persisted usage-event columns.
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
python -m pip install ".[dev]" twine
codex-usage-tracker install-plugin --python .venv/bin/python
```

## Branch And PR Workflow

This project is now a published PyPI package with user-facing docs, JSON/MCP contracts, a release workflow, and privacy guarantees. Treat `main` as always releasable.

- Do not commit directly to `main`.
- Start each coherent task from current `main` with a short-lived branch.
- Use branch prefixes `feature/`, `fix/`, `docs/`, `chore/`, `test/`, `release/`, or `hotfix/`.
- Keep each branch focused on one issue, one reviewable task, or one release.
- Do not create a long-lived `develop` branch.
- Do not mix release prep with unrelated feature work.
- Push task branches and open a PR for all changes headed to `main`.
- Prefer squash merge for ordinary task PRs so `main` stays readable.
- Use the PR as the review artifact even when there is only one maintainer.

Recommended branch names:

```text
feature/<issue-number>-short-description
fix/<issue-number>-short-description
docs/<issue-number>-short-description
chore/<issue-number>-short-description
test/<issue-number>-short-description
release/0.4.0
hotfix/0.3.3
```

Before starting a task branch:

```bash
git switch main
git pull --ff-only
git switch -c docs/123-short-description
```

## Agent Boundaries

Codex may create task branches, write tests, update docs, run local gates, prepare PR summaries, prepare release branches, and prepare changelog/version changes.

Codex must not do these without explicit maintainer approval:

- Push directly to `main`.
- Create or push release tags.
- Publish to TestPyPI or PyPI.
- Add PyPI or TestPyPI API tokens.
- Publish from a local machine.
- Change privacy semantics.
- Rename the PyPI distribution, import package, CLI command, plugin name, MCP tools, schema IDs, or stable JSON contracts.
- Delete branches.
- Force-push shared branches.

Publishing must happen only through the approved GitHub Actions Trusted Publishing workflow and protected `testpypi`/`pypi` environments.

## Issue And Milestone Workflow

Use GitHub issues as the normal unit of work once the task is non-trivial. A branch should usually map to one issue and close it from the PR.

Recommended labels:

```text
bug
docs
packaging
release
privacy
security
performance
dashboard
cli
mcp
parser-compat
good-first-issue
blocked
1.0-blocker
```

Recommended milestones:

```text
0.4.0
1.0-readiness
1.0.0
```

Use patch releases for public blockers such as broken PyPI installs, missing package data, broken CLI entry points, privacy leaks, bad plugin installs, or bad runtime pins. Put planned stabilization work into the next minor release instead of bundling it into a patch.

## Validation

Run focused tests first, then broader checks. Run the full local CI gate before opening or updating PRs that touch release, packaging, CLI contracts, MCP behavior, dashboard behavior, privacy behavior, schemas, generated docs/assets, or bundled plugin/skill files.

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
rm -rf dist build src/codex_usage_tracker.egg-info src/codex_usage_tracking.egg-info
python -m build
python -m twine check dist/*
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

For documentation-only branches, at minimum run:

```bash
python scripts/check_release.py
git diff --check
```

## Release Branches

Use release branches only for version/changelog/pinning/publish prep, for example `release/0.4.0` or `hotfix/0.3.3`.

Release branches may include:

- Version bumps.
- `CHANGELOG.md` updates.
- Install/version wording updates.
- Runtime package pins.
- Publish workflow tweaks.
- Release notes.
- Final smoke-test fixes directly tied to release readiness.

Release branches must not include unrelated features.

Recommended release sequence:

```bash
git switch main
git pull --ff-only
git switch -c release/0.4.0
# version/changelog/release edits
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
rm -rf dist build src/codex_usage_tracker.egg-info src/codex_usage_tracking.egg-info
python -m build
python -m twine check dist/*
python scripts/check_release.py --dist
git add .
git commit -m "Prepare 0.4.0 release"
git push -u origin release/0.4.0
```

Open a PR to `main` and merge only after CI passes. After merge, tag from updated `main`, not from an unreviewed release branch, and only after explicit maintainer approval:

```bash
git switch main
git pull --ff-only
git tag -a v0.4.0 -m "codex-usage-tracker 0.4.0"
git push origin v0.4.0
```

## Privacy Rules

- Never commit real Codex session logs.
- Never store raw prompts, assistant text, tool outputs, pasted secrets, or message snippets.
- Raw context may be read only on demand from original local JSONL files; never persist it to SQLite, CSV, generated HTML, fixtures based on real logs, or commits.
- Store only selected aggregate session metadata for subagents, including parent thread labels; do not persist raw session instructions or source JSON.
- Keep fixture data synthetic.
- Keep local SQLite databases, CSV exports, HTML dashboards, caches, and virtualenvs out of git.
- Do not hard-code real current USD model pricing in source; refresh the local config from OpenAI's published pricing docs or use manual local overrides. Internal Codex model estimates must be explicitly marked as estimates with source and rationale metadata.
- Source-stamped Codex credit rate-card snapshots must include source/date metadata, confidence labels, and local override support. Manually copied allowance remaining values stay in local config only.

## Definition Of Done

- Parser handles synthetic session logs without reading raw message content.
- SQLite refresh is idempotent.
- MCP tool functions return concise aggregate data.
- Dashboard is generated from aggregate-only JSON.
- Doctor, summary presets, dashboard, and expensive-call views work from CLI and MCP wrappers.
- `codex-usage-tracker install-plugin` can register the installed package without relying on a source-checkout symlink.
- `python -m codex_usage_tracker` and `codex-usage-tracker --version` both work.
- Wheel and source distribution builds include plugin assets and the Codex skill.
- `scripts/check_release.py --dist` passes before any public release.
- Pricing coverage clearly separates configured, estimated, and unpriced model usage.
- Codex credit coverage clearly separates exact rate-card matches, inferred aliases, and missing credit rates.
- Dashboard Calls and Threads views share filters, totals, and aggregate-only hover details.
- Dashboard usage docs are updated when the visible dashboard workflow changes, and screenshots must be generated from synthetic data only.
- Dashboard aggregate refresh is localhost-only and keeps generated HTML aggregate-only; context loading is lazy, localhost-only, explicit, redacted, and not embedded in the static HTML payload.
- Subagent calls preserve logged parent-session metadata, latch to parent thread labels when available, and auto-review attachment is clearly marked when inferred.
- Tests and compile checks pass.
