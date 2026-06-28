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
### `refactor/usage-drain-one-percent-grace`

Goal:
- Move one-percent grace calibration and prediction helpers out of `usage_drain_model.py`.
- Preserve regime-grace constants as a single source by importing them back into the model for remaining transition logic.
- Keep row generation and prediction-error diagnostics in `usage_drain_model.py` for later slices.

Acceptance:
- Focused usage-drain tests pass.
- Full test suite passes.
- `agent-maintainer verify --profile fast` passes.
- Ratchets pass and max-file-lines tightens.
- `tach.toml` explicitly tracks the new grace module.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/usage_drain_grace.py` for regime-grace constants, calibration grids, calibration rows, grace config records, one-percent regime prediction, and small-break age detection.
- Replaced local grace helper definitions in `usage_drain_model.py` with compatibility imports.
- Preserved remaining regime-grace uses in the model through imported constants and helpers.
- Updated `tach.toml` so `usage_drain_grace.py` belongs to the diagnostics/reporting boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Metrics:
- `usage_drain_model.py`: 3,844 lines.
- `usage_drain_grace.py`: 180 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 7,389 -> 7,243 total source-line overage.

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
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_grace.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-grace.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Continue with prediction-error diagnostics or span error metadata in separate local branches. The large model is now under 3,900 lines; continue preserving compatibility imports until the public orchestration shape is ready to simplify.

### `refactor/usage-drain-error-diagnostics`

Goal:
- Move prediction-error diagnostics and span error metadata helpers out of `usage_drain_model.py`.
- Preserve existing report schemas and internal helper names through compatibility imports.
- Reduce duplicate-helper and max-file-lines ratchet baselines.

Acceptance:
- Focused usage-drain tests pass.
- Full test suite passes.
- `agent-maintainer verify --profile fast` passes.
- Ratchets pass and tighten where possible.
- `tach.toml` explicitly tracks the new error diagnostics module.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/usage_drain_error_diagnostics.py` for span error metadata, prediction error rollups, transition error groupings, largest error rows, and shared value distributions.
- Replaced local helper definitions in `usage_drain_model.py` with compatibility imports.
- Updated `tach.toml` so `usage_drain_error_diagnostics.py` belongs to the diagnostics/reporting boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json` and `.agent-maintainer/git-agent-ratchet-duplicate-helpers.json`.

Metrics:
- `usage_drain_model.py`: 3,660 lines.
- `usage_drain_error_diagnostics.py`: 202 lines.
- `git-agent-ratchet max-file-lines`: baseline ratcheted down 7,243 -> 7,059 total source-line overage.
- `git-agent-ratchet duplicate-helpers`: baseline ratcheted down 66 -> 64.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_error_diagnostics.py`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed, ratcheted baseline.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_error_diagnostics.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-error-diagnostics.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Continue with remaining walk-forward orchestration helpers or start the store-query-boundary roadmap item once the usage-drain hotspot is small enough for review.

### `refactor/usage-drain-history-state`

Goal:
- Move walk-forward history-state bucket helpers out of `usage_drain_model.py`.
- Preserve existing report schemas and private call-site aliases.
- Keep the split small enough to verify with existing usage-drain characterization tests.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/usage_drain_history_state.py` for previous-delta buckets, streak buckets, previous-span wall-time buckets, and previous-call-duration buckets.
- Replaced local helper definitions in `usage_drain_model.py` with compatibility imports.
- Updated `tach.toml` so `usage_drain_history_state.py` belongs to the diagnostics/reporting boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_history_state.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline from 7059 to 7002.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_history_state.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-history-state.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.
- `.venv/bin/radon cc src -a -s`: completed; average complexity remains A.
- `.venv/bin/radon mi src -s`: completed; legacy large-file maintainability index warnings remain visible.
- `.venv/bin/xenon --max-absolute B --max-modules A --max-average A src`: expected baseline failure on legacy hotspots outside this slice plus existing usage-drain modules not yet refactored.

Next handoff:
- Continue one small usage-drain orchestration extraction at a time, likely around walk-forward prediction row assembly or transition-risk summary helpers only if the dependency map stays clean.

### `refactor/usage-drain-transition-risk-summary`

Goal:
- Move transition-risk prediction and summary helpers out of `usage_drain_model.py`.
- Keep walk-forward orchestration call sites stable through compatibility imports.
- Keep the slice limited to existing transition metrics instead of creating another module.

Status:
- Complete locally.

Completed edits:
- Moved transition-risk prediction, summary, and scoped target helpers into `src/codex_usage_tracker/usage_drain_transition_metrics.py`.
- Replaced local helper definitions in `usage_drain_model.py` with compatibility imports.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_transition_metrics.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline from 7002 to 6913.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_transition_metrics.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-transition-risk-summary.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Continue with another narrow helper cluster only if it has a clean dependency map; otherwise move to the next roadmap milestone rather than forcing a risky usage-drain split.

### `refactor/usage-drain-capacity-specs`

Goal:
- Move capacity-model specification construction out of `usage_drain_model.py`.
- Avoid creating a new oversized file while preserving predictive model behavior.
- Keep the model facade responsible for orchestration only.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/usage_drain_capacity_specs.py` for capacity-model `PredictiveModelSpec` construction.
- Replaced the local `_capacity_model_specs` definition in `usage_drain_model.py` with a compatibility import.
- Registered the new module in `tach.toml`.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.
- Corrected an initial placement that made `usage_drain_predictive_specs.py` exceed the source-line budget by isolating capacity specs into their own module.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_predictive_specs.py src/codex_usage_tracker/usage_drain_capacity_specs.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline from 6913 to 6722.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_capacity_specs.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-capacity-specs.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Consider moving from usage-drain split work to store/query boundary characterization, because further usage-drain orchestration moves are higher-risk and should be handled only with more targeted tests.

### `refactor/store-connection-boundary`

Goal:
- Move the SQLite connection context manager out of `store.py`.
- Preserve `codex_usage_tracker.store.connect` as a compatibility facade import.
- Set up future store query modules without circular imports back into `store.py`.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/store_connection.py` for the SQLite connection context manager.
- Removed the local `connect` definition from `store.py` and imported it from `store_connection.py`.
- Updated `tach.toml` so `store_connection.py` belongs to the persistence/store boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_connection.py`: passed.
- `.venv/bin/python -m pytest tests/test_store_migrations.py tests/test_store_dashboard_mcp.py tests/test_store_large_batches.py`: 27 passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline from 6722 to 6706.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_connection.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-store-connection.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Extract diagnostic read queries into a store query module now that they can import `store_connection.connect` and `store_schema.init_db` without circularly depending on `store.py`.

### `refactor/store-diagnostic-query-boundary`

