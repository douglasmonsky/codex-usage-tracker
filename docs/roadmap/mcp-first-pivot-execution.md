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

## Task 18 - Introduce the Evidence Console Route Model

- Status: complete; legacy direct workbenches remain renderable for the 0.23
  compatibility window but are absent from persistent navigation.
- Branch: `pivot/18-evidence-console-routes`
- Commits: `d30dd48` (`refactor: define Evidence Console routes`) plus
  `fix: preserve canonical Evidence Console links` (this commit).
- Focused verification: the six-file route, alias, shell, and target acceptance
  suite passed 70 tests. Canonical calls, threads, and investigator URL-builder
  regressions passed another 20 tests. The Python v2 dashboard-target suite
  passed all 307 tests, including call `record` selectors and both contextual
  and Explore thread targets.
- Full verification: dashboard type checking and lint passed; touched Python
  files passed Ruff; `git diff --check` passed. One diagnostic full-dashboard
  run passed 505 of 576 tests. Its 71 remaining failures are legacy assertions
  that navigate with workbench buttons intentionally removed by this task or
  assert pre-pivot output IDs; Tasks 19 through 23 own those parity migrations.
- Review: an independent read-only review reported no critical or important
  findings in canonical routes, compatibility normalization, contextual
  Evidence behavior, navigation exactness, or Python v2 targets.
- Deviations from plan: `App.tsx` and the page-level calls, threads, Explore,
  and investigator URL emitters also changed because they are the direct shell
  consumers that otherwise rewrote canonical links back to legacy IDs. Call
  URLs use the roadmap's `record` query key while preserving the design
  contract's `record_id` selector field. No publication action was taken.
- Follow-up risks: legacy navigation-heavy dashboard tests remain intentionally
  red until their owning Home, Explore, Evidence, Limits, and parity tasks land.
  Target Evidence kinds other than call still render through compatibility
  pages until Task 21 supplies the unified contextual renderer.

## Task 19 - Build the Focused Evidence Console Home

- Status: complete; the canonical Home route and its legacy Overview alias now
  render the same focused operational summary instead of the broad legacy
  dashboard.
- Branch: `pivot/19-home-status`
- Commits: `ff5dc7b` (`fix: restore Evidence Console route boundaries`),
  `5847bc3` (`feat: add bounded Home status payload`), `879faae`
  (`feat: load focused Home status`), `c90daac` (`feat: add focused Evidence
  Console home`), plus this documentation commit.
- Focused verification: 51 frontend tests passed across the Home view/model,
  readiness refresh lifecycle, shell, canonical-link, and route contracts. The
  Home store/status/shell and CLI integration targets passed 17 Python tests.
- Full verification: dashboard type checking, lint, stylelint, the named
  dashboard-governance gate, targeted Pyright, touched-file Ruff, and
  `git diff --check` passed. A diagnostic full-dashboard run passed 499 of 588
  tests; its 89 legacy Overview/workbench assertions are owned by Tasks 20
  through 24 and no Task 19 named acceptance check remains failing.
- Review: an independent review initially found four boundedness/scope issues:
  an unbounded recommendation count, missing pricing and allowance data in the
  fast payload, archived rows affecting active Home freshness, and overly wide
  recent-evidence materialization. All four were fixed, and the narrow
  independent re-review passed.
- Deviations from plan: a narrow store-query module owns the hard three-finding
  and five-evidence caps. The fast status payload carries pricing and allowance
  coverage so Home does not need a report scan. The route contract moved to its
  governance-approved feature boundary, and the three existing oversized
  source files touched by this task were ratcheted downward. No publication
  action was taken.
- Follow-up risks: legacy Overview and workbench tests remain intentionally red
  until Tasks 20 through 24 complete their parity migration. The static legacy
  shell receives an embedded Home summary, while the React path intentionally
  marks that summary deferred and loads the live bounded status endpoint.

## Task 20 - Consolidate Calls and Threads into Explore

- Status: complete; Explore now owns one accessible Calls/Threads mode switch,
  mounts only the active evidence surface, and canonicalizes legacy Calls and
  Threads URLs without losing mode-specific state.
- Branch: `pivot/20-explore-workspace`
- Commits: `cabaa0b` (`feat: unify calls and threads in Explore`), `15d6f5c`
  (`refactor: remove obsolete Explore diagnostics`), and `3175e82` (`test:
  migrate Explore browser journeys`), plus this documentation commit.
