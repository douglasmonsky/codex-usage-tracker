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

### refactor/server-diagnostic-fact-payloads

Objective:
- Extract diagnostics summary, facts, and fact-call payload construction from `_UsageDashboardHandler`.
- Preserve query parsing, default sort/limit behavior, route fact filters, privacy mode forwarding, and existing HTTP error mapping.
- Keep HTTP response writing in `server.py` while moving report-builder argument assembly into a focused helper module.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_diagnostic_facts.py`
- `tests/test_server_diagnostic_facts.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `diagnostics_summary_payload()`, `diagnostics_facts_payload()`, and `diagnostic_fact_calls_payload()`.
- Replaced inline diagnostics fact report construction in `server.py` with helper calls and preserved `ValueError`/`sqlite3.Error` status mapping.
- Added focused tests for summary filter normalization, route-level fact filters, required fact identity validation, paging, and privacy forwarding.
- Declared `server_diagnostic_facts` in the dashboard/server `tach` boundary.
- Avoided adding duplicate private-helper debt by giving the local integer parser a diagnostics-specific helper name.
- Ratcheted max file-line baseline `2453 -> 2401`, reducing `server.py` from `1288` to `1236` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_facts.py tests/test_server_diagnostic_facts.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_facts.py tests/test_server_diagnostic_facts.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_diagnostic_facts.py tests/test_dashboard_server.py -q`: 15 passed.
- `radon cc src/codex_usage_tracker/server_diagnostic_facts.py -a -s`: average A (3.0).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_diagnostic_facts.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 345 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-diagnostic-fact-payloads-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2453 -> 2401`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1236` lines; context, call/thread, recommendations, and some route handlers still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, and usage-drain modules remain above the eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with another small payload/handler extraction, likely context or recommendations handling, then commit only after the same local gate pattern.

### refactor/server-recommendations-payload

Objective:
- Extract recommendations API payload construction from `_UsageDashboardHandler`.
- Preserve query filters, min-score validation, default limit, privacy mode forwarding, raw-context suppression, and existing HTTP error mapping.
- Keep HTTP response writing in `server.py` while moving report-builder argument assembly into a focused helper module.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_recommendations.py`
- `tests/test_server_recommendations.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `recommendations_payload()` as a small payload facade around `build_recommendations_report()`.
- Replaced inline recommendations report construction in `server.py` with a helper call and preserved `ValueError`/`sqlite3.Error` status mapping.
- Added focused tests for query filter normalization, defaults, raw context exclusion, and invalid `min_score` validation.
- Declared `server_recommendations` in the dashboard/server `tach` boundary.
- Ratcheted max file-line baseline `2401 -> 2391`, reducing `server.py` from `1236` to `1226` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_recommendations.py tests/test_server_recommendations.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_recommendations.py tests/test_server_recommendations.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_recommendations.py tests/test_dashboard_server.py -q`: 14 passed.
- `radon cc src/codex_usage_tracker/server_recommendations.py -a -s`: average A (1.0).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_recommendations.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 348 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-recommendations-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2401 -> 2391`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1226` lines; context, call/thread, summary, and remaining route handlers still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, and usage-drain modules remain above the eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with another small payload/handler extraction, likely summary payload or context handler extraction.

### refactor/server-summary-payload

Objective:
- Extract summary API payload construction from `_UsageDashboardHandler`.
- Preserve group-by/default limit/preset/since query behavior, privacy mode forwarding, raw-context suppression, and existing HTTP error mapping.
- Keep HTTP response writing in `server.py` while moving report-builder argument assembly into a focused helper module.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_summary.py`
- `tests/test_server_summary.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `summary_payload()` as a small payload facade around `build_summary_report()`.
- Replaced inline summary report construction in `server.py` with a helper call and preserved `ValueError`/`sqlite3.Error` status mapping.
- Added focused tests for query filter normalization, default behavior, and raw context exclusion.
- Declared `server_summary` in the dashboard/server `tach` boundary.
- Ratcheted max file-line baseline `2391 -> 2385`, reducing `server.py` from `1226` to `1220` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_summary.py tests/test_server_summary.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_summary.py tests/test_server_summary.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_summary.py tests/test_dashboard_server.py -q`: 13 passed.
- `radon cc src/codex_usage_tracker/server_summary.py -a -s`: average A (2.0).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_summary.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 350 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-summary-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2391 -> 2385`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1220` lines; context, call/thread, and remaining route handlers still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, and usage-drain modules remain above the eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with context handler extraction or call/thread response helpers.

### refactor/server-status-payload

Objective:
- Extract live status API payload construction from `_UsageDashboardHandler`.
- Preserve include-archived parsing, status/observed usage store queries, refresh metadata fields, parser diagnostics filtering, and existing HTTP error mapping.
- Keep HTTP response writing in `server.py` while moving status payload assembly into a focused helper module.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_status.py`
- `tests/test_server_status.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `status_payload()` around status row-count, observed usage, and refresh metadata queries.
- Replaced inline status payload construction in `server.py` with a helper call and preserved `sqlite3.Error` status mapping.
- Added focused tests for include-archived query parsing, metadata parser diagnostic filtering, and default include-archived behavior.
- Declared `server_status` in the dashboard/server `tach` boundary.
- Ratcheted max file-line baseline `2385 -> 2359`, reducing `server.py` from `1220` to `1194` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_status.py tests/test_server_status.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_status.py tests/test_server_status.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_status.py tests/test_dashboard_server.py -q`: 13 passed.
- `radon cc src/codex_usage_tracker/server_status.py -a -s`: average A (4.0).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_status.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 352 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-status-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2385 -> 2359`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1194` lines; context, call/thread, and remaining route handlers still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, and usage-drain modules remain above the eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with call/thread response helper extraction or raw context handler extraction after adding stronger characterization coverage.

### refactor/server-threads-payload

Objective:
- Extract thread-list API payload construction from `_UsageDashboardHandler`.
- Preserve limit/offset/search/include-archived/sort query behavior, raw-context suppression, and existing HTTP error mapping.
- Keep HTTP response writing in `server.py` while moving thread-list payload assembly into a focused helper module.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_threads.py`
- `tests/test_server_threads.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `threads_payload()` around `query_thread_summaries()`.
- Replaced inline thread-list payload construction in `server.py` with a helper call and preserved `ValueError`/`sqlite3.Error` status mapping.
- Added focused tests for query filter normalization, `q` precedence over `search`, `limit=all`, defaults, and invalid limit validation.
- Declared `server_threads` in the dashboard/server `tach` boundary.
- Ratcheted max file-line baseline `2359 -> 2336`, reducing `server.py` from `1194` to `1171` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_threads.py tests/test_server_threads.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_threads.py tests/test_server_threads.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_threads.py tests/test_dashboard_server.py -q`: 14 passed.
- `radon cc src/codex_usage_tracker/server_threads.py -a -s`: average A (4.0).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_threads.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 355 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-threads-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2359 -> 2336`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1171` lines; context, call detail, call-list, thread-call, and usage handlers still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, and usage-drain modules remain above the eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with call-list/thread-call response helper extraction or raw context handler extraction after characterization tests.

### refactor/server-call-detail-payload

Objective:
- Extract call-detail API payload construction from `_UsageDashboardHandler`.
- Preserve `record_id`/`record` alias behavior, missing-id 400, not-found 404, adjacent-record lookup, annotation, raw-context suppression, and existing database error mapping.
- Keep HTTP response writing in `server.py` while moving call-detail payload assembly into a focused helper module.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_call_detail.py`
- `tests/test_server_call_detail.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `call_detail_payload()` with explicit `MissingRecordIdError` and `UsageRecordNotFoundError` exception types for handler status mapping.
- Replaced inline call-detail payload construction in `server.py` with helper call and preserved 400/404/500 mappings.
- Added focused tests for record alias handling, adjacent-record annotation/order, missing record id, and not-found behavior.
- Split helper internals until the new module passed direct `xenon` B/A/A.
- Declared `server_call_detail` in the dashboard/server `tach` boundary.
- Ratcheted max file-line baseline `2336 -> 2311`, reducing `server.py` from `1171` to `1146` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_call_detail.py tests/test_server_call_detail.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_call_detail.py tests/test_server_call_detail.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_call_detail.py tests/test_dashboard_server.py -q`: 14 passed.
- `radon cc src/codex_usage_tracker/server_call_detail.py -a -s`: average A (2.56).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_call_detail.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 358 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-call-detail-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2336 -> 2311`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1146` lines; context, call-list, thread-call, and usage handlers still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, and usage-drain modules remain above the eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with call-list/thread-call response helpers or raw context handler extraction after characterization tests.

### refactor/server-call-list-payloads

Objective:
- Extract call-list and thread-call list API payload construction from `_UsageDashboardHandler`.
- Preserve derived filter validation, pagination metadata, thread-key alias behavior, missing-thread-key 400 message, and existing database error mappings.
- Keep HTTP response writing in `server.py` while moving list envelope construction into a focused helper module.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_call_lists.py`
- `tests/test_server_call_lists.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `calls_payload()` and `thread_calls_payload()` around existing live query/live row callbacks.
- Replaced inline call-list and thread-call payload construction in `server.py` with helper calls and preserved 400/500 mappings.
- Moved pricing-status and credit-confidence filter validation out of `server.py` into the helper.
- Added focused tests for derived filters, pagination metadata, `limit=None`, missing thread key, and invalid pricing status.
- Preserved the existing missing-thread-key message `thread_key required`.
- Declared `server_call_lists` in the dashboard/server `tach` boundary.
- Ratcheted max file-line baseline `2311 -> 2262`, reducing `server.py` from `1146` to `1097` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_call_lists.py tests/test_server_call_lists.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_call_lists.py tests/test_server_call_lists.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_call_lists.py tests/test_dashboard_server.py -q`: 15 passed.
- `radon cc src/codex_usage_tracker/server_call_lists.py -a -s`: average A (1.75).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_call_lists.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m pytest -q`: 362 passed.
- `.venv/bin/python -m compileall src`: passed before final message-string correction; focused `py_compile` passed afterward.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed, all modules validated.
- `.venv/bin/tach map -o /tmp/server-call-list-payloads-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2311 -> 2262`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1097` lines; context, usage refresh route, and diagnostic snapshot handler plumbing still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, and usage-drain modules remain above the eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with raw context handler extraction or another route plumbing split.

### `refactor/server-context-payload`

Goal:
- Extract raw-context request validation and payload construction from `_UsageDashboardHandler`.
- Keep dashboard-server enablement and API-token enforcement in the HTTP handler.
- Preserve existing error mappings and privacy behavior; this helper loads context on demand and does not persist raw prompts, tool outputs, command text, or patch text.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_context.py`
- `tests/test_server_context.py`
- `tests/test_dashboard_server.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `context_payload()` and `ContextRequestError` for context API query parsing and `load_call_context()` dispatch.
- Replaced inline context parameter parsing in `_handle_context` with the helper while keeping disabled-context and token checks in `server.py`.
- Added tests for full parameter normalization, defaults, missing `record_id`, and invalid context mode.
- Updated the SQLite-error dashboard server test to patch the new helper boundary instead of the old direct `load_call_context` import.
- Declared `server_context` in the dashboard/server `tach` boundary.
- Ratcheted file-line baseline `2262 -> 2231`, reducing `server.py` from `1097` to `1066` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_context.py tests/test_server_context.py`: passed.
- `.venv/bin/python -m ruff check tests/test_dashboard_server.py src/codex_usage_tracker/server.py src/codex_usage_tracker/server_context.py tests/test_server_context.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_context.py tests/test_dashboard_server.py -q`: 15 passed.
- `radon cc src/codex_usage_tracker/server_context.py -a -s`: average A (2.5).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_context.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 366 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/server-context-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2262 -> 2231`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1066` lines; usage handler, context settings, open-investigator, diagnostic snapshot plumbing, and dashboard-server factory code still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, usage-drain modules, and persistence modules remain above eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with a small context-settings, open-investigator, or usage-handler extraction.

### `refactor/server-context-settings-payload`

Goal:
- Extract context API mutable state and settings payload construction from `_UsageDashboardHandler`.
- Keep API-token enforcement in the HTTP handler.
- Avoid creating a cross-module private import while preserving route behavior.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_context_settings.py`
- `tests/test_server_context_settings.py`
- `tests/test_dashboard_server.py`
- `tests/test_privacy.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added public `ContextApiState` and `context_settings_payload()` in `server_context_settings.py`.
- Replaced inline `/api/context-settings` state mutation and response construction with the helper.
- Updated dashboard server and privacy tests to use the public state class through the server/module boundary.
- Added focused tests for default enablement, explicit disablement, truthy enablement, response schema, and non-persistence marker.
- Declared `server_context_settings` in the dashboard/server `tach` boundary.
- Fixed a ratchet regression by avoiding cross-module private import of `_ContextApiState`.
- Ratcheted file-line baseline `2231 -> 2211`, reducing `server.py` from `1066` to `1046` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_context_settings.py tests/test_server_context_settings.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_context_settings.py tests/test_server_context_settings.py tests/test_privacy.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_context_settings.py tests/test_privacy.py::test_context_server_requires_loopback_origin_token_and_enablement tests/test_dashboard_server.py -q`: 15 passed.
- `radon cc src/codex_usage_tracker/server_context_settings.py -a -s`: average A (1.2).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_context_settings.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 369 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/server-context-settings-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2231 -> 2211`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1046` lines; usage handler, open-investigator, diagnostic snapshot plumbing, and dashboard-server factory code still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, usage-drain modules, and persistence modules remain above eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with open-investigator URL validation/payload extraction or another route plumbing split.

### `refactor/server-open-investigator-payload`

Goal:
- Extract open-investigator URL validation, safe URL reconstruction, browser opening, and response payload construction from `_UsageDashboardHandler`.
- Keep API-token enforcement in the HTTP handler.
- Preserve loopback-only, same-port, dashboard-path, and `view=call&record=...` safety checks.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_open_investigator.py`
- `tests/test_server_open_investigator.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `open_investigator_payload()` and `OpenInvestigatorRequestError`.
- Replaced inline `/api/open-investigator` validation and payload construction with the helper, preserving 403 token handling in `server.py` and mapping request errors to HTTP 400.
- Added focused tests for safe relative URLs, encoded absolute URLs with fragments, missing URL, non-dashboard schemes, non-loopback hosts, wrong ports, wrong dashboard paths, and missing call-record query shape.
- Kept the existing live dashboard server open-investigator test passing.
- Declared `server_open_investigator` in the dashboard/server `tach` boundary.
- Ratcheted file-line baseline `2211 -> 2189`, reducing `server.py` from `1046` to `1024` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_open_investigator.py tests/test_server_open_investigator.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_open_investigator.py tests/test_server_open_investigator.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_open_investigator.py tests/test_dashboard_server.py::test_dashboard_server_opens_only_token_protected_investigator_urls -q`: 9 passed.
- `radon cc src/codex_usage_tracker/server_open_investigator.py -a -s`: average A (4.67); `open_investigator_payload` is B (9), accepted for this slice.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_open_investigator.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 377 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/server-open-investigator-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2211 -> 2189`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1024` lines; usage handler, diagnostic snapshot plumbing, and dashboard-server factory code still need extraction.
- `open_investigator_payload()` is B complexity; acceptable now, but it can be split further if strict wemake/radon scope later requires it.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, usage-drain modules, and persistence modules remain above eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers`; likely extract diagnostic snapshot/refresh route plumbing or usage refresh handler next.

### `refactor/server-diagnostics-refresh-payload`

Goal:
- Move `/api/diagnostics/refresh` query parsing into the existing diagnostic snapshot payload module.
- Keep API-token enforcement and HTTP error mapping in `_UsageDashboardHandler`.
- Preserve explicit diagnostic refresh behavior and include-archived defaults.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_diagnostic_snapshots.py`
- `tests/test_server_diagnostic_snapshots.py`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `diagnostic_refresh_payload()` to parse `include_archived` from the query and delegate to `refresh_all_diagnostic_snapshots_payload()`.
- Replaced inline include-archived parsing in `_handle_diagnostics_refresh` with the helper.
- Added tests for default include-archived behavior and explicit query override.
- Ratcheted file-line baseline `2189 -> 2185`, reducing `server.py` from `1024` to `1020` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_diagnostic_snapshots.py tests/test_dashboard_server.py -q`: 17 passed.
- `radon cc src/codex_usage_tracker/server_diagnostic_snapshots.py -a -s`: average A (1.43).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 379 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/server-diagnostics-refresh-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2189 -> 2185`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` remains oversized at `1020` lines; single-section diagnostic snapshot wrappers, usage handler, and dashboard-server factory code still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, usage-drain modules, and persistence modules remain above eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers`; likely extract repeated diagnostic section wrapper methods or the `/api/usage` handler.

### `refactor/server-usage-payload`

Goal:
- Extract `/api/usage` query parsing, optional refresh execution, dashboard payload timing, and diagnostics metadata from `_UsageDashboardHandler`.
- Keep HTTP token/status mapping in the server handler.
- Preserve the existing live dashboard JSON shape, refresh token behavior, shell-only row omission, and diagnostics payload.

Files touched:
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_usage_refresh.py`
- `tests/test_server_usage_refresh.py`
- `tests/test_dashboard_server.py`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `usage_payload()` and `UsageRefreshAuthError` to `server_usage_refresh.py`.
- Replaced inline `/api/usage` payload construction in `server.py` with the helper while preserving 403, SQLite, and `OSError` mappings.
- Added tests for query option forwarding, refresh-token rejection, refresh diagnostics metadata, `refreshed_at`, `refresh_result`, shell-only behavior, and include-archived parsing.
- Updated the dashboard server SQLite-error test to patch the new `usage_payload` boundary without growing the oversized test file.
- Ratcheted file-line baseline `2185 -> 2149`, reducing `server.py` from `1020` to `984` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_usage_refresh.py tests/test_server_usage_refresh.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_usage_refresh.py tests/test_server_usage_refresh.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_usage_refresh.py tests/test_dashboard_server.py -q`: 15 passed.
- `radon cc src/codex_usage_tracker/server_usage_refresh.py -a -s`: average A (3.0); `usage_payload` is B (7), accepted for this slice.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_usage_refresh.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 382 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/server-usage-payload-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2185 -> 2149`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `server.py` is now below 1000 lines, but still above the eventual 600-line target at `984` lines.
- `usage_payload()` is B complexity and can be split later if strict style gates require it.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `context.py`, `cli.py`, diagnostics/report modules, usage-drain modules, and persistence modules remain above eventual file-size/style targets.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with diagnostic section wrapper consolidation or dashboard-server factory extraction, then proceed toward store/context/parser splits.

### `refactor/context-token-estimates`

Goal:
- Start `context.py` decomposition with a pure token-estimation helper split.
- Preserve visible token estimates, serialized-evidence token estimates, and tiktoken fallback labels.
- Keep raw context loading behavior unchanged and privacy invariants intact.

Files touched:
- `src/codex_usage_tracker/context.py`
- `src/codex_usage_tracker/context_token_estimates.py`
- `tests/test_context_token_estimates.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added public `estimate_visible_tokens()`, `token_estimate()`, and `context_encoding()` helpers.
- Moved tiktoken lookup/cache and visible-token text joining out of `context.py`.
- Restored string-key compatibility for `visible_token_estimate` and `raw_json_token_estimate` after the mechanical rename check caught the risk.
- Added direct tests for encoded token counting, fallback char/4 counting, empty text, and joined visible entry text.
- Kept existing context evidence and privacy tests passing.
- Declared `context_token_estimates` in the context/parser `tach` boundary.
- Ratcheted file-line baseline `2149 -> 2112`, reducing `context.py` from `1082` to `1045` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/context.py src/codex_usage_tracker/context_token_estimates.py tests/test_context_token_estimates.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/context.py src/codex_usage_tracker/context_token_estimates.py tests/test_context_token_estimates.py tests/test_context_evidence.py tests/test_privacy.py`: passed.
- `.venv/bin/python -m pytest tests/test_context_token_estimates.py tests/test_context_evidence.py tests/test_privacy.py -q`: 13 passed.
- `radon cc src/codex_usage_tracker/context_token_estimates.py -a -s`: average A (3.13).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/context_token_estimates.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 385 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/context-token-estimates-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2149 -> 2112`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `context.py` remains oversized at `1045` lines; serialized evidence bucketing, event summarization, action timing, and JSON value handling still need extraction.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `cli.py`, diagnostics/report modules, usage-drain modules, and persistence modules remain above eventual file-size/style targets.