Goal:
- Move aggregate diagnostic fact read queries out of `store.py`.
- Preserve `codex_usage_tracker.store.query_diagnostic_facts` and `query_diagnostic_summary` as facade imports.
- Avoid adding new private cross-module imports while sharing SQL helpers and row conversion.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/store_diagnostic_queries.py` for aggregate diagnostic fact and diagnostic summary read models.
- Added `src/codex_usage_tracker/store_rows.py` for shared SQLite row-to-dict conversion.
- Re-exported moved diagnostic query functions from `store.py` and kept the shared diagnostic fact filter available to the remaining per-call query path.
- Added public SQL helper aliases in `store_query_sql.py` for the new query module.
- Updated `tach.toml` so the new store read modules belong to the persistence/store boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_diagnostic_queries.py src/codex_usage_tracker/store_rows.py src/codex_usage_tracker/store_query_sql.py`: passed.
- `.venv/bin/python -m pytest tests/test_store_dashboard_mcp.py tests/test_privacy.py tests/test_context_evidence.py tests/test_diagnostic_snapshots.py`: 39 passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and large-diff/no-test-file change-budget warnings for behavior-preserving refactor.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline from 6706 to 6406.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_diagnostic_queries.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-store-diagnostic-queries.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed.

Next handoff:
- Extract diagnostic fact per-call query/count helpers next, likely together with usage-row timing conversion helpers so the new module does not import back from `store.py`.

### `refactor/store-diagnostic-call-query-boundary`

Goal:
- Move diagnostic fact per-call query/count helpers out of `store.py`.
- Move usage-row timing conversion helpers into a shared row module.
- Keep `codex_usage_tracker.store` as the compatibility facade for existing imports.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/store_diagnostic_call_queries.py` for per-call diagnostic fact read models.
- Extended `src/codex_usage_tracker/store_rows.py` with usage-row timing enrichment helpers.
- Re-exported moved per-call diagnostic query functions from `store.py`.
- Added a public `normalize_offset` alias in `store_query_sql.py` for read-model modules.
- Updated `tach.toml` so the new call-query module belongs to the persistence/store boundary group.
- Split the per-call query path out of `store_diagnostic_queries.py` after `agent-maintainer fast` caught that combining aggregate and per-call queries exceeded the source-line budget.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_diagnostic_call_queries.py src/codex_usage_tracker/store_diagnostic_queries.py src/codex_usage_tracker/store_rows.py src/codex_usage_tracker/store_query_sql.py`: passed.
- `.venv/bin/python -m pytest tests/test_context_evidence.py tests/test_store_dashboard_mcp.py tests/test_dashboard_server.py`: 38 passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m pytest`: 325 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning and no-test-file change-budget warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline from 6406 to 6203.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_diagnostic_call_queries.py --dependencies --usages`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_rows.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-store-diagnostic-call-queries.json`: passed.
- `.venv/bin/tach check`: expected informational failure same 13 documented boundary violations.
- `git diff --check`: passed after trimming EOF whitespace.

Next handoff:
- Continue store/query split with dashboard/API read queries, or attack the remaining parser-to-store boundary by moving refresh orchestration out of `store.py`.
### `refactor/store-dashboard-query-boundary`

Goal:
- Move dashboard usage read queries out of `store.py`.
- Preserve `codex_usage_tracker.store` facade imports for dashboard/API callers.
- Keep query timing SQL shared without introducing a circular dependency.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/store_dashboard_queries.py` for dashboard usage events, counts, token summaries, usage status, latest observed usage, and observed-usage reconciliation helpers.
- Added `src/codex_usage_tracker/store_usage_timing.py` for shared previous-call timing SQL snippets.
- Re-exported moved dashboard query functions from `store.py`.
- Removed stale observed-usage reconciliation constant from `store.py`.
- Updated `tach.toml` so the new dashboard query and timing modules belong to the persistence/store boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json` and `.agent-maintainer/git-agent-ratchet-duplicate-helpers.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_dashboard_queries.py src/codex_usage_tracker/store_usage_timing.py`: passed.
- `.venv/bin/python -m compileall src/codex_usage_tracker/store.py src/codex_usage_tracker/store_dashboard_queries.py src/codex_usage_tracker/store_usage_timing.py`: passed.
- `.venv/bin/python -m pytest -q tests/test_dashboard_server.py tests/test_store_dashboard_mcp.py tests/test_store_migrations.py tests/test_usage_drain_reports.py`: 42 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion warning and behavior-preserving refactor change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 6203 to 5840.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed, ratcheted baseline 64 to 63.
- `.venv/bin/tach report src/codex_usage_tracker/store_dashboard_queries.py --dependencies --usages`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_usage_timing.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-store-dashboard-queries.json`: passed.
- `.venv/bin/tach check`: expected informational failure, same 13 documented legacy boundary violations.
- `git diff --check`: passed.

Remaining risks:
- `store.py` is still a large facade with refresh/upsert/export/query responsibilities and direct parser dependencies.
- Dashboard query behavior is characterized by existing tests only; no schema contract changed.

Next handoff:
- Extract usage API read queries next, keeping `store.py` as compatibility facade and avoiding a too-large query module.

### `refactor/store-usage-api-query-boundary`

Goal:
- Move live dashboard `/api/calls` read queries out of `store.py`.
- Preserve `codex_usage_tracker.store.query_usage_api_events` and `query_usage_api_event_count` facade imports.
- Replace cross-module private SQL helper usage with public aliases.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/store_usage_api_queries.py` for live usage API row and count queries.
- Added public `usage_api_where_clause` and `usage_api_sort_expression` aliases in `store_query_sql.py`.
- Re-exported moved live API query functions from `store.py`.
- Updated `tach.toml` so the new usage API query module belongs to the persistence/store boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json` and `.agent-maintainer/git-agent-ratchet-private-imports.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_usage_api_queries.py src/codex_usage_tracker/store_query_sql.py`: passed.
- `.venv/bin/python -m compileall src/codex_usage_tracker/store.py src/codex_usage_tracker/store_usage_api_queries.py src/codex_usage_tracker/store_query_sql.py`: passed.
- `.venv/bin/python -m pytest -q tests/test_dashboard_server.py::test_dashboard_server_live_sql_api_slices_are_aggregate_only tests/test_store_dashboard_mcp.py::test_dashboard_event_query_uses_sql_prefilters tests/test_store_dashboard_mcp.py::test_large_history_query_prefilter_uses_sql_indexes tests/test_store_dashboard_mcp.py::test_dashboard_query_limit_zero_loads_all_rows`: 4 passed.
- `.venv/bin/python -m pytest -q tests/test_dashboard_server.py tests/test_store_dashboard_mcp.py tests/test_context_evidence.py`: 38 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion warning and behavior-preserving refactor no-test-file warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 5840 to 5723.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed, ratcheted baseline 10 to 8.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_usage_api_queries.py --dependencies --usages`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_query_sql.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-store-usage-api-queries.json`: passed.
- `.venv/bin/tach check`: expected informational failure, same 13 documented legacy boundary violations.
- `git diff --check`: passed.