- Focused verification: the roadmap-named Explore, Calls, Threads, and URL-state
  command passed 23 tests. The expanded eight-file integration suite passed 56
  tests, including legacy route normalization, inactive-mode non-mounting,
  filter preservation, Evidence return state, and Calls/Threads regressions.
  The isolated browser smoke suite passed all 22 desktop and mobile journeys.
- Full verification: dashboard type checking, lint, dependency boundaries,
  dead-code detection, stylelint, source-budget enforcement, and
  `git diff --check` passed. A diagnostic full-dashboard run passed 528 of 596
  tests; its 68 remaining failures assert retired top-level navigation and
  pre-pivot route IDs that Tasks 21 through 24 continue to migrate.
- Review: an independent read-only review reported no critical or important
  findings in active-mode mounting, URL-state preservation, legacy route
  normalization, Evidence returns, query scoping, accessibility, privacy, or
  security.
- Deviations from plan: the obsolete Tools and Files sub-modes and their orphaned
  diagnostic adapters were removed rather than allowlisted after the two-mode
  contract made them dead code. The Playwright web server now derives its URL
  from a configurable strict port and never reuses an unrelated listener; the
  verified run used port 5187 because another local application owned 5173. No
  publication action was taken.
- Follow-up risks: compatibility workbenches remain directly routable while the
  remaining contextual Evidence and legacy-parity migrations land. The full
  dashboard inventory remains diagnostic until those owning tasks complete.

## Task 21 - Build One Contextual Evidence Route

- Status: complete; one contextual route now resolves exact call, thread,
  finding, and allowance-transition selectors without label fallback. Calls
  retain the gated Call Investigator, while the other kinds render bounded
  aggregate records from the shared evidence contract.
- Branch: `pivot/21-contextual-evidence`
- Commits: `44f6308` (`feat: expose bounded contextual evidence`), `c489482`
  (`feat: define canonical Evidence links`), `b9da403` (`feat: render contextual
  Evidence views`), `20cecf6` (`test: cover contextual Evidence views`), and
  `dccea7c` (`test: align release gate with pivot routes`), plus this
  documentation commit.
- Focused verification: 39 Python tests passed across the roadmap-named server,
  application, service, compatibility, and route-inventory suites. Twenty-nine
  frontend tests passed across the Evidence API, URL contract, all four
  renderers, route catalog, and Call Investigator compatibility.
- Full verification: dashboard type checking, lint, dependency boundaries,
  dead-code detection, stylelint, source-budget enforcement, touched-file Ruff,
  Ruff formatting, privacy-pattern scanning, and `git diff --check` passed. The
  port-isolated release-candidate passed all 11 Chromium checks covering
  accessibility, responsive layout, reduced motion, chart/table parity,
  simplified navigation, direct-route compatibility, return state, readiness,
  and localization. A diagnostic full-dashboard run passed 551 of 619 tests;
  its 68 failures are the unchanged legacy navigation and pre-pivot route-ID
  assertions already deferred from Task 20.
- Review: the final local review found no critical or important correctness,
  privacy, security, pagination, selector, or compatibility issue. The three
  task-level child-agent slots had already supplied the Task 20 review and the
  bounded Task 21 backend/frontend reconnaissance, so no fourth child was
  created.
- Deviations from plan: `CallEvidence` delegates to the existing Call
  Investigator instead of moving its 807-line implementation during the 0.23
  compatibility window. The early HTTP adapter accepts validated query fields
  on POST; Task 25 still owns the unified JSON-body v2 facade. The
  release-candidate command now derives its base URL from the configurable
  strict Playwright port, preserving the 5173 CI default while allowing safe
  isolated local runs. No publication action was taken.
- Follow-up risks: the full JSON HTTP facade, payload-budget conformance matrix,
  and compatibility-removal decision remain owned by Tasks 25, 27, and 45.
  Legacy unit assertions that still demand retired top-level route IDs remain
  diagnostic until their owning parity tasks land.

## Task 22 - Refocus Limits and Settings for the Evidence Console

- Status: complete; Limits now leads with observed reset state, marks observed
  facts, descriptive estimates, and supported changes explicitly, and opens
  matching persisted allowance evidence through the contextual Evidence route.
  Settings now presents local runtime readiness and keeps direct compatibility
  Labs behind an off-by-default Advanced preference.
