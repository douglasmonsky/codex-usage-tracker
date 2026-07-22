# MCP-First Pivot Execution Ledger

This ledger is the durable handoff for the
[MCP-first pivot](mcp-first-pivot.md). Update the applicable entry in the same
commit as each roadmap task.

## Entry Format

```markdown
## Task N - Name
- Status: planned | active | blocked | complete
- Branch:
- Commits:
- Focused verification:
- Full verification:
- Deviations from plan:
- Follow-up risks:
```

## Task 1 - Record the pivot baseline and freeze dashboard surface growth

- Status: complete
- Branch: `pivot/1-establish-program`
- Commits: `3488d7a` (`docs: add MCP-first pivot design and roadmap`);
  `9a0d6ce` (`docs: establish MCP-first pivot program`)
- Focused verification: `python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q`
- Full verification: `npx markdownlint-cli2 README.md "docs/**/*.md" ".agent-maintainer/change-plans/*.md"`; `git diff --check`
- Deviations from plan: Approved design and implementation roadmap were adopted
  in a preliminary documentation commit to isolate their 4,209-line reviewed
  content from the Task 1 baseline changes.
- Follow-up risks: The release sequence assumes the published baseline remains
  `0.21.0`; shift all planned minors together if that changes before execution.

## Task 2 - Make public product and storage statements internally consistent

- Status: complete
- Branch: `pivot/2-position-product`
- Commits: `docs: position MCP as the primary product` (this commit)
- Focused verification: `python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q`; `python scripts/check_release.py`
- Full verification: `npx markdownlint-cli2 README.md "docs/**/*.md"`; `git diff --check`
- Deviations from plan: The local Task 2 branch is intentionally stacked on the
  reviewed Task 1 commits because pushing and merging are outside this task.
- Follow-up risks: Rebase or recreate the branch from updated `main` after Task 1
  merges; do not drop the Task 1 baseline and review-fix commits.

## Task 3 - Introduce a declarative MCP tool catalog and profiles

- Status: complete
- Branch: `pivot/3-mcp-tool-catalog`
- Commits: `refactor: catalog MCP tools by profile` (this commit)
- Focused verification: `python -m pytest tests/mcp/test_tool_registry.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/interfaces/mcp src/codex_usage_tracker/cli/mcp_runtime.py`; `python -m ruff check src/codex_usage_tracker/interfaces/mcp tests/mcp`; `git diff --check`
- Deviations from plan: The local Task 3 branch is intentionally stacked on the
  reviewed Task 1 and Task 2 commits because pushing and merging are outside
  this task. The installed compatibility server remains the active legacy
  runtime; profile-selected server activation is deferred to its roadmap task.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Core tools intentionally raise
  `CoreToolNotImplemented` until their service tasks land.

## Task 4 - Define shared MCP evidence contracts

- Status: complete
- Branch: `pivot/4-mcp-evidence-contracts`
- Commits: `feat: define MCP evidence contracts` (this commit)
- Focused verification: `python -m pytest tests/core/contracts tests/core/test_json_contracts.py -q`; `python -m pytest tests/mcp/test_tool_registry.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/core/contracts`; `python -m ruff check src/codex_usage_tracker/core/contracts tests/core/contracts`; `git diff --check`
- Deviations from plan: The local Task 4 branch is intentionally stacked on the
  reviewed Tasks 1-3 commits because pushing and merging are outside this task.
  `ToolDataClass` moved to the core contract layer and is re-exported downward
  by the MCP interface model so core never imports `interfaces` and the alias
  cannot drift.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Later core tools must use the registered envelope and
  evidence schemas without weakening finite-number or payload-budget checks.

## Task 5 - Add request models and shared source/accounting context builders

- Status: complete
- Branch: `pivot/5-request-context`
- Commits: `feat: build shared analysis request context`;
  `fix: harden analysis request context validation`;
  `fix: normalize invalid database context errors` (this commit)
