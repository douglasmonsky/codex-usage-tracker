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
release/0.4.1
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
0.4.1
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

## Installed Package Smoke

Run the installed-package smoke whenever package data, console entry points, plugin installation, release metadata, or public install behavior changes:

```bash
python scripts/smoke_installed_package.py
```

The script builds this checkout into a temporary dist directory, installs the wheel into a clean temporary virtual environment, checks version/help commands, validates bundled dashboard/docs/rate-card/plugin/skill resources, and performs a temporary `install-plugin` run.

For cleaner release verification, prefer Docker when available:

```bash
python scripts/smoke_installed_package.py --docker
```

To verify the public PyPI package instead of the local checkout:

```bash
python scripts/smoke_installed_package.py --from-pypi --version 0.4.1
python scripts/smoke_installed_package.py --docker --from-pypi --version 0.4.1
```

`scripts/check_release.py` treats these public-package smoke commands as release-state claims. Keep their `--version` and `codex-usage-tracking==...` values aligned with `pyproject.toml`; the release gate fails when the docs claim a different public version. It also checks that install docs point at the real PyPI distribution, `codex-usage-tracking`, and keep the warning that `codex-usage-tracker` is a different PyPI package.

Docker avoids local toolchain side effects during install testing. Keep one local `pipx` smoke for platform-specific PATH and plugin-discovery behavior, but use Docker for repeatable Linux package verification.

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
python scripts/benchmark_synthetic_history.py --rows 10000 100000 --json --enforce-thresholds
python scripts/benchmark_synthetic_history.py --rows 500000 --json --enforce-thresholds
```

The script creates synthetic aggregate-only SQLite databases and times common release-sensitive paths. It does not read real Codex logs.

Thresholds are regression sentinels, not universal performance guarantees. Each timed path uses:

```text
limit_seconds = base_seconds + per_10k_seconds * (rows / 10000)
```

Use `--threshold-scale <number>` when intentionally running on a slower local machine. Keep the default scale for release checks unless there is a documented reason to relax it.

Tracked timings:

| Timing key | Path covered |
| --- | --- |
| `populate_seconds` | Synthetic aggregate indexing/upsert path |
| `active_dashboard_query_seconds` | Dashboard row query with archived sessions excluded |
| `all_history_dashboard_query_seconds` | Dashboard row query with archived sessions included |
| `since_until_query_seconds` | Date-window dashboard filtering |
| `filtered_query_seconds` | Model + effort + min-token dashboard filtering |
| `filtered_count_seconds` | Filtered dashboard count query |
| `dashboard_payload_active_seconds` | Active-session dashboard payload assembly |
| `thread_summary_seconds` | Thread summary report |
| `recommendations_report_seconds` | Recommendation report and thread rollup |
| `pricing_coverage_seconds` | Pricing coverage report |
| `project_summary_seconds` | Project summary report |

The normal CI smoke uses a tiny synthetic history with `--enforce-thresholds` so regressions in the benchmark contract are visible on pull requests. The 10k/100k runs are a practical local gate for performance-sensitive changes; the 500k run is the release-sized gate and can take about a minute on a modern laptop because recommendations and project summary intentionally scan all aggregate rows.

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
python scripts/smoke_installed_package.py
python scripts/smoke_installed_package.py --docker
```

The Docker smoke uses `python:3.14-slim` by default so release prep verifies installed-package behavior on the newest supported runtime.

The release checker verifies version alignment, required public docs, packaged plugin assets, wheel contents, and obvious tracked secret patterns. It does not publish anything.

After the release branch merges, tag from updated `main`, not from an unreviewed branch:

```bash
git switch main
git pull --ff-only
git tag -a v0.4.1 -m "codex-usage-tracker 0.4.1"
git push origin v0.4.1
```

Do not create or push release tags without maintainer approval.

## Publishing

Publishing uses GitHub Actions Trusted Publishing through `.github/workflows/publish.yml`; do not upload from a local machine and do not add PyPI or TestPyPI API tokens.

The first public package release, `0.3.0`, was published on June 8, 2026. Patch release `0.3.1` followed the same day to ship the live-dashboard skill launch fix. Patch release `0.3.2` made dashboard launch refresh the default and added runtime enablement for context loading. Minor release `0.4.0` added Python 3.14 support, release recovery docs, stricter privacy/support-bundle regression coverage, and large-history benchmark thresholds. Patch release `0.4.1` was published by workflow dispatch from `main`; it hardened the PyPI publish workflow and checked off completed 1.0 readiness gates.

- GitHub Release: `https://github.com/douglasmonsky/codex-usage-tracker/releases/tag/v0.3.0`
- GitHub Release: `https://github.com/douglasmonsky/codex-usage-tracker/releases/tag/v0.3.1`
- GitHub Release: `https://github.com/douglasmonsky/codex-usage-tracker/releases/tag/v0.3.2`
- GitHub Release: `https://github.com/douglasmonsky/codex-usage-tracker/releases/tag/v0.4.0`
- PyPI: `https://pypi.org/project/codex-usage-tracking/`
- TestPyPI: `https://test.pypi.org/project/codex-usage-tracking/`