- Branch: `pivot/22-focus-limits-settings`
- Commits: `45fa34c` (`refactor: focus Limits and Settings`) and `aef37bf`
  (`fix: localize compatibility Labs controls`), plus this documentation
  commit.
- Focused verification: 32 frontend tests passed across Limits, Settings, the
  browser-local preference hook, conversational readiness, and the route
  catalog. All 148 locale-catalog tests passed, including equal key sets,
  placeholder parity, and non-English Task 22 copy.
- Full verification: dashboard type checking, ESLint, stylelint, dependency
  boundaries, dead-code detection, source-budget enforcement, bundle budgets,
  privacy-pattern scanning, and `git diff --check` passed. The isolated
  port-5195 release candidate passed all 11 Chromium checks, including visible
  chart/table parity, immediate and restored Labs preference state, simplified
  navigation, and Spanish copy. A diagnostic full-dashboard run passed 554 of
  622 tests; its 68 failures are the same legacy navigation and pre-pivot route
  assertions deferred from Tasks 20 and 21.
- Review: the final local review found no critical or important correctness,
  privacy, evidence-link, storage-migration, localization, or compatibility
  issue. The task-level child-agent allowance had already been used for the
  pivot review and bounded backend/frontend reconnaissance, so no additional
  review child was created.
- Deviations from plan: the roadmap's former `usage-drain` page already lived
  at `features/limits/LimitsPage.tsx`. History controls were extracted to keep
  the source ratchet green, and App injects the route-catalog Labs inventory to
  preserve dependency direction. The browser gate and all twelve locale
  catalogs landed in a second focused commit to keep each commit within the
  20-file limit. No allowance calculation, detector, API, or publication
  behavior changed.
- Follow-up risks: five compatibility workbenches remain directly routable
  until Tasks 23 and 24 prove job parity and retire their duplicate navigation
  paths. Their legacy unit assertions remain diagnostic until those owning
  tasks land.

## Task 23 - Prove Job Parity and Hide Legacy Workbenches

- Status: complete; all eight sunset jobs have an executable signed parity
  record covering canonical evidence IDs, history scope, accounting context,
  caveats, replacement requests, destinations, ownership, and removal timing.
  The five legacy workbenches stay directly routable but are absent from the
  default Home, Explore, and Limits navigation and now name a core replacement.
- Branch: `pivot/23-dashboard-sunset-parity`
- Commits: `78934d3` (`feat: simplify the default dashboard surface`), plus this
  documentation commit.
- Focused verification: 69 Python tests passed across the analysis catalog,
  signed sunset parity, analyze, query, and evidence contracts. The roadmap's
  four-file frontend command passed 31 tests across the shell, route catalog,
  transition banner, and Diagnostics lifecycle; the final affected-component
  recheck passed 12 tests.
- Full verification: dashboard type checking, ESLint, dependency boundaries,
  dead-code detection, stylelint, source-budget enforcement, touched-file Ruff,
  bundle budgets, privacy-pattern scanning, and `git diff --check` passed. The
  port-isolated release candidate passed all 11 Chromium checks, including the
  five direct legacy routes and Spanish transition copy. A diagnostic named
  full-dashboard run passed 556 of 624 tests; its 68 failures are the unchanged
  retired-navigation and pre-pivot route-ID assertions already deferred from
  Tasks 20 through 22.
- Review: the final local diff review found no critical or important
  correctness, privacy, selector, accounting, accessibility, localization, or
  compatibility issue. The task-level child-agent allowance had already been
  used by prior pivot slices, so no additional review child was created.
- Deviations from plan: `analysis_catalog.py` changed because it is the source
  that overwrites strategy destinations in public analysis results; leaving it
  untouched would preserve links to retired workbenches. `navigation.ts`
  required no edit because Task 18 already enforced exactly Home, Explore, and
  Limits plus the Settings utility. The release-candidate used port 5197 because
  an unrelated listener owned 5173. Verification-only generated dashboard
  assets were restored to their clean pre-build state; Task 29 owns artifact
  synchronization. No publication action was taken.
- Follow-up risks: the 68 legacy unit assertions remain diagnostic until Task
  24 removes their obsolete workbench assumptions. Full-profile compression
  ranking and direct route bookmarks remain supported only through `0.24.x`,
  with the signed record blocking removal if parity later regresses.

## Task 24 - Remove the Usage Constellation and Frontend Dependencies

