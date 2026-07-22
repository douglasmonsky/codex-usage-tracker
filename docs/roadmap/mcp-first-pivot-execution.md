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

## Remaining Planned Tasks

Tasks 11 through 45 remain planned in the approved implementation roadmap. Add a
full entry using the format above when each task becomes active; do not mark a
task complete without its named focused and full verification evidence.
