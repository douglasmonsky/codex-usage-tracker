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

### Product Kernel Reset Execution

All post-0.25 product work must follow
`docs/roadmap/product-kernel-reset.md`, its approved
`docs/superpowers/specs/2026-07-26-product-kernel-reset-design.md`, and the
code-quarantine amendment at
`docs/superpowers/specs/2026-07-26-kernel-code-quarantine-design.md`.
Use one focused
`kernel/<task-id>-<slug>` branch per task, implement only the task's declared
contract, and update `docs/roadmap/product-kernel-reset-execution.md` in the
same changeset with branch, commits, verification, measurements, deviations,
review metrics, and residual risk.

K1 starts from current `main` and freezes both the public-surface inventory and
the full tracked-tree code-disposition manifest. Its resolver input is exactly
`git ls-files` at the K1 commit; workflows, root metadata, configuration, and
agent instructions are not exempt. After K1, create a detached,
policy-read-only v0.25.1 reference worktree and the temporary,
non-publishable `kernel/0.26-integration` branch. K1A–K9 use short-lived task
branches based on, and merged back into, that integration branch. K10 creates
`release/0.26.0` from an audited current-`main` SHA, incorporates the qualified
integration head once, and opens `release/0.26.0` to `main`. `main` remains the
releasable 0.25.1 line until that cutover.

Before each K1A–K9 task and K10, audit tracked-path deltas from the frozen K1
main SHA. An unrepresented path fails closed. Port required blocker behavior on
`kernel/k<owner>-mainline-port-<issue>`, based on and targeting integration,
with manifest, oracle, ledger, and affected phase-gate updates. Never merge the
legacy main line into integration. If `main` moves after the K10 audit, restart
the cutover audit rather than resolving an unclassified delta.

After K1A, activate only the integration worktree in Serena, GitNexus, and
ordinary agent search. Read retired or transplant source from the v0.25.1 tag
only through a bounded path named in `config/kernel-code-disposition-v1.json`;
do not add the reference worktree to the normal project scope. Never delete an
old worktree or branch without explicit maintainer permission.

The branch/ref publication guard must reject integration and every K1A–K9 task
ref. K9 may remove disposable skeleton metadata but not that guard. Only K10
sets the final version on `release/0.26.0`; publication still occurs only from
merged `main` through the protected release workflow.

The tracker owns exact facts, deterministic calculations, freshness, and
evidence. The consuming model owns inference, explanation, and recommendations.
Do not add server-authored narrative analysis, another MCP tool, a default fact
table, a compatibility profile, default content indexing, or an overlay unless
the active roadmap names it or an approved design amendment authorizes it.
Removal and upgrade behavior must also be due in `docs/deprecations.md`.

The former MCP-first roadmap is archived historical evidence. Its stable
redirects do not authorize new `pivot/` work.

### Engineering Working Style

Start each change from an observable contract: name the behavior, add or select
the focused test that proves it, implement the smallest complete change, and
then run broader validation in proportion to risk.

- Organize modules around one stable responsibility and a clear dependency
  direction. Split code when ownership or testability becomes clearer, and keep
  cohesive behavior together when an extraction would only add forwarding
  layers.
- Prefer direct functions, explicit data structures, and existing repository
  patterns. Add an abstraction only when it removes current duplication,
  isolates an external boundary, or gives a concrete test seam needed now.
- Preserve working names and interfaces unless the task changes their contract.
  When moving code, keep behavior changes separate from mechanical relocation
  so reviewers can verify both.
- Diagnose a failing check from its exact evidence before editing. Fix the
  behavioral, type, privacy, security, dependency, packaging, or release defect
  it identifies; if it identifies none, correct the check or policy rather than
  reshaping unrelated code.
- Use one focused test loop while implementing. At the stable checkpoint, run
  the smallest broad profile that covers every touched contract; reuse that
  evidence instead of rerunning overlapping profiles.
- For approved roadmap-scale work, declare the exact paths, contract, and
  validation once in a change plan. Keep the implementation cohesive and the
  commit focused even when the complete inventory or migration spans many
  files.
- Generate exhaustive inventories, fixtures, schemas, and migration ledgers
  from deterministic scripts. Review their inputs, schema, counts, and semantic
  summaries; do not hand-edit generated output.
- Keep synthetic fixtures small but semantically complete. Include edge states,
  expected failures, privacy assertions, and stable identifiers without copying
  local usage content.
- Treat Ruff, Pyright, Tach, tests, privacy checks, security checks, public
  contract checks, deterministic asset checks, package checks, and release
  readiness as correctness gates.

Wemake is retired from repository governance. Do not install, invoke, or add it
to local or CI workflows without a new explicit maintainer decision.