Next handoff:
- Continue `refactor/context-and-parser-boundaries` with serialized evidence bucketing or event summarization extraction.

### `refactor/context-value-helpers`

Goal:
- Continue `context.py` decomposition by moving generic value conversion, JSON rendering, numeric parsing, and redaction helpers into a dedicated module.
- Preserve raw-context evidence summaries, redaction behavior, and serialized-evidence formatting.

Files touched:
- `src/codex_usage_tracker/context.py`
- `src/codex_usage_tracker/context_values.py`
- `tests/test_context_values.py`
- `tach.toml`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `.agent-maintainer/git-agent-ratchet-duplicate-helpers.json`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added public `context_values` helpers for redacted text/JSON, compact JSON, content text extraction, optional strings, and numeric parsing.
- Replaced private helper calls in `context.py` with public helper imports.
- Fixed the local `content_text` shadowing regression caught by focused context tests.
- Added direct tests for recursive redaction, nested content extraction, numeric parsing, optional strings, compact JSON, and JSON-ish rendering.
- Kept existing context evidence and privacy tests passing.
- Declared `context_values` in the context/parser `tach` boundary.
- Ratcheted file-line baseline `2112 -> 2044`, reducing `context.py` from `1045` to `977` lines.
- Ratcheted duplicate-helper baseline `60 -> 57` by removing context-local `_optional_str` and `_positive_int` duplicates.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/context.py src/codex_usage_tracker/context_values.py tests/test_context_values.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/context.py src/codex_usage_tracker/context_values.py tests/test_context_values.py tests/test_context_evidence.py tests/test_privacy.py`: passed.
- `.venv/bin/python -m pytest tests/test_context_values.py tests/test_context_token_estimates.py tests/test_context_evidence.py tests/test_privacy.py -q`: 17 passed.
- `radon cc src/codex_usage_tracker/context_values.py -a -s`: average A (3.6); two helpers are B and accepted within current xenon limit.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/context_values.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 389 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed after trimming EOF whitespace.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/context-value-helpers-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2112 -> 2044`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed, ratcheted baseline `60 -> 57`.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected beta false-positive `repo-root` failure remains; also reports changed paths while branch uncommitted.

Remaining risks:
- `context.py` remains oversized at `977` lines; event summarization, serialized evidence bucketing, and action timing are next likely split points.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing complexity hotspots outside this slice.
- `server.py`, `cli.py`, diagnostics/report modules, usage-drain modules, and persistence modules remain above eventual file-size/style targets.

Next handoff:
- Continue `refactor/context-and-parser-boundaries` with event summarization or serialized evidence bucketing extraction.
### `refactor/context-summaries`
Goal:
- Move context evidence summarization, safe structured event filtering, compaction summarization, and adjacent chat-message echo dedupe out of `context.py`.
- Keep raw log scanning, selected-turn collection, serialized evidence estimation, and action timing assembly in `context.py`.
- Preserve context/privacy behavior and avoid introducing raw tool-output persistence.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `src/codex_usage_tracker/context.py`
- `src/codex_usage_tracker/context_summaries.py`
- `tach.toml`
- `tests/test_context_summaries.py`
- `tests/test_context_values.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `context_summaries.py` with public helpers `dedupe_chat_message_echoes`, `summarize_payload`, and `summarize_turn_context`.
- Split response item, event message, compaction, token-count, and safe structured event summarization into smaller private helpers.
- Added direct characterization tests for turn-context text, default tool-output omission, token count summaries, safe structured event duration carry, optional compaction history, and chat echo dedupe.
- Changed the redaction fixture in `tests/test_context_values.py` to build the fake OpenAI key at runtime so `scripts/check_release.py` does not flag a literal key-shaped string.
- Added `context_summaries` to `tach.toml` context/parser boundary.
- Ratcheted max-file baseline `2044 -> 1742`; `context.py` reduced from `977` to `675` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/context.py src/codex_usage_tracker/context_summaries.py tests/test_context_summaries.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/context.py src/codex_usage_tracker/context_summaries.py tests/test_context_summaries.py tests/test_context_evidence.py tests/test_privacy.py`: passed.
- `.venv/bin/python -m pytest tests/test_context_summaries.py tests/test_context_evidence.py tests/test_privacy.py -q`: 16 passed.
- `radon cc src/codex_usage_tracker/context_summaries.py -a -s`: worst block B (7), average A under xenon gate.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/context_summaries.py`: passed.
- `.venv/bin/python -m pytest tests/test_cli_release.py::test_release_check_script_passes tests/test_context_values.py -q`: 5 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/context-summaries-tach-map.json`: passed.
- `.venv/bin/python -m pytest -q`: 395 passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and large-diff warnings.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `2044 -> 1742`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `context.py` remains above the eventual 600-line target at 675 lines.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing non-context hotspots outside this slice.
- `context.py` still owns raw scan orchestration, serialized evidence bucketing, and action timing assembly; these are the next obvious context split candidates.

Next handoff:
- Continue `refactor/context-and-parser-boundaries` with a small extraction of serialized evidence bucketing or action timing from `context.py`, then reassess whether `context.py` can drop below 600 without making the orchestration harder to read.
### `refactor/context-action-timing`
Goal:
- Move selected-turn action timing annotation out of `context.py`.
- Keep action timing payload shape unchanged.
- Add direct tests for elapsed time, previous-entry gaps, invalid timestamps, and millisecond normalization.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/context.py`
- `src/codex_usage_tracker/context_action_timing.py`
- `tach.toml`
- `tests/test_context_action_timing.py`

Completed edits:
- Added `context_action_timing.py` with public helpers `annotate_action_timing` and `normalize_millisecond_value`.
- Removed timestamp parsing, gap calculation, and duration normalization helpers from `context.py`.
- Preserved the action timing summary keys and per-entry `action_timing` metadata.
- Added `context_action_timing` to the context/parser `tach` boundary.
- Ratcheted max-file baseline `1742 -> 1680`; `context.py` reduced from `675` to `613` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/context.py src/codex_usage_tracker/context_action_timing.py tests/test_context_action_timing.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/context.py src/codex_usage_tracker/context_action_timing.py tests/test_context_action_timing.py tests/test_context_evidence.py tests/test_privacy.py`: passed.
- `.venv/bin/python -m pytest tests/test_context_action_timing.py tests/test_context_summaries.py tests/test_context_evidence.py tests/test_privacy.py -q`: 19 passed.
- `radon cc src/codex_usage_tracker/context_action_timing.py src/codex_usage_tracker/context.py -a -s`: `context_action_timing.py` worst block B (6); `context.py` still has existing `_read_context_entries` E and `_serialized_bucket_label` C.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/context_action_timing.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 398 passed.
- `.venv/bin/tach map -o /tmp/context-action-timing-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning; warning about changed Python source before staging expected.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1742 -> 1680`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `context.py` remains above the eventual 600-line target at `613` lines.
- `_read_context_entries` remains high complexity and still owns scan orchestration plus serialized evidence accumulation.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing non-context hotspots outside this slice.

Next handoff:
- Continue with serialized evidence helper extraction from `context.py`; this should likely bring `context.py` below 600 and reduce the context module average, while leaving the selected-turn scan loop as the facade.
### `refactor/context-serialized-evidence`
Goal:
- Move serialized raw JSONL evidence estimates and field-bucket accounting out of `context.py`.
- Keep quick vs full serialized analysis behavior unchanged.
- Keep selected-turn scan orchestration in `context.py`.

Files touched:
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/context.py`
- `src/codex_usage_tracker/context_serialized.py`
- `tach.toml`
- `tests/test_context_serialized.py`

Completed edits:
- Added `context_serialized.py` with public helpers `collect_serialized_envelope`, `serialized_context_estimate`, and `quick_serialized_context_estimate`.
- Moved raw envelope accumulation, redacted raw JSON upper-bound estimates, quick char/4 fallback estimates, top-bucket sorting, and serialized field bucket labeling out of `context.py`.
- Reworked bucket labeling into smaller table-driven helpers while preserving the existing bucket keys, labels, and notes.
- Added direct characterization tests for bucket grouping, full serialized estimates, top-bucket ordering, and quick deferred estimates.
- Added `context_serialized` to the context/parser `tach` boundary.
- Reduced `context.py` from `613` to `447` lines; it is now below the 600-line local ratchet target.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/context.py src/codex_usage_tracker/context_serialized.py tests/test_context_serialized.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/context.py src/codex_usage_tracker/context_serialized.py tests/test_context_serialized.py tests/test_context_evidence.py tests/test_privacy.py`: passed after import formatting.
- `.venv/bin/python -m pytest tests/test_context_serialized.py tests/test_context_action_timing.py tests/test_context_summaries.py tests/test_context_evidence.py tests/test_privacy.py -q`: 22 passed.
- `radon cc src/codex_usage_tracker/context_serialized.py src/codex_usage_tracker/context.py -a -s`: `context_serialized.py` worst block B (9); `context.py` still has existing `_read_context_entries` E.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/context_serialized.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed after trimming EOF whitespace.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 401 passed.
- `.venv/bin/tach map -o /tmp/context-serialized-evidence-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning; warning about changed Python source before staging expected.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed; command reported current baseline still ratchets against remaining oversized non-context modules.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `_read_context_entries` is still high complexity and should be the next context target if we continue this area.
- `context_serialized.py` has a B-complexity special bucket helper accepted under current xenon settings.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing non-context hotspots outside this slice.

Next handoff:
- Decide whether to split `_read_context_entries` state handling next, or switch back to larger roadmap targets now that `context.py` is below the local file-length target.
### `refactor/server-request-guards`
Goal:
- Move local dashboard request-origin and API-token guard logic out of `_UsageDashboardHandler`.
- Preserve loopback Host/Origin enforcement and header/query-token behavior.
- Keep response handling and route dispatch unchanged.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_request_guards.py`
- `tach.toml`
- `tests/test_server_request_guards.py`

Completed edits:
- Added `server_request_guards.py` with `request_origin_allowed` and `has_valid_api_token`.
- Replaced handler-local guard implementations with thin delegates.
- Preserved other `server.py` uses of `_first` after an initial focused-test catch.
- Added direct tests for loopback host allowance, external host rejection, loopback origin same-port enforcement, external origin rejection, header token priority, and query token fallback.
- Added `server_request_guards` to the server `tach` boundary.
- Ratcheted max-file baseline `1667 -> 1657`; `server.py` reduced from `984` to `974` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_request_guards.py tests/test_server_request_guards.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_request_guards.py tests/test_server_request_guards.py tests/test_dashboard_server.py`: passed after restoring the still-needed `_first` alias.
- `.venv/bin/python -m pytest tests/test_server_request_guards.py tests/test_dashboard_server.py -q`: 16 passed.
- `radon cc src/codex_usage_tracker/server_request_guards.py src/codex_usage_tracker/server.py -a -s`: `server_request_guards.py` worst block B (6); server handler hotspots unchanged.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_request_guards.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/server-request-guards-tach-map.json`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m pytest -q`: 406 passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1667 -> 1657`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `server.py` remains oversized at `974` lines.
- `_UsageDashboardHandler._handle_context` and route dispatch still contain mixed HTTP/payload concerns.
- Broad `xenon --max-absolute B --max-modules A --max-average A src` remains red on existing non-server-request-guard hotspots.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with another low-risk server slice, likely moving repeated HTTP error mapping or diagnostic route wrapper methods.

### `refactor/server-error-responses`

Goal:
- Centralize local dashboard JSON error payload construction behind response helpers.
- Keep dashboard routes, status codes, and error message strings stable.
- Reduce `server.py` size under the local max-file-lines ratchet.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_responses.py`
- `tests/test_server_responses.py`

Completed edits:
- Added `send_error_response` and `send_exception_response` to `server_responses.py`.
- Replaced repeated inline `{"error": ...}` response payloads in `server.py`.
- Added handler-local `_send_error` and `_send_exception` delegates so call sites stay compact.
- Added direct tests for error payload extras, headers, content length, and exception formatting.
- Ratcheted max-file baseline `1657 -> 1620`; `server.py` reduced `974 -> 937` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_responses.py tests/test_server_responses.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_responses.py tests/test_server_responses.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_responses.py tests/test_dashboard_server.py -q`: 13 passed.
- `radon cc src/codex_usage_tracker/server_responses.py src/codex_usage_tracker/server.py -a -s`: `server_responses.py` all A; server hotspots unchanged with `_handle_context` B.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server_responses.py`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 408 passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/tach map -o /tmp/server-error-responses-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1657 -> 1620`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `server.py` remains oversized at `937` lines.
- `_UsageDashboardHandler._handle_context` is still the server complexity hotspot.
- `agent-maintainer verify --profile fast` still warns that the package folder is structurally large, which is the point of the ongoing branch series.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with another low-risk slice around context route handling or diagnostic route handler repetition.

### `refactor/server-diagnostic-refresh-auth`

Goal:
- Consolidate repeated diagnostic refresh token denial logic in the dashboard server.
- Preserve the same 403 JSON payload for refresh endpoints without adding lines to oversized legacy tests.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `tests/test_server_diagnostic_refresh_auth.py`

Completed edits:
- Added `_DIAGNOSTIC_REFRESH_AUTH_ERROR` and `_reject_missing_diagnostic_refresh_token`.
- Replaced three repeated diagnostics-refresh token checks with the shared helper.
- Added focused tests for missing-token rejection and valid header acceptance.
- Moved the new assertion out of the oversized `tests/test_dashboard_server.py` after `agent-maintainer verify --profile fast` caught the legacy file-length regression.
- Ratcheted max-file baseline `1620 -> 1618`; `server.py` reduced `937 -> 935` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py tests/test_dashboard_server.py tests/test_server_diagnostic_refresh_auth.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py tests/test_dashboard_server.py tests/test_server_diagnostic_refresh_auth.py`: passed.
- `.venv/bin/python -m pytest tests/test_dashboard_server.py tests/test_server_diagnostic_refresh_auth.py -q`: 13 passed.
- `radon cc src/codex_usage_tracker/server.py -a -s`: server hotspots unchanged; `_handle_context` remains B.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 410 passed.
- `.venv/bin/tach map -o /tmp/server-diagnostic-refresh-auth-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1620 -> 1618`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning after moving assertion to the focused test file.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `server.py` remains oversized at `935` lines.
- `_UsageDashboardHandler._handle_context` remains the server complexity hotspot.
- The diagnostic refresh helper is still handler-local; a later route/handler split should move this concern out with the broader routing boundary.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with another small server branch, preferably extracting context route handling or diagnostic snapshot dispatch into tested helpers.

### `refactor/server-context-request-handler`

Goal:
- Move context endpoint auth/error mapping out of `_UsageDashboardHandler`.
- Keep `/api/context` status codes, JSON payloads, and SQLite/OSError handling stable.
- Reduce `server.py` complexity and line count without worsening the oversized dashboard test file.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_context.py`
- `tests/test_dashboard_server.py`
- `tests/test_server_context.py`

Completed edits:
- Added `handle_context_request` in `server_context.py` with typed sender callbacks.
- Replaced `_UsageDashboardHandler._handle_context` body with a thin dispatcher.
- Added focused tests for disabled context API, missing token, and successful context payload forwarding.
- Updated existing dashboard SQLite-error test to patch `server_module.server_context.context_payload`.
- Ratcheted max-file baseline `1618 -> 1593`; `server.py` reduced `935 -> 910` lines.
- Removed `_handle_context` from the server Radon hotspot list; the extracted route helper is B-rated in the focused context module.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_context.py tests/test_server_context.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_context.py tests/test_server_context.py tests/test_dashboard_server.py`: passed after mechanical Ruff import fix.
- `.venv/bin/python -m pytest tests/test_server_context.py tests/test_dashboard_server.py -q`: 18 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_context.py -a -s`: server `_handle_context` removed from hotspot list; `handle_context_request` B.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_context.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 413 passed.
- `.venv/bin/tach map -o /tmp/server-context-request-handler-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1618 -> 1593`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `server.py` remains oversized at `910` lines.
- `handle_context_request` is still B complexity, though now isolated and directly tested.
- Broad package structure remains too flat for the eventual strict cohesion target.

Next handoff:
- Continue `refactor/server-routing-and-handlers` by extracting another route family, likely diagnostic snapshot dispatch, then revisit `server.py` once it is below the largest-file ratchet target.

### `refactor/server-diagnostic-snapshot-handler`

Goal:
- Move diagnostic snapshot route wrapper logic out of `_UsageDashboardHandler`.
- Preserve persisted diagnostics snapshot payload behavior, refresh auth behavior, and SQLite error mapping.
- Continue reducing `server.py` while keeping new modules and tests below file-length budgets.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_diagnostic_snapshots.py`
- `tests/test_server_diagnostic_snapshots.py`

Completed edits:
- Added `handle_diagnostic_snapshot_request` and `handle_usage_drain_snapshot_request`.
- Replaced `_handle_diagnostic_snapshot` and `_handle_diagnostic_usage_drain_snapshot` bodies with thin delegates.
- Added focused tests for refresh auth rejection, regular snapshot payload forwarding, and usage-drain SQLite error mapping.
- Ratcheted max-file baseline `1593 -> 1578`; `server.py` reduced `910 -> 895` lines.
- Kept `server_diagnostic_snapshots.py` at `208` lines and `tests/test_server_diagnostic_snapshots.py` at `313` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_diagnostic_snapshots.py tests/test_dashboard_server.py -q`: 20 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py -a -s`: extracted snapshot handlers A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 416 passed.
- `.venv/bin/tach map -o /tmp/server-diagnostic-snapshot-handler-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1593 -> 1578`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `server.py` remains oversized at `895` lines.
- Diagnostic refresh-all endpoint remains in `server.py`; a later branch can extract the all-snapshot refresh route wrapper.
- Broad package structure remains too flat for strict cohesion.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with the remaining refresh-all diagnostic wrapper or move to another server route family if a cleaner boundary is available.

### `refactor/server-diagnostic-refresh-handler`

Goal:
- Move the all-diagnostics refresh route wrapper out of `_UsageDashboardHandler`.
- Preserve refresh auth short-circuiting, refresh payload construction, and SQLite error mapping.
- Continue shrinking `server.py` without creating oversized helper/test modules.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_diagnostic_snapshots.py`
- `tests/test_server_diagnostic_snapshots.py`