- Status: complete; the experimental Usage Constellation, its Three.js renderer
  and models, its browser and unit coverage, and all packaged constellation
  assets are removed. `three` and `@types/three` are absent from both manifests
  and the lockfile, and release validation now rejects their reintroduction.
- Branch: `pivot/24-remove-usage-constellation`
- Commits: `b34066e` (`refactor: remove non-core dashboard visualization`),
  `064f83b` (`test: enforce dashboard visualization sunset`), `7c279b1`,
  `e9f7ea7`, `a3a4dd2`, and `726e1f8` (bounded packaged-asset refreshes),
  `c1761f7` (`test: align dashboard coverage with core routes`), plus this
  documentation commit.
- Focused verification: the release suite passed 26 tests; the migrated route,
  Evidence, diagnostics, live-refresh, export, filter, source-identity, and
  compatibility subset passed 85 tests. `npm ls three --all` returned empty,
  asset synchronization was byte-for-byte clean, the initial bundle measured
  60.02 KiB under its 67 KiB ceiling, and the largest visualization route
  measured 112 KiB under its 113 KiB ceiling with no Three.js inputs.
- Full verification: the repository-defined `dashboard-verify` gate passed all
  607 frontend tests, TypeScript, ESLint, dependency boundaries, dead-code
  detection, stylelint, the refreshed source ratchet, production build, asset
  parity, bundle budgets, and `scripts/check_release.py`. The port-isolated
  release candidate passed all 11 Chromium checks. `npm ci`, governance,
  `git diff --check`, and the final staged-file review also passed.
- Review: the final diff contains 193 additions and 628 deletions across the
  compatibility-test cleanup, with no secret-bearing paths or unexpected
  worktree changes. The task-level child-agent allowance had already been used
  by prior pivot slices, so no additional review child was created.
- Deviations from plan: three obsolete top-level shell suites and two retired
  Overview-only load-more cases were deleted instead of being rewritten to
  assert navigation that no longer exists. Direct-route compatibility remains
  covered through canonical Home, Explore, Evidence, diagnostics, reports,
  investigator, and cache tests. The generated asset refresh was split into
  four commits to respect the 20-file commit cap. The release documentation's
  Tools catalog boundary was corrected so its parser does not consume the
  following workbench-replacement section. No publication action was taken.
- Follow-up risks: `npm ci` reports four existing audit findings (two moderate
  and two high); no automatic dependency rewrite was attempted. The remaining
  compatibility workbenches and static dashboard are still governed by their
  documented two-release sunset and later roadmap tasks.

## Task 25 - Add the Versioned HTTP API v2 Application Facade

- Status: complete; eight stable `/api/v2/` endpoints now decode bounded strict
  requests, invoke the same application services as the core MCP tools, and
  serialize their shared result contracts without calling MCP handlers. The
  Evidence Console's contextual Evidence client now posts a typed JSON body and
  consumes `evidence-result.v1` directly.
- Branch: `pivot/25-http-api-v2`
- Commits: `8f54acb` (`feat: add HTTP API v2 facade`), `d4a9d86`
  (`feat: serve stable HTTP API v2 routes`), `6e32622` (`feat: migrate Evidence
  Console to HTTP v2`), `ab2d307` (`fix: guard expensive allowance requests`),
  `bcafa59` (`fix: enforce strict JSON request bodies`), `9cdc103` (`chore:
  satisfy HTTP v2 quality gates`), and `c0f643f` (`docs: update tracked schema
  count`), plus this documentation commit.
- Focused verification: 60 Python tests passed across the pure decoder/facade,
  body and output limits, live localhost server, route inventory, shared JSON
  contracts, and the full dashboard-server suite. The roadmap's four-file
  frontend command passed 23 tests across the client and Home, Explore, and
  Evidence pages. The public documentation/contract check passed 21 tests.
- Performance and quality verification: the repository-defined 100,000-row
  dashboard route budget passed in 65.984 seconds with enforced thresholds.
  TypeScript type checking and ESLint passed; targeted Ruff lint and formatting,
  isolated mypy, project-interpreter Pyright, `git diff --check`, and the
  Task 25 route-handler dead-code recheck passed.
- Broad verifier: the repository-wide `full` profile ran for 4 minutes 13
  seconds and exposed existing pivot-branch debt in legacy file lengths,
  allowance exports/types, Tach boundaries, optional frontend tool discovery,
  and dependency audit. Its only Task 25-local findings were formatting,
  test-only type narrowing, dynamic route-handler discovery, and the public
  schema count; all four were repaired and rechecked. The raw repository-wide
  profile remains red on the unrelated inherited findings and is not represented
  as a passing gate.
