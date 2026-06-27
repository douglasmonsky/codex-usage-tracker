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

### `refactor/architecture-boundary-map`

Goal:

- Add `tach` as explicit Python 3.11+ dev tooling.
- Add a report-mode `tach.toml` boundary map for current coarse modules.
- Document intended dependency direction before moving code.
- Keep `tach check` informational until the later strict-local branch.

Acceptance:

- `tach report` runs against a representative module.
- `tach map` emits a local dependency map.
- Known `tach check` violations are documented.
- No runtime behavior changes.

Status:

- Complete locally.

Checks:

- `python -m pip install ".[dev]"`: passed.
- `tach report src/codex_usage_tracker/usage_drain_reports.py --dependencies --usages`: passed.
- `tach map -o /tmp/codex-usage-tracker-tach-map.json`: passed.
- `tach check`: expected informational failure with 13 documented boundary violations.
- `python -m agent_maintainer verify --profile fast`: passed with the existing structure-cohesion warning.
- `python -m ruff check .`: passed.
- `python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `python -m mypy`: passed.
- `python -m compileall src`: passed.
- `python -m pytest`: 324 passed.

Current boundary debt:

- `context.py` reaches into persistence through `store.query_usage_record`.
- `store.py` and `store_sources.py` reach into parser refresh/state helpers.
- `support.py` reaches upward into `diagnostics.run_doctor`.

Next handoff:

- Use the boundary debt list to choose the first safe refactor target after the usage-drain split branches, or deliberately reorder if store/parser/context boundaries look lower risk than usage-drain.

### `refactor/usage-drain-model-split-1`

Goal:

- Add characterization coverage for the usage-drain model summary payload.
- Move shared usage-drain types and constants out of the giant model module.
- Preserve `usage_drain_model.py` as the compatibility facade for current imports.
- Keep CLI/API/dashboard payload behavior unchanged.

Acceptance:

- Existing usage-drain report tests pass.
- New characterization test protects summary schema, span stats, plan/model mixes, token component features, fast-proxy result list, and predictive-modeling block shape.
- `usage_drain_model.py` line count moves downward without algorithm changes.
- `tach.toml` tracks the new type module.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_types.py`.
- Moved `FastProxyAnnotation`, `UsageDeltaSpan`, `UsageDrainModelResult`, `PredictiveModelSpec`, documented fast multipliers, proxy names, and shared span field constants.
- Added `test_usage_drain_model_summary_characterizes_synthetic_spans`.

Remaining before local commit:

- None.

Metrics:

- `usage_drain_model.py`: 6,602 lines after split.
- `usage_drain_types.py`: 178 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down from 10,152 to 10,001 total source-line overage.

Checks:

- `python -m pytest tests/test_usage_drain_reports.py`: 5 passed.
- `python -m pytest`: 325 passed.
- `python -m ruff check .`: passed.
- `python -m mypy`: passed.
- `python -m compileall src`: passed.
- `python scripts/check_release.py`: passed.
- `python -m agent_maintainer verify --profile fast`: passed with the existing structure-cohesion warning.
- `git-agent-ratchet max-file-lines ...`: passed after ratcheting the baseline down.
- `git-agent-ratchet no-cross-module-private-import ...`: passed.
- `git-agent-ratchet no-duplicate-helpers ...`: passed.
- `tach report src/codex_usage_tracker/usage_drain_reports.py --dependencies --usages`: passed.
- `tach check`: expected informational failure with the same 13 documented boundary violations.
- `git diff --check`: passed.

### `refactor/usage-drain-model-split-2`

Goal:

- Move usage-drain span construction out of `usage_drain_model.py`.
- Preserve `usage_drain_model.py` compatibility imports for existing scripts/tests.
- Keep usage-drain dashboard/report/model payloads unchanged.
- Ratchet maintainability baselines downward when the split reduces existing debt.

Acceptance:

- Direct usage-drain model tests pass.
- Usage-drain dashboard report tests pass.
- Full suite passes.
- `tach.toml` tracks the new spans module without adding new strict-check violations.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_spans.py`.
- Moved `build_usage_delta_spans`, `load_fast_proxy_annotations`, span row construction, usage-window selection, token component row conversion, and span-specific row coercion helpers.
- Moved `TOKEN_COMPONENT_FIELDS` and `EFFORT_LEVELS` to `usage_drain_types.py`.
- Kept compatibility imports in `usage_drain_model.py` for existing `scripts/model_usage_drain.py` and tests.
- Updated `tach.toml` so `usage_drain_spans.py` belongs to the diagnostics module group.

Metrics:

- `usage_drain_model.py`: 6,269 lines after split.
- `usage_drain_spans.py`: 348 lines.
- `usage_drain_types.py`: 187 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down from 10,001 to 9,668 total source-line overage.
- `git-agent-ratchet duplicate-helpers`: baseline ratcheted down from 79 to 76 duplicate helper names.

Checks:

- `python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `python -m pytest`: 325 passed.
- `python -m ruff check .`: passed.
- `python -m mypy`: passed.
- `python -m compileall src`: passed.
- `python scripts/check_release.py`: passed.
- `python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning and a large-diff warning.
- `git-agent-ratchet max-file-lines ...`: passed after ratcheting the baseline down.
- `git-agent-ratchet no-cross-module-private-import ...`: passed.
- `git-agent-ratchet no-duplicate-helpers ...`: passed after ratcheting the baseline down.
- `tach report src/codex_usage_tracker/usage_drain_reports.py --dependencies --usages`: passed.
- `tach map -o /tmp/codex-usage-tracker-tach-map.json`: passed.
- `tach check`: expected informational failure with the same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:

- Continue with feature/model-fitting extraction inside usage-drain modeling, targeting `_span_feature_row`, predictive feature row enrichment, and `fit_usage_drain_proxy` in smaller commits.

### `refactor/usage-drain-shared-utils`

Goal:

- Extract generic usage-drain math/time/bucketing helpers from `usage_drain_model.py`.
- Keep old private helper names available inside `usage_drain_model.py` through aliases.
- Avoid increasing cross-module private imports.
- Prepare a cleaner follow-up extraction for feature-row construction.

Acceptance:

- Focused usage-drain tests pass.
- Full test suite passes.
- Ratchets pass and tighten line/duplicate baselines.
- `tach.toml` explicitly tracks the new utility module.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_utils.py` with public helpers for timestamp parsing, numeric coercion, rounding, bucket labels, reset timing, value distributions, and bounded wall-time calculations.
- Replaced local helper definitions in `usage_drain_model.py` with compatibility aliases imported from the utility module.
- Kept utility exports public to avoid worsening the `no-cross-module-private-import` ratchet.
- Added `usage_drain_utils.py` to the shared/core tach module group.

Metrics:

- `usage_drain_model.py`: 6,158 lines.
- `usage_drain_utils.py`: 169 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 9,668 -> 9,557 total source-line overage.
- `git-agent-ratchet duplicate-helpers`: baseline ratcheted down 76 -> 72 duplicate helper names.

Checks:

- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning and source-change/no-test-file warning.
- `.venv/bin/git-agent-ratchet max-file-lines ...`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import ...`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers ...`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_utils.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-shared-utils.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.

Next handoff:

- Start `refactor/usage-drain-feature-rows` and move `_span_feature_row`, causal history features, and remainder/capacity feature helpers onto the shared utilities without private imports.

### `refactor/usage-drain-feature-rows`

Goal:

- Move usage-drain feature-row construction out of `usage_drain_model.py`.
- Keep the existing model/report API unchanged through compatibility aliases.
- Keep new files under `agent-maintainer` source-line limits.

Acceptance:

- Focused usage-drain tests pass.
- Full test suite passes.
- `agent-maintainer verify --profile fast` passes.
- Ratchets pass and max-file-lines tightens.
- `tach.toml` explicitly tracks the new feature modules.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_features.py` for span feature-row construction and days-since-first-span enrichment.
- Added `src/codex_usage_tracker/usage_drain_feature_history.py` for causal history, rolling, streak, remainder, and capacity feature helpers.
- Replaced local helper definitions in `usage_drain_model.py` with compatibility aliases from the new modules.
- Split the initial feature module again after `agent-maintainer` caught it exceeding the source-line budget.
- Updated `tach.toml` so the feature modules live in the diagnostics/reporting boundary group.

Metrics:

- `usage_drain_model.py`: 5,643 lines.
- `usage_drain_features.py`: 200 lines.
- `usage_drain_feature_history.py`: 383 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 9,557 -> 9,042 total source-line overage.

Checks:

- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion and large-diff/no-test-file warnings.
- `.venv/bin/git-agent-ratchet max-file-lines ...`: passed and ratcheted baseline down.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import ...`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers ...`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_feature_history.py --dependencies --usages`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_features.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-feature-rows.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:

- Continue `refactor/usage-drain-model-split-2` with predictive fitting/model diagnostic extraction. Keep the next branch smaller than this one if possible; target `_fit_predictive_model`, design-matrix preparation, and regression metrics separately from walk-forward diagnostics.

### `refactor/usage-drain-fitting-core`

Goal:

- Move usage-drain regression, correlation, and fast-proxy fit helper functions out of `usage_drain_model.py`.
- Keep existing private helper names available inside `usage_drain_model.py` through compatibility aliases.
- Preserve report/model JSON behavior, especially regression metric keys such as `mean_predicted`.

Acceptance:

- Focused usage-drain tests pass.
- Full test suite passes.
- Regression metrics smoke check confirms `mean_predicted` key remains stable.
- Ratchets pass and tighten file-length and duplicate-helper baselines.
- `tach.toml` explicitly tracks the new regression module.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_regression.py` for design-matrix preparation, ridge fitting, prediction, regression metrics, correlations, ranks, count summaries, and proxy multiplier helper fits.
- Replaced local helper definitions in `usage_drain_model.py` with aliases imported from the regression module.
- Updated `tach.toml` so `usage_drain_regression.py` belongs to the diagnostics/reporting boundary group.
- Added a one-off smoke verification for the `mean_predicted` metric key after catching a mechanical rename typo.

Metrics:

- `usage_drain_model.py`: 5,403 lines.
- `usage_drain_regression.py`: 297 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 9,042 -> 8,802 total source-line overage.
- `git-agent-ratchet duplicate-helpers`: baseline ratcheted down 72 -> 66 duplicate helper names.

Checks:

- `PYTHONPATH=src .venv/bin/python - <<'PY' ... regression_metrics smoke ... PY`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion and large-diff/no-test-file warnings.
- `.venv/bin/git-agent-ratchet max-file-lines ...`: passed and ratcheted baseline down.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import ...`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers ...`: passed and ratcheted baseline down.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_regression.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-regression.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:

- Continue predictive fitting orchestration extraction in a separate branch. Target `_fit_predictive_model`, `_fit_causal_baseline_models`, `_predictive_model_specs`, and capacity residual diagnostics separately from walk-forward diagnostics.

### `refactor/usage-drain-predictive-orchestration`

Goal:

- Move predictive usage-drain model orchestration out of `usage_drain_model.py`.
- Keep predictive model specs in a separate size-compliant module.
- Preserve existing model/report behavior through compatibility aliases still used by capacity modeling paths.

Acceptance:

- Focused usage-drain tests pass.
- Full test suite passes.
- `agent-maintainer verify --profile fast` passes after splitting oversized new modules.
- Ratchets pass and max-file-lines tightens.
- `tach.toml` explicitly tracks predictive orchestration and spec modules.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_predictive.py` for predictive model orchestration, split generation, causal baselines, fitted model assembly, and capacity residual diagnostics.
- Added `src/codex_usage_tracker/usage_drain_predictive_specs.py` for predictive model specifications.
- Replaced local predictive orchestration definitions in `usage_drain_model.py` with compatibility aliases from the new modules.
- Split predictive specs into their own module after `agent-maintainer` flagged the first new predictive module as over the source-line budget.
- Updated `tach.toml` so both predictive modules live in the diagnostics/reporting boundary group.

Metrics:

- `usage_drain_model.py`: 4,848 lines.
- `usage_drain_predictive.py`: 315 lines.
- `usage_drain_predictive_specs.py`: 268 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 8,802 -> 8,247 total source-line overage.

Checks:

- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion and large-diff/no-test-file warnings.
- `.venv/bin/git-agent-ratchet max-file-lines ...`: passed and ratcheted baseline down.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import ...`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers ...`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_predictive.py --dependencies --usages`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_predictive_specs.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-predictive.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:

- Continue usage-drain split work with walk-forward and boundary diagnostics. Keep the next branch narrower than the current one; target one diagnostic family at a time before moving on to store/server roadmap items.

### `refactor/usage-drain-summary-metrics`

Goal:

- Move usage-drain summary metric helpers out of `usage_drain_model.py` before extracting the larger walk-forward engine.
- Preserve existing summary/report behavior through compatibility aliases and imported correlation constants.
- Keep the new summary module under `agent-maintainer` source-line limits.

Acceptance:

- Focused usage-drain tests pass.
- Full test suite passes.
- `agent-maintainer verify --profile fast` passes.
- Ratchets pass and max-file-lines tightens.
- `tach.toml` explicitly tracks the summary metrics module.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_summary_metrics.py` for model family attribution, best-holdout selection, span correlation rows, correlation reports, and delta distributions.
- Moved `SPAN_RAW_CORRELATION_FEATURES` and `SPAN_CAPACITY_CORRELATION_FEATURES` with the correlation helpers.
- Replaced local helper definitions in `usage_drain_model.py` with compatibility aliases from the summary metrics module.
- Fixed moved-module dependencies on token total fields and span wall-time helpers.
- Updated `tach.toml` so `usage_drain_summary_metrics.py` belongs to the diagnostics/reporting boundary group.

Metrics:

- `usage_drain_model.py`: 4,596 lines.
- `usage_drain_summary_metrics.py`: 288 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 8,247 -> 7,995 total source-line overage.

Checks:

- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion and large-diff/no-test-file warnings.
- `.venv/bin/git-agent-ratchet max-file-lines ...`: passed and ratcheted baseline down.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import ...`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers ...`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_summary_metrics.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-summary-metrics.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:

- Continue with walk-forward transition diagnostics in a separate branch. Start by moving `_walk_forward_prediction_summary`, `_walk_forward_prediction_rows`, and directly required transition-risk helpers if they stay under the file-size gate; otherwise split risk helpers first.
### `refactor/usage-drain-diagnostic-helpers`

Goal:
- Move the state ambiguity diagnostic helpers out of `usage_drain_model.py` as a smaller bite-size split before tackling the broader walk-forward transition-risk engine.
- Preserve existing walk-forward report behavior through public helper imports aliased back to the existing private names.
- Keep the new diagnostic module under `agent-maintainer` source-line limits.

