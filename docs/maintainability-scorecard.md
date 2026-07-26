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
just vp
just v
just vc
```

Current passing evidence:

- `PYTHONPATH=src .venv/bin/python -m pytest -q`: 531 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest --cov=codex_usage_tracker --cov-report=term-missing -q`: 531 passed, 86% total coverage.
- `.venv/bin/python -m mypy`: passed for the configured 8 source files.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
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

Wemake is retired from repository governance. Agent Maintainer keeps its wemake
provider disabled, the standalone narrow baseline has been removed, and wemake
is no longer installed by the development extra. Do not reintroduce or expand a
wemake gate without a new explicit product decision.

## Low-Churn Gate Policy

The standalone `git-agent-ratchet` file-length, private-import, and
duplicate-helper gates are retired. Their useful responsibilities are covered
by the repository's single physical file bound, Tach dependency contracts,
Ruff, tests, and review. Agent Maintainer uses the same 600-line physical and
source ceilings in its advisory configuration, while the repository-owned
kernel gate enforces those two 600-line ceilings and a B ceiling for
absolute/module/average Xenon complexity on the clean replacement kernel.
The legacy runtime remains protected by the product-complexity non-regression
budget until K1A removes it. Roadmap-compatible change budgets are 5,000 Python
lines or 100 Python files. Approved larger changes still require an explicit
change plan.

Agent Maintainer's generic verification profiles are no longer repository
acceptance gates. The repository-owned `just vp`, `just v`, and `just vc`
recipes run the maintained Python, architecture, test, security, release, and
frontend checks without generic Markdown code-fence formatting, expanded test
typechecking, historical file-length baselines, or stale change-plan scanning.
`just vc` also runs `scripts/check_kernel_maintainability.py`; focused tests
prove oversized or Xenon-C replacement modules fail.
GitHub CI remains the final shared acceptance authority.

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
4. Revisit `forbid_circular_dependencies = true` after package boundaries are less coarse.
5. Only after explicit approval, decide whether any local gates should become remote CI.