Completed edits:
- Added `handle_diagnostic_refresh_request` in `server_diagnostic_snapshots.py`.
- Replaced `_handle_diagnostics_refresh` body with a thin delegate.
- Added focused tests for missing-token short-circuit and successful refresh payload sending.
- Ratcheted max-file baseline `1578 -> 1573`; `server.py` reduced `895 -> 890` lines.
- Kept `server_diagnostic_snapshots.py` at `241` lines and `tests/test_server_diagnostic_snapshots.py` at `372` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_diagnostic_snapshots.py tests/test_dashboard_server.py -q`: 22 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py -a -s`: diagnostic refresh helper A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_snapshots.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 418 passed.
- `.venv/bin/tach map -o /tmp/server-diagnostic-refresh-handler-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1578 -> 1573`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `server.py` remains oversized at `890` lines.
- Diagnostic fact routes and list/detail route wrappers are still server-owned.
- Broad package structure remains too flat for strict cohesion.

Next handoff:
- Continue `refactor/server-routing-and-handlers` with diagnostic fact route wrappers or stop server slicing and switch to the next roadmap module if server risk starts increasing.

### `refactor/server-diagnostic-fact-handlers`

Goal:
- Move diagnostic summary, fact-list, and fact-call route wrappers out of `_UsageDashboardHandler`.
- Preserve bad-request and SQLite error response behavior.
- Continue reducing `server.py` while keeping helper/test modules below file-length budgets.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_diagnostic_facts.py`
- `tests/test_server_diagnostic_facts.py`

Completed edits:
- Added `handle_diagnostics_summary_request`, `handle_diagnostics_facts_request`, and `handle_diagnostics_fact_calls_request`.
- Replaced three `_UsageDashboardHandler` diagnostic fact wrappers with delegates.
- Added focused tests for successful summary response, bad-request mapping, and diagnostic-call SQLite error mapping.
- Ratcheted max-file baseline `1573 -> 1558`; `server.py` reduced `890 -> 875` lines.
- Kept `server_diagnostic_facts.py` at `210` lines and `tests/test_server_diagnostic_facts.py` at `218` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_facts.py tests/test_server_diagnostic_facts.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_facts.py tests/test_server_diagnostic_facts.py tests/test_dashboard_server.py`: passed after mechanical Ruff import fix.
- `.venv/bin/python -m pytest tests/test_server_diagnostic_facts.py tests/test_dashboard_server.py -q`: 18 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_facts.py -a -s`: extracted fact handlers A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_facts.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 421 passed.
- `.venv/bin/tach map -o /tmp/server-diagnostic-fact-handlers-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1573 -> 1558`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `server.py` remains oversized at `875` lines.
- Usage/call/thread route wrappers remain server-owned.
- Broad package structure remains too flat for strict cohesion.

Next handoff:
- Continue server route wrapper extraction with call/thread/list/status routes, or switch to store/query boundaries if the next route family looks too coupled.

### `refactor/server-status-handler`

Goal:
- Move `/api/status` route wrapper out of `_UsageDashboardHandler`.
- Preserve status payload response and SQLite error behavior.
- Continue reducing `server.py` with a small low-risk branch.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_status.py`
- `tests/test_server_status.py`

Completed edits:
- Added `handle_status_request` in `server_status.py`.
- Replaced `_handle_status` body with a thin delegate.
- Added focused tests for successful status response and SQLite error mapping.
- Ratcheted max-file baseline `1558 -> 1555`; `server.py` reduced `875 -> 872` lines.
- Kept `server_status.py` at `83` lines and `tests/test_server_status.py` at `139` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_status.py tests/test_server_status.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_status.py tests/test_server_status.py tests/test_dashboard_server.py`: passed after mechanical Ruff import fix.
- `.venv/bin/python -m pytest tests/test_server_status.py tests/test_dashboard_server.py -q`: 15 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_status.py -a -s`: status handler A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_status.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 423 passed.
- `.venv/bin/tach map -o /tmp/server-status-handler-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1558 -> 1555`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; also warned verify-log metadata was stale/missing after the fast profile, but `verify --profile fast` itself passed.

Remaining risks:
- `server.py` remains oversized at `872` lines.
- Calls, threads, summary, recommendations, and usage route wrappers remain server-owned.
- Broad package structure remains too flat for strict cohesion.

Next handoff:
- Continue extracting call/thread route wrappers, or switch to store/query boundaries if server slicing becomes too granular.

### `refactor/server-call-handlers`

Goal:
- Move `/api/calls` and `/api/call` route wrappers out of `_UsageDashboardHandler`.
- Preserve bad-request, not-found, and SQLite error behavior.
- Continue reducing `server.py` while keeping helper/test modules below file-length budgets.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_call_detail.py`
- `src/codex_usage_tracker/server_call_lists.py`
- `tests/test_server_call_detail.py`
- `tests/test_server_call_lists.py`

Completed edits:
- Added `handle_calls_request` in `server_call_lists.py`.
- Added `handle_call_detail_request` in `server_call_detail.py`.
- Replaced `_handle_calls` and `_handle_call` bodies with delegates.
- Added focused tests for successful call-list/detail responses, missing-record mapping, and SQLite error mapping.
- Ratcheted max-file baseline `1555 -> 1540`; `server.py` reduced `872 -> 857` lines.
- Kept `server_call_lists.py` at `145` lines, `server_call_detail.py` at `137` lines, and related tests below `170` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_call_lists.py src/codex_usage_tracker/server_call_detail.py tests/test_server_call_lists.py tests/test_server_call_detail.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_call_lists.py src/codex_usage_tracker/server_call_detail.py tests/test_server_call_lists.py tests/test_server_call_detail.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_call_lists.py tests/test_server_call_detail.py tests/test_dashboard_server.py -q`: 23 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_call_lists.py src/codex_usage_tracker/server_call_detail.py -a -s`: new route handlers A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_call_lists.py src/codex_usage_tracker/server_call_detail.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 428 passed.
- `.venv/bin/tach map -o /tmp/server-call-handlers-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed, ratcheted baseline `1555 -> 1540`.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected `agent-maintainer 0.1.0b1` repo-root false positive remains; changed-path warning expected before commit.

Remaining risks:
- `server.py` remains oversized at `857` lines.
- Thread list/thread calls, summary, recommendations, and usage route wrappers remain server-owned.
- Broad package structure remains too flat for strict cohesion.

Next handoff:
- Continue with thread route wrappers or summary/recommendation wrappers as another small server branch.

### `refactor/server-thread-handlers`

Goal:
- Move `/api/threads` and `/api/thread-calls` route wrappers out of `_UsageDashboardHandler`.
- Preserve bad-request and SQLite error response behavior.
- Continue reducing `server.py` without changing route URLs or JSON payload schemas.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_call_lists.py`
- `src/codex_usage_tracker/server_threads.py`
- `tests/test_server_call_lists.py`
- `tests/test_server_threads.py`

Completed edits:
- Added `handle_threads_request` in `server_threads.py`.
- Added `handle_thread_calls_request` in `server_call_lists.py`.
- Replaced `_handle_threads` and `_handle_thread_calls` bodies with thin delegates.
- Added focused tests for successful thread-list/thread-call responses plus SQLite and missing-thread error mapping.
- Ratcheted max-file baseline `1540 -> 1526`; `server.py` reduced `857 -> 843` lines.
- Kept `server_threads.py` `80` lines, `server_call_lists.py` `170` lines, `tests/test_server_threads.py` `141` lines, and `tests/test_server_call_lists.py` `197` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_threads.py src/codex_usage_tracker/server_call_lists.py tests/test_server_threads.py tests/test_server_call_lists.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_threads.py src/codex_usage_tracker/server_call_lists.py tests/test_server_threads.py tests/test_server_call_lists.py tests/test_dashboard_server.py`: passed after mechanical import sort.
- `.venv/bin/python -m pytest tests/test_server_threads.py tests/test_server_call_lists.py tests/test_dashboard_server.py -q`: 24 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_threads.py src/codex_usage_tracker/server_call_lists.py -a -s`: new route handlers A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_threads.py src/codex_usage_tracker/server_call_lists.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 432 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach map -o /tmp/server-thread-handlers-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings.

Remaining risks:
- `server.py` remains oversized at `843` lines.
- Summary, recommendation, and usage route wrappers remain server-owned.
- Broad package structure remains too flat for strict cohesion.

Next handoff:
- Continue with summary/recommendation wrappers as the next small server branch, then isolate `_handle_usage` separately if still worth doing before switching roadmap modules.

### `refactor/server-summary-recommendation-handlers`

Goal:
- Move `/api/summary` and `/api/recommendations` route wrappers out of `_UsageDashboardHandler`.
- Preserve bad-request and SQLite error response behavior.
- Continue reducing `server.py` while keeping report payload schemas unchanged.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_recommendations.py`
- `src/codex_usage_tracker/server_summary.py`
- `tests/test_server_recommendations.py`
- `tests/test_server_summary.py`

Completed edits:
- Added `handle_summary_request` in `server_summary.py`.
- Added `handle_recommendations_request` in `server_recommendations.py`.
- Replaced `_handle_summary` and `_handle_recommendations` bodies with thin delegates.
- Added focused tests for successful summary/recommendation responses plus SQLite error mapping.
- Ratcheted max-file baseline `1526 -> 1516`; `server.py` reduced `843 -> 833` lines.
- Kept `server_summary.py` `70` lines, `server_recommendations.py` `82` lines, `tests/test_server_summary.py` `145` lines, and `tests/test_server_recommendations.py` `159` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_summary.py src/codex_usage_tracker/server_recommendations.py tests/test_server_summary.py tests/test_server_recommendations.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_summary.py src/codex_usage_tracker/server_recommendations.py tests/test_server_summary.py tests/test_server_recommendations.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_server_summary.py tests/test_server_recommendations.py tests/test_dashboard_server.py -q`: 20 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_summary.py src/codex_usage_tracker/server_recommendations.py -a -s`: new route handlers A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_summary.py src/codex_usage_tracker/server_recommendations.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 436 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach map -o /tmp/server-summary-recommendation-handlers-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings.

Remaining risks:
- `server.py` remains oversized at `833` lines.
- Usage refresh route wrapper and `_handle_usage` remain server-owned.
- Broad package structure remains too flat for strict cohesion.

Next handoff:
- Isolate `_handle_usage` only if it stays small enough for one branch; otherwise switch to the next roadmap module and leave usage handling for a separate design slice.

### `refactor/server-usage-handler`

Goal:
- Move `/api/usage` route wrapper out of `_UsageDashboardHandler`.
- Preserve refresh-token authorization, SQLite, and aggregate-read error response behavior.
- Keep the oversized dashboard server test from worsening the file-length ratchet.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_usage_refresh.py`
- `tests/test_dashboard_server.py`
- `tests/test_server_usage_refresh.py`

Completed edits:
- Added `handle_usage_request` in `server_usage_refresh.py`.
- Replaced `_handle_usage` with a thin delegate.
- Kept token-query parsing and refresh authorization inside the usage route wrapper.
- Added focused tests for successful usage responses, forbidden refresh responses, and aggregate-read error mapping.
- Updated the dashboard SQLite-error test to patch the new usage module boundary without increasing `tests/test_dashboard_server.py`.
- Ratcheted max-file baseline `1516 -> 1506`; `server.py` reduced `833 -> 823` lines.
- Kept `tests/test_dashboard_server.py` at `1150` lines while expanding usage wrapper coverage in `tests/test_server_usage_refresh.py`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_usage_refresh.py tests/test_server_usage_refresh.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_usage_refresh.py tests/test_server_usage_refresh.py tests/test_dashboard_server.py`: passed after import boundary cleanup.
- `.venv/bin/python -m pytest tests/test_server_usage_refresh.py tests/test_dashboard_server.py -q`: 18 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_usage_refresh.py -a -s`: usage route handler A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_usage_refresh.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach map -o /tmp/server-usage-handler-tach-map.json`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings.

Remaining risks:
- `server.py` remains oversized at `823` lines.
- Shell/open-investigator/context/dashboard-shell handling still lives in `server.py`.
- Broad package structure remains too flat for strict cohesion.

Next handoff:
- Stop server route-wrapper slicing here unless another route wrapper is clearly trivial; move to the next roadmap module so the branch series does not over-optimize one file.

### `refactor/diagnostic-snapshot-report-slice`

Goal:
- Move pure diagnostic snapshot payload/metadata helpers out of `diagnostic_snapshots.py`.
- Avoid private cross-module imports by exposing public helper names.
- Preserve existing missing/ready snapshot payload schemas.

Files touched:
- `.agent-maintainer/git-agent-ratchet-duplicate-helpers.json`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/diagnostic_snapshot_payloads.py`
- `src/codex_usage_tracker/diagnostic_snapshots.py`
- `tach.toml`

Completed edits:
- Added `diagnostic_snapshot_payloads.py` for `ready_payload`, `missing_payload`, `snapshot_metadata`, `history_scope`, `utc_now`, and `int_value`.
- Updated `diagnostic_snapshots.py` to import public helpers and removed the moved helper tail.
- Preserved missing-payload defaults, including `by_extension` for file-modification snapshots.
- Added `diagnostic_snapshot_payloads` to the relevant `tach.toml` module path/dependency lists.
- Ratcheted max-file baseline `1506 -> 1388`; `diagnostic_snapshots.py` reduced `823 -> 705` lines.
- Ratcheted duplicate-helper baseline `57 -> 51`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_payloads.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_payloads.py tests/test_diagnostic_snapshots.py tach.toml`: passed after mechanical import sort.
- `.venv/bin/python -m pytest tests/test_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py tests/test_cli_lifecycle.py -q`: 24 passed.
- `radon cc src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_payloads.py -a -s`: passed; moved `missing_payload` remains B-rated under current ceiling.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_payloads.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed and ratcheted.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach map -o /tmp/diagnostic-snapshot-report-slice-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning plus expected change-budget warning because existing tests covered this extraction.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings.

Remaining risks:
- `server.py` remains oversized at `823` lines.
- `diagnostic_snapshots.py` remains above the 600-line target at `705` lines.
- `missing_payload` is B-complexity and may deserve a small table-driven cleanup later.

Next handoff:
- Continue diagnostic snapshot reduction with a narrow table-driven `missing_payload` cleanup or split source-log refresh persistence from `diagnostic_snapshots.py`.

### `refactor/diagnostic-missing-payload-table`

Goal:
- Reduce `missing_payload` complexity after extracting diagnostic snapshot payload helpers.
- Preserve missing snapshot schemas and fresh mutable defaults for lists/dicts.

Files touched:
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/diagnostic_snapshot_payloads.py`

Completed edits:
- Replaced the `missing_payload` conditional ladder with `_MISSING_SECTION_DEFAULTS`.
- Added `_resolve_missing_field` and `_empty_thread_cost_curves` so callable defaults produce fresh payload values.
- Reduced `missing_payload` radon complexity from B to A.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/diagnostic_snapshot_payloads.py src/codex_usage_tracker/diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/diagnostic_snapshot_payloads.py src/codex_usage_tracker/diagnostic_snapshots.py tests/test_diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m pytest tests/test_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py tests/test_cli_lifecycle.py -q`: 24 passed.
- `radon cc src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_payloads.py -a -s`: `missing_payload` now A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_payloads.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach map -o /tmp/diagnostic-missing-payload-table-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning plus expected change-budget warning because existing tests covered this refactor.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings.

Remaining risks:
- `diagnostic_snapshots.py` remains above target at `705` lines.
- Source-log snapshot refresh and persistence remain coupled in `diagnostic_snapshots.py`.

Next handoff:
- Split source-log snapshot payload construction/persistence or move to another roadmap hotspot if diagnostic snapshots stop being the best payoff.

### `refactor/diagnostic-source-log-snapshots`

Goal:
- Move source-log diagnostic snapshot report/read/refresh/persist helpers out of `diagnostic_snapshots.py`.
- Get `diagnostic_snapshots.py` below the 600-line target without changing snapshot schemas.
- Keep source-log snapshot helpers public to avoid cross-module private imports.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `docs/maintainability-roadmap.md`
- `src/codex_usage_tracker/diagnostic_snapshot_source_logs.py`
- `src/codex_usage_tracker/diagnostic_snapshots.py`
- `tach.toml`

Completed edits:
- Added `diagnostic_snapshot_source_logs.py` for source-log snapshot report, refresh, persistence, and stored-payload loading.
- Updated `diagnostic_snapshots.py` to delegate tool-output, command, git, file-read, file-modification, and read-productivity sections.
- Added `diagnostic_snapshot_source_logs` to `tach.toml` module path/dependency lists.
- Ratcheted max-file baseline `1388 -> 1283`; `diagnostic_snapshots.py` reduced `705 -> 539` lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_source_logs.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_source_logs.py tests/test_diagnostic_snapshots.py tach.toml`: passed after mechanical import sort.
- `.venv/bin/python -m pytest tests/test_diagnostic_snapshots.py tests/test_server_diagnostic_snapshots.py tests/test_cli_lifecycle.py -q`: 24 passed.
- `radon cc src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_source_logs.py -a -s`: passed; moved persistence helper remains B-rated under current ceiling.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/diagnostic_snapshots.py src/codex_usage_tracker/diagnostic_snapshot_source_logs.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/tach map -o /tmp/diagnostic-source-log-snapshots-tach-map.json`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning plus expected change-budget warning because existing tests covered this extraction.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings.

Remaining risks:
- `server.py` remains oversized at `823` lines.
- `diagnostic_snapshot_source_logs.persist_source_log_snapshot` is still B-complexity.
- Overall package is still flat and triggers structure-cohesion warnings.

Next handoff:
- Move to the next high-payoff hotspot, likely `cli.py` or a narrow source-log persistence table cleanup, depending on whether the next goal is file length or complexity.

### `refactor/cli-diagnostics-runner`

Goal:
- Move diagnostics CLI command routing out of oversized `cli.py`.
- Reduce the moved diagnostics runner from a C-rated branch ladder to small A-rated builders.
- Preserve diagnostics CLI JSON/text output and command dispatch behavior.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `src/codex_usage_tracker/cli.py`
- `src/codex_usage_tracker/cli_diagnostics.py`
- `src/codex_usage_tracker/cli_output.py`
- `tach.toml`
- `docs/maintainability-roadmap.md`

Baseline and metric notes:
- `cli.py` line count fell from `976` to `827`.
- Max file-line ratchet fell from `1283` to `1134`.
- `cli_diagnostics.py` is `160` lines; `cli_output.py` is `11` lines.
- `run_diagnostics` is now A-rated complexity `3`; `cli_diagnostics.py` average complexity is A `1.5`.
- `diagnostic_snapshots.py` remains below target at `539` lines; `server.py` remains oversized at `823` lines.