Remaining risks:
- `store.py` still imports private SQL helpers for legacy summary/thread/export query functions.
- `store_thread_summaries.py` still has private helper imports; private-import ratchet improved but is not yet zero.

Next handoff:
- Extract thread-summary or session/record query read models next, depending on which gives the cleaner boundary improvement without broad blast radius.
### `refactor/store-thread-summary-query-boundary`

Goal:
- Move materialized thread-summary read query out of `store.py`.
- Keep `store.py` as the compatibility facade for `query_thread_summaries`.
- Replace thread-summary module private SQL helper imports with public aliases.

Status:
- Complete locally.

Completed edits:
- Moved `query_thread_summaries` into `src/codex_usage_tracker/store_thread_summaries.py`.
- Added public `thread_key_expression` alias in `store_query_sql.py`.
- Updated `store_thread_summaries.py` to use public `usage_where_clause`, normalizers, and `thread_key_expression`.
- Re-exported `query_thread_summaries` from `store.py`.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json` and `.agent-maintainer/git-agent-ratchet-private-imports.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_thread_summaries.py src/codex_usage_tracker/store_query_sql.py`: passed.
- `.venv/bin/python -m compileall src/codex_usage_tracker/store.py src/codex_usage_tracker/store_thread_summaries.py src/codex_usage_tracker/store_query_sql.py`: passed.
- `.venv/bin/python -m pytest -q tests/test_store_dashboard_mcp.py::test_upsert_materializes_thread_summaries tests/test_store_dashboard_mcp.py::test_thread_summaries_keep_active_and_all_history_scopes_separate tests/test_dashboard_server.py::test_dashboard_server_live_sql_api_slices_are_aggregate_only`: 3 passed.
- `.venv/bin/python -m pytest -q tests/test_dashboard_server.py tests/test_store_dashboard_mcp.py tests/test_context_evidence.py`: 38 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion warning and behavior-preserving refactor no-test-file warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 5723 to 5666.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed, ratcheted baseline 8 to 4.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_thread_summaries.py --dependencies --usages`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-store-thread-summary-queries.json`: passed.
- `.venv/bin/tach check`: expected informational failure, same 13 documented legacy boundary violations.
- `git diff --check`: passed.

Remaining risks:
- `store.py` still owns summary/session/record/export read functions and refresh/upsert orchestration.
- Private SQL helper ratchet is improved but still not zero because `store.py` has legacy helper imports.

Next handoff:
- Extract session/record/evidence read models next; this should also enable moving `context.py` off the `store.py` facade later.
### `refactor/store-usage-record-query-boundary`

Goal:
- Move usage detail read models out of `store.py`.
- Preserve `store.py` compatibility facade imports for session, record, and expensive-call callers.
- Point context evidence loading at the narrower read-model module instead of the broad store facade.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/store_usage_record_queries.py` for `query_session_usage`, `query_usage_record`, and `query_most_expensive_calls`.
- Re-exported moved detail query functions from `store.py`.
- Updated `context.py` to import `query_usage_record` from the narrower usage-record query module.
- Updated `tach.toml` to place the new query module in the store boundary and allow the context/parser group to depend on that read model.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json` and `.agent-maintainer/git-agent-ratchet-private-imports.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_usage_record_queries.py src/codex_usage_tracker/context.py`: passed.
- `.venv/bin/python -m compileall src/codex_usage_tracker/store.py src/codex_usage_tracker/store_usage_record_queries.py src/codex_usage_tracker/context.py`: passed.
- `.venv/bin/python -m pytest -q tests/test_context_evidence.py tests/test_privacy.py tests/test_mcp_integration.py tests/test_dashboard_server.py::test_dashboard_server_can_enable_context_api_at_runtime`: 13 passed.
- `.venv/bin/python -m pytest -q tests/test_dashboard_server.py tests/test_store_dashboard_mcp.py tests/test_context_evidence.py tests/test_privacy.py tests/test_mcp_integration.py tests/test_usage_drain_reports.py tests/test_dashboard_payload.py tests/test_dashboard_data.py`: 61 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion warning and behavior-preserving refactor no-test-file warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 5666 to 5544.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed, ratcheted baseline 4 to 3.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_usage_record_queries.py --dependencies --usages`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/context.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-store-usage-record-queries.json`: passed.
- `.venv/bin/tach check`: expected informational failure now reduced to 12 documented legacy parser/support boundary violations.
- `git diff --check`: passed.

Remaining risks:
- `store.py` still owns summary/export and refresh/upsert orchestration.
- Parser dependencies remain the dominant Tach blocker for the store boundary.

Next handoff:
- Extract summary/export read models or split refresh orchestration from parser-facing ingestion, depending on desired next risk slice.
### `refactor/store-summary-query-boundary`

Goal:
- Move `query_summary` out of `store.py`.
- Preserve `store.py` compatibility facade import.
- Bring `store.py` below the 600-line file-size target before touching export behavior.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/store_summary_queries.py` for aggregate summary read queries.
- Added public `group_expression` and `since_where_clause` aliases in `store_query_sql.py`.
- Re-exported `query_summary` from `store.py`.
- Updated `tach.toml` so the summary query module belongs to the persistence/store boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json` and `.agent-maintainer/git-agent-ratchet-private-imports.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_summary_queries.py src/codex_usage_tracker/store_query_sql.py`: passed.
- `.venv/bin/python -m compileall src/codex_usage_tracker/store.py src/codex_usage_tracker/store_summary_queries.py src/codex_usage_tracker/store_query_sql.py`: passed.
- `.venv/bin/python -m pytest -q tests/test_store_dashboard_mcp.py::test_refresh_is_idempotent_and_summary_works tests/test_usage_drain_reports.py tests/test_dashboard_payload.py`: 12 passed.
- `.venv/bin/python -m pytest -q tests/test_dashboard_server.py tests/test_store_dashboard_mcp.py tests/test_usage_drain_reports.py tests/test_dashboard_payload.py tests/test_dashboard_data.py tests/test_mcp_integration.py`: 51 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion warning and behavior-preserving refactor no-test-file warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 5544 to 5522.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed, ratcheted baseline 3 to 1.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_summary_queries.py --dependencies --usages`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_query_sql.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-store-summary-queries.json`: passed.
- `.venv/bin/tach check`: expected informational failure, 12 documented legacy parser/support boundary violations.
- `git diff --check`: passed.

Remaining risks:
- `store.py` still owns CSV export and parser-facing refresh/upsert orchestration.
- One cross-module private import remains in `store.py` for export limit normalization.

Next handoff:
- Extract export behavior next to eliminate the remaining private SQL helper import from `store.py`.
### `refactor/store-export-boundary`

Goal:
- Move CSV export behavior out of `store.py`.
- Preserve `store.py` compatibility facade import for CLI/MCP callers.
- Eliminate the remaining cross-module private SQL helper import from `store.py`.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/store_exports.py` for `export_usage_csv`.
- Moved export privacy handling and CSV writing out of `store.py`.
- Re-exported `export_usage_csv` from `store.py`.
- Updated `tach.toml` so the export module belongs to the persistence/store boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-private-imports.json` to zero.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_exports.py`: passed.
- `.venv/bin/python -m compileall src/codex_usage_tracker/store.py src/codex_usage_tracker/store_exports.py`: passed.
- `.venv/bin/python -m pytest -q tests/test_mcp_integration.py tests/test_privacy.py tests/test_cli_release.py`: 23 passed.
- `.venv/bin/python -m pytest -q tests/test_dashboard_server.py tests/test_store_dashboard_mcp.py tests/test_privacy.py tests/test_mcp_integration.py tests/test_context_evidence.py tests/test_usage_drain_reports.py tests/test_dashboard_payload.py tests/test_dashboard_data.py`: 61 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion warning and behavior-preserving refactor no-test-file warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed, ratcheted baseline 1 to 0.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/store_exports.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-store-exports.json`: passed.
- `.venv/bin/tach check`: expected informational failure, 12 documented legacy parser/support boundary violations.
- `git diff --check`: passed after removing the EOF blank line from `store.py`.

Remaining risks:
- `store.py` still owns parser-facing refresh/upsert orchestration and diagnostic snapshot persistence.
- Tach blockers are now dominated by parser imports in store/store_sources and the support-to-diagnostics dependency.

Next handoff:
- Start splitting parser-facing refresh orchestration from store persistence, or isolate support diagnostics, now that read/export query boundaries are smaller.
### `refactor/server-response-helper-boundary`

Goal:
- Start server split with a low-risk response-helper extraction.
- Keep `_UsageDashboardHandler._send_json` and `_send_html` call sites stable.
- Reduce `server.py` without changing routing or API payloads.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/server_responses.py` for JSON/HTML response writing and broken-connection handling.
- Updated `server.py` `_send_json` and `_send_html` to delegate to response helpers.
- Removed direct `_json_response_body` alias from `server.py`.
- Updated `tach.toml` so `server_responses.py` belongs to the dashboard/server boundary group.
- Ratcheted `.agent-maintainer/git-agent-ratchet-max-file-lines.json`.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_responses.py`: passed.
- `.venv/bin/python -m compileall src/codex_usage_tracker/server.py src/codex_usage_tracker/server_responses.py`: passed.
- `.venv/bin/python -m pytest -q tests/test_dashboard_server.py tests/test_dashboard_status.py tests/test_dashboard_live.py`: 17 passed.
- `.venv/bin/python -m pytest -q tests/test_dashboard_server.py tests/test_dashboard_status.py tests/test_dashboard_live.py tests/test_dashboard_payload.py tests/test_dashboard_data.py tests/test_dashboard_diagnostics_snapshots.py`: 38 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion warning and behavior-preserving refactor no-test-file warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 5522 to 5506.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/server_responses.py --dependencies --usages`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/server.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/codex-usage-tracker-tach-map-server-responses.json`: passed.
- `.venv/bin/tach check`: expected informational failure, 12 documented legacy parser/support boundary violations.
- `git diff --check`: passed.

Remaining risks:
- `server.py` still owns routing and handler methods in one large class.
- The next server slices should move route handlers or request parsing one endpoint family at a time.

Next handoff:
- Continue `server.py` split with an API route dispatch table or one handler family extraction after adding focused route characterization.
### `refactor/support-diagnostics-boundary-map`

Goal:
- Encode the intentional support-bundle dependency on diagnostics in `tach.toml`.
- Remove the stale support-to-diagnostics boundary violation without changing runtime behavior.

Status:
- Complete locally.

Completed edits:
- Added `codex_usage_tracker.diagnostics` to the support/report module group's allowed dependencies.

Checks:
- `.venv/bin/tach check`: expected informational failure now reduced to 11 parser/store-source boundary violations.
- `.venv/bin/tach report src/codex_usage_tracker/support.py --dependencies --usages`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks:
- Remaining Tach blockers are parser dependencies from `store.py` and `store_sources.py`.

Next handoff:
- Split parser-facing refresh/source-state code so persistence modules no longer depend directly on parser internals.

### `refactor/parser-state-boundary`

Goal:
- Move persisted parser cursor and diagnostic counter metadata behind a narrow state contract.
- Remove `store_sources.py` dependency on parser implementation while preserving parser compatibility names.
- Keep behavior unchanged and reduce Tach blockers before the larger refresh orchestration split.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/parser_state.py` for `ParserState`, parser adapter version, diagnostic key ordering, parser-state JSON serialization, and compact diagnostic counters.
- Updated `parser.py` to consume parser-state helpers and keep compatibility aliases for `parser_state_from_json` and `parser_state_to_json`.
- Updated `store.py` and `store_sources.py` to import parser metadata from `parser_state.py` instead of `parser.py`.
- Updated `tach.toml` so parser-state is an explicit narrow dependency for store persistence code.
- Ratcheted `max_file_lines` 5506 -> 5380 and `duplicate_helpers` 63 -> 62.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/parser.py src/codex_usage_tracker/parser_state.py src/codex_usage_tracker/store.py src/codex_usage_tracker/store_sources.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/parser.py src/codex_usage_tracker/parser_state.py src/codex_usage_tracker/store.py src/codex_usage_tracker/store_sources.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_store_migrations.py tests/test_context_evidence.py tests/test_dashboard_payload.py tests/test_privacy.py`: 21 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure/cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 5506 -> 5380.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed, ratcheted baseline 63 -> 62.
- `.venv/bin/tach report src/codex_usage_tracker/store_sources.py --dependencies --usages`: passed.
- `.venv/bin/tach map -o /tmp/parser-state-boundary-tach-map.json`: passed.
- `.venv/bin/tach check --output json`: expected informational failure now reduced to 3 `store.py` -> `parser.py` refresh-orchestration imports.
- `git diff --check`: passed.

Remaining risks:
- `store.py` still imports parser scanning/parsing functions for `refresh_usage_index`; this is the last known Tach blocker in this area.
- Parser state now depends on diagnostic-fact serialization, so it remains in the parser/context boundary group rather than lowest-level core.

Next handoff:
- Extract refresh orchestration out of `store.py` into a service module allowed to depend on both parser and store persistence, while preserving the `store.refresh_usage_index`/`rebuild_usage_index` public facade.

### `refactor/store-refresh-orchestration-boundary`

Goal:
- Remove the remaining direct parser dependency from `store.py`.
- Move log scanning/parsing refresh orchestration into an application-service module.
- Preserve `store.refresh_usage_index` and `store.rebuild_usage_index` as public compatibility facades.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/store_refresh.py` for refresh/rebuild orchestration.
- Left persistence helpers in `store.py` and replaced refresh/rebuild implementations with thin local-import wrappers.
- Preserved the existing `codex_usage_tracker.store.parse_usage_events_from_file_with_state` monkeypatch seam by publishing and consulting the parser callable through the store facade from `store_refresh.py`.
- Updated `tach.toml` to classify `store_refresh` with application/report services and allow persistence facades to depend on it.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/store.py src/codex_usage_tracker/store_refresh.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py src/codex_usage_tracker/store_refresh.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_store_dashboard_mcp.py::test_refresh_indexes_only_appended_token_events_when_source_grows tests/test_store_dashboard_mcp.py::test_refresh_reparses_source_when_parser_adapter_changes`: 2 passed.
- `.venv/bin/python -m pytest -q tests/test_store_migrations.py tests/test_context_evidence.py tests/test_dashboard_payload.py tests/test_privacy.py`: 21 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach report src/codex_usage_tracker/store_refresh.py --dependencies --usages`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure/cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach map -o /tmp/store-refresh-orchestration-boundary-tach-map.json`: passed.
- `git diff --check`: passed.

Remaining risks:
- `store.py` still contains persistence responsibilities that can be split further, but it no longer owns parser refresh orchestration.
- The compatibility monkeypatch seam is intentionally preserved for existing tests/callers; a later public API cleanup should deprecate it deliberately instead of removing it as incidental refactor fallout.

Next handoff:
- Move to smaller store persistence slices or server route-handler extraction now that Tach passes for the current boundary map.

### `refactor/usage-drain-regression-helper-boundary`

Goal:
- Remove generic linear-regression helper code from the large usage-drain model module.
- Reuse the existing `usage_drain_regression.py` boundary for ordinary least-squares coefficients and predictions.
- Keep usage-drain model outputs unchanged.

Status:
- Complete locally.

Completed edits:
- Added `fit_linear_coefficients` and `predict_linear` to `src/codex_usage_tracker/usage_drain_regression.py`.
- Updated `usage_drain_model.py` to import those helpers under existing internal aliases.
- Removed the duplicate local regression helper implementations from `usage_drain_model.py`.
- Ratcheted `max_file_lines` 5380 -> 5347.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_regression.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_regression.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure/cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 5380 -> 5347.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach map -o /tmp/usage-drain-regression-helper-boundary-tach-map.json`: passed.
- `git diff --check`: passed.