Use the repository-owned `just vp`, `just v`, and `just vc` recipes for broad
local verification. They intentionally mirror maintained repository and GitHub
checks without Agent Maintainer's generic style, file-length, change-budget,
Markdown-code-formatting, or expanded test-typecheck profiles. Do not invoke
`agent_maintainer verify` as a repository acceptance gate. Agent Maintainer
remains available for doctor, guidance, change-plan, context, and host-side wait
workflows.

- Do not commit directly to `main`.
- Start ordinary work and K1 from current `main` with a short-lived branch.
  For the approved reset only, start K1A–K9 from
  `kernel/0.26-integration`; K10 creates `release/0.26.0` from audited current
  `main`, incorporates qualified integration once, and targets `main`.
- Use branch prefixes `feature/`, `fix/`, `docs/`, `chore/`, `test/`, `release/`, `hotfix/`, or `kernel/`. Reserve `kernel/` for tasks in the approved Product Kernel Reset roadmap.
- Keep each branch focused on one issue, one reviewable task, or one release.
- Do not create a long-lived `develop` branch. The non-publishable
  `kernel/0.26-integration` branch is the sole temporary exception and exists
  only for K1A–K10.
- Do not mix release prep with unrelated feature work.
- Push task branches and open a PR for all changes headed to `main` or
  `kernel/0.26-integration`.
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
kernel/0.26-integration
kernel/k1a-legacy-quarantine
kernel/k3-ingest-tail
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

## Performance Work

Use the `agent-perf` skill and CLI when optimizing localhost API endpoints, dashboard refreshes, report generation, content indexing, parser or SQLite hot paths, or other latency- or CPU-sensitive code, and when investigating a performance regression or making a speedup claim.

Install the repository's pinned profiling tools with `uv sync --group performance`. Profile the smallest repeatable workload with synthetic or anonymized inputs; never profile production, live private databases, arbitrary processes, or real Codex session content. Record the identical workload without a profiler before making a performance claim. Change one suspected cause at a time, rerun the unprofiled workload, and use `agent-perf compare` only to compare attribution evidence rather than as proof of a speedup.

### Code intelligence tools

Use GitNexus for repository orientation, architecture, execution-flow tracing, subsystem discovery, and broad change-impact analysis.

Start unfamiliar or cross-cutting GitNexus work with the repository context resource, then open only the relevant cluster or process:

| Resource | Use for |
| -------- | ------- |
| `gitnexus://repo/codex-usage-tracker/context` | Codebase overview and index-freshness check |
| `gitnexus://repo/codex-usage-tracker/clusters` | Functional-area discovery |
| `gitnexus://repo/codex-usage-tracker/processes` | Execution-flow discovery |
| `gitnexus://repo/codex-usage-tracker/process/{name}` | One selected step-by-step execution trace |

Use Serena for exact symbol definitions, references, implementations, type-aware navigation, diagnostics, and symbol-level edits or refactors.

For unfamiliar or cross-cutting work, use GitNexus to identify where to investigate, then use Serena to verify the exact symbols before editing.

Treat GitNexus relationships as navigational guidance. Treat Serena as authoritative for precise symbol resolution and modification.

Confirm architectural conclusions against the source and relevant tests before changing behavior. Use `agent-perf` and an identical unprofiled workload for performance evidence; GitNexus may locate a hot path but does not prove a regression or speedup.

Do not repeat the same lookup in both tools unless validating an uncertain relationship or investigating conflicting results.

Refresh the GitNexus index after major branch changes, file moves, or architectural
refactors with `gitnexus analyze --index-only .`. Use the repo-local GitNexus skill
matching the task when a client supports it; do not load every GitNexus workflow by
default.

## Validation

Run focused tests first, then broader checks. Run the full local CI gate before opening or updating PRs that touch release, packaging, CLI contracts, MCP behavior, dashboard behavior, privacy behavior, schemas, generated docs/assets, or bundled plugin/skill files.

## Source Inspection And Tool Output

Large command outputs in Codex chat can be visually compacted by the transcript renderer. When inspecting source, especially after broad `rg`, `sed`, `nl`, generated dashboard assets, logs, or workflow output, do not treat a mangled rendered snippet as proof that the file is corrupt. Prefer small targeted file windows, `git diff`, `python -m py_compile`, focused tests, and CI as the source of truth. If exact syntax matters, inspect a narrow range or use a parser/compiler rather than relying on large printed source dumps.

Use this progressive inspection ladder:

1. Choose one first locator based on the question:
   - Use GitNexus for an unfamiliar subsystem, cross-cutting architecture, execution flow, dependency cycle, or broad change impact.
   - Use Serena for a known code symbol, exact definition, callers, references, implementations, types, diagnostics, or a symbol-level edit.
   - Use `rg -n` for an exact string, route, configuration key, SQL fragment, schema field, error text, documentation claim, or non-symbol asset.
   - Use `rg --files` when the filename or owning directory is unknown.