- Focused verification: `python -m pytest tests/application/test_requests.py tests/application/test_context.py tests/store/test_store_dashboard_queries.py -q`
- Full verification: `python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /private/tmp/pivot-context-after-final`; `python -m pyright src/codex_usage_tracker/application src/codex_usage_tracker/store/api.py`; `python -m ruff check src/codex_usage_tracker/application src/codex_usage_tracker/store/api.py tests/application tests/store/test_store_dashboard_queries.py`; `git diff --check`
- Deviations from plan: The local Task 5 branch is intentionally stacked on
  the reviewed Tasks 1-4 commits because pushing and merging are outside this
  task. The shared context query opens the existing database in read-only mode
  and computes all scoped physical, canonical, coverage, revision, and freshness
  facts in one explicit transaction and one aggregate SQL statement. The route
  benchmark was not repeated for the review fix because its SQL body and every
  valid-file execution path remained byte-for-byte unchanged.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Later interface adapters may accept `record` as a
  compatibility alias, but application `EvidenceRequest` remains canonical on
  `record_id`.

## Task 6 - Implement stable status and capabilities use case

- Status: complete
- Branch: `pivot/6-stable-status`
- Commits: `f39e152` (`feat: add stable MCP usage status`);
  `fix: report exact status freshness thresholds` (this commit)
- Focused verification: `python -m pytest tests/application/test_status.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py tests/core/test_conversational_readiness.py -q`; `python -m pytest tests/application/test_requests.py tests/application/test_context.py tests/store/test_store_dashboard_queries.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/application/status.py src/codex_usage_tracker/interfaces/mcp/core_tools.py`; `python -m ruff check src/codex_usage_tracker/application/status.py src/codex_usage_tracker/application/requests.py src/codex_usage_tracker/interfaces/mcp/core_tools.py src/codex_usage_tracker/interfaces/mcp/registry.py tests/application/test_status.py tests/mcp/test_tool_profiles.py`; `git diff --check`
- Deviations from plan: The historical full/developer `usage_status` already
  delegated to dashboard status behavior through the profile registry, so no
  compatibility-module change was needed. `StatusRequest` gained additive
  local path and profile fields to keep the application and adapter seams
  deterministic and testable. Review follow-up restricted freshness thresholds
  to whole seconds and made the returned context use the exact adjusted
  freshness contract emitted in the result.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Status reports existing readiness and persistent
  service probes but deliberately does not claim current-task MCP exposure.

## Task 7 - Introduce the generic job facade over existing registries

- Status: complete
- Branch: `pivot/7-job-facade`
- Commits: `refactor: unify usage job status` (this commit)
- Focused verification: `python -m pytest tests/jobs tests/server/test_analysis_jobs.py tests/server/test_diagnostic_jobs.py tests/server/test_refresh_jobs.py tests/server/test_server_usage_refresh.py tests/server/test_server_allowance_v2.py tests/server/test_compression_routes.py tests/compression/test_jobs.py tests/cli/test_mcp_integration.py -q`; existing-only baseline comparison: `python -m pytest tests/server/test_analysis_jobs.py tests/server/test_refresh_jobs.py tests/server/test_server_usage_refresh.py tests/server/test_diagnostic_jobs.py tests/server/test_compression_routes.py tests/compression/test_jobs.py tests/cli/test_mcp_integration.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/jobs src/codex_usage_tracker/server/usage_refresh.py src/codex_usage_tracker/server/analysis_jobs.py src/codex_usage_tracker/server/compression_routes.py src/codex_usage_tracker/cli/mcp_dogfood.py src/codex_usage_tracker/cli/mcp_server.py`; `python -m ruff check --no-cache` and `python -m ruff format --check --no-cache` over all touched Python source and tests; `git diff --check`
- Deviations from plan: Dogfood job records are created in
  `cli/mcp_server.py`, not `cli/mcp_dogfood.py`, so the creation point received
  one additive registration call while lifecycle and historical payloads stayed
  in the existing helper module. Compression registration remains route-local
  because its registry lives in the pre-existing compression package, which
  was outside this task's declared mutation list.
