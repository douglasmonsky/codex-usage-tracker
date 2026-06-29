# Maintainability Scorecard

This scorecard records the current local-only maintainability repair state. It is
not a release note and does not imply that any branch has been pushed.

## Scope

- Branch stack: local-only, currently ending at `docs/maintainability-roadmap-and-scorecard`.
- Runtime support remains Python 3.10 through 3.14.
- Maintainability tooling is dev-only and may require Python 3.11+.
- No GitHub pushes, PRs, tags, releases, or issue comments were part of this repair series.

## Baseline Versus Current

| Metric | `main` baseline | current local stack |
| --- | ---: | ---: |
| Local commits over `main` | 0 | 159 |
| Source Python files | 50 | 142 |
| Source Python lines | 26,645 | 32,991 |
| Test files | 33 | 90 |
| Test lines | 12,521 | 18,516 |
| Source files over 1000 lines | 4 | 0 |
| Source files over 600 lines | 14 | 0 |
| Largest source file | 6,753 lines | 599 lines |
| Radon blocks | 1,023 | 1,624 |
| Radon average complexity | 4.49 | 3.11 |
| Radon max complexity | 41 | 10 |
| Radon C-or-worse blocks | 89 | 0 |

Largest file reductions:

| File | before | current |
| --- | ---: | ---: |
| `src/codex_usage_tracker/usage_drain_model.py` | 6,753 | 497 |
| `src/codex_usage_tracker/store.py` | 1,800 | 558 |
| `src/codex_usage_tracker/server.py` | 1,508 | 558 |
| `src/codex_usage_tracker/parser.py` | 852 | 228 |
| `src/codex_usage_tracker/context.py` | 1,082 | 514 |
| `src/codex_usage_tracker/cli.py` | 976 | 530 |
| `src/codex_usage_tracker/diagnostic_snapshots.py` | 823 | 539 |
| `src/codex_usage_tracker/allowance.py` | 759 | 514 |

Current largest source files:

| File | lines |
| --- | ---: |
| `src/codex_usage_tracker/usage_drain_reports.py` | 599 |
| `src/codex_usage_tracker/dashboard.py` | 565 |
| `src/codex_usage_tracker/store.py` | 558 |
| `src/codex_usage_tracker/server.py` | 558 |
| `src/codex_usage_tracker/cli_parser.py` | 550 |
| `src/codex_usage_tracker/diagnostic_snapshots.py` | 539 |
| `src/codex_usage_tracker/cli.py` | 530 |
| `src/codex_usage_tracker/diagnostic_snapshot_events.py` | 528 |

## Enforced Local Gates

These are the current local blocking gates for the repair stack:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/python -m compileall src
.venv/bin/tach check
.venv/bin/python scripts/check_release.py
git diff --check
.venv/bin/python scripts/check_wemake_baseline.py
.venv/bin/python -m agent_maintainer verify --profile fast
.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__
.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__
.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python
```

Current passing evidence:

- `PYTHONPATH=src .venv/bin/python -m pytest -q`: 531 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest --cov=codex_usage_tracker --cov-report=term-missing -q`: 531 passed, 86% total coverage.
- `.venv/bin/python -m mypy`: passed for the configured 8 source files.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python scripts/check_wemake_baseline.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with the documented structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- Git-agent-ratchet file length, private import, and duplicate helper checks passed.
- Temporary detached-worktree package gates passed:
  - `.venv/bin/python -m build <worktree> --outdir <worktree>/dist`
  - `.venv/bin/python -m twine check <worktree>/dist/*`
  - `.venv/bin/python scripts/check_release.py --dist`

## Local Architecture Status

`tach` is now active as a local architecture gate. The current `tach check`
passes with explicit layer dependencies enabled.

Deferred architecture strictness:

- `forbid_circular_dependencies = true` is still deferred. Enabling it currently reports broad circular dependencies across the coarse module groups.
- The next meaningful architecture branch should split the package into responsibility folders before turning that option on.

## Wemake Status

Wemake is installed as a Python 3.11+ dev dependency and is intentionally scoped
through `scripts/check_wemake_baseline.py`.

Current wemake baseline modules:

- `src/codex_usage_tracker/__main__.py`
- `src/codex_usage_tracker/diagnostic_snapshot_constants.py`
- `src/codex_usage_tracker/diagnostics_types.py`
- `src/codex_usage_tracker/paths.py`
- `src/codex_usage_tracker/server_routes.py`
- `src/codex_usage_tracker/store_usage_timing.py`
- `src/codex_usage_tracker/usage_drain_boundary_scopes.py`

Global wemake remains disabled in `agent-maintainer` until coverage expands
enough to be a useful signal. The current policy is to add modules only after
they pass without broad ignores.

## Accepted Exceptions

- `agent_maintainer doctor --strict` still reports a known beta repo-root false positive for `src/agent_maintainer/__main__.py`.
- `agent_maintainer doctor --strict` also reports missing optional integration files such as remote CI, pre-commit config, and Codex hooks. Those are intentionally not added during the local-only series.
- `agent_maintainer verify --profile precommit` is not yet a blocking gate. It currently fails on existing formatter drift, pyright findings, and xenon module-level strictness.
- `agent_maintainer verify --profile full` is not yet a blocking gate. It currently reports the precommit findings plus broader optional/audit tools including pylint, deptry, vulture, bandit, actionlint, zizmor, markdownlint, yamllint, taplo, and check-jsonschema.
- `xenon --max-absolute B --max-modules A --max-average A src` still fails because five modules are rank B at module level:
  - `src/codex_usage_tracker/store_diagnostic_queries.py`
  - `src/codex_usage_tracker/pricing_config.py`
  - `src/codex_usage_tracker/usage_drain_regression.py`
  - `src/codex_usage_tracker/usage_drain_grace.py`
  - `src/codex_usage_tracker/usage_drain_proxy_fit.py`
- `agent-maintainer verify --profile fast` warns that `src/codex_usage_tracker` has 141 Python files in one folder. This is expected until package directories are split by responsibility.

## Next Targets

1. Split `src/codex_usage_tracker` into responsibility packages so structure-cohesion warnings become actionable.
2. Reduce the five B-ranked xenon modules until strict `--max-modules A` can pass.
3. Decide whether to adopt repo-wide Ruff formatting or keep formatter drift as a documented non-blocking item.
4. Expand `scripts/check_wemake_baseline.py` in small module groups.
5. Revisit `forbid_circular_dependencies = true` after package boundaries are less coarse.
6. Only after explicit approval, decide whether any local gates should become remote CI.