- Review: POST bodies require `Content-Length`, enforce per-route byte budgets,
  reject wrong media types, malformed/non-object JSON, duplicate keys,
  non-finite numbers, and unknown top-level/nested fields. Responses enforce
  route budgets, async starts return `202`, all v2 errors are JSON, and Host,
  Origin, refresh/analyze/allowance token guards remain active. HTTP status and
  MCP status results have equal schema identifiers and field sets.
- Deviations from plan: the stable server integration lives in a small
  `HttpV2RouteMixin` so the legacy request handler becomes smaller rather than
  growing further. `request_guards.py` required no behavior change; live-server
  coverage proves the existing Origin and token guards remain in force. No v1
  route or publication state changed.
- Follow-up risks: compatibility routes remain intentionally available through
  their documented window. The repository-wide inherited verifier debt remains
  owned by later architecture, CI, and release-hardening roadmap tasks.

## Task 26 - Introduce the Simplified CLI Hierarchy

- Status: complete; primary help now exposes exactly `setup`, `status`,
  `doctor`, `refresh`, `analyze`, `query`, `open`, `export`, `config`,
  `service`, and `admin`. All historical top-level spellings remain parseable
  through `0.24.x` but are hidden from primary help, and interactive alias
  notices are isolated to stderr.
- Branch: `pivot/26-simplified-cli`
- Commits: `10314a9` (`feat: add simplified CLI hierarchy`), `7d71cf1`
  (`feat: route stable CLI application commands`), `9a73642` (`docs: publish
  simplified CLI migration`), plus this documentation commit.
- Behavior: `status`, bounded `query`, and `analyze` serialize the shared v2
  application contracts. Old-only query filters and `--limit 0` retain the v1
  compatibility path. `open` resolves Home, call, thread, target ID, or strict
  dashboard-target-v2 JSON and opens only matching loopback URLs. Configuration,
  service, operational, dogfood, and manual MCP commands are routed through the
  documented namespaces without duplicating their existing option builders.
- Verification: 191 tests passed across the new parser and command adapters,
  CLI release contracts, legacy CLI lifecycle, and i18n. Focused Ruff lint and
  formatting, project-interpreter Pyright, Python compileall, release readiness,
  `git diff --check`, primary/nested help smoke tests, and a real empty-state
  `status.v2` invocation passed. The architecture checker reported only the
  same inherited core/store dependency violations present before this task; it
  reported no CLI-interface violation.
- Review: strict target JSON rejects mismatched loopback absolute and relative
  URLs, machine-readable output never receives deprecation text, translated
  help keeps the same short inventory, and every legacy parser remains covered.
  No secrets or private records were added. The task-level child-agent allowance
  had already been used by prior pivot slices, so no additional review child was
  created.
- Deviations from plan: the work was split into three focused implementation
  commits to remain below the repository's 800-added-line commit cap. The
  installed-package smoke and release catalogs changed because they previously
  defined every historical command as stable. No compatibility command was
  deleted and no publication action was taken.
- Follow-up risks: the CLI default service object currently shares the proven
  HTTP v2 application-service adapter; a later boundary cleanup may move that
  adapter into the application package without changing contracts. Historical
  aliases and legacy query mode remain removal-blocked until `0.25.0`.

## Task 27 - Gate and Prepare Release 0.23.0

- Status: release-ready; the complete local release candidate and required
  100,000-row route budget pass. Publication proceeds through the reviewed PR,
  updated `main`, GitHub release, and Trusted Publishing workflow.
- Branch: `pivot/27-release-0.23.0`
- Commits: `6441076` (`chore: prepare 0.23 release contracts`), `f67a647`
  (`docs: explain the 0.23 Evidence Console`), `a84b10e` (`docs: add core
  Evidence Console screenshots`), `b775d3c` (`test: capture responsive
  Evidence Console release evidence`), `460d1e5` (`fix: localize the service
  namespace`), `893d2f9` (`perf: index all-history allowance observations`),
  and `1813169` (`chore: refresh Evidence Console assets`), plus this
  documentation commit.