- Follow-up risks: The facade is intentionally observational and process-local;
  later roadmap tasks own launch policy, unified persistence, recovery, TTL,
  cleanup, and the public core job-status adapter.

## Task 8 - Implement core refresh and generic job-status tools

- Status: complete
- Branch: `pivot/8-core-refresh-jobs`
- Commits: `feat: add core refresh and job tools` (this commit)
- Focused verification: `python -m pytest tests/application/test_refresh.py tests/application/test_job_status.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py tests/store/test_store_large_batches.py -q`
- Full verification: Task 7 facade regression plus
  `tests/store/test_store_sources.py tests/store/test_store_dashboard_mcp.py`;
  Pyright on the new application services and core adapter; Ruff check/format
  on all touched Python files; `git diff --check`.
- Deviations from plan: The application owns a small process-local async
  coordinator rather than importing the legacy server registry. Coordinators
  are weakly shared per injected `JobService`, so active equivalent requests
  deduplicate without retaining test services or contaminating later tests.
- Follow-up risks: Refresh jobs remain intentionally process-local. Later
  roadmap tasks own durable recovery/retention; this task adds no persistence,
  schema, dependency, or legacy payload change.

## Task 9 - Implement the canonical query request and application service

- Status: complete
- Branch: `pivot/9-canonical-query`
- Commits: `7449ec2` (`feat: add canonical usage query service`);
  `fix: harden canonical query semantics` (this commit)
- Focused verification: `python -m pytest -p no:cacheprovider -p no:tach tests/application/test_query.py tests/application/test_query_validation.py tests/core/test_json_contracts.py tests/store/test_store_dashboard_queries.py -q` (63 passed)
- Full verification: focused verification plus
  `tests/application/test_requests.py tests/reports/test_query_exports.py tests/cli/test_mcp_integration.py`
  (88 passed); shared subagent-predicate regression
  `tests/store/test_subagent_usage_queries.py` (10 passed); Pyright on the three
  canonical query application modules (0
  errors); Ruff check and format check on all touched Python files;
  `git diff --check`.
- Deviations from plan: The authoritative typed `QueryRequest` lives in
  `application.query_models` and is re-exported from `application.requests`.
  Estimate-only queries use truthful entity-identity ordering because cost and
  credit estimates are attached through established pricing helpers after the
  bounded canonical SQL query; explicit sorting by those derived estimates is
  rejected. `reports/api.py` required no change because legacy
  `build_query_report()` behavior remains intact.
- Follow-up risks: Aggregates containing multiple pricing models or service
  tiers report cost and credit as unknown with zero coverage rather than
  presenting a misleading blended estimate. A later task may add per-model
  pre-aggregation when partial mixed-group coverage is needed.

## Task 10 - Define the analysis-goal catalog and strategy protocol

- Status: complete
- Branch: `pivot/10-analysis-catalog`
- Commits: `refactor: catalog usage analysis strategies` (this commit)
- Focused verification: analytics catalog/protocol tests plus existing agentic,
  evidence, recommendation, and subagent report regressions.
- Full verification: Pyright on `analytics/`; Ruff check and format on touched
  files; diff/privacy review.
- Deviations from plan: Compatibility strategies retain existing algorithms at
  existing boundaries, use default paths only in `analyze()`, and preserve legacy
  summary/schema provenance without reinterpreting incompatible evidence.
- Follow-up risks: Task 11 owns canonical execution/job orchestration and fuller
  conversion of compatibility evidence into the analysis-v2 result contract.
  Comparison goals fail closed with `comparison_algorithm` unavailable until a
  Task 11 strategy explicitly consumes both canonical timestamp windows.

## Task 11 - Implement the canonical analysis application service

- Status: complete
- Branch: `pivot/11-analysis-service`
- Commits: `feat: orchestrate evidence-backed usage analysis` (this commit)
- Focused verification: analysis, analytics, JSON contracts, jobs, server jobs, and report regressions.
- Full verification: Pyright; Ruff check/format; release checker; diff/privacy review.
- Deviations from plan: Jobs use a bounded process-local semantic index; comparison goals remain fail-closed.
- Follow-up risks: Task 12 owns transport serialization; job persistence remains out of scope.

