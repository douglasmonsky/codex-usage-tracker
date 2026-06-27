# Maintainability Roadmap

This roadmap tracks the local-only maintainability repair series. Keep this file
current before each local checkpoint commit so long-running refactors do not
drift from the intended order.

## Local-Only Rules

- Do not push, open PRs, tag, publish, or comment on GitHub during this series.
- Start each branch from local `main` unless this file explicitly records a stacked branch.
- Keep one branch to one reviewable capability.
- Commit locally only after focused tests and the relevant local gates pass.
- Record branch goal, touched areas, checks, and next handoff here before each commit.

## Branch Checklist

For every branch:

- [ ] Confirm `git status --short --branch`.
- [ ] Confirm the branch is local-only.
- [ ] Record branch goal and acceptance criteria.
- [ ] Add characterization tests before behavior-preserving refactors.
- [ ] Run focused tests first.
- [ ] Run relevant broader local gates.
- [ ] Review `git diff --stat` and the actual diff.
- [ ] Commit locally at a green checkpoint.
- [ ] Record remaining risks and next branch handoff.

## Baseline Metrics

Initial inspection on `main` at `55265365` found the main maintainability risks are
large architectural zones rather than isolated style problems.

- Largest module: `src/codex_usage_tracker/usage_drain_model.py`, about 6,700 lines.
- Other large modules: `store.py`, `server.py`, `context.py`, `cli.py`, `parser.py`.
- Strict `xenon --max-absolute B --max-modules A --max-average A src` currently fails.
- `agent-maintainer` is dev-only and requires Python 3.11+, while runtime support remains Python 3.10-3.14.
- `agent-maintainer doctor --strict` in `0.1.0b1` has one known beta false positive for this repo: it checks for `src/agent_maintainer/__main__.py`, which belongs to the maintainer tool's own source layout, not this package.

## Local Commands

Core project gate:

```bash
python -m ruff check .
python -m mypy
python -m pytest
python -m compileall src
for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done
python scripts/check_release.py
git diff --check
```

Maintainability gate:

```bash
python -m agent_maintainer doctor --strict
python -m agent_maintainer verify --profile fast
python -m agent_maintainer verify --profile precommit
git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__
git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__
git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python
radon cc src -a -s
radon mi src -s
xenon --max-absolute B --max-modules A --max-average A src
```

## Branch Ledger

### `chore/maintainability-agent-maintainer-baseline`

Goal:

- Add the local-only maintainability control layer without changing runtime behavior.
- Configure `agent-maintainer` in `legacy-ratchet` mode.
- Keep wemake disabled until the repo has been split enough for useful signal.
- Establish a file-length baseline so existing oversized modules do not block the first branch, but new or worsened oversized files can be detected.
- Generate `AGENTS.agent-maintainer.md` from `[tool.agent_maintainer]` so future agents have the current local policy.

Acceptance:

- Existing project checks still pass.
- `agent-maintainer verify --profile fast` passes locally.
- `agent-maintainer doctor --strict` has no unexplained failures; the `src/agent_maintainer/__main__.py` repo-root failure is documented as an `agent-maintainer 0.1.0b1` beta false positive.
- Remaining warnings are expected bootstrap gaps for later branches: `tach.toml`, local command wrappers/hooks, disabled wemake/interrogate, and no committed remote CI integration.

Status:

- Baseline configured.
- File-length ratchet baseline written to `.agent-maintainer/file-length-baseline.json`.
- `agent-maintainer verify --profile fast` passed with one structure-cohesion warning: `src/codex_usage_tracker` currently has 49 Python files and needs responsibility-based package splitting.
- `agent-maintainer doctor --strict` passed tool capability/config checks after adding `actionlint-py` and `zizmor`, with the one known beta repo-root false positive documented above.
- Product gates passed locally:
  - `python -m ruff check .`
  - `python -m mypy`
  - `python -m pytest` (`324 passed`)
  - `python -m compileall src`
  - dashboard JavaScript `node --check`
  - `python scripts/check_release.py`
  - `git diff --check`
- Maintainer gates passed locally:
  - `python -m agent_maintainer verify --profile fast`
  - `python -m agent_maintainer guidance --check`
  - file-length ratchet check via the fast profile.

Next handoff:

- `chore/maintainability-ratchet-workflow-local` should make `precommit` useful locally without adding remote workflow files. Start by deciding whether strict `xenon B/A/A` should remain fast-profile blocking now or move to a later profile until module splitting reduces current complexity.

### `chore/maintainability-ratchet-workflow-local`

Goal:

- Keep the maintainability workflow local-only.
- Add `git-agent-ratchet` as Python 3.11+ dev tooling.
- Seed local ratchet baselines for current line overage, cross-module private imports, and duplicate helpers.
- Clarify that `fast` is the green local maintainer gate today, while `precommit` and `full` are diagnostic until their failures are paid down.

Acceptance:

- `agent-maintainer verify --profile fast` passes.
- `agent-maintainer verify --profile precommit` runs and writes diagnostics, but known existing failures are recorded.
- `git-agent-ratchet` baseline checks pass without worsening current debt counters.
- No remote workflow files are added.

Status:

- Complete locally.

Baseline metrics:

- `max-file-lines`: 10,152 total line overage across `src`.
- `cross-module-private-imports`: 10 current private-import edges.
- `duplicate-helpers`: 79 current duplicate helper names.

Checks:

- `python -m pip install ".[dev]"`: passed.
- `python -m agent_maintainer verify --profile fast`: passed with the existing structure-cohesion warning.
- `git-agent-ratchet max-file-lines ...`: passed.
- `git-agent-ratchet no-cross-module-private-import ...`: passed.
- `git-agent-ratchet no-duplicate-helpers ...`: passed.
- `python -m ruff check .`: passed.
- `python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `python -m mypy`: passed.
- `python -m compileall src`: passed.
- `python -m pytest`: 324 passed.

Known `precommit` diagnostics:

- `ruff-format` would reformat many existing Python files. Do not apply globally in this branch.
- `pyright` reports existing type issues in broad modules such as `cli.py`, `context.py`, `dashboard.py`, and `server.py`.
- `xenon-complexity-gate` fails on known high-complexity blocks, especially `usage_drain_model.py`, `server.py`, `store.py`, diagnostics, and time-series reporting.

Next handoff:

- Keep `fast` as the green local gate.
- In the next branch, add a local command wrapper or documented alias that runs the green gate plus optional diagnostics without implying `precommit` is clean.