Remaining risks:
- `fit_usage_drain_proxy` remains the highest complexity block and should be split behind characterization checks.
- `usage_drain_model.py` is still large at roughly 3.3k lines.

Next handoff:
- Split one `fit_usage_drain_proxy` output family or one walk-forward helper cluster into a dedicated model submodule, with usage-drain tests as the characterization gate.

### `refactor/usage-drain-proxy-fit-boundary`

Goal:
- Extract the high-complexity `fit_usage_drain_proxy` implementation from `usage_drain_model.py`.
- Preserve `codex_usage_tracker.usage_drain_model.fit_usage_drain_proxy` as the public import path.
- Keep proxy-fit output schema and calculations unchanged.

Status:
- Complete locally.

Completed edits:
- Added `src/codex_usage_tracker/usage_drain_proxy_fit.py` for candidate/non-candidate proxy fit calculations.
- Updated `usage_drain_model.py` to import `fit_usage_drain_proxy` from the new module.
- Removed now-unused proxy-fit regression imports from `usage_drain_model.py`.
- Added `usage_drain_proxy_fit` to the Tach usage-drain module group.
- Ratcheted `max_file_lines` 5347 -> 5242.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_proxy_fit.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_proxy_fit.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach report src/codex_usage_tracker/usage_drain_proxy_fit.py --dependencies --usages`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure/cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 5347 -> 5242.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach map -o /tmp/usage-drain-proxy-fit-boundary-tach-map.json`: passed.
- `git diff --check`: passed.