## Task 12 - Add the core query and analysis MCP tools

- Status: complete
- Branch: `pivot/12-core-query-analysis`
- Commits: `4dcbeb7`, `2f11833`
- Focused verification: core query/analysis transports, default profile identity,
  CLI compatibility, and application regressions; 69 tests passed.
- Full verification: targeted Pyright and Ruff; format check; release checker;
  skill-mirror byte comparison; diff/privacy review.
- Deviations from plan: transport implementation lives in a focused private module
  and is re-exported from `core_tools.py` so both files remain within source limits.
- Follow-up risks: analysis jobs remain process-local; durable persistence is deferred.

## Task 13 - Implement canonical evidence retrieval and `usage_evidence`

- Status: complete
- Branch: `pivot/13-canonical-evidence`
- Commits: `319230e`, `bf8a5b5`, `981d8b6`, `ae58abc`
- Focused verification: evidence contracts, all selector types, pagination,
  dashboard targets, default profile registration, and Task 9/11/12 regressions;
  353 primary tests, 74 application/job regressions, and 24 Task 12 regressions passed.
- Full verification: targeted Pyright and Ruff; format check; release checker;
  diff/privacy review; independent re-review after the ambiguity fix.
- Deviations from plan: finding selectors accept an optional `analysis_id` so
  report-local finding IDs cannot resolve ambiguously across compatible analyses.
- Follow-up risks: analysis and finding evidence remains process-local until
  durable analysis persistence is implemented.

## Task 14 - Consolidate allowance operations behind `usage_allowance`

- Status: complete
- Branch: `pivot/14-allowance`
- Commits: `d58242f`, `33dda26`, `58a44c6`, `2ebfe46`, plus this documentation commit.
- Focused verification: every application operation, legacy payload equivalence,
  MCP envelope/target/budget behavior, tool registration, allowance intelligence,
  and server regressions; 441 tests passed. A combined Task 12/13 regression
  superset passed 369 tests.
- Full verification: targeted source Pyright; Ruff check and format check on all
  touched Python files; release checker; skill-mirror retrieval tests; diff/privacy review.
- Deviations from plan: result targets use the richer Limits v2 descriptor and
  generic job polling. The public roadmap field remains `range`; the internal
  builder uses `range_preset` to avoid shadowing the built-in.
- Follow-up risks: analysis jobs remain process-local, five-hour analysis is not
  supported, and individual allowance tools remain compatibility surfaces through 0.24.

## Task 15 - Move legacy MCP tools into explicit compatibility and developer profiles

- Status: complete
- Branch: `pivot/15-mcp-profiles`
- Commits: `b2a3b58`, plus this checklist/ledger commit.
- Focused verification: complete MCP/profile/CLI-release suite; 74 tests passed.
  The Task 14 allowance regression gate passed 442 tests after registration changed.
- Full verification: targeted source Pyright; Ruff check and format check; release
  checker; staged diff, source-size, and privacy review; independent review clean.
- Deviations from plan: PR290 already exposed the five dogfood/visualization names.
  The explicit developer-only invariant takes precedence: all 59 baseline names remain
  in `developer`, while `full` preserves the 54 non-developer baseline names. The
  legacy CLI module retains import-compatible implementations, but its decorators are
  inert and its process entrypoint delegates to the selected-profile server.
- Follow-up risks: Task 16 still owns installed-launcher selection of `core`. The
  temporary empty `compatibility_mcp` import sentinel remains for compatibility but
  cannot register or run hidden tools.

## Task 16 - Make the installed plugin launch the core MCP profile by default

- Status: complete
- Branch: `pivot/16-core-launcher`
- Commits: `feat: default the plugin to core MCP tools` (this commit)
- Focused verification: launcher, generated-installer, readiness, doctor, and
  selected-profile server tests passed; the full MCP profile suite also passed.