Before publishing a future release, confirm Trusted Publishers are still configured in both services with project name `codex-usage-tracking`, owner `douglasmonsky`, repository `codex-usage-tracker`, workflow filename `publish.yml`, and the matching environment name:

- TestPyPI environment: `testpypi`
- PyPI environment: `pypi`

TestPyPI and PyPI are separate services/accounts. Configure both before publishing to both, and keep the `pypi` GitHub environment behind manual approval.

To publish to TestPyPI, run the `Publish Python package` workflow manually with `target` set to `testpypi`. The job builds once, checks the artifacts with `twine`, uploads them as workflow artifacts, then publishes the same artifacts to `https://test.pypi.org/project/codex-usage-tracking/`.

To publish to PyPI, either publish a GitHub Release for the tag or manually run the workflow with `target` set to `pypi`. The final project URL is `https://pypi.org/project/codex-usage-tracking/`.

PyPI and TestPyPI filenames and versions cannot be reused after upload. If a bad artifact is uploaded, cut the next patch version instead of trying to replace it.

## Release Recovery

Default to patch-forward recovery. PyPI and TestPyPI artifacts are immutable: an uploaded filename/version cannot be replaced, even if the project page lags or a release was a mistake. Do not add API tokens, publish locally, force-push tags, delete releases, or try to reuse a version. If the uploaded artifact is wrong, open a hotfix branch, bump to the next patch version, update `CHANGELOG.md` and release notes, rerun the release gate, and publish the corrected version through GitHub Actions Trusted Publishing.

If the release workflow fails before upload:

```bash
gh run list --workflow publish.yml --limit 10
gh run view <run-id> --json status,conclusion,headBranch,headSha,event,createdAt,url
gh run view <run-id> --log-failed
```

Fix the branch or workflow, rerun the workflow, and keep the same version only if the failed run did not upload artifacts to TestPyPI or PyPI. If upload succeeded anywhere, cut the next patch version for follow-up validation.

If Trusted Publishing or environment approval breaks, inspect `.github/workflows/publish.yml` first. The publish jobs should use `permissions: id-token: write`, `pypa/gh-action-pypi-publish@release/v1`, environment `testpypi` for TestPyPI, and environment `pypi` for PyPI. Confirm the Trusted Publisher entries in TestPyPI and PyPI still point to owner `douglasmonsky`, repository `codex-usage-tracker`, workflow `publish.yml`, and the matching environment. Do not work around a Trusted Publishing failure by adding API tokens.

If PyPI or TestPyPI appears stale, verify with the JSON API and simple index before assuming the upload failed:

```bash
python -c "import json, urllib.request; print(json.load(urllib.request.urlopen('https://pypi.org/pypi/codex-usage-tracking/json'))['info']['version'])"
python -c "import json, urllib.request; print(json.load(urllib.request.urlopen('https://test.pypi.org/pypi/codex-usage-tracking/json'))['info']['version'])"
python -c "import urllib.request; print(urllib.request.urlopen('https://pypi.org/simple/codex-usage-tracking/').read().decode()[:2000])"
python -c "import urllib.request; print(urllib.request.urlopen('https://test.pypi.org/simple/codex-usage-tracking/').read().decode()[:2000])"
```

If a runtime pin, wheel contents, plugin asset, or installed CLI is wrong after publication, create `hotfix/<next-version>` and run the full release gate before publishing the replacement patch:

```bash
python -m ruff check .
python -m mypy
python -m pytest
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m compileall src
python scripts/check_release.py
git diff --check
rm -rf dist build src/codex_usage_tracker.egg-info src/codex_usage_tracking.egg-info
python -m build
python -m twine check dist/*
python scripts/check_release.py --dist
python scripts/smoke_installed_package.py
python scripts/smoke_installed_package.py --docker
```

After a public PyPI upload completes, verify fresh production install paths and Docker smoke coverage:

```bash
python -m venv /tmp/codex-usage-pypi-smoke
. /tmp/codex-usage-pypi-smoke/bin/activate
python -m pip install --upgrade pip
python -m pip install "codex-usage-tracking==<version>"
codex-usage-tracker --version
codex-usage-tracker setup --help
deactivate
python scripts/smoke_installed_package.py --docker --from-pypi --version <version>
pipx install --force "codex-usage-tracking==<version>"
codex-usage-tracker --version
```

If the GitHub Release notes or tag description are wrong but the artifact is correct, edit the GitHub Release text. If the artifact is wrong, leave the old version as historical record and patch forward. Yank only when maintainers explicitly decide that the existing artifact should be hidden from ordinary installers; yanking does not make the filename/version reusable.