Remaining risks:
- Walk-forward and allowance-capacity helper clusters remain high-complexity inside `usage_drain_model.py`.
- `usage_drain_model.py` is still the largest module, now roughly 3.2k lines.

Next handoff:
- Extract one walk-forward prediction helper cluster or allowance capacity family behind usage-drain characterization tests.
### refactor/usage-drain-boundary-delta-prediction

Objective:

- Extract boundary-delta model signatures, boundary-risk helpers, walk-forward delta prediction rows, and adaptive risk-gate threshold helpers from `usage_drain_model.py`.
- Keep public report behavior and CLI/API schemas unchanged.
- Preserve Tach boundaries and avoid new private cross-module imports.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_boundary_delta.py` for the boundary-delta prediction helper cluster.
- Updated `usage_drain_model.py` to call the new module through a public module namespace.
- Updated `tach.toml` so the new usage-drain module is included in the existing diagnostics/report boundary.
- Ratcheted `max_file_lines` baseline 5242 -> 4862; `usage_drain_model.py` is now 2805 lines and the extracted module is 407 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_boundary_delta.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_boundary_delta.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/usage-drain-boundary-delta-prediction-tach-map.json`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 5242 -> 4862.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `git diff --check`: passed.

Remaining risks:

- `usage_drain_model.py` remains the largest module by a wide margin.
- Allowance-capacity walk-forward prediction and summary-table formatting are still candidates for focused extraction.
- Agent-maintainer still warns that the package folder is large and that this refactor branch changes Python source without adding new tests; existing characterization tests are covering behavior for now.

Next handoff:

- Continue splitting the remaining allowance-capacity prediction helpers or summary row-formatting helpers into another narrow usage-drain module.
### refactor/usage-drain-capacity-prediction-boundary

Objective:

- Split allowance breakpoint, piecewise credit-to-delta, and online-capacity fit helpers out of `usage_drain_model.py`.
- Keep the existing `allowance_breakpoint_analysis` payload shape unchanged.
- Keep each newly extracted module below agent-maintainer new-file size limits.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_allowance_breakpoints.py` for allowance breakpoint segmentation and row shaping.
- Added `src/codex_usage_tracker/usage_drain_allowance_fits.py` for global, piecewise, and online credit-to-delta fit mechanics.
- Updated `usage_drain_model.py` to call the new allowance breakpoint module through a public module namespace.
- Updated `tach.toml` to include both new usage-drain allowance modules in the existing diagnostics/report boundary.
- Ratcheted `max_file_lines` baseline 4862 -> 4205 and `duplicate_helpers` baseline 62 -> 60.
- `usage_drain_model.py` is now 2148 lines; new modules are 290 and 409 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_allowance_breakpoints.py src/codex_usage_tracker/usage_drain_allowance_fits.py src/codex_usage_tracker/usage_drain_model.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_allowance_breakpoints.py src/codex_usage_tracker/usage_drain_allowance_fits.py src/codex_usage_tracker/usage_drain_model.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/usage-drain-capacity-prediction-boundary-tach-map.json`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 4862 -> 4205.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed, ratcheted baseline 62 -> 60.
- `git diff --check`: passed.

Remaining risks:

- `usage_drain_model.py` is still over the 600-line target, though now much smaller than the baseline.
- Walk-forward prediction rows and segment/regime summaries remain candidates for further extraction.
- Agent-maintainer still warns that the package folder is large and that this refactor branch changes Python source without adding new tests; behavior is covered by existing usage-drain characterization tests.