Acceptance:
- Focused usage-drain tests pass.
- Full test suite passes.
- `agent-maintainer verify --profile fast` passes.
- Ratchets pass and max-file-lines tightens.
- `tach.toml` explicitly tracks the new state diagnostics module.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/usage_drain_state_diagnostics.py` for state ambiguity signatures, ambiguity scope summaries, ambiguous-state row formatting, and state signature generation.
- Replaced local state ambiguity helper definitions in `usage_drain_model.py` with compatibility imports.
- Updated `tach.toml` so `usage_drain_state_diagnostics.py` belongs to the diagnostics/reporting boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Metrics:
- `usage_drain_model.py`: 4,412 lines.
- `usage_drain_state_diagnostics.py`: 204 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 7,995 -> 7,811 total source-line overage.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_state_diagnostics.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-state-diagnostics.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Continue the walk-forward diagnostic split in a separate local branch. Good next candidates are `_state_bucket_predictions`, `_transition_risk_predictions`, `_state_bucket_transition_risk`, `_transition_rate`, `_state_bucket_prediction`, and state bucket diagnostics; keep threshold-gated delta prediction and row generation for later slices if the module would exceed the size budget.
### `refactor/usage-drain-state-buckets`

Goal:
- Move reusable state-bucket prediction and transition-risk detail helpers out of `usage_drain_model.py`.
- Keep regime-grace transition orchestration in `usage_drain_model.py` for a later narrower branch.
- Preserve existing report schema and helper names through compatibility imports.

Acceptance:
- Focused usage-drain tests pass.
- Full test suite passes.
- `agent-maintainer verify --profile fast` passes.
- Ratchets pass and max-file-lines tightens.
- `tach.toml` explicitly tracks the new state bucket module.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/usage_drain_state_buckets.py` for state-bucket model signatures, minimum support, state-bucket predictions, transition-rate helpers, bucket diagnostics, and transition-risk detail diagnostics.
- Replaced local state-bucket helper definitions in `usage_drain_model.py` with compatibility imports.
- Left `_transition_risk_predictions` in `usage_drain_model.py` because it still owns regime-grace policy decisions.
- Updated `tach.toml` so `usage_drain_state_buckets.py` belongs to the diagnostics/reporting boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Metrics:
- `usage_drain_model.py`: 4,205 lines.
- `usage_drain_state_buckets.py`: 235 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 7,811 -> 7,617 total source-line overage.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_state_buckets.py src/codex_usage_tracker/usage_drain_state_diagnostics.py`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_state_buckets.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-state-buckets.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Continue usage-drain walk-forward split with threshold-gated delta helpers or transition-risk summary metrics in a separate branch. Keep `_walk_forward_prediction_rows` and `_walk_forward_prediction_summary` for a later orchestration branch unless characterization coverage is broadened first.
### `refactor/usage-drain-transition-risk-metrics`

Goal:
- Move transition-risk target and binary-classification metric helpers out of `usage_drain_model.py`.
- Keep transition-risk summary/scope orchestration in `usage_drain_model.py` because it still owns regime-grace threshold policy.
- Preserve existing report schema and helper names through compatibility imports.

Acceptance:
- Focused usage-drain tests pass.
- Full test suite passes.
- `agent-maintainer verify --profile fast` passes.
- Ratchets pass and max-file-lines tightens.
- `tach.toml` explicitly tracks the new transition metrics module.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/usage_drain_transition_metrics.py` for transition target metrics, risk-model name extraction, Brier/AUC/average-precision metrics, and top-decile precision/recall helpers.
- Replaced local transition metric helper definitions in `usage_drain_model.py` with compatibility imports.
- Kept regime-scoped transition summary functions in `usage_drain_model.py` for a later branch.
- Updated `tach.toml` so `usage_drain_transition_metrics.py` belongs to the diagnostics/reporting boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Metrics:
- `usage_drain_model.py`: 4,105 lines.
- `usage_drain_transition_metrics.py`: 134 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 7,617 -> 7,504 total source-line overage.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_transition_metrics.py`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_transition_metrics.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-transition-metrics.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Continue with threshold-gated delta helpers or one-percent grace calibration in separate local branches. Avoid moving full walk-forward row generation until the surrounding diagnostics are smaller and characterization coverage is easier to audit.
### `refactor/usage-drain-transition-gates`

Goal:
- Move transition delta gate thresholds and gate helper functions out of `usage_drain_model.py`.
- Preserve the shared threshold constants by importing them back into the model for existing boundary and transition row logic.
- Keep walk-forward row generation in `usage_drain_model.py` for a later orchestration branch.

Acceptance:
- Focused usage-drain tests pass.
- Full test suite passes.
- `agent-maintainer verify --profile fast` passes.
- Ratchets pass and max-file-lines tightens.
- `tach.toml` explicitly tracks the new transition gate module.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/usage_drain_transition_gates.py` for risk-gate threshold constants, risk-gated transition delta prediction, gate-threshold selection, threshold error-sum updates, and gate diagnostics.
- Replaced local transition gate helper definitions in `usage_drain_model.py` with compatibility imports.
- Preserved `RISK_GATE_THRESHOLDS`, `TRANSITION_DELTA_RISK_GATE_THRESHOLD`, and `TRANSITION_DELTA_RISK_GATE_THRESHOLDS` as single-source imported constants.
- Updated `tach.toml` so `usage_drain_transition_gates.py` belongs to the diagnostics/reporting boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Metrics:
- `usage_drain_model.py`: 3,982 lines.
- `usage_drain_transition_gates.py`: 147 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 7,504 -> 7,389 total source-line overage.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_transition_gates.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-transition-gates.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Continue with one-percent grace calibration helpers or prediction error diagnostics in separate local branches. `usage_drain_model.py` is now below 4,000 lines; keep using small modules rather than moving full walk-forward row generation in one shot.
