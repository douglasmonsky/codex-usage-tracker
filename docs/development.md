# Development And Release

## Local Setup

```bash
git clone https://github.com/douglasmonsky/codex-usage-tracker.git
cd codex-usage-tracker
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]" twine
codex-usage-tracker install-plugin --python .venv/bin/python
```

The public PyPI distribution is [`codex-usage-tracking`](https://pypi.org/project/codex-usage-tracking/); it installs the `codex-usage-tracker` command. The repository and import package remain `douglasmonsky/codex-usage-tracker` and `codex_usage_tracker`.

## Repo Layout

- `src/codex_usage_tracker/`: parser, SQLite store, reports, dashboard, CLI, and MCP server.
- `src/codex_usage_tracker/plugin_data/`: plugin assets, dashboard assets, bundled docs, rate cards, and packaged skill files.
- `skills/`: source skill files copied into package data.
- `docs/`: user documentation, architecture notes, JSON schemas, and synthetic screenshots.
- `tests/`: synthetic fixtures and unit tests.
- `scripts/check_release.py`: release-readiness checks for docs, versions, packaging, wheel contents, and tracked secret patterns.
- `scripts/benchmark_synthetic_history.py`: synthetic benchmark for large aggregate histories.

## Branch And PR Model

This repository uses trunk-based development with protected `main`, short-lived task branches, and release branches only when preparing a release. Do not use a permanent `develop` branch.

`main` should always be releasable: tests pass, package builds, dashboard assets are valid, docs are coherent, and any tag from `main` would be publishable.

Use one branch per coherent task or issue:

```text
feature/<issue-number>-short-description
fix/<issue-number>-short-description
docs/<issue-number>-short-description
chore/<issue-number>-short-description
test/<issue-number>-short-description
release/0.4.0
hotfix/0.3.3
```

Start work from current `main`:

```bash
git switch main
git pull --ff-only
git switch -c fix/125-wheel-package-data
```

Keep each branch focused. Do not mix release prep with unrelated features, and do not push directly to `main`. Push the branch, open a PR, use the PR template, and merge only after required checks pass.

For solo-maintainer work, the PR itself is still the review artifact. Prefer squash merge for ordinary task PRs so `main` remains readable.

Recommended `main` protection:

- Require pull request before merging.
- Require status checks before merging.
- Require branches to be up to date before merging.
- Require conversation resolution.
- Require linear history if it fits the current workflow.
- Disable force pushes.
- Disable branch deletion.
- Keep production PyPI publication behind the protected `pypi` GitHub environment.

## Issue And Milestone Model

Use issues for non-trivial work so Codex sessions stay focused.

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

Suggested 1.0-readiness issues:

- Installed-package smoke script.
- Strict privacy regression tests.
- Upgrade and migration tests.
- JSON contract documentation parity.
- Benchmark thresholds.
- Support-bundle safety tests.
- Release recovery docs.

## Local CI Gate

Run focused tests first, then broader checks. Run the full local CI gate before opening or updating PRs that touch release, packaging, CLI contracts, MCP behavior, dashboard behavior, privacy behavior, schemas, generated docs/assets, or bundled plugin/skill files:

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

For documentation-only branches, at minimum run:

```bash
python scripts/check_release.py
git diff --check
```

## Additional Smoke Checks

Run these when touching related CLI surfaces:

```bash
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

## Dashboard Screenshots

Dashboard screenshots in `docs/assets/` and `src/codex_usage_tracker/plugin_data/docs/assets/` must be generated from synthetic aggregate fixture data only.

Do not use real session logs, real prompts, assistant text, tool output, secrets, or private data in docs or screenshots.

## Large-History Benchmarking

Use the synthetic benchmark script when changing SQLite filters, dashboard payload loading, or indexes:

```bash
python scripts/benchmark_synthetic_history.py --rows 10000 100000 500000
```

The script creates synthetic aggregate-only SQLite databases and times common filtered dashboard query paths. It does not read real Codex logs.

## Release Checklist

Use a release branch only for version/changelog/pinning/publish prep. It should include release-specific changes such as version bumps, `CHANGELOG.md`, install/version wording, runtime package pins, publish workflow tweaks, release notes, and final smoke-test fixes. It should not include unrelated features.

Before opening a release PR:

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

Then verify the local package install path:

```bash
python -m pip install ".[dev]"
codex-usage-tracker --version
codex-usage-tracker install-plugin --plugin-dir /tmp/codex-usage-tracker-plugin-smoke --marketplace /tmp/codex-usage-marketplace-smoke.json --python .venv/bin/python --force
```

The release checker verifies version alignment, required public docs, packaged plugin assets, wheel contents, and obvious tracked secret patterns. It does not publish anything.

After the release branch merges, tag from updated `main`, not from an unreviewed branch:

```bash
git switch main
git pull --ff-only
git tag -a v0.4.0 -m "codex-usage-tracker 0.4.0"
git push origin v0.4.0
```

Do not create or push release tags without maintainer approval.

## Publishing

Publishing uses GitHub Actions Trusted Publishing through `.github/workflows/publish.yml`; do not upload from a local machine and do not add PyPI or TestPyPI API tokens.

The first public package release, `0.3.0`, was published on June 8, 2026. Patch release `0.3.1` followed the same day to ship the live-dashboard skill launch fix. Patch release `0.3.2` made dashboard launch refresh the default and added runtime enablement for context loading:

- GitHub Release: `https://github.com/douglasmonsky/codex-usage-tracker/releases/tag/v0.3.0`
- GitHub Release: `https://github.com/douglasmonsky/codex-usage-tracker/releases/tag/v0.3.1`
- GitHub Release: `https://github.com/douglasmonsky/codex-usage-tracker/releases/tag/v0.3.2`
- PyPI: `https://pypi.org/project/codex-usage-tracking/`
- TestPyPI: `https://test.pypi.org/project/codex-usage-tracking/`

Before publishing a future release, confirm Trusted Publishers are still configured in both services with project name `codex-usage-tracking`, owner `douglasmonsky`, repository `codex-usage-tracker`, workflow filename `publish.yml`, and the matching environment name:

- TestPyPI environment: `testpypi`
- PyPI environment: `pypi`

TestPyPI and PyPI are separate services/accounts. Configure both before publishing to both, and keep the `pypi` GitHub environment behind manual approval.

To publish to TestPyPI, run the `Publish Python package` workflow manually with `target` set to `testpypi`. The job builds once, checks the artifacts with `twine`, uploads them as workflow artifacts, then publishes the same artifacts to `https://test.pypi.org/project/codex-usage-tracking/`.

To publish to PyPI, either publish a GitHub Release for the tag or manually run the workflow with `target` set to `pypi`. The final project URL is `https://pypi.org/project/codex-usage-tracking/`.

PyPI and TestPyPI filenames and versions cannot be reused after upload. If a bad artifact is uploaded, cut the next patch version instead of trying to replace it.