Next handoff:

- Continue with one more usage-drain split around walk-forward prediction row construction or segment/regime summary formatting.
### refactor/usage-drain-walk-forward-boundary

Objective:

- Split walk-forward prediction summary, row construction, and scope metrics out of `usage_drain_model.py`.
- Preserve the existing `walk_forward_prediction` report payload and piecewise-regime dependency on prediction rows.
- Keep the new module below agent-maintainer new-file size limits and avoid private cross-module imports.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_walk_forward.py` for walk-forward prediction summaries, rows, scope metrics, transition gate diagnostics, and state-bucket diagnostics.
- Updated `usage_drain_model.py` to call `usage_drain_walk_forward` through a public module namespace.
- Updated `tach.toml` to include the walk-forward usage-drain module in the existing diagnostics/report boundary.
- Ratcheted `max_file_lines` baseline 4205 -> 3744.
- `usage_drain_model.py` is now 1687 lines; the new walk-forward module is 419 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_walk_forward.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_walk_forward.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/usage-drain-walk-forward-boundary-tach-map.json`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 4205 -> 3744.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `git diff --check`: passed.

Remaining risks:

- `usage_drain_model.py` remains above the 600-line target and still contains piecewise regime, boundary, token-component, and one-percent capacity modeling helpers.
- Agent-maintainer still warns about package folder size and source changes without new tests; existing usage-drain tests are serving as characterization coverage.

Next handoff:

- Extract either the piecewise-regime/boundary summary cluster or token-component regression cluster into a focused module.
### refactor/usage-drain-token-component-boundary

Objective:

- Split token-component regression helpers out of `usage_drain_model.py`.
- Preserve visible-drain token regression and exact-1%-capacity token accounting report payloads.
- Keep the new module below agent-maintainer new-file size limits and avoid private cross-module imports.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_token_components.py` for token-component feature extraction, visible-drain regression variants, credit-accounting variants, and exact-1%-capacity component checks.
- Updated `usage_drain_model.py` to call token-component diagnostics through a public module namespace.
- Updated `tach.toml` to include the token-component usage-drain module in the existing diagnostics/report boundary.
- Ratcheted `max_file_lines` baseline 3744 -> 3515.
- `usage_drain_model.py` is now 1458 lines; the new token-component module is 240 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_token_components.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_token_components.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/usage-drain-token-component-boundary-tach-map.json`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 3744 -> 3515.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `git diff --check`: passed.

Remaining risks:

- `usage_drain_model.py` remains above the 600-line target.
- Piecewise regime and boundary summary helpers are now the next major dense cluster.
- Agent-maintainer still warns about package folder size; that is expected until broader package boundaries are introduced.

Next handoff:

- Extract piecewise-regime summary helpers or split the remaining boundary summary cluster into two size-limited modules.
### refactor/usage-drain-boundary-delta-summary

Objective:

- Split boundary-delta summary diagnostics out of `usage_drain_model.py` without taking the full regime/boundary cluster in one oversized branch.
- Preserve the existing `walk_forward_delta_prediction` payload inside piecewise boundary diagnostics.
- Keep the branch under agent-maintainer change-budget limits.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_boundary_delta_summary.py` for boundary-delta prediction scopes, risk-gate diagnostics, residual diagnostics, top error groups, and largest-error rows.
- Added `src/codex_usage_tracker/usage_drain_boundary_scopes.py` for the shared boundary scope start helper, avoiding duplicate-helper ratchet regressions.
- Updated `usage_drain_model.py` to call boundary-delta summaries through a public module namespace.
- Updated `tach.toml` to include the new boundary-delta summary and boundary-scope modules in the existing diagnostics/report boundary.
- Ratcheted `max_file_lines` baseline 3515 -> 3195.
- `usage_drain_model.py` is now 1138 lines; new modules are 339 and 15 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_boundary_delta_summary.py src/codex_usage_tracker/usage_drain_boundary_scopes.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_boundary_delta_summary.py src/codex_usage_tracker/usage_drain_boundary_scopes.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/usage-drain-boundary-delta-summary-tach-map.json`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 3515 -> 3195.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `git diff --check`: passed.

Remaining risks:

- `usage_drain_model.py` remains above the 600-line target.
- Boundary-risk/basic summary and regime-segment summary helpers are still embedded in `usage_drain_model.py`.

Next handoff:

- Extract boundary-risk/basic summary helpers as the next small branch, then extract regime segment summaries.
### refactor/usage-drain-boundary-risk-summary

Objective:

- Split boundary-risk and boundary-basic diagnostics out of `usage_drain_model.py`.
- Preserve the existing piecewise boundary diagnostics payload and keep the branch under agent-maintainer change-budget limits.
- Introduce shared regime label helpers needed by both boundary diagnostics and the remaining model code.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_boundary_summary.py` for boundary rows, context rates, transition counts, latest boundary rows, and walk-forward boundary-risk summaries.
- Added `src/codex_usage_tracker/usage_drain_regime_labels.py` for shared delta-regime and segment-position labels.
- Expanded `src/codex_usage_tracker/usage_drain_boundary_scopes.py` with shared boundary-risk scope starts.
- Updated `usage_drain_model.py` to call boundary summaries and regime labels through public module namespaces.
- Updated `tach.toml` to include the new boundary summary and regime label modules in the existing diagnostics/report boundary.
- Ratcheted `max_file_lines` baseline 3195 -> 2824.
- `usage_drain_model.py` is now 767 lines; new modules are 358 and 29 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_boundary_summary.py src/codex_usage_tracker/usage_drain_boundary_scopes.py src/codex_usage_tracker/usage_drain_regime_labels.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_boundary_summary.py src/codex_usage_tracker/usage_drain_boundary_scopes.py src/codex_usage_tracker/usage_drain_regime_labels.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/usage-drain-boundary-risk-summary-tach-map.json`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 3195 -> 2824.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `git diff --check`: passed.

Remaining risks:

- `usage_drain_model.py` is close but still above the 600-line target.
- Piecewise regime segment summaries remain embedded in `usage_drain_model.py`.

Next handoff:

- Extract the remaining piecewise regime segment/streak helpers; this should bring `usage_drain_model.py` below the 600-line target.
### refactor/usage-drain-regime-segment-summary

Objective:

- Split remaining piecewise regime segment and one-percent streak helpers out of `usage_drain_model.py`.
- Bring `usage_drain_model.py` below the 600-line file-size target.
- Preserve existing `delta_regimes`, `regime_streaks`, and `piecewise_regime_segments` payloads.

Status:

- Complete locally.

Completed edits:

- Added `src/codex_usage_tracker/usage_drain_regime_segments.py` for delta-regime summaries, streak/run records, piecewise segment summaries, position-bucket adaptation, and segment prediction metrics.
- Updated `usage_drain_model.py` to call regime segment summaries through a public module namespace.
- Updated `tach.toml` to include the regime segment module in the existing diagnostics/report boundary.
- Ratcheted `max_file_lines` baseline 2824 -> 2657.
- `usage_drain_model.py` is now 446 lines; the new regime segment module is 336 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_regime_segments.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py src/codex_usage_tracker/usage_drain_regime_segments.py --fix`: passed.
- `.venv/bin/python -m pytest -q tests/test_usage_drain_model.py tests/test_usage_drain_reports.py`: 20 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/usage-drain-regime-segment-summary-tach-map.json`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 325 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 2824 -> 2657.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `git diff --check`: passed.

Remaining risks:

- `usage_drain_model.py` now meets the file-size target, but `server.py`, `context.py`, `cli.py`, and several diagnostics modules remain oversized.
- The broader roadmap still needs subsequent server/context/parser/store boundary work.

Next handoff:

- Move from usage-drain-model split work to the next large module family, likely `server.py` routing/handlers or `context.py` parser/context boundaries.

### refactor/server-route-boundary

Objective:

- Extract pure dashboard server route tables from `_UsageDashboardHandler`.
- Keep existing handler methods and response payload behavior unchanged.
- Make future server handler splits smaller and easier to test.

Files touched:

- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_routes.py`
- `tests/test_server_routes.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`

Completed edits:

- Added `GET_ROUTE_METHODS`, `GET_DIAGNOSTIC_FACT_ROUTES`, `POST_ROUTE_METHODS`, and `is_dashboard_shell_path`.
- Replaced long `do_GET` and `do_POST` route condition chains with table-driven dispatch.
- Preserved special diagnostics fact filtering for compactions (`fact_type=compaction`) and tools (`fact_group=tools`).
- Added server route characterization tests.
- Declared `server_routes` in the dashboard/server `tach` module boundary.
- Ratcheted max file-line baseline from 2657 to 2570 after reducing `server.py` from 1492 to 1405 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_routes.py tests/test_server_routes.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_routes.py tests/test_server_routes.py`: passed.
- `.venv/bin/python -m pytest -q tests/test_server_routes.py tests/test_dashboard_server.py tests/test_dashboard_diagnostics_snapshots.py`: 23 passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m pytest -q`: 328 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-route-boundary-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch is uncommitted.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 2657 -> 2570.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `radon cc src -a -s`: ran and reported current complexity inventory.
- `radon mi src -s`: ran and reported current maintainability inventory.
- `xenon --max-absolute B --max-modules A --max-average A src`: failed on existing C/D/F complexity hotspots outside this routing slice.
- `git diff --check`: passed.

Remaining risks:

- `server.py` remains oversized at 1405 lines and still needs handler/body extraction.
- Broad `xenon` remains red on existing parser/dashboard/usage-drain/report complexity blocks.
- `context.py`, `cli.py`, and several diagnostics modules remain above the target file-size budget.

Next handoff:

- Continue `refactor/server-routing-and-handlers` with a narrow extraction of live API query/row helper logic or diagnostics snapshot handler plumbing.

### refactor/server-live-query-params

Objective:

- Extract live dashboard API query-parameter normalization from `_UsageDashboardHandler`.
- Keep `/api/calls` and `/api/thread-calls` behavior unchanged.
- Leave database row fetching and annotation for a later, separate branch.

Files touched:

- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_live_queries.py`
- `tests/test_server_live_queries.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`

Completed edits:

- Added `live_query_params()` as a pure helper for limit, offset, search, filters, sort, direction, history scope, and thread-key normalization.
- Kept `_UsageDashboardHandler._live_query_params()` as a small compatibility wrapper for existing handlers.
- Added focused tests for normal filters, thread-key override behavior, `limit=all`, and invalid limit rejection.
- Declared `server_live_queries` in the dashboard/server `tach` module boundary.
- Ratcheted max file-line baseline from 2570 to 2544 after reducing `server.py` from 1405 to 1379 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_live_queries.py tests/test_server_live_queries.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_live_queries.py tests/test_server_live_queries.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_live_queries.py tests/test_dashboard_server.py -q`: 14 passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 331 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch is uncommitted.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 2570 -> 2544.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/tach map -o /tmp/server-live-query-params-tach-map.json`: passed.
- `radon cc src -a -s`: ran and reported current complexity inventory.
- `radon mi src -s`: ran and reported current maintainability inventory.
- `xenon --max-absolute B --max-modules A --max-average A src`: failed on existing C/D/F complexity hotspots outside this query-params slice.

Remaining risks:

- `server.py` remains oversized at 1379 lines and still needs live row fetching, diagnostics snapshot handling, and usage refresh handler extraction.
- Broad `xenon` remains red on existing parser/dashboard/usage-drain/report complexity blocks.
- `context.py`, `cli.py`, and several diagnostics modules remain above the target file-size budget.

Next handoff:

- Continue `refactor/server-routing-and-handlers` with a narrow extraction of live row fetching/annotation or diagnostics snapshot handler plumbing.

### refactor/server-live-row-queries

Objective:

- Extract live dashboard API row fetching and annotation from `_UsageDashboardHandler`.
- Preserve `/api/calls`, `/api/thread-calls`, and `/api/call` annotation behavior.
- Keep derived pricing/credit filters applied after annotation, as before.

Files touched:

- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_live_rows.py`
- `tests/test_server_live_rows.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`

Completed edits:

- Added `query_live_call_rows()` for store-backed live row fetching and pagination.
- Added `annotate_live_rows()` for the existing call-origin, thread-attachment, pricing, allowance, recommendation, project-identity, and privacy annotation sequence.
- Kept `_UsageDashboardHandler._live_call_rows()` and `_annotate_live_rows()` as compatibility wrappers around the extracted helpers.
- Added tests for normal count-backed pagination, derived-filter pagination, and empty annotation behavior.
- Split the new module helpers so `server_live_rows.py` itself passes `xenon --max-absolute B --max-modules A --max-average A`.
- Declared `server_live_rows` in the dashboard/server `tach` module boundary.
- Ratcheted max file-line baseline from 2544 to 2490 after reducing `server.py` from 1379 to 1325 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_live_rows.py tests/test_server_live_rows.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_live_rows.py tests/test_server_live_rows.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_live_rows.py tests/test_dashboard_server.py -q`: 14 passed.
- `radon cc src/codex_usage_tracker/server_live_rows.py -a -s`: average A (2.8).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_live_rows.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 334 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-live-row-queries-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch is uncommitted.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 2544 -> 2490.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `radon cc src -a -s`: ran and reported current complexity inventory.
- `radon mi src -s`: ran and reported current maintainability inventory.
- `xenon --max-absolute B --max-modules A --max-average A src`: failed on existing C/D/F complexity hotspots outside this live-row slice.

Remaining risks:

- `server.py` remains oversized at 1325 lines and still needs diagnostics snapshot handling and usage refresh handler extraction.
- Broad `xenon` remains red on existing parser/dashboard/usage-drain/report complexity blocks.
- `context.py`, `cli.py`, and several diagnostics modules remain above the target file-size budget.