- Full verification: release checker before and after build; wheel and sdist
  build; distribution release check; clean installed-wheel smoke with an isolated
  FastMCP registry probe proving the seven ordered core tools; touched-file Ruff
  check/format; source/package launcher byte comparison; independent review clean.
- Deviations from plan: The public installer module is an import alias, so the
  generated-config change lives in `cli/plugin_installer.py`. MCP diagnostics also
  learned the new internal module path, and explicit package data includes the
  packaged launcher. Static smoke catalogs moved to a small helper so the main
  smoke gate stays below the repository source-size limit. Its synthetic dashboard
  check now uses the bounded 5,000-row limit instead of the legacy unbounded value.
- Follow-up risks: Task 17 must bump both byte-identical launcher copies' pinned
  runtime version and package spec together with the 0.22.0 release metadata.

## Task 17 - Gate Release 0.22.0

- Status: release candidate complete; publication and public qualification are
  deferred pending explicit authorization.
- Branch: `pivot/17-release-022`
- Commits: `7f4e50b` (`test: add core MCP golden questions`), `ba6fd3d`
  (`fix: harden release gate compatibility`), plus
  `chore: prepare 0.22.0 MCP core release` (this commit).
- Focused verification: ten synthetic golden-question fixtures and their
  deterministic routing evaluator passed 11 tests; release, plugin-installer,
  launcher, public-doc, canonical-query, SQL-filter, and JSON-contract
  regressions passed. The installed-wheel smoke reported version `0.22.0`, 59
  packaged resources, and the exact ordered seven-tool core profile.
- Full verification: 1,820 Python tests passed in 101.74 seconds; the coverage
  pass also ran 1,820 tests in 102.01 seconds and reported
  88.31270245256826% combined coverage, 90.99716960592205% statement
  coverage, and 77.77144485608436% branch
  coverage. Pyright reported 0 errors and 7 existing lazy-export warnings;
  Ruff and mypy passed. Dashboard verification passed 109 files / 571 tests,
  lint, type checking, governance, source budgets, and bundle budgets. The
  100,000-row route benchmark reported no budget violations (46.478998-second
  population and 10.183382-second recommendation materialization). Release
  checks, build, Twine, distribution inspection, installed-package smoke, and
  diff checks passed.
- Release inventory: `core` exposes 7 tools, `full` exposes 59, and `developer`
  exposes 64. The tracked JSON schema inventory contains 90 identifiers,
  including 14 additive MCP-core/application schemas listed in the release
  note. The local wheel is 5,320,724 bytes with SHA-256
  `bd828aaad0fe0af7ad93c423f265a0b6dc5412c562341254c43ce922de699318`;
  the local sdist is 28,493,191 bytes with SHA-256
  `fae196b193c79a4b7e969a53a32beb56c58dd903518c152f36637aa350015027`.
- Deviations from plan: public historical 0.21 readiness evidence is no longer
  treated as a current-version claim by the release checker. The full-suite
  command now uses pytest importlib collection so duplicate test filenames in
  separate directories collect deterministically. The full gate also exposed
  and fixed a prior regression that replaced raw session-ID filtering with the
  canonical `session:` form; both forms are now additive and covered. TestPyPI,
  public PyPI, tags, pushes, and public-package smoke tests were not run because
  they require explicit publication authorization. The Task 15 developer-only
  invariant remains authoritative: `developer` preserves all 59 baseline
  0.21/PR290 names, while `full` preserves the 54 non-developer baseline names.
- Follow-up risks: the recorded hashes identify the local Step 3 artifacts;
  evidence text was appended to tracked docs afterward as required by the
  plan, so an authorized rebuild would need fresh hashes and qualification.
  The coverage run emitted 71 non-failing pre-existing resource warnings.

## Remaining Planned Tasks

Tasks 18 through 45 remain planned in the approved implementation roadmap. Add a
full entry using the format above when each task becomes active; do not mark a
task complete without its named focused and full verification evidence.