Completed edits:
- Added `cli_diagnostics.run_diagnostics` and changed the CLI command handler table to dispatch to it.
- Moved diagnostics report/snapshot imports out of `cli.py`.
- Added shared `cli_output.print_json` so diagnostics and the main CLI use the same JSON formatting behavior.
- Collapsed repeated diagnostic snapshot command wrappers into a snapshot builder table.
- Kept existing diagnostics CLI characterization coverage through `tests/test_cli_lifecycle.py::test_diagnostics_cli_returns_aggregate_json`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_diagnostics.py src/codex_usage_tracker/cli_output.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_diagnostics.py src/codex_usage_tracker/cli_output.py`: passed.
- `.venv/bin/python -m pytest tests/test_cli_lifecycle.py::test_diagnostics_cli_returns_aggregate_json tests/test_cli_release.py::test_cli_reference_documents_only_existing_stable_commands -q`: 2 passed.
- `radon cc src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_diagnostics.py src/codex_usage_tracker/cli_output.py -a -s`: passed; moved diagnostics runner is A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_diagnostics.py src/codex_usage_tracker/cli_output.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning plus expected change-budget warning because existing tests covered the extraction.
- `.venv/bin/python -m agent_maintainer verify --profile precommit`: diagnostics-only failure; broad existing repo ruff-format, pyright, and xenon findings remain outside this slice.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings. New CLI modules are now explicitly assigned in `tach.toml`.

Remaining risks:
- `cli.py` is still oversized at `827` lines.
- `server.py` remains oversized at `823` lines.
- Overall package still triggers structure-cohesion warnings because the package is intentionally still flat during ratchet setup.
- Precommit profile is useful as diagnostics but not yet a clean gate for this repo.

Next handoff:
- Continue reducing `cli.py` with another narrow runner extraction or move back to `server.py` once the CLI slices stop being the highest payoff.

### `refactor/cli-dashboard-runner`

Goal:
- Move dashboard/open-dashboard/serve-dashboard CLI command runners out of oversized `cli.py`.
- Keep dashboard generation, refresh-before-open, and live server behavior unchanged.
- Keep the new runner A-rated and explicitly mapped in `tach.toml`.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `src/codex_usage_tracker/cli.py`
- `src/codex_usage_tracker/cli_dashboard.py`
- `tach.toml`
- `docs/maintainability-roadmap.md`

Baseline and metric notes:
- `cli.py` line count fell from `827` to `700`.
- Max file-line ratchet fell from `1134` to `1007`.
- `cli_dashboard.py` is `163` lines.
- `cli_dashboard.py` average complexity is A `1.89`; command runners are A-rated complexity `3`.
- `server.py` remains oversized at `823` lines.

Completed edits:
- Added `cli_dashboard.py` with dashboard, open-dashboard, and serve-dashboard runners.
- Moved browser-opening, static dashboard generation, live server launch, context API selection, and dashboard JSON payload helpers out of `cli.py`.
- Updated `_COMMAND_HANDLERS` to point at public dashboard runner functions.
- Added `cli_dashboard` to the CLI adapter module group in `tach.toml`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_dashboard.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_dashboard.py`: passed.
- `.venv/bin/python -m pytest tests/test_cli_lifecycle.py::test_report_json_and_query_cli tests/test_cli_release.py::test_cli_reference_documents_only_existing_stable_commands tests/test_dashboard_server.py -q`: 13 passed.
- `radon cc src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_dashboard.py -a -s`: passed; dashboard runners A-rated.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_dashboard.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning plus expected change-budget warning because existing tests covered the extraction.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings.

Remaining risks:
- `cli.py` is still oversized at `700` lines.
- `server.py` remains oversized at `823` lines.
- Overall package still triggers structure-cohesion warnings because the package is intentionally still flat during ratchet setup.

Next handoff:
- Continue reducing `cli.py`; the setup/plugin/pricing sections are now the biggest remaining CLI chunks.

### `refactor/cli-config-runners`

Goal:
- Move pricing, allowance, rate-card, threshold, and project-template CLI runners out of `cli.py`.
- Preserve CLI JSON schemas and text output for local config commands.
- Bring `cli.py` under the 600-line target.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `src/codex_usage_tracker/cli.py`
- `src/codex_usage_tracker/cli_config.py`
- `tach.toml`
- `docs/maintainability-roadmap.md`

Baseline and metric notes:
- `cli.py` line count fell from `700` to `530`.
- Max file-line ratchet fell from `1007` to `907`.
- `cli_config.py` is `196` lines.
- `cli_config.py` average complexity is A `3.22`; update-pricing and update-rate-card remain B-rated but below the current ceiling.
- `server.py` remains oversized at `823` lines.

Completed edits:
- Added `cli_config.py` with init/update/pin pricing, allowance parsing, rate-card update, threshold template, and project template runners.
- Updated `_COMMAND_HANDLERS` to point at public config runner functions.
- Removed config-specific imports and command implementations from `cli.py`.
- Added `cli_config` to the CLI adapter module group in `tach.toml`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_config.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_config.py`: passed after mechanical import sort.
- `.venv/bin/python -m pytest tests/test_cli_lifecycle.py::test_setup_support_bundle_and_reset_db_cli tests/test_cli_lifecycle.py::test_rate_card_allowance_and_pricing_snapshot_cli tests/test_cli_release.py::test_cli_reference_documents_only_existing_stable_commands -q`: 3 passed.
- `radon cc src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_config.py -a -s`: passed.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/cli.py src/codex_usage_tracker/cli_config.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning plus expected change-budget warning because existing tests covered the extraction.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings.

Remaining risks:
- `server.py` remains oversized at `823` lines and is now the largest clear file-length target.
- Overall package still triggers structure-cohesion warnings because the package is intentionally still flat during ratchet setup.
- `cli.py` still has B-complexity setup and inspect-log runners, but it is below the file-length target now.

Next handoff:
- Shift back to `server.py` or targeted B-complexity functions now that the CLI file-length ratchet goal is met.

### `refactor/server-diagnostic-route-mixin`

Goal:
- Move diagnostic server route wrappers out of `server.py`.
- Preserve existing route method names used by `server_routes.py`.
- Bring `server.py` under the 600-line target without changing diagnostic JSON schemas.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `src/codex_usage_tracker/server.py`
- `src/codex_usage_tracker/server_diagnostic_routes.py`
- `tach.toml`
- `docs/maintainability-roadmap.md`

Baseline and metric notes:
- `server.py` line count fell from `823` to `558`.
- Max file-line ratchet fell from `907` to `684`.
- `server_diagnostic_routes.py` is `227` lines.
- Server and diagnostic route modules remain A average complexity; `server.py` keeps only one B-rated stdlib route hook, `do_GET`.
- `cli.py` remains below target at `530` lines.

Completed edits:
- Added `DiagnosticRouteMixin` with diagnostics summary, facts, snapshots, usage-drain, refresh, and diagnostic refresh auth route methods.
- Made `_UsageDashboardHandler` inherit the mixin while preserving all route method names.
- Removed diagnostic route wrappers and diagnostic snapshot imports from `server.py`.
- Added `server_diagnostic_routes` to the server/dashboard architecture module group in `tach.toml`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_routes.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_routes.py`: passed after mechanical import sort.
- `.venv/bin/python -m pytest tests/test_server_diagnostic_snapshots.py tests/test_server_diagnostic_refresh_auth.py tests/test_dashboard_server.py -q`: 24 passed.
- `radon cc src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_routes.py -a -s`: passed.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/server.py src/codex_usage_tracker/server_diagnostic_routes.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning plus expected change-budget warning because existing tests covered the extraction.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected nonzero; same beta `src/agent_maintainer/__main__.py` repo-root false-positive plus optional/local integration warnings.

Remaining risks:
- File-length ratchet is now led by `allowance.py` at `759` lines, then `usage_drain_boundary_delta_summary.py` at `726` lines.
- Overall package still triggers structure-cohesion warnings because the package is intentionally still flat during ratchet setup.
- Route methods in `server_diagnostic_routes.py` intentionally rely on `_UsageDashboardHandler` attributes by mixin convention.

Next handoff:
- Move to the next file-length hotspot, likely `allowance.py`, or reduce remaining B-complexity hotspots if file-length progress pauses.
### `refactor/allowance-rate-card-module`

Goal:
- Move Codex rate-card loading, update-result metadata, parser helpers, and numeric/string helpers out of `allowance.py`.
- Keep `codex_usage_tracker.allowance` as the public compatibility facade for existing CLI/API/test imports.
- Reduce file-length and duplicate-helper ratchets without changing allowance JSON schemas or dashboard payload behavior.

Files touched:
- `.agent-maintainer/git-agent-ratchet-duplicate-helpers.json`
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `src/codex_usage_tracker/allowance.py`
- `src/codex_usage_tracker/allowance_rate_card.py`
- `tach.toml`
- `docs/maintainability-roadmap.md`

Baseline metric notes:
- `allowance.py` line count fell from `759` to `591`.
- Added `allowance_rate_card.py` at `279` lines.
- Max file-line ratchet fell from `684` to `525`.
- Duplicate-helper ratchet fell from `51` to `49`.
- `allowance_rate_card.py` has no C-rated functions; its highest functions are B-rated parser/update helpers.
- Remaining `allowance.py` complexity is pre-existing allowance-window logic: `_allowance_line_matches` C(18), `summarize_allowance_usage` C(15), and `resolve_credit_rate` C(13).

Completed edits:
- Extracted rate-card constants, bundled-card loading, rate-card update writing, credit-rate parsing, alias parsing, metadata parsing, and shared helper coercions to `allowance_rate_card.py`.
- Re-exported the stable public names from `allowance.py` through an explicit `__all__`.
- Split extracted metadata parser branches into row-level helpers so the new module stays below the Xenon absolute B ceiling.
- Added `allowance_rate_card` to the pricing/allowance architecture group in `tach.toml`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/allowance.py src/codex_usage_tracker/allowance_rate_card.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/allowance.py src/codex_usage_tracker/allowance_rate_card.py`: passed.
- `.venv/bin/python -m pytest tests/test_allowance.py tests/test_cli_lifecycle.py::test_rate_card_allowance_and_pricing_snapshot_cli -q`: 9 passed.
- `radon cc src/codex_usage_tracker/allowance.py src/codex_usage_tracker/allowance_rate_card.py -a -s`: passed; new module has no C-rated functions.
- `radon mi src/codex_usage_tracker/allowance.py src/codex_usage_tracker/allowance_rate_card.py -s`: `allowance.py` B, `allowance_rate_card.py` A.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/allowance_rate_card.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed and ratcheted.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected flat-package structure warning and branch-size warning.

Remaining risks:
- `allowance.py` is below the local 600-line target but still has C-rated allowance-window functions.
- Full Xenon across both allowance files still fails because those pre-existing `allowance.py` functions remain C-rated; this branch only made the extracted rate-card module clean under the B ceiling.
- Overall package still triggers structure-cohesion warnings because the project is intentionally being decomposed gradually from a flat package.

Next handoff:
- Start a separate allowance-window parser/summary complexity branch instead of mixing it into the rate-card extraction.

### `refactor/allowance-window-complexity`

Goal:
- Reduce the remaining C-rated allowance-window functions without changing allowance parsing, summary keys, or credit-rate behavior.
- Keep `allowance.py` below the local 600-line target after the complexity split.
- Isolate standalone copied-status text matching from allowance config and credit estimation logic.

Files touched:
- `src/codex_usage_tracker/allowance.py`
- `src/codex_usage_tracker/allowance_text.py`
- `tach.toml`
- `docs/maintainability-roadmap.md`

Baseline metric notes:
- `allowance.py` line count fell from `591` to `514`.
- Added `allowance_text.py` at `116` lines.
- `allowance.py` MI improved from B to A.
- `allowance.py` and `allowance_text.py` have no C-rated functions; average complexity is A.
- Highest remaining allowance complexity is B: `_resolve_alias_credit_rate` B(8), `_allowance_window_rows` B(7), and `write_allowance_from_text` B(6).

Completed edits:
- Extracted copied Codex status text matching and allowance-label regex helpers to `allowance_text.py`.
- Split `summarize_allowance_usage` into totals and numeric-field helpers.
- Split `resolve_credit_rate` into direct-rate and alias-rate helpers while preserving existing note wording.
- Split `parse_windows` into raw-row normalization and single-window construction.
- Added `allowance_text` to the pricing/allowance architecture group in `tach.toml`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/allowance.py src/codex_usage_tracker/allowance_text.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/allowance.py src/codex_usage_tracker/allowance_text.py`: passed after safe import formatting.
- `.venv/bin/python -m pytest tests/test_allowance.py tests/test_cli_lifecycle.py::test_rate_card_allowance_and_pricing_snapshot_cli -q`: 9 passed.
- `radon cc src/codex_usage_tracker/allowance.py src/codex_usage_tracker/allowance_text.py -a -s`: passed; no C-rated functions.
- `radon mi src/codex_usage_tracker/allowance.py src/codex_usage_tracker/allowance_text.py -s`: both A.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/allowance.py src/codex_usage_tracker/allowance_text.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected flat-package structure warning and Python-source-without-test-change warning.

Remaining risks:
- `allowance.py` still has B-rated helpers, but the C-rated allowance-window hotspots are removed.
- The package-wide structure-cohesion warning remains because the project is still intentionally flat during gradual decomposition.

Next handoff:
- Move to the next current file-length hotspot (`cli_parser.py`, `parser.py`, `usage_drain_reports.py`, `dashboard.py`, `diagnostics.py`, `reports.py`, or `diagnostic_facts.py`) depending on the roadmap priority and risk.

### `refactor/reports-query-helpers`

Goal:
- Reduce `reports.py` file length and the worst query/recommendation report complexity hotspots.
- Extract reusable query-row predicates and recommendation thread rollups without changing CLI/MCP report JSON schemas.
- Keep newly extracted report modules under the Xenon B/A/A threshold.

Files touched:
- `.agent-maintainer/git-agent-ratchet-max-file-lines.json`
- `src/codex_usage_tracker/reports.py`
- `src/codex_usage_tracker/report_filters.py`
- `src/codex_usage_tracker/report_recommendations.py`
- `tach.toml`
- `docs/maintainability-roadmap.md`

Baseline metric notes:
- `reports.py` line count fell from `637` to `569`.
- Added `report_filters.py` at `88` lines and `report_recommendations.py` at `127` lines.
- Max file-line ratchet fell from `525` to `488`.
- Removed the prior E/D query/recommendation helper hotspots from `reports.py`.
- `build_recommendations_report` fell to A(5); the new report helper modules pass Xenon B/A/A.

Completed edits:
- Extracted report row predicates to `report_filters.query_row_matches`.
- Extracted recommendation sorting and per-thread rollups to `report_recommendations`.
- Split recommendation report orchestration into source-row loading, annotation, filtering, and final payload construction helpers.
- Renamed a branch-local helper to avoid introducing a duplicate-helper ratchet regression.
- Added both new modules to the application/report-services architecture group in `tach.toml`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/reports.py src/codex_usage_tracker/report_filters.py src/codex_usage_tracker/report_recommendations.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/reports.py src/codex_usage_tracker/report_filters.py src/codex_usage_tracker/report_recommendations.py`: passed.
- `.venv/bin/python -m pytest tests/test_cli_release.py tests/test_mcp_integration.py -q`: 19 passed.
- `radon cc src/codex_usage_tracker/reports.py src/codex_usage_tracker/report_filters.py src/codex_usage_tracker/report_recommendations.py -a -s`: passed; remaining C-rated function is `_project_summary_rows`, outside this branch's query/recommendation helper slice.
- `radon mi src/codex_usage_tracker/reports.py src/codex_usage_tracker/report_filters.py src/codex_usage_tracker/report_recommendations.py -s`: all A.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/report_filters.py src/codex_usage_tracker/report_recommendations.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed after renaming the duplicate helper.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected flat-package structure warning and Python-source-without-test-change warning.

Remaining risks:
- `reports.py` still has `_project_summary_rows` C(17), which should be a separate project-summary report slice.
- `build_query_report` is still B(10), just under the current ceiling.
- Package-wide structure-cohesion warning remains while the flat package is being gradually decomposed.

Next handoff:
- Split or simplify `_project_summary_rows` separately, or move to the next larger file if report project summaries are lower risk than parser/dashboard work.

### `refactor/reports-project-summary`

Goal:
- Remove the remaining C-rated project-summary helper from `reports.py`.
- Preserve `summary --group-by project` and `summary --group-by project_tag` payload behavior.
- Keep the project-summary bucket lifecycle readable and independently testable.

Files touched:
- `src/codex_usage_tracker/reports.py`
- `src/codex_usage_tracker/report_project_summary.py`
- `tach.toml`
- `docs/maintainability-roadmap.md`

Baseline metric notes:
- `reports.py` line count fell from `569` to `498`.
- Added `report_project_summary.py` at `128` lines.
- `reports.py` now has no C-rated functions; highest remaining function is `build_query_report` B(10).
- `report_project_summary.py` is A-rated throughout.

Completed edits:
- Extracted project/project-tag summary aggregation to `report_project_summary.project_summary_rows`.
- Split project row annotation, group-key selection, bucket creation, bucket updates, token totals, ratio totals, and final rendering into focused helpers.
- Added `report_project_summary` to the application/report-services architecture group in `tach.toml`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/reports.py src/codex_usage_tracker/report_project_summary.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/reports.py src/codex_usage_tracker/report_project_summary.py`: passed.
- `.venv/bin/python -m pytest tests/test_cli_release.py tests/test_mcp_integration.py -q`: 19 passed.
- `radon cc src/codex_usage_tracker/reports.py src/codex_usage_tracker/report_project_summary.py -a -s`: passed; no C-rated functions.
- `radon mi src/codex_usage_tracker/reports.py src/codex_usage_tracker/report_project_summary.py -s`: both A.
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/reports.py src/codex_usage_tracker/report_project_summary.py`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m compileall src`: passed.
- `for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected flat-package structure warning and Python-source-without-test-change warning.

Remaining risks:
- `build_query_report` remains B(10), just under the current ceiling.
- Package-wide structure-cohesion warning remains while decomposition continues.

Next handoff:
- Move to the next largest files: `cli_parser.py`, `parser.py`, `usage_drain_reports.py`, `dashboard.py`, `diagnostics.py`, or `diagnostic_facts.py`.
### Branch: `refactor/parser-jsonl-v1-events`

Objective:
- Split Codex JSONL v1 event parsing out of the parser facade while preserving aggregate-only parser behavior and cursor state.

Baseline metrics:
- `parser.py` from current local `main`: 852 lines.
- Branch base before this slice: `parser.py` 726 lines after prior parser-state boundary work.
- Before this slice, `_parse_codex_jsonl_v1` remained the parser hotspot.

Completed edits:
- Added `parser_jsonl_v1.py` as the dedicated JSONL v1 aggregate parser state machine.
- Added `parser_jsonl_values.py` for low-level usage event construction, session metadata, rate-limit field parsing, and parser diagnostic counters.
- Kept `parser.py` as the public facade for adapter, session-index loading, file discovery, parse entrypoints, and inspect-log reporting.
- Split JSONL parsing into parse-state construction, per-line dispatch, session-meta handling, token-count handling, diagnostic-fact assignment, usage payload validation, and event construction helpers.
- Moved parser-private session id extraction, token field parsing, rate-limit observation, thread-key derivation, and parser diagnostic counters into parser JSONL helper modules.
- Added `parser_jsonl_v1` and `parser_jsonl_values` to the context/parser boundary in `tach.toml`.

Metrics after edits:
- `parser.py`: 199 lines.
- `parser_jsonl_v1.py`: 418 lines.
- `parser_jsonl_values.py`: 326 lines.
- Combined parser facade plus JSONL implementation/value helpers: 943 lines, +217 versus the immediate branch base but with parser responsibilities separated and no new oversized parser file.
- `parse_codex_jsonl_v1`: B(7).
- `_handle_jsonl_line`: B(7).
- `parser.py` still has `inspect_log` C(11), left as the next parser-facade complexity target.
- Max-file and agent-maintainer fast file-length gates passed without weakening the baseline; max-file overage ratcheted from 488 to 362.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/parser.py src/codex_usage_tracker/parser_jsonl_v1.py src/codex_usage_tracker/parser_jsonl_values.py`: passed.
- `.venv/bin/python -m mypy src/codex_usage_tracker/parser.py src/codex_usage_tracker/parser_jsonl_v1.py src/codex_usage_tracker/parser_jsonl_values.py`: passed.
- `.venv/bin/python -m pytest tests/test_parser.py tests/test_store_dashboard_mcp.py tests/test_dashboard_payload.py -q`: 39 passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted baseline 488 -> 362.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure/change-budget warnings only.
- `.venv/bin/python -m agent_maintainer doctor --strict`: expected local-only/beta failure remains `repo-root` missing `src/agent_maintainer/__main__.py`, plus non-blocking local integration warnings.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Next parser slice should reduce `inspect_log` C(11) and consider whether the facade should delegate inspect-log row formatting to a smaller report helper.
- Global Xenon still fails on known C/F-rated hotspots outside this branch.
### Branch: `refactor/usage-drain-span-feature-row`