Next handoff:

- Continue `refactor/server-routing-and-handlers` with diagnostics snapshot handler plumbing or `_handle_usage` refresh payload extraction.

### refactor/server-usage-refresh-payload

Objective:

- Extract the live dashboard usage-refresh metadata block from `_handle_usage`.
- Preserve `/api/usage?refresh=1` token checks, locking behavior, refresh payload keys, and diagnostics timing.
- Keep HTTP error handling and dashboard payload generation in the handler for this branch.

Files touched:

- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_usage_refresh.py`
- `tests/test_server_usage_refresh.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`

Completed edits:

- Added `refresh_usage_payload()` to run `refresh_usage_index()` under the existing refresh lock and return aggregate refresh metadata plus elapsed milliseconds.
- Replaced the inline refresh metadata assembly in `_handle_usage` with a helper call.
- Added a focused test proving lock usage, forwarded paths/options, aggregate payload keys, parser diagnostics, and elapsed timing type.
- Declared `server_usage_refresh` in the dashboard/server `tach` module boundary.
- Ratcheted max file-line baseline from 2490 to 2479 after reducing `server.py` from 1325 to 1314 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_usage_refresh.py tests/test_server_usage_refresh.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_usage_refresh.py tests/test_server_usage_refresh.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_usage_refresh.py tests/test_dashboard_server.py -q`: 12 passed.
- `radon cc src/codex_usage_tracker/server_usage_refresh.py -a -s`: average A (1.0).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_usage_refresh.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 335 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-usage-refresh-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch is uncommitted.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 2490 -> 2479.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `radon cc src -a -s`: ran and reported current complexity inventory.
- `radon mi src -s`: ran and reported current maintainability inventory.
- `xenon --max-absolute B --max-modules A --max-average A src`: failed on existing C/D/F complexity hotspots outside this refresh-payload slice.

Remaining risks:

- `server.py` remains oversized at 1314 lines and still needs diagnostics snapshot handling and dashboard/context handler extraction.
- Broad `xenon` remains red on existing parser/dashboard/usage-drain/report complexity blocks.
- `context.py`, `cli.py`, and several diagnostics modules remain above the target file-size budget.

Next handoff:

- Continue `refactor/server-routing-and-handlers` with diagnostics snapshot handler plumbing or dashboard shell/context handler extraction.

### refactor/server-diagnostic-snapshot-payloads

Objective:

- Extract diagnostic snapshot payload construction from `_UsageDashboardHandler`.
- Preserve diagnostic refresh auth checks, lock usage, include-archived handling, payload shapes, and existing HTTP error messages.
- Keep HTTP response writing in `server.py` for this branch.

Files touched:

- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_diagnostic_snapshots.py`
- `tests/test_server_diagnostic_snapshots.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`

Completed edits:

- Added `refresh_all_diagnostic_snapshots_payload()` for `/api/diagnostics/refresh`.
- Added `diagnostic_snapshot_payload()` for ordinary diagnostic sections.
- Added `usage_drain_snapshot_payload()` for usage-drain snapshots that need pricing, allowance, and rate-card paths.
- Replaced inline diagnostic snapshot payload construction in `server.py` with helper calls while keeping endpoint auth and status handling unchanged.
- Added focused tests for lock use, refresh/read behavior, usage-drain pricing path forwarding, and payload return semantics.
- Declared `server_diagnostic_snapshots` in the dashboard/server `tach` module boundary.
- Ratcheted max file-line baseline from 2479 to 2466 after reducing `server.py` from 1314 to 1301 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_diagnostic_snapshots.py tests/test_dashboard_server.py tests/test_dashboard_diagnostics_snapshots.py -q`: 24 passed.
- `radon cc src/codex_usage_tracker/server_diagnostic_snapshots.py -a -s`: average A (1.5).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 339 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-diagnostic-snapshot-payloads-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch is uncommitted.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 2479 -> 2466.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `radon cc src -a -s`: ran and reported current complexity inventory.
- `radon mi src -s`: ran and reported current maintainability inventory.
- `xenon --max-absolute B --max-modules A --max-average A src`: failed on existing C/D/F complexity hotspots outside this diagnostic-snapshot slice.

Remaining risks:

- `server.py` remains oversized at 1301 lines; large remaining methods include context, call/thread handlers, diagnostics fact handlers, and usage payload generation.
- Broad `xenon` remains red on existing parser/dashboard/usage-drain/report complexity blocks.
- `context.py`, `cli.py`, and several diagnostics modules remain above the target file-size budget.

Next handoff:

- Continue `refactor/server-routing-and-handlers` with dashboard shell/context handler extraction or diagnostics fact handler payload extraction.

### refactor/server-dashboard-shell-payload

Objective:

- Extract dashboard shell payload construction from `_UsageDashboardHandler`.
- Preserve shell route behavior, history/include-archived query handling, language normalization, and existing HTTP error messages.
- Keep HTML rendering and response writing in `server.py` for this branch.

Files touched:

- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_dashboard_shell.py`
- `tests/test_server_dashboard_shell.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`

Completed edits:

- Added `dashboard_shell_payload()` for the lightweight shell payload used before live hydration.
- Added `_shell_include_archived()` for `history=all|active` and explicit `include_archived` precedence.
- Replaced inline shell payload construction in `server.py` with the helper while keeping exception handling local to the handler.
- Added focused tests for lightweight payload settings, history-scope behavior, explicit include-archived override, and language forwarding.
- Declared `server_dashboard_shell` in the dashboard/server `tach` module boundary.
- Ratcheted max file-line baseline from 2466 to 2453 after reducing `server.py` from 1301 to 1288 lines.

Checks:

- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_dashboard_shell.py tests/test_server_dashboard_shell.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_dashboard_shell.py tests/test_server_dashboard_shell.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_dashboard_shell.py tests/test_dashboard_server.py -q`: 13 passed.
- `radon cc src/codex_usage_tracker/server_dashboard_shell.py -a -s`: average A (2.5).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_dashboard_shell.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 341 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-dashboard-shell-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch is uncommitted.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline 2466 -> 2453.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `radon cc src -a -s`: ran and reported current complexity inventory.
- `radon mi src -s`: ran and reported current maintainability inventory.
- `xenon --max-absolute B --max-modules A --max-average A src`: failed on existing C/D/F complexity hotspots outside this dashboard-shell slice.

Remaining risks:

- `server.py` remains oversized at 1288 lines; large remaining methods include context, call/thread handlers, diagnostics fact handlers, and usage payload generation.
- Broad `xenon` remains red on existing parser/dashboard/usage-drain/report complexity blocks.
- `context.py`, `cli.py`, and several diagnostics modules remain above the target file-size budget.

Next handoff:

- Continue `refactor/server-routing-and-handlers` with context handler extraction or diagnostics fact handler payload extraction.