- Product inventory: 15 browser routes comprise five Evidence Console routes
  and ten direct-only legacy routes. Default analytical navigation is Home,
  Explore, and Limits; Settings is a utility action and Evidence is contextual.
  Home begins with the bounded Usage Pulse calls, tokens, cache-reuse, and cost
  summary before its readiness and evidence sections. Explore provides Calls
  and Threads modes. All four Evidence selector kinds render, stable old URLs
  normalize, and Home performs no hidden heavy scan.
  MCP profiles expose 7 core, 59 full, and 64 developer tools. Primary CLI help
  exposes 11 commands and retains 34 hidden compatibility aliases. The shared
  JSON inventory contains 95 schemas.
- Focused verification: 381 Python acceptance tests passed. The frontend suite
  passed 609 tests across 115 files. The port-isolated Playwright release
  candidate passed 14 scenarios, including Explore Calls and Threads parity,
  stable URL normalization, all Evidence selectors, and the Home scan guard.
  The restored Usage Pulse recheck passed 31 focused frontend tests and the
  complete dashboard and browser release-candidate gates again.
  Twelve synthetic screenshots cover Home, Explore Calls, Explore Threads,
  Limits, Evidence, Settings, a legacy route, tablet, mobile, 200% zoom,
  reduced motion, and keyboard use without private user data.
- Full verification: all 1,905 Python tests passed and coverage measured 88%.
  Ruff, mypy, Pyright (zero errors and seven inherited lazy-export warnings),
  TypeScript, ESLint, dependency boundaries, dead-code detection, stylelint,
  source budgets, dashboard asset parity, release checks, installed-package
  smoke, and `git diff --check` passed. Initial dashboard payloads measure
  60.02 KiB JavaScript and 9.66 KiB CSS. The largest visualization chunk is the
  documented 112.00 KiB gzip exception under its 113.00 KiB ADR limit. The
  recorded candidate wheel and sdist measure 6,956,865 and 31,909,932 bytes,
  respectively, and both pass Twine and distribution release checks.
- Performance evidence: migrations 32–34 add the global newest-first allowance,
  focused recommendation/call sorting, source, and parent-thread lookup indexes.
  The stable enforced 100,000-row run passed every route budget: Calls measured
  0.074 seconds p95, Threads 0.007 seconds p95, thread calls 0.014 seconds p95,
  and allowance diagnostics 0.584 seconds p95. Population completed in 44.8
  seconds.
- Post-candidate polish and freshness correction: Home once again exposes
  refresh/loading progress, removes annotation footnotes from Usage Pulse, and
  replaces the three generic actions with an MCP/plugin setup guide and six
  visible copyable investigation prompts. Explore now points first-time visitors
  to the Calls/Threads switch. Live preview diagnosis found macOS volume-device
  drift was misclassifying 1,217 tracked logs as replacements; preserving
  path/inode/prefix-tail safety while tolerating `st_dev` drift reduced the same
  catch-up to 11 append-safe logs and 14 new logs. The preview advanced from
  `2026-07-22T19:59:50.013Z` to `2026-07-23T17:21:33.634Z`; the focused Calls
  route returned that newest row with populated cost and credit fields in 0.006
  seconds. A profiled synthetic refresh identified per-row canonical
  fingerprint lookups as the Python hotspot. Batched lookups reduced the
  identical unprofiled 10,000-row refresh from 7.55 to 3.52 seconds. Startup
  refresh is now asynchronous: the real 224,244-call preview served its stored
  dashboard in about four seconds while refresh continued in the background,
  instead of withholding the server behind the roughly 10.5-minute full scan.
- Roadmap protection: Tasks 25, 27, 34, and 41 now explicitly preserve bounded
  Home/Limits hydration and the focused Calls, Threads, and Thread Calls query
  plans. A v2 facade may not replace or deprecate those routes until functional
  parity, exact filtering/sorting/counts, cost/credit parity,
  incremental-freshness coverage, and the named 100,000-row route budget all
  pass.
- Deviations from plan: additive migrations 33 and 34 and focused endpoint
  changes were necessary to correct real filter/count/query-plan defects found
  during release qualification. No route threshold was loosened and no failing
  route result was hidden.
- Follow-up risks: the broader 100,000-row full-content ingestion benchmark
  retained exact table parity and measured a 23.5% parallel speedup, but its
  26.9-second median and 578 MiB sampled process-tree peak remain above the
  historical 20-second/544 MiB sentinels. The excess is in the optional
  content/fact indexing pipeline rather than dashboard availability or focused
  endpoint hydration; it is recorded for 0.24 performance hardening.