2. Do not run all locators by default. After GitNexus selects a code path, use Serena only on the relevant symbol before editing. After `rg` finds an exact non-code match, inspect that narrow file window directly.
3. Inspect symbol metadata, callers, and references before requesting source bodies.
4. Read the smallest useful source window, normally one symbol or roughly 80-160 lines.
5. Expand only to a dependency, caller, test, or contract needed to answer the current question.
6. Run the smallest relevant validation, then broaden checks in proportion to risk.

Start GitNexus searches with a small result limit and without `--content`; request full symbol content only after selecting the relevant process or symbol. Use Serena symbol overviews and reference queries before reading whole files. Do not dump entire directories, generated bundles, large JSON, full database rows, or multiple long files into one tool response.

Within one uninterrupted task, do not reread unchanged files, guidance, roadmap sections, or the complete diff unless context was compacted, the branch or guidance changed, evidence conflicts, or exact verification requires it. Persist durable cross-cutting findings in the active task report or execution ledger and reuse them. For edits, prefer a path-scoped diff; inspect the complete diff once when it reaches a stable review checkpoint.

Redirect oversized machine output to an ignored temporary file and extract a bounded summary with `rg`, `jq`, a parser, or a short read-only script. Keep the exact command and artifact path when the full result is evidence, but do not stream the full artifact into the conversation. Batch independent narrow lookups when useful, but do not concatenate unrelated large outputs.

These rules optimize context use, not correctness. Reopen source or rerun evidence whenever behavior, safety, privacy, or a public contract remains uncertain.

```bash
python -m ruff check .
python -m mypy
python -m pytest
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m compileall src
find src/codex_usage_tracker/plugin_data/dashboard \
  -type f -name '*.js' -exec node --check '{}' ';'
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
find src/codex_usage_tracker/plugin_data/dashboard \
  -type f -name '*.js' -exec node --check '{}' ';'
python -m build
python scripts/check_release.py --dist
git diff --check
python scripts/smoke_installed_package.py
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
find src/codex_usage_tracker/plugin_data/dashboard \
  -type f -name '*.js' -exec node --check '{}' ';'
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
- Never commit real prompts, assistant text, tool outputs, pasted secrets, message snippets, or raw Codex logs.
- The local content index may store bounded snippets in the user-owned SQLite database by approved design. Do not expose indexed/raw content through default CSV, generated HTML, support bundles, screenshots, aggregate JSON, fixtures based on real logs, or commits.
- Raw context may be read during refresh/content indexing or explicit selected-call context loading. Keep shareable outputs aggregate-first unless a command is explicitly documented as a local raw/content export.
- Keep fixture data synthetic.
- Keep local SQLite databases, CSV exports, HTML dashboards, caches, and virtualenvs out of git.
- Do not hard-code real current USD model pricing in source; refresh the local config from OpenAI's published pricing docs or use manual local overrides. Internal Codex model estimates must be explicitly marked as estimates with source and rationale metadata.
- Source-stamped Codex credit rate-card snapshots must include source/date metadata, confidence labels, and local override support. Manually copied allowance remaining values stay in local config only.

## Definition Of Done

- Parser and content-index handling are covered by synthetic session logs.
- SQLite refresh is idempotent.
- MCP tool functions return concise aggregate data by default; content-aware tools must be explicit local investigation surfaces.
- Dashboard generated HTML is aggregate-first and does not embed indexed/raw content.
- Doctor, summary presets, dashboard, and expensive-call views work from CLI and MCP wrappers.
- `codex-usage-tracker install-plugin` can register the installed package without relying on a source-checkout symlink.
- `python -m codex_usage_tracker` and `codex-usage-tracker --version` both work.
- Wheel and source distribution builds include plugin assets and the Codex skill.
- `scripts/check_release.py --dist` passes before any public release.
- Pricing coverage clearly separates configured, estimated, and unpriced model usage.
- Codex credit coverage clearly separates exact rate-card matches, inferred aliases, and missing credit rates.
- Dashboard Calls and Threads views share filters, totals, and aggregate-first hover details.
- Dashboard usage docs are updated when the visible dashboard workflow changes, and screenshots must be generated from synthetic data only.
- Dashboard refresh is localhost-only, generated HTML stays aggregate-first, and context loading is lazy, localhost-only, explicit, redacted, and not embedded in the static HTML payload.
- Subagent calls preserve logged parent-session metadata, latch to parent thread labels when available, and auto-review attachment is clearly marked when inferred.
- Tests and compile checks pass.