Objective:
- Reduce the worst remaining usage-drain feature construction hotspot while preserving the predictive model row schema.

Baseline metrics:
- `usage_drain_features.py`: 198 lines at branch start.
- `span_feature_row`: F(41).
- Module average complexity: D(25.0).

Completed edits:
- Split `span_feature_row` into feature groups for time, credits/tokens, turns, effort, usage-window buckets, and timing buckets.
- Added small shared helpers for safe division, cyclic time encodings, turn fallbacks, and usage-window elapsed calculations.
- Preserved existing output keys and kept `add_days_since_first_span` behavior unchanged.

Metrics after edits:
- `usage_drain_features.py`: 304 lines.
- `span_feature_row`: A(3).
- Highest remaining function in module: `add_days_since_first_span` B(9).
- Module average complexity: A(2.62).
- `xenon --max-absolute B --max-modules A --max-average A src/codex_usage_tracker/usage_drain_features.py`: passed.

Checks:
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy src/codex_usage_tracker/usage_drain_features.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py -q`: 15 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_server_diagnostic_snapshots.py -q`: 26 passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure/change-budget warnings only.
- `.venv/bin/python -m pytest -q`: 439 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `add_days_since_first_span` remains B(9) but within current Xenon ceiling.
- Global Xenon still fails on other known C/F-rated usage-drain, store, diagnostic, and doctor hotspots.
### `refactor/diagnostic-fact-structured-classifier`

Objective:
- Finish the diagnostic-fact classifier split after the in-file refactor made
  `diagnostic_facts.py` too large for the file-length ratchet.
- Keep aggregate/privacy behavior unchanged for function, MCP, skill, command,
  search/read, and derived loop facts.
- Add a focused characterization test for the extracted classifier entrypoint.

Baseline metrics:
- `diagnostic_facts.py`: 636 lines on branch base, temporarily 743 lines after
  in-file helper extraction.
- `_structured_tool_and_skill_facts`: D(23) before helper split.
- `_with_derived_loop_facts`: C(12) before derived-loop helper split.
- Max-file ratchet overage before branch completion: 362.

Completed edits:
- Added `diagnostic_fact_classifiers.py` for structured function/MCP/skill and
  command/search classifier helpers.
- Kept `diagnostic_facts.py` focused on envelope orchestration, derived loop
  facts, persistence row conversion, merge, confidence, and timestamp helpers.
- Passed the `_fact` factory into the classifier module so no private helper
  import is needed across modules.
- Added `tests/test_diagnostic_fact_classifiers.py` to assert safe aggregate
  command-family and search/read labels without raw command argument leakage.

Metrics edits:
- `diagnostic_facts.py`: 393 lines.
- `diagnostic_fact_classifiers.py`: 383 lines.
- `tests/test_diagnostic_fact_classifiers.py`: 65 lines.
- `_with_derived_loop_facts`: A(3).
- `structured_tool_and_skill_facts`: A(2).
- `diagnostic_fact_classifiers.py` average complexity: A(3.55).
- Targeted Xenon B/A/A passed for both diagnostic fact modules.
- Max-file ratchet overage tightened from 362 to 326.

Checks:
- `.venv/bin/python -m ruff check src/codex_usage_tracker/diagnostic_facts.py src/codex_usage_tracker/diagnostic_fact_classifiers.py tests/test_diagnostic_fact_classifiers.py tests/test_parser.py`: passed.
- `.venv/bin/python -m mypy src/codex_usage_tracker/diagnostic_facts.py src/codex_usage_tracker/diagnostic_fact_classifiers.py`: passed.
- `.venv/bin/python -m pytest tests/test_diagnostic_fact_classifiers.py tests/test_parser.py tests/test_store_dashboard_mcp.py tests/test_server_diagnostic_facts.py -q`: 41 passed.
- `.venv/bin/python -m pytest -q`: 440 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted baseline.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `diagnostic_fact_classifiers._mcp_event_facts` is still B(10), within current
  ceiling but a good later cleanup target.
- `diagnostic_facts.diagnostic_facts_from_envelope` and
  `diagnostic_fact_from_json` remain B(8), acceptable for now.
- Global Xenon still fails on unrelated C-rated hotspots.
### `refactor/cli-parser-diagnostics`

Objective:
- Reduce the largest remaining source file by moving only diagnostics CLI
  parser construction into a dedicated module.
- Preserve public `build_parser()` behavior and nested diagnostics subcommand
  argument parsing.
- Keep all parser builder functions A-rated.

Baseline metrics:
- `cli_parser.py`: 742 lines.
- `cli_parser.py` functions: A-rated, but file length exceeded the current
  ratchet threshold.
- Max-file ratchet overage before branch completion: 326.

Completed edits:
- Added `cli_parser_diagnostics.py` for diagnostics subparser construction and
  diagnostics-specific filter/sort parser helpers.
- Replaced the in-file diagnostics parser call with
  `add_diagnostics_parser(subparsers)`.
- Removed diagnostics sort-choice imports from `cli_parser.py`.
- Added `tests/test_cli_parser_diagnostics.py` to lock nested diagnostics
  parser behavior without making `tests/test_cli_release.py` larger.

Metrics edits:
- `cli_parser.py`: 550 lines.
- `cli_parser_diagnostics.py`: 201 lines.
- `tests/test_cli_parser_diagnostics.py`: 36 lines.
- Combined CLI parser complexity remains A(1.0).
- Max-file ratchet overage tightened from 326 to 184.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/cli_parser.py src/codex_usage_tracker/cli_parser_diagnostics.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/cli_parser.py src/codex_usage_tracker/cli_parser_diagnostics.py tests/test_cli_parser_diagnostics.py tests/test_cli_release.py`: passed.
- `.venv/bin/python -m pytest tests/test_cli_parser_diagnostics.py tests/test_cli_release.py -q`: 18 passed.
- `.venv/bin/python -m pytest -q`: 441 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted baseline.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `usage_drain_reports.py`, `dashboard.py`, and `diagnostics.py` are now the
  largest remaining source files over 600 lines.
- Global Xenon still fails on unrelated C-rated hotspots.
### `refactor/usage-drain-report-thread-curves`

Objective:
- Reduce `usage_drain_reports.py` by extracting the dashboard thread cost curve
  report slice.
- Preserve aggregate-only thread curve output schema and bounded sampling.
- Avoid leaving the new public thread-curve entrypoint C-rated.

Baseline metrics:
- `usage_drain_reports.py`: 677 lines.
- `_thread_cost_curves`: C(11).
- Max-file ratchet overage before branch completion: 184.

Completed edits:
- Added `usage_drain_thread_curves.py` for thread cost curve constants,
  grouping, sorting, summary, curve-point sampling, labels, and numeric
  coercion.
- Replaced the in-file curve builder call with `thread_cost_curves(...)`.
- Split the moved public entrypoint into bucket, sort, summary, and record
  helpers so `thread_cost_curves` is A-rated.
- Fixed the curve sampler edge case where `max_curve_points=1` divided by zero.
- Added `tests/test_usage_drain_thread_curves.py` for ordering, top-thread
  share, and one-point sampling behavior.

Metrics edits:
- `usage_drain_reports.py`: 565 lines.
- `usage_drain_thread_curves.py`: 171 lines.
- `tests/test_usage_drain_thread_curves.py`: 38 lines.
- `thread_cost_curves`: A(1).
- `usage_drain_thread_curves.py` average complexity: A(3.83).
- Max-file ratchet overage tightened from 184 to 107.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_reports.py src/codex_usage_tracker/usage_drain_thread_curves.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_reports.py src/codex_usage_tracker/usage_drain_thread_curves.py tests/test_usage_drain_thread_curves.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_thread_curves.py tests/test_usage_drain_reports.py -q`: 6 passed.
- `.venv/bin/python -m pytest -q`: 442 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted baseline.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `dashboard.py` and `diagnostics.py` are now the largest source files over
  600 lines.
- `usage_drain_reports.py` still has C-rated modeling helpers; split those in
  later report-model branches if prioritizing global Xenon cleanup.
### `refactor/dashboard-asset-helpers`

Objective:
- Reduce `dashboard.py` below the current file-length ratchet by moving static
  asset, docs, versioned href, and template rendering helpers into a dedicated
  module.
- Preserve public `generate_dashboard()` and `render_dashboard_html()` APIs.
- Remove one duplicate private helper name from the dashboard module.

Baseline metrics:
- `dashboard.py`: 667 lines.
- `dashboard_payload`: C(16), left for later behavior-focused cleanup.
- `_copy_resource_tree` duplicated a helper name from plugin installation.
- Max-file ratchet overage before branch completion: 107.
- Duplicate-helper ratchet debt before branch completion: 49.

Completed edits:
- Added `dashboard_assets.py` for dashboard stylesheet/script constants,
  docs/assets copying, versioned asset hrefs, script source mapping, body
  attribute formatting, dashboard template rendering, and asset reads.
- Kept `dashboard.py` focused on payload generation, static dashboard output,
  pricing snapshots, previous-payload parsing, and summary helpers.
- Preserved the public `render_dashboard_html()` name used by the live server.
- Renamed the copied-resource helper to `_copy_dashboard_resource_tree`.