## Task 27.5 - Foundation Audit and 0.24 Plan Confirmation

- Stable task ID: `ARCH-AUDIT-00`
- Status: complete; Task 27 and the `0.23.0` release gate completed before
  evidence collection, and this checkpoint recorded `PROCEED`.
- Branch: `pivot/27.5-foundation-audit`
- Commits: `docs: add 0.24 foundation audit checkpoint` (this checkpoint;
  exact SHA is recorded in Git/PR history).
- Audit report: `docs/superpowers/reports/0.24-foundation-audit.md`.
- Audited commit SHA: `589e10a1afeca72e47d6b2d5777cd8189d292996`.
- Decision: `PROCEED`.
- Changed files:
  `docs/superpowers/reports/0.24-foundation-audit.md`,
  `docs/roadmap/mcp-first-pivot-execution.md`, `.gitignore`, and `AGENTS.md`.
  The latter two add the user-approved ignored GitNexus index and
  context-efficient GitNexus/Serena/source/test workflow; the 548 MiB local
  `.gitnexus/` index and IntelliJ `.idea/` directory remain untracked.
- Focused verification:
  - migration, canonical accounting, refresh, content, OTel, allowance,
    contract, core MCP, profile, and HTTP-v2 suite: `126 passed in 11.35s`;
  - fresh temporary SQLite database: schema/user version 34, 34 migration
    records, 38 physical tables, `integrity_check=ok`,
    `foreign_key_check=[]`, and normal `foreign_keys=0`;
  - `ruff check .`: passed;
  - `.venv/bin/python -m pyright --pythonpath .venv/bin/python src`: 0 errors,
    7 existing lazy-export warnings;
  - `python scripts/check_release.py`: passed;
  - `npx markdownlint-cli2`: passed;
  - synthetic isolated doctor: completed with the expected warning-only
    missing-local-setup result.
- Full verification: `.venv/bin/python -m pytest -q`:
  `1907 passed in 116.87s`.
- Architecture graph and inventory evidence:
  - Tach map: 381 modules, 1,327 edges, 3 non-trivial SCCs;
  - `tach check`: the 8 pre-existing direction violations recorded in the
    report, assigned to Tasks 28-30;
  - GitNexus at the audited SHA: 1,348 files, 25,190 symbols, 54,349
    relationships, 1,311 clusters, and 300 processes;
  - `gitnexus check --cycles --json`: 7 file-level cycles, including
    analytics/application, store/schema, store/refresh, frontend, and one
    generated-bundle cycle.
- Migration fixtures tested: unversioned legacy aggregate through v34; fresh
  v34; representative v23, v24, v25, v27, v28, v31, and v33 states; canonical
  rebuild; OTel v30/v31; malformed legacy failure/partial-commit evidence;
  refresh idempotency and CSV compatibility. Every retained SQLite fixture
  returned `integrity_check=ok` and zero `foreign_key_check` rows.
- Findings assigned to Tasks 28-33:
  - Task 28: composition, status, repository, evidence, focused-route, and
    refresh workflow ownership;
  - Task 29: MCP extraction and registration cycles;
  - Task 30: dependency direction, explicit adapters, contract isolation, and
    remaining cycles;
  - Task 31: foreign-key enforcement, atomic migration failure,
    transaction/rebuild/cache-write safety, cascade and retained migration
    fixtures;
  - Task 32: indexed byte-offset context retrieval and inspected-byte budgets;
  - Task 33: persistent generic jobs/results and recovery.
- Maintainer approval reference: not required for `PROCEED`.
- Deviations from plan: no production behavior or schema changed. GitNexus
  added independent graph evidence and user-approved repository guidance; no
  roadmap task was broadened.
- Follow-up risks: the report contains 14 assigned findings and no blocker or
  unassigned high-severity finding. Task 28 may start only after this audit
  checkpoint lands. Focused Home, Limits, Calls, Threads, and Thread Calls
  routes remain protected until exact parity and performance gates pass.

## Remaining Planned Tasks

Task 27.5 is complete once this independent checkpoint lands. Tasks 28 through
45 remain planned in the approved implementation roadmap, and no later `0.24`
task may begin before that checkpoint. Add a full entry using the format above
when each task becomes active; do not mark a task complete without its named
focused and full verification evidence.