Metrics edits:
- `dashboard.py`: 525 lines.
- `dashboard_assets.py`: 169 lines.
- `dashboard_assets.py` average complexity: A-rated.
- Max-file ratchet overage tightened from 107 to 40.
- Duplicate-helper ratchet debt tightened from 49 to 47.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/dashboard.py src/codex_usage_tracker/dashboard_assets.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/dashboard.py src/codex_usage_tracker/dashboard_assets.py`: passed.
- `.venv/bin/python -m pytest tests/test_dashboard_server.py tests/test_dashboard_data.py tests/test_dashboard_state.py tests/test_dashboard_status.py tests/test_dashboard_live.py -q`: 24 passed.
- `.venv/bin/python -m pytest -q`: 442 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted baseline.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed and ratcheted baseline.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `diagnostics.py` is the only remaining source file over 600 lines.
- `dashboard_payload` and `_pricing_snapshot_warning` remain C-rated and should
  be addressed in later dashboard-payload cleanup branches.
### `refactor/diagnostics-mcp-checks`

Objective:
- Clear the last source file over the 600-line limit by moving MCP-specific
  doctor checks out of `diagnostics.py`.
- Preserve `run_doctor()` output shape and MCP wrapper behavior.
- Avoid circular imports by moving `DoctorCheck` into a shared type module.

Baseline metrics:
- `diagnostics.py`: 640 lines.
- `_check_mcp_runtime`: C(19).
- `_check_mcp_config`: C(14).
- `run_doctor`: C(14), left for later orchestration cleanup.
- Max-file ratchet overage before branch completion: 40.

Completed edits:
- Added `diagnostics_types.py` containing the shared `DoctorCheck` dataclass.
- Added `diagnostics_mcp.py` for MCP config, runtime, launcher, command/cwd
  resolution, error-line extraction, and module import checks.
- Replaced `run_doctor()` MCP check calls with public `check_mcp_config`,
  `check_mcp_runtime`, and `check_mcp_import`.

Metrics edits:
- `diagnostics.py`: 402 lines.
- `diagnostics_mcp.py`: 254 lines.
- `diagnostics_types.py`: 16 lines.
- Max-file ratchet overage tightened from 40 to 0.
- No `src/codex_usage_tracker/*.py` file is over 600 lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/diagnostics.py src/codex_usage_tracker/diagnostics_mcp.py src/codex_usage_tracker/diagnostics_types.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/diagnostics.py src/codex_usage_tracker/diagnostics_mcp.py src/codex_usage_tracker/diagnostics_types.py`: passed.
- `.venv/bin/python -m pytest tests/test_cli_release.py tests/test_mcp_integration.py -q`: 19 passed.
- `.venv/bin/python -m pytest -q`: 442 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed and ratcheted baseline to zero.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- File-size ratchet is now clean for `src`.
- `check_mcp_runtime`, `check_mcp_config`, `run_doctor`, and
  `_check_parser_diagnostics` remain C-rated complexity cleanup targets.
- Next branches should shift from file-size repair to complexity reduction and
  then stricter local gates.
### `refactor/diagnostics-doctor-orchestration`

Objective:
- Reduce `run_doctor` orchestration complexity without changing doctor report
  schema or check ordering.
- Keep the split close to existing diagnostics behavior and tests.

Baseline metrics:
- `run_doctor`: C(14).
- `diagnostics.py` module average: B before this split.

Completed edits:
- Split `run_doctor` into root resolution, `_doctor_checks`, `_doctor_report`,
  `_count_check_status`, `_doctor_status`, and `_doctor_repair_suggestions`.
- Preserved check order, status precedence, failure/warning counts, and repair
  suggestion filtering.

Metrics edits:
- `run_doctor`: A(3).
- `diagnostics.py` average complexity: A(4.15).
- `diagnostics.py`: 442 lines.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/diagnostics.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/diagnostics.py`: passed.
- `.venv/bin/python -m pytest tests/test_cli_release.py tests/test_mcp_integration.py tests/test_support.py -q`: 21 passed.
- `.venv/bin/python -m pytest -q`: 442 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `_check_parser_diagnostics` remains C(11) in `diagnostics.py`.
- MCP runtime/config checks remain C-rated in `diagnostics_mcp.py`.
- Global Xenon still fails on unrelated usage-drain, store, parser-state,
  costing, and diagnostic snapshot hotspots.

### `refactor/diagnostics-parser-check`

Objective:
- Reduce the parser diagnostics doctor check complexity without changing doctor messages or remediation wording.

Files touched:
- `src/codex_usage_tracker/diagnostics.py`

Completed edits:
- Split parser drift extraction into `_parser_diagnostic_drift_parts`, `_parser_diagnostic_counts`,
  `_skipped_event_parts`, and `_parser_diagnostic_drift_keys`.
- Split warning/pass response construction into `_parser_diagnostic_warning` and
  `_parser_diagnostic_pass`.
- Preserved the existing parser diagnostics status strings and remediation text.

Metrics:
- `_check_parser_diagnostics`: C(11) -> A(4).
- `diagnostics.py` average complexity: A(3.38).
- No file-size ratchet regression; `diagnostics.py` remains below the 600-line budget.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/diagnostics.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/diagnostics.py`: passed.
- `.venv/bin/python -m radon cc src/codex_usage_tracker/diagnostics.py -a -s`: passed, parser check now A(4).
- `.venv/bin/python -m pytest tests/test_cli_release.py tests/test_mcp_integration.py tests/test_support.py tests/test_store_migrations.py -q`: 26 passed.
- `.venv/bin/python -m pytest -q`: 442 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `_check_plugin_link` and `_check_marketplace` are the next B-rated functions in `diagnostics.py`.
- MCP runtime/config checks remain C-rated in `diagnostics_mcp.py`.
- Global Xenon still fails on unrelated usage-drain, store, parser-state, costing, diagnostic snapshot hotspots.

### `refactor/context-read-entries`

Objective:
- Reduce the worst remaining source complexity hotspot, `_read_context_entries`, while preserving on-demand context loading and privacy behavior.

Files touched:
- `src/codex_usage_tracker/context.py`
- `tests/test_context_scan.py`

Completed edits:
- Added `_ContextReadState` to make scan state explicit instead of spreading mutable loop state through one large function.
- Split JSONL line parsing, per-line scan handling, selected-turn reset, serialized-context collection, pending summary carry-forward, and result assembly into focused helpers.
- Added a parse-error characterization test that proves malformed JSONL lines increment context diagnostics without losing the selected turn.

Metrics:
- `_read_context_entries`: E(31) -> A(4).
- `context.py` average complexity: B(8.63) -> A(4.16).
- New helper ceiling in this module: B(9) for existing `_limit_entries`; new scan helpers are B(7) or better.
- Source file remains below the 600-line budget.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/context.py tests/test_context_evidence.py tests/test_context_scan.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/context.py tests/test_context_evidence.py tests/test_context_scan.py`: passed.
- `.venv/bin/python -m pytest tests/test_context_evidence.py tests/test_context_scan.py tests/test_context_serialized.py tests/test_context_summaries.py tests/test_context_action_timing.py -q`: 19 passed.
- `.venv/bin/python -m radon cc src/codex_usage_tracker/context.py -a -s`: passed, `_read_context_entries` now A(4).
- `.venv/bin/python -m pytest -q`: 443 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `load_call_context` remains C(13) in `context.py`.
- Global Xenon still fails on remaining C-rated blocks in usage-drain, store, diagnostics MCP, recommendations, formatting, and project config modules.

### `refactor/usage-drain-proxy-fit`

Objective:
- Reduce the worst remaining usage-drain modeling complexity hotspot, `fit_usage_drain_proxy`, without changing the `UsageDrainModelResult` contract.

Files touched:
- `src/codex_usage_tracker/usage_drain_proxy_fit.py`

Completed edits:
- Split proxy vector extraction, two-feature no-intercept fit, grid fit selection, and candidate/non-candidate drain comparison into focused helpers.
- Preserved existing proxy-fit return fields, rounding behavior, grid rows, and documented multiplier logic.
- Reused the existing multiplier recovery characterization test for behavior coverage.

Metrics:
- `fit_usage_drain_proxy`: D(28) -> A(5).
- `usage_drain_proxy_fit.py` average complexity: D(28.0) -> B(6.0).
- New helper ceiling: B(9) for `_candidate_drain_comparison`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_proxy_fit.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_proxy_fit.py`: passed.
- `.venv/bin/python -m radon cc src/codex_usage_tracker/usage_drain_proxy_fit.py -a -s`: passed, target function now A(5).
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py::test_fit_usage_drain_proxy_recovers_documented_multiplier -q`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py tests/test_usage_drain_thread_curves.py -q`: 21 passed.
- `.venv/bin/python -m pytest -q`: 443 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Global Xenon still fails on C/D-rated blocks in projects, usage-drain feature history/time series/allowance fits, store, diagnostics MCP, recommendations, formatting, and diagnostic snapshot analysis.

### `refactor/project-config-loader`

Objective:
- Reduce the project config loader complexity while preserving permissive local-config parsing behavior.

Files touched:
- `src/codex_usage_tracker/projects.py`
- `tests/test_projects.py`

Completed edits:
- Split missing/error config construction, JSON payload loading, aliases, ignored paths, tags, and section normalization into focused helpers.
- Added a malformed-section characterization test proving invalid aliases, ignored paths, and tag values are discarded while valid values are retained.

Metrics:
- `load_project_config`: D(23) -> A(4).
- `projects.py` average complexity remains A-rated.
- New helper ceiling in this module: B(8) for existing `project_identity_for_cwd`; config loader helpers are B(6) or better.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/projects.py tests/test_projects.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/projects.py tests/test_projects.py`: passed.
- `.venv/bin/python -m pytest tests/test_projects.py -q`: 5 passed.
- `.venv/bin/python -m pytest tests/test_projects.py tests/test_privacy.py tests/test_server_summary.py tests/test_server_recommendations.py -q`: 18 passed.
- `.venv/bin/python -m radon cc src/codex_usage_tracker/projects.py -a -s`: passed, loader now A(4).
- `.venv/bin/python -m pytest -q`: 444 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Global Xenon still fails on remaining C-rated blocks in usage-drain feature history/time series/allowance fits, store, diagnostics MCP, recommendations, formatting, dashboard payload, and diagnostic snapshot analysis.

### `refactor/format-recommendations`

Objective:
- Reduce the human-readable recommendation formatter complexity while preserving current CLI text output.

Files touched:
- `src/codex_usage_tracker/formatting.py`
- `tests/test_formatting.py`

Completed edits:
- Added direct formatter characterization for empty payloads, top-thread output, primary recommendation output, and fallback title/action text.
- Split recommendation row extraction, thread-section formatting, call-line formatting, primary recommendation normalization, and thread label selection into formatter-specific helpers.
- Renamed helpers with a `formatted_` prefix to avoid increasing duplicate-helper ratchet debt.

Metrics:
- `format_recommendations`: C(20) -> A(3).
- `formatting.py` average complexity: B(6.91) -> A(4.82).
- New helper ceiling: B(7) for `_formatted_recommendation_call`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/formatting.py tests/test_formatting.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/formatting.py tests/test_formatting.py`: passed.
- `.venv/bin/python -m pytest tests/test_formatting.py -q`: 2 passed.
- `.venv/bin/python -m pytest tests/test_formatting.py tests/test_recommendations.py tests/test_server_recommendations.py tests/test_cli_lifecycle.py -q`: 14 passed.
- `.venv/bin/python -m radon cc src/codex_usage_tracker/formatting.py -a -s`: passed, recommendation formatter now A(3).
- `.venv/bin/python -m pytest -q`: 446 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `format_calls` remains C(13) in `formatting.py`.
- Global Xenon still fails on remaining C-rated blocks in usage-drain feature history/time series/allowance fits, store, diagnostics MCP, recommendations, dashboard payload, and diagnostic snapshot analysis.

### `refactor/usage-drain-feature-history`

Objective:
- Reduce the walk-forward causal history feature function complexity while preserving causal-only feature semantics.

Files touched:
- `src/codex_usage_tracker/usage_drain_feature_history.py`
- `tests/test_usage_drain_feature_history.py`

Completed edits:
- Added focused characterization proving history features only use prior rows and matching prior bucket/date/hour/day rows.
- Introduced `_CausalHistoryState` and `_HistoryKeys` to hold mutable walk-forward state explicitly.
- Split global rolling features, streak features, capacity features, same-period features, EWMA features, and state updates into focused helpers.

Metrics:
- `add_causal_history_features`: C(20) -> A(2).
- `usage_drain_feature_history.py` remains A-rated on average.
- New helper ceiling: B(6) for `_history_keys` and existing `streak_bucket`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_feature_history.py tests/test_usage_drain_feature_history.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_feature_history.py tests/test_usage_drain_feature_history.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_feature_history.py -q`: 1 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_feature_history.py tests/test_usage_drain_model.py tests/test_usage_drain_reports.py tests/test_usage_drain_thread_curves.py -q`: 22 passed.
- `.venv/bin/python -m radon cc src/codex_usage_tracker/usage_drain_feature_history.py -a -s`: passed, target function now A(2).
- `.venv/bin/python -m pytest -q`: 447 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Global Xenon still fails on remaining C-rated blocks in usage-drain time series/allowance fits/boundary rows, store, diagnostics MCP, recommendations, dashboard payload, formatting calls, and diagnostic snapshot analysis.

### `refactor/usage-drain-weekly-projection`

Objective:
- Reduce weekly credit projection time-series complexity while preserving dashboard/report projection shape.

Files touched:
- `src/codex_usage_tracker/usage_drain_time_series.py`

Completed edits:
- Split usable span filtering, weekly observed totals, full-week estimates, confidence interval calculation, and timestamp range extraction out of `_weekly_projection_point`.
- Split trend value extraction, insufficient-trend response, slope calculation, and direction labeling out of `_weekly_projection_trend`.
- Preserved existing weekly projection fields, confidence method, CI math, and plan-aware trend behavior.

Metrics:
- `_weekly_projection_point`: C(19) -> A(4).
- `_weekly_projection_trend`: C(15) -> A(4).
- `usage_drain_time_series.py` no longer has C-rated weekly projection helpers; remaining ceiling is B(10) for `_trend_points_for_latest_plan`.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_time_series.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_time_series.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_reports.py tests/test_dashboard_diagnostics_snapshots.py -q`: 14 passed.
- `.venv/bin/python -m radon cc src/codex_usage_tracker/usage_drain_time_series.py -a -s`: passed, projection point and trend now A(4).
- `.venv/bin/python -m pytest -q`: 447 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Global Xenon still fails on remaining C-rated blocks in diagnostics MCP, usage-drain boundary/allowance/state/spans, store, recommendations, dashboard payload, formatting calls, and diagnostic snapshot analysis.

### `refactor/diagnostics-mcp-runtime`

Objective:
- Reduce MCP doctor check complexity while preserving generated plugin/runtime validation messages.

Files touched:
- `src/codex_usage_tracker/diagnostics_mcp.py`

Completed edits:
- Split MCP config JSON loading, server entry validation, command validation, and environment detail formatting out of `check_mcp_config`.
- Split MCP runtime server loading, args validation, command error formatting, subprocess import check execution, runtime environment creation, and failure formatting out of `check_mcp_runtime`.
- Preserved existing doctor check names, statuses, remediation strings, and plugin installer behavior.

Metrics:
- `check_mcp_runtime`: C(19) -> B(7).
- `check_mcp_config`: C(14) -> B(9).
- `diagnostics_mcp.py` average complexity: A(3.76).

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/diagnostics_mcp.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/diagnostics_mcp.py`: passed.
- `.venv/bin/python -m pytest tests/test_cli_release.py tests/test_mcp_integration.py tests/test_support.py tests/test_plugin_installer.py -q`: 31 passed.
- `.venv/bin/python -m radon cc src/codex_usage_tracker/diagnostics_mcp.py -a -s`: passed, MCP config/runtime checks now B-rated.
- `.venv/bin/python -m pytest -q`: 447 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Global Xenon still fails on remaining C-rated blocks in usage-drain boundary/allowance/state/spans, store, recommendations, dashboard payload, formatting calls, threads, diagnostic reports, and diagnostic snapshot analysis.
### `refactor/usage-drain-boundary-delta`

Objective:
- Reduce boundary-delta walk-forward prediction complexity without changing report/dashboard fields.
- Keep compatibility imports through `usage_drain_boundary_delta.py`.
- Add focused row-level characterization for matched-state, boundary-conditioned, risk-gated, and adaptive-threshold details.

Files touched:
- `src/codex_usage_tracker/usage_drain_boundary_delta.py`
- `src/codex_usage_tracker/usage_drain_boundary_delta_core.py`
- `src/codex_usage_tracker/usage_drain_boundary_delta_rows.py`
- `tests/test_usage_drain_boundary_delta.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split constants and primitive risk/threshold helpers into `usage_drain_boundary_delta_core.py`.
- Split walk-forward row construction and extracted helpers into `usage_drain_boundary_delta_rows.py`.
- Kept `usage_drain_boundary_delta.py` as a small compatibility facade exporting the same public names.
- Added direct characterization coverage for prediction aliases and detail metadata consumed by downstream summaries.

Metrics:
- `boundary_walk_forward_delta_prediction_rows`: C(18) -> A(4).
- Boundary-delta implementation modules average complexity: A(2.5).
- Global C-or-worse blocks: 55 -> 54.
- New largest remaining hotspot: `usage_drain_allowance_fits.py::allowance_piecewise_credit_to_delta_fit` C(18).

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_boundary_delta.py src/codex_usage_tracker/usage_drain_boundary_delta_core.py src/codex_usage_tracker/usage_drain_boundary_delta_rows.py tests/test_usage_drain_boundary_delta.py tests/test_usage_drain_model.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_boundary_delta.py src/codex_usage_tracker/usage_drain_boundary_delta_core.py src/codex_usage_tracker/usage_drain_boundary_delta_rows.py tests/test_usage_drain_boundary_delta.py tests/test_usage_drain_model.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_boundary_delta.py tests/test_usage_drain_model.py::test_boundary_walk_forward_risk_learns_segment_age_pattern tests/test_usage_drain_model.py::test_boundary_delta_risk_gate_keeps_previous_delta_for_stable_regime -q`: 3 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_reports.py tests/test_usage_drain_thread_curves.py -q`: 22 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_boundary_delta.py src/codex_usage_tracker/usage_drain_boundary_delta_core.py src/codex_usage_tracker/usage_drain_boundary_delta_rows.py -a -s`: passed, all analyzed blocks A-rated.
- `.venv/bin/python -m pytest -q`: 448 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Global Xenon still fails on remaining C-rated blocks in allowance fits, store upserts, recommendations, usage-drain spans/state summaries, dashboard payload, and diagnostic snapshot analysis.
- Next high-impact target is likely `usage_drain_allowance_fits.py::allowance_piecewise_credit_to_delta_fit` or `store.py::upsert_usage_events`.
### `refactor/usage-drain-allowance-fits`

Objective:
- Reduce piecewise allowance credit-to-delta fit complexity while preserving breakpoint diagnostics schema and metrics.
- Add direct characterization around segment model records and piecewise model names.

Files touched:
- `src/codex_usage_tracker/usage_drain_allowance_fits.py`
- `tests/test_usage_drain_allowance_fits.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added a focused direct test for `allowance_piecewise_credit_to_delta_fit`.
- Split empty response, no-intercept slope fitting, prediction-list construction, segment extraction, leave-one-out denominator calculation, prediction accumulation, and segment model formatting into helpers.
- Preserved existing output keys and downstream `allowance_breakpoint_analysis` behavior.

Metrics:
- `allowance_piecewise_credit_to_delta_fit`: C(18) -> B(6).
- `usage_drain_allowance_fits.py` average complexity: A(4.75).
- Global C-or-worse blocks: 54 -> 53.
- New largest remaining hotspots: `store.py::upsert_usage_events` C(18) and `recommendations.py::action_recommendations` C(18).
- `usage_drain_allowance_fits.py`: 481 physical lines, 450 source lines; still within the active source-line ratchet.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_allowance_fits.py tests/test_usage_drain_allowance_fits.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_allowance_fits.py tests/test_usage_drain_allowance_fits.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_allowance_fits.py tests/test_usage_drain_model.py::test_allowance_breakpoint_analysis_detects_capacity_denominator_change -q`: 2 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_allowance_fits.py -a -s`: passed, target now B-rated.
- `.venv/bin/python -m pytest -q`: 449 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `allowance_online_capacity_credit_to_delta_fit` remains C(15), but this branch kept scope to the highest piecewise-fit hotspot.
- Next likely targets are `store.py::upsert_usage_events`, `recommendations.py::action_recommendations`, or a follow-up allowance-online branch.
### `refactor/recommendation-action-tree`

Objective:
- Reduce recommendation decision-tree complexity while preserving recommendation order, keys, severity, and text.
- Add coverage for estimated-pricing, high-cost, elevated-context, and reasoning-spike branches.

Files touched:
- `src/codex_usage_tracker/recommendations.py`
- `tests/test_recommendations.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split pricing, high-cost, context, low-cache, reasoning, low-output, large-thread, and subagent checks into focused helpers.
- Kept `action_recommendations` as an ordered candidate aggregator.
- Added direct characterization for the estimated-pricing/high-cost/elevated-context/reasoning branch combination.

Metrics:
- `action_recommendations`: C(18) -> A(4).
- `recommendations.py` average complexity: A(3.81).
- Global C-or-worse blocks: 53 -> 52.
- New largest remaining hotspot: `store.py::upsert_usage_events` C(18).

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/recommendations.py tests/test_recommendations.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/recommendations.py tests/test_recommendations.py`: passed.
- `.venv/bin/python -m pytest tests/test_recommendations.py -q`: 3 passed.
- `.venv/bin/python -m pytest tests/test_recommendations.py tests/test_server_recommendations.py tests/test_mcp_integration.py tests/test_cli_lifecycle.py -q`: 15 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/recommendations.py -a -s`: passed, target now A-rated.
- `.venv/bin/python -m pytest -q`: 450 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `store.py::upsert_usage_events` is now the highest remaining C-rated block.
- Several usage-drain span/state/dashboard diagnostics functions remain C-rated and need subsequent small branches.
### `refactor/store-upsert-usage-events`

Objective:
- Reduce `upsert_usage_events` complexity without changing transaction scope, upsert SQL semantics, diagnostic fact replacement, or link refresh behavior.
- Keep persistence behavior covered by existing store, migration, and diagnostic fact tests.

Files touched:
- `src/codex_usage_tracker/store.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split usage-event row conversion, diagnostic-fact row conversion, source-file string normalization, source-file replacement deletes, empty-replacement refresh behavior, record-id extraction, usage-event upsert SQL construction, row insertion, and post-upsert link refresh into focused helpers.
- Preserved the single `connect` transaction boundary and existing `init_db` call placement.
- Preserved batched diagnostic fact deletion and existing diagnostic fact insert/update behavior.

Metrics:
- `upsert_usage_events`: C(18) -> A(2).
- `store.py` average complexity: A(2.71).
- Global C-or-worse blocks: 52 -> 51.
- New largest remaining hotspots: `usage_drain_spans.py::_span_from_rows` C(17) and `diagnostic_snapshot_analysis.py::_scan_source_log` C(17).
- `store.py`: 558 lines, still under the active 600-line physical file budget.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/store.py tests/test_store_large_batches.py tests/test_store_dashboard_mcp.py tests/test_store_migrations.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/store.py tests/test_store_large_batches.py tests/test_store_dashboard_mcp.py tests/test_store_migrations.py`: passed.
- `.venv/bin/python -m pytest tests/test_store_large_batches.py tests/test_store_migrations.py tests/test_store_dashboard_mcp.py -q`: 27 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/store.py -a -s`: passed, target now A-rated.
- `.venv/bin/python -m pytest -q`: 450 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Store persistence behavior was verified through existing tests, but this branch intentionally avoids schema or SQL contract changes.
- Next likely target is `usage_drain_spans.py::_span_from_rows` or `diagnostic_snapshot_analysis.py::_scan_source_log`.
### `refactor/usage-drain-span-row`

Objective:
- Reduce `_span_from_rows` complexity while preserving `UsageDeltaSpan` field construction, proxy weighting, token totals, timing totals, and turn/model/effort counts.

Files touched:
- `src/codex_usage_tracker/usage_drain_spans.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split proxy total initialization, weighted token total initialization, row dimension counts, numeric total accumulation, proxy flag calculation, and proxy credit/token accumulation into helpers.
- Kept `build_usage_delta_spans` boundary behavior unchanged.
- Preserved five-hour/fallback usage-window metadata from the final row in the span.

Metrics:
- `_span_from_rows`: C(17) -> B(7).
- `usage_drain_spans.py` average complexity: A(4.16).
- Global C-or-worse blocks: 51 -> 50.
- `usage_drain_spans.py`: 414 lines, still under active file-size budgets.
- Remaining span hotspot: `build_usage_delta_spans` C(16).

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_spans.py tests/test_usage_drain_model.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_spans.py tests/test_usage_drain_model.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py::test_build_usage_delta_spans_includes_zero_change_calls_then_censors_resets tests/test_usage_drain_model.py::test_alternate_codex_limit_rows_count_as_work_but_not_boundaries tests/test_usage_drain_model.py::test_build_usage_delta_spans_prefers_five_hour_window_when_secondary -q`: 3 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_spans.py -a -s`: passed, target now B-rated.
- `.venv/bin/python -m pytest -q`: 450 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `build_usage_delta_spans` remains C(16) and is the next natural span follow-up.
- `diagnostic_snapshot_analysis.py::_scan_source_log` remains one of the highest C-rated blocks.
### `refactor/usage-drain-span-state-machine`

Objective:
- Reduce `build_usage_delta_spans` complexity while preserving chronological span grouping, reset/censor handling, five-hour window preference, and alternate-limit treatment.

Files touched:
- `src/codex_usage_tracker/usage_drain_spans.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `_SpanBuildState` to hold baseline percent, usage bucket, and pending rows.
- Split row sorting, initial stats, missing usage handling, window-source stats, baseline setting, bucket resets, usage-decrease resets, and positive-span closure into helpers.
- Kept `_span_from_rows` as the single `UsageDeltaSpan` construction point.

Metrics:
- `build_usage_delta_spans`: C(16) -> B(10).
- `usage_drain_spans.py` average complexity improved while staying within budget.
- Global C-or-worse blocks: 50 -> 49.
- `usage_drain_spans.py`: 495 lines, still under active file-size budgets.

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_spans.py tests/test_usage_drain_model.py`: passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_spans.py tests/test_usage_drain_model.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py::test_build_usage_delta_spans_includes_zero_change_calls_then_censors_resets tests/test_usage_drain_model.py::test_alternate_codex_limit_rows_count_as_work_but_not_boundaries tests/test_usage_drain_model.py::test_build_usage_delta_spans_prefers_five_hour_window_when_secondary -q`: 3 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_spans.py -a -s`: passed, target now B-rated.
- `.venv/bin/python -m pytest -q`: 450 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `diagnostic_snapshot_analysis.py::_scan_source_log` is now the largest remaining C-rated block.
- `usage_drain_state_buckets.py` has two C(16) diagnostic helpers that are likely low-risk report-formatting splits.

### `refactor/diagnostic-source-log-scan`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `diagnostic_snapshot_analysis.py::_scan_source_log` complexity while preserving aggregate-only diagnostic snapshot behavior and source-log privacy guarantees.
- Keep the active file-size ratchet intact after splitting the scanner.

Files touched:
- `src/codex_usage_tracker/diagnostic_snapshot_analysis.py`
- `src/codex_usage_tracker/diagnostic_snapshot_source_scan.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added `_SourceLogScanState` so source-log scan state is explicit instead of carried through parallel local dict/list variables.
- Split line filtering, JSON envelope parsing, event dispatch, modification recording, and response-item dispatch out of `_scan_source_log`.
- Moved low-level function-call, command, read, modification, output-count, and read-productivity recorders into `diagnostic_snapshot_source_scan.py`.
- Preserved existing aggregate counters and safe path labels; no raw prompts, command output text, patch text, or source-log paths are added to persisted snapshot payloads.

Metrics:
- `_scan_source_log`: C(17) -> A(3).
- `diagnostic_snapshot_analysis.py`: 590 -> 441 lines.
- New `diagnostic_snapshot_source_scan.py`: 252 lines.
- Global C-or-worse blocks: 49 -> 48.
- Largest remaining hotspot after this branch: `usage_drain_state_buckets.py::transition_risk_detail_diagnostics` C(16).

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/diagnostic_snapshot_analysis.py src/codex_usage_tracker/diagnostic_snapshot_source_scan.py tests/test_diagnostic_snapshots.py`: passed.
- `.venv/bin/python -m pytest tests/test_diagnostic_snapshots.py tests/test_dashboard_diagnostics_snapshots.py tests/test_server_diagnostic_snapshots.py -q`: 28 passed.
- `.venv/bin/python -m pytest -q`: 450 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `diagnostic_snapshot_source_scan.py::record_function_call` is still C(11), but below the current C(15)+ hotspot threshold.
- Next best small branch is one of the C(16) report-diagnostic helpers in `usage_drain_state_buckets.py` or `usage_drain_boundary_summary.py`.

### `refactor/usage-drain-state-bucket-diagnostics`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce the two C(16) state-bucket diagnostic summary helpers without changing walk-forward or transition-risk JSON payloads.
- Add direct characterization tests for the public summary helpers before refactoring the shared aggregation behavior.

Files touched:
- `src/codex_usage_tracker/usage_drain_state_buckets.py`
- `tests/test_usage_drain_state_buckets.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added direct tests for `state_bucket_model_diagnostics` and `transition_risk_detail_diagnostics` covering matched-state shares, fallback share, mean support, missing signatures, and top-signature ordering.
- Replaced duplicate detail extraction, matched-state filtering, support averaging, and top-signature construction with focused helpers.
- Kept public function names and payload keys unchanged.

Metrics:
- `state_bucket_model_diagnostics`: C(16) -> A(2).
- `transition_risk_detail_diagnostics`: C(16) -> A(2).
- `usage_drain_state_buckets.py` average complexity: A(3.33).
- Global C-or-worse blocks: 48 -> 46.
- Largest remaining hotspot after this branch: `usage_drain_boundary_summary.py::_boundary_risk_detail_diagnostics` C(16).

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_state_buckets.py -q`: 2 passed before refactor.
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_state_buckets.py tests/test_usage_drain_state_buckets.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_state_buckets.py tests/test_usage_drain_model.py tests/test_usage_drain_boundary_delta.py -q`: 18 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_state_buckets.py tests/test_usage_drain_state_buckets.py`: passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_state_buckets.py -a -s`: passed, targets now A-rated.
- `.venv/bin/python -m pytest -q`: 452 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `usage_drain_boundary_summary.py::_boundary_risk_detail_diagnostics` and `dashboard.py::dashboard_payload` are the next C(16) hotspots.
- The new helpers return a `fallback_share` field that transition-risk diagnostics intentionally omit from their public payload.

### `refactor/boundary-risk-detail-diagnostics`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `_boundary_risk_detail_diagnostics` without changing the boundary risk diagnostics payload consumed by usage-drain reports.
- Add a focused characterization test before extracting the duplicated matched-boundary summary logic.

Files touched:
- `src/codex_usage_tracker/usage_drain_boundary_summary.py`
- `tests/test_usage_drain_boundary_summary.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added direct characterization coverage for matched boundary-state share, mean support, missing signatures, and top-signature ordering.
- Extracted boundary-risk detail lookup, matched-boundary filtering, support averaging, top-signature construction, and signature labeling helpers.
- Preserved `_boundary_risk_detail_diagnostics` output keys and omission of fallback-share from this payload.

Metrics:
- `_boundary_risk_detail_diagnostics`: C(16) -> A(2).
- `usage_drain_boundary_summary.py` average complexity: A(4.63).
- Global C-or-worse blocks: 46 -> 45.
- Largest remaining hotspot after this branch: `dashboard.py::dashboard_payload` C(16).

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_boundary_summary.py -q`: 1 passed before refactor.
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_boundary_summary.py tests/test_usage_drain_boundary_summary.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_boundary_summary.py tests/test_usage_drain_model.py tests/test_usage_drain_boundary_delta.py -q`: 17 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_boundary_summary.py tests/test_usage_drain_boundary_summary.py`: passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_boundary_summary.py -a -s`: passed, target now A-rated.
- `.venv/bin/python -m pytest -q`: 453 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `dashboard.py::dashboard_payload` is now the only C(16) block.
- `usage_drain_boundary_delta_summary.py::_boundary_delta_top_error_groups`, `usage_drain_allowance_fits.py::allowance_online_capacity_credit_to_delta_fit`, `threads.py::_resolve_thread_attachment`, `diagnostic_reports.py::_action_hint`, and `call_origin.py::event_flags_from_envelope` remain C(15).

### `refactor/dashboard-payload-orchestration`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `dashboard_payload` orchestration complexity without changing the static dashboard/API payload contract.
- Keep dashboard row loading, annotation, pagination, parser diagnostics, and cache-key behavior stable.

Files touched:
- `src/codex_usage_tracker/dashboard.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Extracted dashboard source row loading into `_dashboard_source_rows`.
- Extracted pricing/allowance/recommendation/project/privacy row annotation into `_annotated_dashboard_rows`.
- Extracted dashboard availability counts into `_dashboard_available_row_counts`.
- Extracted limit/offset/next-page fields into `_dashboard_pagination_payload`.
- Extracted parser metadata filtering into `_parser_diagnostics_payload`.
- Preserved returned payload keys and dashboard-focused tests.

Metrics:
- `dashboard_payload`: C(16) -> B(7).
- `dashboard.py` average complexity: A(4.63).
- Global C-or-worse blocks: 45 -> 44.
- Highest remaining complexity is now C(15).

Checks:
- `.venv/bin/python -m py_compile src/codex_usage_tracker/dashboard.py tests/test_dashboard_payload.py tests/test_dashboard_server.py`: passed.
- `.venv/bin/python -m pytest tests/test_dashboard_payload.py tests/test_dashboard_server.py tests/test_dashboard_live.py tests/test_server_dashboard_shell.py -q`: 24 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/dashboard.py tests/test_dashboard_payload.py tests/test_dashboard_server.py tests/test_dashboard_live.py tests/test_server_dashboard_shell.py`: passed.
- `.venv/bin/radon cc src/codex_usage_tracker/dashboard.py -a -s`: passed, target now B-rated.
- `.venv/bin/python -m pytest -q`: 453 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Next C(15) targets are `usage_drain_boundary_delta_summary.py::_boundary_delta_top_error_groups`, `usage_drain_allowance_fits.py::allowance_online_capacity_credit_to_delta_fit`, `threads.py::_resolve_thread_attachment`, `diagnostic_reports.py::_action_hint`, and `call_origin.py::event_flags_from_envelope`.
- `dashboard.py::_pricing_snapshot_warning` remains C(11) and can be addressed later after higher-ranked blocks.

### `refactor/boundary-delta-summary-groups`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `_boundary_delta_top_error_groups` complexity without changing residual-diagnostic group tables.
- Add direct characterization tests for concentration math, RMSE, sort order, and `boundary_state` key mapping before refactoring.

Files touched:
- `src/codex_usage_tracker/usage_drain_boundary_delta_summary.py`
- `tests/test_usage_drain_boundary_delta_summary.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added focused tests for top error-group summaries and boundary/same-label grouping.
- Extracted error grouping, group-key resolution, row construction, absolute-error sums, RMSE calculation, and sort-key construction.
- Left `_boundary_delta_prediction_scope` for a later branch because it is a separate C(14) scope aggregation concern.

Metrics:
- `_boundary_delta_top_error_groups`: C(15) -> A(2).
- `usage_drain_boundary_delta_summary.py` average complexity: B(5.15).
- Global C-or-worse blocks: 44 -> 43.
- Highest remaining complexity remains C(15).

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_boundary_delta_summary.py -q`: 2 passed before refactor.
- `.venv/bin/python -m py_compile src/codex_usage_tracker/usage_drain_boundary_delta_summary.py tests/test_usage_drain_boundary_delta_summary.py`: passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_boundary_delta_summary.py tests/test_usage_drain_boundary_delta.py tests/test_usage_drain_model.py -q`: 18 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_boundary_delta_summary.py tests/test_usage_drain_boundary_delta_summary.py`: passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_boundary_delta_summary.py -a -s`: passed, target now A-rated.
- `.venv/bin/python -m pytest -q`: 455 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Remaining C(15) targets: `usage_drain_allowance_fits.py::allowance_online_capacity_credit_to_delta_fit`, `threads.py::_resolve_thread_attachment`, `diagnostic_reports.py::_action_hint`, and `call_origin.py::event_flags_from_envelope`.
- `usage_drain_boundary_delta_summary.py::_boundary_delta_prediction_scope` is still C(14).

### `refactor/call-origin-event-flags`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `event_flags_from_envelope` complexity while preserving metadata-only call-origin classification.
- Keep existing privacy-oriented tests and add direct coverage for event-message user, MCP tool-result, and agent-activity shapes.

Files touched:
- `src/codex_usage_tracker/call_origin.py`
- `tests/test_call_origin.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added direct characterization tests for event-message `user_message`, `mcp_tool_call_end`, and `agent_message` shapes.
- Extracted payload mapping and four named predicate helpers for user-message, compaction, tool-result, and Codex-activity event detection.
- Preserved existing classification/fallback tests and raw-content privacy behavior.

Metrics:
- `event_flags_from_envelope`: C(15) -> A(2).
- `call_origin.py` average complexity: A(4.25).
- Global C-or-worse blocks: 43 -> 42.
- Remaining C(15) targets: allowance fits, thread attachment resolution, and diagnostic action hints.

Checks:
- `.venv/bin/python -m pytest tests/test_call_origin.py -q`: 3 added tests passed before refactor.
- `.venv/bin/python -m pytest tests/test_call_origin.py tests/test_parser.py::test_parser_persists_call_origin_from_metadata_segments tests/test_dashboard_payload.py::test_dashboard_payload_uses_persisted_call_origin_without_source_scan tests/test_store_dashboard_mcp.py::test_append_cursor_preserves_pending_call_origin_between_refreshes -q`: 9 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/call_origin.py tests/test_call_origin.py`: passed.
- `.venv/bin/radon cc src/codex_usage_tracker/call_origin.py -a -s`: passed, target now A-rated.
- `.venv/bin/python -m pytest -q`: 458 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Next C(15) targets are `usage_drain_allowance_fits.py::allowance_online_capacity_credit_to_delta_fit`, `threads.py::_resolve_thread_attachment`, and `diagnostic_reports.py::_action_hint`.

### `refactor/diagnostic-action-hints`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce diagnostic action-hint complexity without changing the diagnostic report payload text.
- Keep `diagnostic_reports.py` under its file-length ratchet baseline.

Files touched:
- `src/codex_usage_tracker/diagnostic_action_hints.py`
- `src/codex_usage_tracker/diagnostic_reports.py`
- `tests/test_diagnostic_reports.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added focused action-hint characterization tests for compaction, unknown command-family, command-family fallback, specific fact names, and generic fallback.
- Moved action-hint constants and lookup logic into `diagnostic_action_hints.py`.
- Kept `diagnostic_reports._action_hint` as an imported compatibility name for existing report code and tests.
- Reworked `_action_hint` into table lookup plus small compaction/command-family helpers.

Metrics:
- `_action_hint`: C(15) -> A(5), now implemented as `diagnostic_action_hints.action_hint`.
- `diagnostic_reports.py`: 507 baseline physical lines -> 478 physical lines after split.
- `diagnostic_action_hints.py`: 80 lines.
- Global C-or-worse blocks: 42 -> 41.
- Remaining C(15) targets: allowance fits and thread attachment resolution.

Checks:
- `.venv/bin/python -m pytest tests/test_diagnostic_reports.py -q`: 3 passed before refactor.
- `.venv/bin/python -m py_compile src/codex_usage_tracker/diagnostic_reports.py src/codex_usage_tracker/diagnostic_action_hints.py tests/test_diagnostic_reports.py`: passed.
- `.venv/bin/python -m pytest tests/test_diagnostic_reports.py tests/test_cli_parser_diagnostics.py tests/test_server_diagnostic_facts.py -q`: 11 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/diagnostic_reports.py src/codex_usage_tracker/diagnostic_action_hints.py tests/test_diagnostic_reports.py`: passed.
- `.venv/bin/radon cc src/codex_usage_tracker/diagnostic_reports.py src/codex_usage_tracker/diagnostic_action_hints.py -a -s`: passed, target now A-rated.
- `.venv/bin/python -m pytest -q`: 461 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with expected structure-cohesion and change-budget warnings.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Remaining top C(15) targets are `usage_drain_allowance_fits.py::allowance_online_capacity_credit_to_delta_fit` and `threads.py::_resolve_thread_attachment`.
- `diagnostic_reports.py::_filter_fact_group` remains B(6), below the current hotspot threshold.
### `refactor/allowance-online-capacity-fit`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `allowance_online_capacity_credit_to_delta_fit` complexity while preserving the existing online-capacity model contract and known-breakpoint diagnostics.
- Keep the public import surface stable for existing allowance breakpoint callers.

Files touched:
- `src/codex_usage_tracker/usage_drain_allowance_fits.py`
- `src/codex_usage_tracker/usage_drain_allowance_online.py`
- `tests/test_usage_drain_allowance_fits.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added a characterization test for the online-capacity fit model set, prediction row counts, skipped initial rows, and known-breakpoint diagnostics.
- Extracted online-capacity model descriptions, prediction allocation, estimate construction, model record formatting, and residual diagnostics behind small helpers.
- Split the online-capacity fit into `usage_drain_allowance_online.py` and kept `usage_drain_allowance_fits.py` as the compatibility facade.

Metrics:
- `allowance_online_capacity_credit_to_delta_fit`: C(15) -> B(7).
- `usage_drain_allowance_fits.py`: 481 -> 281 physical lines.
- `usage_drain_allowance_online.py`: new focused module, 287 physical lines.
- Global C-or-worse blocks: 41 -> 40.
- No D/E/F complexity blocks remain.
- Remaining top C target: `threads.py::_resolve_thread_attachment` C(15).

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_allowance_fits.py tests/test_usage_drain_model.py -q`: 17 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_allowance_fits.py src/codex_usage_tracker/usage_drain_allowance_online.py -a -s`: target now B(7); new module top helper C(11).
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_allowance_fits.py src/codex_usage_tracker/usage_drain_allowance_online.py tests/test_usage_drain_allowance_fits.py`: passed.
- `.venv/bin/python -m pytest -q`: 462 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning only.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `usage_drain_allowance_online.py::_allowance_online_capacity_error_diagnostics` remains C(11), but the branch objective was the larger C(15) public fit function.
- Next branch should target `threads.py::_resolve_thread_attachment` C(15) with attachment-resolution characterization tests.

### `refactor/thread-attachment-resolution`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `_resolve_thread_attachment` complexity while preserving dashboard thread attachment metadata.
- Characterize direct threads, explicit parent threads, parent-session matching, unmatched parent sessions, auto-review fallback, and generic session/subagent fallback behavior.

Files touched:
- `src/codex_usage_tracker/threads.py`
- `tests/test_threads.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added focused tests for every resolver branch not previously covered.
- Split direct, parent, auto-review, and session fallback attachment decisions into named helpers.
- Preserved the public `annotate_thread_attachments` behavior and dashboard row keys.

Metrics:
- `_resolve_thread_attachment`: C(15) -> A(4).
- `threads.py`: 183 -> 210 physical lines.
- `threads.py` average complexity: A(3.50).
- Global C-or-worse blocks: 40 -> 39.
- No D/E/F complexity blocks remain.
- Remaining top C targets: `usage_drain_regression.py::fit_linear_coefficients`, `usage_drain_boundary_delta_summary.py::_boundary_delta_prediction_scope`, and `store_dashboard_queries.py::observed_usage_reconciliation` at C(14).

Checks:
- `.venv/bin/python -m pytest tests/test_threads.py -q`: 8 passed.
- `.venv/bin/python -m pytest tests/test_threads.py tests/test_dashboard_payload.py tests/test_server_threads.py tests/test_dashboard_data.py -q`: 25 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/threads.py -a -s`: target now A(4).
- `.venv/bin/python -m pytest -q`: 468 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning only.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `_build_parent_candidates` remains B(10), below the current C hotspot threshold.
- Next branch should target one of the C(14) hotspots, preferably `usage_drain_regression.py::fit_linear_coefficients` if we want to keep reducing modeling core risk.

### `refactor/usage-drain-regression-fit-linear`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `fit_linear_coefficients` complexity while preserving existing ordinary least-squares and tiny ridge fallback behavior.
- Add focused regression-helper characterization tests because this module previously relied mostly on higher-level usage-drain tests.

Files touched:
- `src/codex_usage_tracker/usage_drain_regression.py`
- `tests/test_usage_drain_regression.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added characterization tests for intercept fit, no-intercept fit, singular-design ridge fallback, and unsolved zero-coefficient fallback.
- Extracted normal-equation construction, row accumulation, and fallback regularization into named helpers.
- Preserved `fit_linear_coefficients` and `predict_linear` public call behavior.

Metrics:
- `fit_linear_coefficients`: C(14) -> A(5).
- `usage_drain_regression.py`: 344 -> 367 physical lines.
- `usage_drain_regression.py` average complexity: B(5.91).
- Global C-or-worse blocks: 39 -> 38.
- No D/E/F complexity blocks remain.
- Remaining top C targets: `usage_drain_boundary_delta_summary.py::_boundary_delta_prediction_scope` and `store_dashboard_queries.py::observed_usage_reconciliation` at C(14).

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_regression.py -q`: 4 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_regression.py tests/test_usage_drain_model.py tests/test_usage_drain_allowance_fits.py -q`: 21 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_regression.py -a -s`: target now A(5).
- `.venv/bin/python -m pytest -q`: 472 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning after staging.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `prepare_design` remains C(12) in the regression module, below the current top hotspot threshold.
- Next branch should target either `usage_drain_boundary_delta_summary.py::_boundary_delta_prediction_scope` or `store_dashboard_queries.py::observed_usage_reconciliation`.

### `refactor/boundary-delta-prediction-scope`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `_boundary_delta_prediction_scope` complexity while preserving scope filtering, model metrics, prediction-detail diagnostics, risk-gate diagnostics, and residual diagnostics.
- Add direct characterization for the scope helper before refactoring.

Files touched:
- `src/codex_usage_tracker/usage_drain_boundary_delta_summary.py`
- `tests/test_usage_drain_boundary_delta_summary.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added a compact boundary-delta scope test covering row filtering, actual value distribution, model metric keys, risk-gate diagnostics, and residual diagnostics.
- Split scope filtering, actual extraction, model metric generation, prediction-detail diagnostics, risk-gate diagnostics, and residual diagnostics into named helpers.
- Preserved the `boundary_walk_forward_delta_prediction_summary` payload structure.

Metrics:
- `_boundary_delta_prediction_scope`: C(14) -> A(1).
- `usage_drain_boundary_delta_summary.py`: 373 -> 421 physical lines.
- `usage_drain_boundary_delta_summary.py` average complexity: A(3.84).
- Global C-or-worse blocks: 38 -> 37.
- No D/E/F complexity blocks remain.
- Remaining top C target: `store_dashboard_queries.py::observed_usage_reconciliation` C(14).

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_boundary_delta_summary.py -q`: 3 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_boundary_delta_summary.py tests/test_usage_drain_boundary_delta.py tests/test_usage_drain_model.py -q`: 19 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_boundary_delta_summary.py -a -s`: target now A(1).
- `.venv/bin/python -m pytest -q`: 473 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning only.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `_boundary_delta_residual_diagnostics` remains C(12), below the current top hotspot threshold.
- Next branch should target `store_dashboard_queries.py::observed_usage_reconciliation` C(14).

### `refactor/store-dashboard-usage-reconciliation`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `observed_usage_reconciliation` complexity while preserving live-usage reconciliation behavior for alternate Codex limit rows.
- Add direct SQLite-backed characterization tests for recommendation, interrupted streak, and selected-latest-alternate cases.

Files touched:
- `src/codex_usage_tracker/store_dashboard_queries.py`
- `tests/test_store_dashboard_queries.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Added focused in-memory SQLite tests for observed usage reconciliation decisions.
- Split recent observed row loading, alternate-limit streak counting, recommendation decision, and payload formatting into named helpers.
- Preserved `query_latest_observed_usage` reconciliation payload shape.

Metrics:
- `observed_usage_reconciliation`: C(14) -> A(2).
- `store_dashboard_queries.py`: 401 -> 446 physical lines.
- `store_dashboard_queries.py` average complexity: A(4.54).
- Global C-or-worse blocks: 37 -> 36.
- No D/E/F complexity blocks remain.
- Remaining top C targets are now C(13), led by `usage_drain_walk_forward.py::walk_forward_prediction_rows`.

Checks:
- `.venv/bin/python -m pytest tests/test_store_dashboard_queries.py -q`: 3 passed.
- `.venv/bin/python -m pytest tests/test_store_dashboard_queries.py tests/test_dashboard_payload.py tests/test_dashboard_server.py tests/test_server_status.py -q`: 24 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/store_dashboard_queries.py -a -s`: target now A(2).
- `.venv/bin/python -m pytest -q`: 476 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning after staging.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `_observed_usage_reconciliation_payload` remains B(6), below the current C hotspot threshold.
- Next branch should target one of the C(13) hotspots, starting with `usage_drain_walk_forward.py::walk_forward_prediction_rows`.

### `refactor/usage-drain-walk-forward-rows`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `walk_forward_prediction_rows` complexity while preserving the public walk-forward row contract and transition prediction detail payloads.
- Add direct characterization coverage for row indexes, actual values, base predictions, metadata, prediction details, and transition-risk fields.

Files touched:
- `src/codex_usage_tracker/usage_drain_walk_forward.py`
- `src/codex_usage_tracker/usage_drain_walk_forward_rows.py`
- `tests/test_usage_drain_walk_forward.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Moved walk-forward row construction into `usage_drain_walk_forward_rows.py`.
- Kept `usage_drain_walk_forward.py` as the summary/scope module with a compatibility facade for `walk_forward_prediction_rows`.
- Split row construction into helpers for history metrics, state construction, base predictions, state-bucket prediction attachment, transition prediction values, and transition prediction details.

Metrics:
- `walk_forward_prediction_rows`: C(13) -> A(1) facade in `usage_drain_walk_forward.py`; implementation A(3) in `usage_drain_walk_forward_rows.py`.
- `usage_drain_walk_forward.py`: 579 -> 180 physical lines after moving the row builder.
- `usage_drain_walk_forward_rows.py`: 408 physical lines, under the 450 source-line agent-maintainer budget.
- Global C-or-worse blocks: 36 -> 35.
- No D/E/F complexity blocks remain.
- Remaining top C targets are C(13), led by `usage_drain_walk_forward.py::_walk_forward_scope_metrics`.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_walk_forward.py -q`: 1 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_walk_forward.py tests/test_usage_drain_model.py tests/test_usage_drain_regression.py tests/test_usage_drain_allowance_fits.py -q`: 22 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_walk_forward.py src/codex_usage_tracker/usage_drain_walk_forward_rows.py -a -s`: row target now A-grade; `_walk_forward_scope_metrics` remains C(13).
- `.venv/bin/python -m pytest -q`: 477 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed after staging, with only existing structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `_walk_forward_scope_metrics` remains C(13) in `usage_drain_walk_forward.py`.
- Next branch should target `_walk_forward_scope_metrics` while keeping the walk-forward summary payload stable.

### `refactor/usage-drain-walk-forward-scope`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `_walk_forward_scope_metrics` complexity while preserving walk-forward summary scope payloads.
- Add characterization coverage for scope names, actual distributions, model metrics, error diagnostics, transition gate diagnostics, and state-bucket diagnostics.

Files touched:
- `src/codex_usage_tracker/usage_drain_walk_forward.py`
- `tests/test_usage_drain_walk_forward.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split scope row filtering, actual extraction, model-name selection, model metrics, error diagnostics, transition gate diagnostics, and state-bucket diagnostics into named helpers.
- Lifted scope diagnostic model groups into module constants.
- Preserved `walk_forward_prediction_summary` scope output shape.

Metrics:
- `_walk_forward_scope_metrics`: C(13) -> A(1).
- `usage_drain_walk_forward.py` average complexity: A(2.08).
- `usage_drain_walk_forward.py`: 180 -> 236 physical lines.
- Global C-or-worse blocks: 35 -> 34.
- No D/E/F complexity blocks remain.
- Remaining top C targets are C(13), led by `usage_drain_state_diagnostics.py::state_ambiguous_group_record`, `usage_drain_model.py::_one_percent_capacity_modeling`, and `usage_drain_transition_metrics.py::binary_risk_metrics`.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_walk_forward.py -q`: 2 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_walk_forward.py tests/test_usage_drain_model.py tests/test_usage_drain_regression.py tests/test_usage_drain_allowance_fits.py -q`: 23 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_walk_forward.py -a -s`: target now A(1).
- `.venv/bin/python -m pytest -q`: 478 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning only.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Next branch should target a remaining C(13) hotspot. Prefer `usage_drain_state_diagnostics.py::state_ambiguous_group_record` because it is isolated and testable.

### `refactor/state-ambiguous-group-record`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `state_ambiguous_group_record` complexity while preserving state ambiguity summary records.
- Add synthetic characterization coverage for state labels, actual value counts, shares, mode error metrics, and date bounds.

Files touched:
- `src/codex_usage_tracker/usage_drain_state_diagnostics.py`
- `tests/test_usage_drain_state_diagnostics.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split ambiguous-state record construction into helpers for actual values, rounded counts, mode errors, row dates, signature state mapping, value rows, mode share, and mean error.
- Preserved the existing record keys and value ordering semantics.

Metrics:
- `state_ambiguous_group_record`: C(13) -> A(3).
- `usage_drain_state_diagnostics.py` average complexity: A(3.31).
- `usage_drain_state_diagnostics.py`: 203 -> 242 physical lines.
- Global C-or-worse blocks remain 33 because `state_signature_ambiguity` remains C(12) in the same module.
- No D/E/F complexity blocks remain.
- Remaining top C targets are C(13), led by `usage_drain_model.py::_one_percent_capacity_modeling`, `usage_drain_transition_metrics.py::binary_risk_metrics`, and `formatting.py::format_calls`.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_state_diagnostics.py -q`: 1 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_state_diagnostics.py tests/test_usage_drain_walk_forward.py tests/test_usage_drain_model.py -q`: 18 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_state_diagnostics.py -a -s`: target now A(3).
- `.venv/bin/python -m pytest -q`: 479 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed after staging, with only existing structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `state_signature_ambiguity` remains C(12) and is a natural follow-up if continuing in this module.
- The top C(13) targets are now outside this module.

### `refactor/binary-risk-metrics`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `binary_risk_metrics` complexity while preserving transition-risk metric output.
- Add direct characterization coverage for valid, empty, and length-mismatched inputs.

Files touched:
- `src/codex_usage_tracker/usage_drain_transition_metrics.py`
- `tests/test_usage_drain_transition_metrics.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split binary risk metrics into helpers for empty payloads, score clipping, positive/negative score grouping, top-risk rows, top positive counts, Brier score, and mean score.
- Preserved metric keys and rounded values for Brier, AUC, average precision, top-decile precision/recall/rate, and positive/negative mean scores.

Metrics:
- `binary_risk_metrics`: C(13) -> A(4).
- `usage_drain_transition_metrics.py` average complexity: A(3.87).
- `usage_drain_transition_metrics.py`: 229 -> 259 physical lines.
- Global C-or-worse blocks: 33 -> 32.
- No D/E/F complexity blocks remain.
- Remaining top C targets are C(13), led by `usage_drain_model.py::_one_percent_capacity_modeling`, `formatting.py::format_calls`, and `context.py::load_call_context`.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_transition_metrics.py -q`: 2 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_transition_metrics.py tests/test_usage_drain_model.py tests/test_usage_drain_boundary_summary.py tests/test_usage_drain_walk_forward.py -q`: 20 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_transition_metrics.py -a -s`: target now A(4).
- `.venv/bin/python -m pytest -q`: 481 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed after staging, with only existing structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Remaining C(13) hotspots include `_one_percent_capacity_modeling`, `format_calls`, `load_call_context`, `validate_json_payload_contract`, `transition_delta_gate_diagnostics`, and `regime_streak_summary`.
- Prefer the next branch by isolating one of those with existing or newly added characterization tests.

### `refactor/format-calls-output`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `format_calls` complexity while preserving human-readable call output.
- Add characterization coverage for thread fallback labels, cost suffixes, pricing-estimated marker, efficiency flags, action suffixes, and empty defaults.

Files touched:
- `src/codex_usage_tracker/formatting.py`
- `tests/test_formatting.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split formatted call line construction into helpers for call rows, thread labels, combined suffixes, flag suffixes, and action suffixes.
- Preserved existing output text and fallback behavior.

Metrics:
- `format_calls`: C(13) -> A(3).
- `formatting.py` average complexity: A(3.95).
- `formatting.py`: 228 -> 272 physical lines.
- Global C-or-worse blocks: 32 -> 31.
- No D/E/F complexity blocks remain.
- Remaining top C targets are C(13), led by `usage_drain_model.py::_one_percent_capacity_modeling`, `context.py::load_call_context`, `json_contracts.py::validate_json_payload_contract`, `usage_drain_transition_gates.py::transition_delta_gate_diagnostics`, and `usage_drain_regime_segments.py::regime_streak_summary`.

Checks:
- `.venv/bin/python -m pytest tests/test_formatting.py -q`: 3 passed.
- `.venv/bin/python -m pytest tests/test_formatting.py tests/test_recommendations.py tests/test_diagnostic_reports.py tests/test_usage_drain_reports.py -q`: 14 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/formatting.py -a -s`: target now A(3).
- `.venv/bin/python -m pytest -q`: 482 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed with existing structure-cohesion warning only.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Remaining C(13) hotspots are now concentrated in usage-drain capacity modeling, context loading, JSON contract validation, transition gate diagnostics, and regime streak summaries.
- Pick the next branch based on which of those has the narrowest characterization surface.

### `refactor/transition-delta-gate-diagnostics`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `transition_delta_gate_diagnostics` complexity while preserving transition gate diagnostic payloads.
- Add direct characterization coverage for empty rows and mixed source/risk/threshold summaries.

Files touched:
- `src/codex_usage_tracker/usage_drain_transition_gates.py`
- `tests/test_usage_drain_transition_gates.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split transition gate diagnostics into helpers for detail extraction, empty payloads, source/risk/threshold accumulation, override share, nullable means, and source rows.
- Preserved source sorting, missing-detail behavior, mean risk/threshold behavior, and override-source suffix detection.

Metrics:
- `transition_delta_gate_diagnostics`: C(13) -> A(2).
- `usage_drain_transition_gates.py` average complexity: A(2.8).
- `usage_drain_transition_gates.py`: 147 -> 184 physical lines.
- Global C-or-worse blocks: 31 -> 30.
- No D/E/F complexity blocks remain.
- Remaining top C targets are C(13), led by `usage_drain_model.py::_one_percent_capacity_modeling`, `context.py::load_call_context`, `json_contracts.py::validate_json_payload_contract`, and `usage_drain_regime_segments.py::regime_streak_summary`.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_transition_gates.py -q`: 2 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_transition_gates.py tests/test_usage_drain_transition_metrics.py tests/test_usage_drain_walk_forward.py tests/test_usage_drain_model.py -q`: 21 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_transition_gates.py -a -s`: target now A(2).
- `.venv/bin/python -m pytest -q`: 484 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed after staging, with only existing structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Remaining C(13) targets now include `_one_percent_capacity_modeling`, `load_call_context`, `validate_json_payload_contract`, and `regime_streak_summary`.
- Choose the next branch based on strongest existing coverage or smallest synthetic fixture cost.

### `refactor/regime-streak-summary`

Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `regime_streak_summary` complexity while preserving one-percent run and long-run break summaries.
- Add direct characterization coverage for run counts, latest/current run behavior, top run ordering, and break records.

Files touched:
- `src/codex_usage_tracker/usage_drain_regime_segments.py`
- `tests/test_usage_drain_regime_segments.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split regime streak summary into helpers for one-percent run summary, long-run count, max run length, current run selection, top run ranking, and breaks after long runs.
- Preserved the existing top-run limit, long-run threshold, current streak behavior, and break ordering.

Metrics:
- `regime_streak_summary`: C(13) -> A(1).
- `usage_drain_regime_segments.py` average complexity: A(3.65).
- `usage_drain_regime_segments.py`: 324 -> 369 physical lines.
- Global C-or-worse blocks: 30 -> 29.
- No D/E/F complexity blocks remain.
- Remaining top C targets are C(13), led by `usage_drain_model.py::_one_percent_capacity_modeling`, `context.py::load_call_context`, and `json_contracts.py::validate_json_payload_contract`.

Checks:
- `.venv/bin/python -m pytest tests/test_usage_drain_regime_segments.py -q`: 1 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_regime_segments.py tests/test_usage_drain_model.py tests/test_usage_drain_reports.py -q`: 21 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_regime_segments.py -a -s`: target now A(1).
- `.venv/bin/python -m pytest -q`: 485 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed after staging, with only existing structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- `_piecewise_adaptation_by_position` remains C(12) in this module.
- The remaining C(13) targets are broader: `_one_percent_capacity_modeling`, `load_call_context`, and `validate_json_payload_contract`.

### `refactor/json-payload-contract-validator`
Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `validate_json_payload_contract` complexity while preserving public CLI/MCP JSON contract validation errors.
- Add nested optional-field characterization coverage so `int | null` error wording stays stable.

Files touched:
- `src/codex_usage_tracker/json_contracts.py`
- `src/codex_usage_tracker/json_contract_validation.py`
- `tests/test_json_contracts.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Moved validation implementation helpers into `json_contract_validation.py`.
- Kept `json_contracts.py` as the public facade with existing schema registry ownership.
- Preserved non-object payload, missing schema, unknown schema, required field, nested required field, and optional `null` wording semantics.

Metrics:
- `json_contracts.py::validate_json_payload_contract`: C(13) -> A(1).
- `json_contract_validation.py` maximum complexity: B(9), average A(3.67).
- `json_contracts.py`: 574 -> 515 physical lines.
- New `json_contract_validation.py`: 112 physical lines.
- Global C-or-worse blocks: 29 -> 27.
- No D/E/F complexity blocks remain.
- Remaining C(13) targets: `usage_drain_model.py::_one_percent_capacity_modeling`, `context.py::load_call_context`.

Checks so far:
- `.venv/bin/python -m pytest tests/test_json_contracts.py tests/test_cli_lifecycle.py tests/test_cli_release.py -q`: 28 passed.
- `.venv/bin/radon cc src/codex_usage_tracker/json_contracts.py src/codex_usage_tracker/json_contract_validation.py -a -s`: target now A(1), extracted helper max B(9).
- `.venv/bin/python -m ruff check src/codex_usage_tracker/json_contracts.py src/codex_usage_tracker/json_contract_validation.py tests/test_json_contracts.py`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/python -m pytest -q`: 485 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed after staging, only existing structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Next complexity targets are broader and should stay separate slices.

### `refactor/one-percent-capacity-modeling`
Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `_one_percent_capacity_modeling` complexity while preserving the one-percent capacity report schema and model-selection behavior.
- Add explicit characterization coverage for the low-data report shape before refactoring.

Files touched:
- `src/codex_usage_tracker/usage_drain_model.py`
- `tests/test_usage_drain_model.py`
- `tests/test_usage_drain_one_percent_capacity.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split one-percent capacity report assembly into focused helpers for low-data output, row preparation, model fitting, model annotation, causal-model filtering, and notes.
- Kept helpers in `usage_drain_model.py` to avoid a circular dependency around `UsageDeltaSpan` and existing private fitting helpers.
- Moved the one-percent capacity characterization tests into a focused file so the already-large model test file gets smaller rather than larger.
- Preserved the existing report fields: `target`, `target_description`, `span_count`, `target_distribution`, `splits`, best model names, token component regression, feature-family attribution, models, and notes.

Metrics:
- `_one_percent_capacity_modeling`: C(13) -> A(5).
- `usage_drain_model.py` maximum complexity: B(8).
- `usage_drain_model.py`: 446 -> 497 physical lines.
- `tests/test_usage_drain_model.py`: 918 -> 823 physical lines.
- New `tests/test_usage_drain_one_percent_capacity.py`: 137 physical lines.
- Global C-or-worse blocks: 27 -> 26.
- No D/E/F complexity blocks remain.
- Remaining C(13) target: `context.py::load_call_context`.

Checks so far:
- `.venv/bin/python -m pytest tests/test_usage_drain_model.py tests/test_usage_drain_one_percent_capacity.py -q`: 16 passed.
- `.venv/bin/python -m pytest tests/test_usage_drain_one_percent_capacity.py tests/test_usage_drain_model.py tests/test_usage_drain_reports.py tests/test_usage_drain_allowance_fits.py tests/test_usage_drain_regression.py -q`: 27 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/usage_drain_model.py tests/test_usage_drain_model.py`: passed.
- `.venv/bin/radon cc src/codex_usage_tracker/usage_drain_model.py -a -s`: target now A(5), module max B(8).
- `.venv/bin/python -m pytest -q`: 486 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed after staging, only existing structure-cohesion warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Next likely branch is `context.py::load_call_context`; treat it carefully because it touches raw-context privacy behavior.

### `refactor/context-load-call-context`
Status:
- Local branch only. Not pushed.
- Green checkpoint reached.

Objective:
- Reduce `load_call_context` complexity while preserving on-demand raw-context privacy behavior and the public context payload schema.
- Keep raw JSONL scanning internals behavior-preserving and avoid broad context-reader rewrites.

Files touched:
- `src/codex_usage_tracker/context.py`
- `src/codex_usage_tracker/context_loader.py`
- `docs/maintainability-roadmap.md`

Completed edits:
- Split record lookup, source-location validation, context bounds, payload assembly, record payload formatting, diagnostics attachment, and JSON-byte counting into `context_loader.py`.
- Kept raw JSONL scanning and entry collection in `context.py`.
- Preserved diagnostics timing fields, source metadata, visible-token estimates, serialized evidence, action timing, entries, omitted counts, and raw-context on-demand behavior.

Metrics:
- `context.py::load_call_context`: C(13) -> A(2).
- `context.py` maximum complexity: B(9).
- `context.py`: 525 -> 515 physical lines.
- New `context_loader.py`: 144 physical lines.
- Global C-or-worse blocks: 26 -> 25.
- No C(13) or D/E/F complexity blocks remain.
- Current top complexity targets are C(12), led by `usage_drain_summary_metrics.py::model_family_attribution`.

Checks so far:
- `.venv/bin/python -m pytest tests/test_context_evidence.py tests/test_context_scan.py tests/test_context_serialized.py tests/test_context_action_timing.py tests/test_context_token_estimates.py tests/test_context_values.py -q`: 20 passed.
- `.venv/bin/python -m ruff check src/codex_usage_tracker/context.py src/codex_usage_tracker/context_loader.py tests/test_context_evidence.py tests/test_context_scan.py tests/test_context_action_timing.py`: passed.
- `.venv/bin/python -m mypy`: passed.
- `.venv/bin/radon cc src/codex_usage_tracker/context.py src/codex_usage_tracker/context_loader.py -a -s`: target now A(2), modules max B(9).
- `.venv/bin/python -m pytest -q`: 486 passed.
- `.venv/bin/python -m compileall src`: passed.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/tach check`: passed.
- `.venv/bin/git-agent-ratchet max-file-lines --baseline .agent-maintainer/git-agent-ratchet-max-file-lines.json --dir src --max 600 --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-cross-module-private-import --baseline .agent-maintainer/git-agent-ratchet-private-imports.json --dir src --exclude __pycache__`: passed.
- `.venv/bin/git-agent-ratchet no-duplicate-helpers --baseline .agent-maintainer/git-agent-ratchet-duplicate-helpers.json --dir src --exclude __pycache__ --lang python`: passed.
- `.venv/bin/python -m agent_maintainer verify --profile fast`: passed after staging; existing structure-cohesion warning plus source-only change-budget warning.
- `.venv/bin/python scripts/check_release.py`: passed.
- `git diff --check`: passed.

Remaining risks / next handoff:
- Next branch can ratchet C(12) hotspots, starting with either `model_family_attribution` or `state_signature_ambiguity`.
